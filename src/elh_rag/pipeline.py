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
from elh_rag.schemas import RAGResponse, RetrievalResult, ReviewMetadata

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    RAG pipeline with optional query rewriting.

    Steps:
        (optional) rewrite query  ← Phase 2, Step 1
        embed query
        retrieve top-k
        build context
        generate answer
    
    Query rewriting can be toggled via the ENABLE_QUERY_REWRITING env var
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        llm_client: LLMClient | None = None,
        query_rewriter: QueryRewriter | None = None,
    ) -> None:
        self._store = vector_store or PineconeVectorStore()
        self._embedder = embedder or Embedder()
        self._llm = llm_client or LLMClient()
        self._rewriter = query_rewriter or QueryRewriter()

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

        retrival_query, rewritten = self._maybe_rewrite(question)

        sources = self._retrieve(
            retrival_query,
            top_k=top_k,
            city_filter=city_filter,
            min_rating=min_rating,
        )

        if not sources:
            return RAGResponse(
                query=question,
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
        question: str,
        top_k: int,
        city_filter: str | None,
        min_rating: int | None,
    ) -> list[RetrievalResult]:
        """Embed the question and retrieve the most similar documents."""
        embedding = self._embedder.encode_query(question)
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
                score=round(m["score"], 3),
            )
            for m in matches
        ]

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
        if settings.enable_query_rewriting:
            return "advanced-rewriting"
        return "naive-pinecone"
