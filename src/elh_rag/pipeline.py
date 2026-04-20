"""
RAG pipeline orchestration.
"""
from __future__ import annotations

import logging

from elh_rag.config import settings
from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RAGResponse, RetrievalResult, ReviewMetadata

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    RAG pipeline with optional query rewriting.

    Steps:
        (optional) rewrite query  ← Phase 2, Step 1
        embed query
        retrieve top-k (N-candidates)
        (optional) rerank -> top-k
        build context
        generate answer
    
    Each optional step is gated by an env-var toggle so the same pipeline
    instance can serve all three A/B configurations for evaluation:
    Naive / +Rewriting / +Rewriting+Reranking.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        llm_client: LLMClient | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._store = vector_store or PineconeVectorStore()
        self._embedder = embedder or Embedder()
        self._llm = llm_client or LLMClient()
        self._rewriter = query_rewriter or QueryRewriter()
        self._reranker = reranker or Reranker()

    # Public API

    def query(
        self,
        question: str,
        top_k: int | None = None,
        city_filter: str | None = None,
        min_rating: int | None = None,
    ) -> RAGResponse:
        """Run the full RAG pipeline on a single question."""
        top_k = top_k or settings.retrieval_top_k
        pool_size = self._pool_size(top_k)

        retrival_query, rewritten = self._maybe_rewrite(question)

        candidates = self._retrieve(
            retrival_query,
            top_k=pool_size,
            city_filter=city_filter,
            min_rating=min_rating,
        )

        sources = self._maybe_rerank(retrival_query, candidates, top_k=top_k)

        if not sources:
            return RAGResponse(
                query=question,
                rewritten_query=rewritten,
                answer="No relevant reviews found for your question.",
                sources=[],
                mode=self._mode_label()
            )

        context = self._build_context(sources)
        answer = self._generate(question, context)

        return RAGResponse(
            query=question, 
            rewritten_query=rewritten,
            answer=answer, 
            sources=sources,
            mode=self._mode_label()
        )

    # Pipeline steps

    def _maybe_rewrite(self, question: str) -> tuple[str, str | None]:
        """Apply query rewriting if enabled.

        Returns:
            (retrieval_query, rewritten_query)
            - retrieval_query: the string fed to the retriever (rewritten or original)
            - rewritten_query: the rewritten text, or None if rewriting was disabled
              or produced no change
        """
        if not settings.enable_query_rewriting:
            return question, None
        
        rewritten = self._rewriter.rewrite(question)
        if rewritten == question:
            return question, None
        
        return rewritten, rewritten

    def _retrieve(
        self,
        query_text: str,
        top_k: int,
        city_filter: str | None,
        min_rating: int | None,
    ) -> list[RetrievalResult]:
        """Embed the question and retrieve the most similar documents."""
        embedding = self._embedder.encode_query(query_text)
        metadata_filter = self._build_metadata_filter(city_filter, min_rating)
        matches = self._store.query(
            embedding=embedding,
            top_k=top_k,
            metadata_filter=metadata_filter,
        )

        return [
            RetrievalResult(
                text=m["metadata"].get("review_text_original", ""),
                metadata=ReviewMetadata.from_pinecone_dict(m["metadata"]),
                vector_score=round(m["score"], 3),
            )
            for m in matches
        ]

    def _maybe_rerank(
            self,
            query: str,
            candidates: list[RetrievalResult],
            top_k: int,
    ) -> list[RetrievalResult]:
        """Apply corss-encoder reranking if enabled, else truncate to top_k."""
        if not settings.enable_reranking:
            return candidates[:top_k]
        
        return self._reranker.rerank(query, candidates, top_k=top_k)
    
    @staticmethod
    def _pool_size(top_k: int) -> int:
        """Candidate pool size for retrieval."""
        if settings.enable_reranking:
            return max(settings.reranker_pool_size, top_k)
        
        return top_k

    @staticmethod
    def _build_metadata_filter(
        city_filter: str | None, min_rating: int | None
    ) -> dict | None:
        """Compose a Pinecone-compatible metadata filter from optional constraints."""
        f: dict = {}
        if city_filter:
            f["city"] = {"$eq": city_filter}
        if min_rating:
            f["overall_rating"] = {"$gte": min_rating}
        return f or None

    @staticmethod
    def _build_context(sources: list[RetrievalResult]) -> str:
        """Format retrieved sources into a single context string for the LLM."""
        parts: list[str] = []
        for i, src in enumerate(sources, 1):
            m = src.metadata
            location = ", ".join(filter(None, [m.zone, m.city]))
            prop = " — ".join(filter(None, [m.flatname, m.roomname]))

            header = [f"[Review {i}]"]
            if location:
                header.append(f"Location: {location}")
            if prop:
                header.append(f"Property: {prop}")
            if m.overall_rating:
                header.append(f"Overall rating: {m.overall_rating}/5")
            if m.review_title:
                header.append(f'Title: "{m.review_title}"')

            parts.append(" | ".join(header) + "\n" + src.text)

        return "\n\n".join(parts)

    def _generate(self, question: str, context: str) -> str:
        """Invoke the LLM with the assembled prompt."""
        return self._llm.complete(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(question=question, context=context),
        )
    
    @staticmethod
    def _mode_label() -> str:
        """Return a short string identifying the pipeline configuration."""
        flags = []
        if settings.enable_query_rewriting:
            flags.append("rewrite")
        if settings.enable_reranking:
            flags.append("rerank")
        if not flags:
            return "naive-pinecone"
        return "advanced-" + "+".join(flags)
