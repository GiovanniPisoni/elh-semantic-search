"""
CorpusPipeline — retrieval-only pipeline for a single corpus.

The base class encapsulates three retrieval concerns:
    1. (optional) query rewriting
    2. vector retrieval from ONE index
    3. (optional) cross-encoder reranking

Crucially it does NOT call the generation LLM.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from elh_rag.config import settings
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RetrievalResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CorpusResult:
    """Output of a single corpus pipeline run."""

    corpus_name: str
    sources: list[RetrievalResult]
    rewritten_query: str | None = None


class CorpusPipeline(ABC):
    """Base class for a retrieval pipeline over a single corpus."""

    corpus_name: str = "generic"

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder or Embedder()
        self._rewriter = query_rewriter or QueryRewriter()
        self._reranker = reranker or Reranker()

    # Public API

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> CorpusResult:
        """Run rewrite → retrieve → rerank on this corpus."""
        top_k = top_k or settings.retrieval_top_k
        pool = self.pool_size(top_k)

        retrieval_query, rewritten = self._maybe_rewrite(question)

        candidates = self._retrieve(
            retrieval_query,
            top_k=pool,
            metadata_filter=metadata_filter,
        )

        sources = self._maybe_rerank(retrieval_query, candidates, top_k=top_k)

        return CorpusResult(
            corpus_name=self.corpus_name,
            sources=sources,
            rewritten_query=rewritten,
        )

    # Hooks for subclasses

    @abstractmethod
    def build_retrieval_result(self, match: dict[str, Any]) -> RetrievalResult:
        """Convert a raw Pinecone match into a RetrievalResult."""

    def pool_size(self, top_k: int) -> int:
        """How many candidates to pre-fetch before reranking.

        Default: if reranking is on, use `reranker_pool_size`; otherwise
        `top_k`.
        """
        if settings.enable_reranking:
            return max(settings.reranker_pool_size, top_k)
        return top_k

    # Internal steps

    def _maybe_rewrite(self, question: str) -> tuple[str, str | None]:
        """Apply query rewriting if enabled."""
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
        metadata_filter: dict[str, Any] | None,
    ) -> list[RetrievalResult]:
        """Embed the query and retrieve the most similar documents."""
        embedding = self._embedder.encode_query(query_text)
        matches = self._store.query(
            embedding=embedding,
            top_k=top_k,
            metadata_filter=metadata_filter,
        )
        return [self.build_retrieval_result(m) for m in matches]

    def _maybe_rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Apply cross-encoder reranking if enabled, else truncate to top_k."""
        if not settings.enable_reranking:
            return candidates[:top_k]
        return self._reranker.rerank(query, candidates, top_k=top_k)
