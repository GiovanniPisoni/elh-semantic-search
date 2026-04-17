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
from elh_rag.schemas import RAGResponse, RetrievalResult, ReviewMetadata

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Naive RAG pipeline (Phase 1).

    Steps: embed query → retrieve top-k → build context → generate answer.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._store = vector_store or PineconeVectorStore()
        self._embedder = embedder or Embedder()
        self._llm = llm_client or LLMClient()

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

        sources = self._retrieve(
            question,
            top_k=top_k,
            city_filter=city_filter,
            min_rating=min_rating,
        )

        if not sources:
            return RAGResponse(
                query=question,
                answer="No relevant reviews found for your question.",
                sources=[],
            )

        context = self._build_context(sources)
        answer = self._generate(question, context)

        return RAGResponse(query=question, answer=answer, sources=sources)

    # Pipeline steps

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
