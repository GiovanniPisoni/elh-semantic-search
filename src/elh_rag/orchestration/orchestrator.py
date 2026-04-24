"""
Orchestrator — the top-level controller.

Binds together:
    - IntentRouter      → decides which corpus(es) to query
    - ReviewsPipeline   → retrieval over student reviews
    - DescriptionsPipeline → retrieval over house+room descriptions
    - LLMClient         → final answer generation
"""
from __future__ import annotations

import logging
from typing import Any

from elh_rag.config import settings
from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import (
    MULTICORPUS_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_multicorpus_user_prompt,
    build_user_prompt,
)
from elh_rag.orchestration.corpus_pipeline import CorpusResult
from elh_rag.orchestration.descriptions_pipeline import DescriptionsPipeline
from elh_rag.orchestration.reviews_pipeline import ReviewsPipeline
from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.retrieval.followup_rewriter import FollowUpRewriter
from elh_rag.retrieval.intent_router import IntentRouter
from elh_rag.schemas import (
    DocumentSource,
    Intent,
    RAGResponse,
    RetrievalResult,
    RoutingDecision,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Composes IntentRouter + per-corpus pipelines + final generation."""

    def __init__(
        self,
        reviews_pipeline: ReviewsPipeline | None = None,
        descriptions_pipeline: DescriptionsPipeline | None = None,
        intent_router: IntentRouter | None = None,
        llm_client: LLMClient | None = None,
        followup_rewriter: FollowUpRewriter | None = None,
    ) -> None:
        self._reviews = reviews_pipeline or ReviewsPipeline()
        self._descriptions = descriptions_pipeline or DescriptionsPipeline()
        self._router = intent_router or IntentRouter()
        self._llm = llm_client or LLMClient()
        self._followup = followup_rewriter or FollowUpRewriter()

    # Public API

    def query(
        self,
        question: str,
        top_k: int | None = None,
        city_filter: str | None = None,
        min_rating: int | None = None,
        conversation_memory: ConversationMemory | None = None,
    ) -> RAGResponse:
        """Run the full orchestrated pipeline on a single question."""
        top_k = top_k or settings.retrieval_top_k

        retrieval_question = self._resolve_followup(
            question=question, memory=conversation_memory
        )

        routing = self._decide_route(retrieval_question)

        per_corpus = self._run_pipelines(
            question=retrieval_question,
            routing=routing,
            top_k=top_k,
            city_filter=city_filter,
            min_rating=min_rating,
        )

        sources_by_source, merged_sources = self._merge(per_corpus, top_k=top_k)
        rewritten_query = _first_rewrite(per_corpus)

        if rewritten_query is None and retrieval_question != question:
            rewritten_query = retrieval_question

        if not merged_sources:
            return RAGResponse(
                query=question,
                rewritten_query=rewritten_query,
                answer=_empty_answer(routing),
                sources=[],
                sources_by_source=sources_by_source,
                routing=routing,
                mode=_mode_label(routing),
            )

        context = _build_context(merged_sources)
        system_prompt, user_prompt = _select_prompts(
            question=question,
            context=context,
            sources=merged_sources,
        )
        answer = self._llm.complete(system=system_prompt, user=user_prompt)

        return RAGResponse(
            query=question,
            rewritten_query=rewritten_query,
            answer=answer,
            sources=merged_sources,
            sources_by_source=sources_by_source,
            routing=routing,
            mode=_mode_label(routing),
        )

    # Follow-up rewriting

    def _resolve_followup(
        self,
        question: str,
        memory: ConversationMemory | None,
    ) -> str:
        """Expand follow-up questions using conversation memory."""
        if not settings.enable_conversational_memory:
            return question
        if memory is None or memory.is_empty():
            return question
        return self._followup.rewrite(question=question, memory=memory)

    # Routing

    def _decide_route(self, question: str) -> RoutingDecision:
        """Run the intent router, or return a static 'reviews' decision if disabled."""
        if not settings.enable_intent_routing:
            return RoutingDecision(
                intent=Intent.REVIEWS,
                confidence=1.0,
                reasoning="Intent routing disabled via ENABLE_INTENT_ROUTING=false",
                source="default",
            )
        return self._router.route(question)

    # Pipeline dispatch

    def _run_pipelines(
        self,
        question: str,
        routing: RoutingDecision,
        top_k: int,
        city_filter: str | None,
        min_rating: int | None,
    ) -> list[CorpusResult]:
        """Execute the pipelines selected by the routing decision."""
        results: list[CorpusResult] = []

        if routing.intent in (Intent.REVIEWS, Intent.BOTH):
            filter_reviews = _build_reviews_filter(city_filter, min_rating)
            results.append(
                self._reviews.retrieve(
                    question, top_k=top_k, metadata_filter=filter_reviews
                )
            )

        if routing.intent in (Intent.DESCRIPTIONS, Intent.BOTH):
            filter_descriptions = _build_descriptions_filter(city_filter)
            results.append(
                self._descriptions.retrieve(
                    question, top_k=top_k, metadata_filter=filter_descriptions
                )
            )

        return results

    # Merging

    @staticmethod
    def _merge(
        per_corpus: list[CorpusResult],
        top_k: int,
    ) -> tuple[dict[str, list[RetrievalResult]], list[RetrievalResult]]:
        """Combine per-corpus results into a single flat list."""
        sources_by_source: dict[str, list[RetrievalResult]] = {
            r.corpus_name: r.sources for r in per_corpus
        }

        all_sources = [s for r in per_corpus for s in r.sources]
        all_sources.sort(key=lambda s: s.score, reverse=True)

        merged_cap = 2 * top_k if len(per_corpus) > 1 else top_k
        merged = all_sources[:merged_cap]

        return sources_by_source, merged


# Helpers (module-level for easier testing and reuse)


def _build_reviews_filter(
    city_filter: str | None, min_rating: int | None
) -> dict[str, Any] | None:
    """Compose a Pinecone metadata filter for the reviews index."""
    f: dict[str, Any] = {}
    if city_filter:
        f["city"] = {"$eq": city_filter}
    if min_rating:
        f["overall_rating"] = {"$gte": min_rating}
    return f or None


def _build_descriptions_filter(city_filter: str | None) -> dict[str, Any] | None:
    """Compose a Pinecone metadata filter for the descriptions index."""
    if not city_filter:
        return None
    return {"city": {"$eq": city_filter}}


def _build_context(sources: list[RetrievalResult]) -> str:
    """Format sources into a single context string for the LLM."""
    parts: list[str] = []
    for i, src in enumerate(sources, 1):
        m = src.metadata
        source_tag = m.source.value.upper()

        location = ", ".join(filter(None, [getattr(m, "zone", ""), m.city]))
        prop_parts = [
            getattr(m, "flatname", ""),
            getattr(m, "roomname", ""),
        ]
        prop = " — ".join(filter(None, prop_parts))

        header = [f"[{source_tag} {i}]"]
        if location:
            header.append(f"Location: {location}")
        if prop:
            header.append(f"Property: {prop}")

        if m.source == DocumentSource.REVIEW:
            overall_rating = getattr(m, "overall_rating", 0)
            if overall_rating:
                header.append(f"Overall rating: {overall_rating}/5")
            review_title = getattr(m, "review_title", "")
            if review_title:
                header.append(f'Title: "{review_title}"')

        parts.append(" | ".join(header) + "\n" + src.text)

    return "\n\n".join(parts)


def _select_prompts(
    question: str,
    context: str,
    sources: list[RetrievalResult],
) -> tuple[str, str]:
    """Pick the system+user prompts that match the kinds of sources retrieved."""
    has_description = any(
        s.metadata.source in (DocumentSource.HOUSE, DocumentSource.ROOM)
        for s in sources
    )

    if has_description:
        return (
            MULTICORPUS_SYSTEM_PROMPT,
            build_multicorpus_user_prompt(question=question, context=context),
        )
    return (
        SYSTEM_PROMPT,
        build_user_prompt(question=question, context=context),
    )


def _first_rewrite(per_corpus: list[CorpusResult]) -> str | None:
    """Return the first non-None rewritten_query across pipelines."""
    for r in per_corpus:
        if r.rewritten_query is not None:
            return r.rewritten_query
    return None


def _empty_answer(routing: RoutingDecision) -> str:
    """Produce a user-facing message when no sources were retrieved."""
    if routing.intent == Intent.REVIEWS:
        return "No relevant reviews found for your question."
    if routing.intent == Intent.DESCRIPTIONS:
        return "No relevant property descriptions found for your question."
    return "No relevant documents found for your question."


def _mode_label(routing: RoutingDecision) -> str:
    """Short string identifying the active pipeline configuration."""
    flags: list[str] = []
    if settings.enable_query_rewriting:
        flags.append("rewrite")
    if settings.enable_reranking:
        flags.append("rerank")
    if settings.enable_intent_routing:
        flags.append(f"route:{routing.intent.value}")

    if not flags:
        return "naive-pinecone"
    return "advanced-" + "+".join(flags)