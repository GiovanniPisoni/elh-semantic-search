"""
ReviewsPipeline — retrieval over the student-reviews corpus.

Concrete subclass of CorpusPipeline.
"""

from __future__ import annotations

from typing import Any

from elh_rag.config import settings
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.orchestration.corpus_pipeline import CorpusPipeline
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RetrievalResult, ReviewMetadata


class ReviewsPipeline(CorpusPipeline):
    """Retrieval pipeline scoped to the reviews Pinecone index."""

    corpus_name = "reviews"

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        super().__init__(
            vector_store=vector_store
            or PineconeVectorStore(index_name=settings.pinecone_index_name),
            embedder=embedder,
            query_rewriter=query_rewriter,
            reranker=reranker,
        )

    def build_retrieval_result(self, match: dict[str, Any]) -> RetrievalResult:
        """Build the result using the `text` metadata field."""
        metadata = match["metadata"]
        text = metadata.get("text") or metadata.get("review_text_original", "")
        return RetrievalResult(
            text=text,
            metadata=ReviewMetadata.from_pinecone_dict(metadata),
            vector_score=round(match["score"], 3),
        )
