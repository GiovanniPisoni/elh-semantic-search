"""
Pinecone implementation of the VectorStore protocol.
"""
from __future__ import annotations

import logging
from typing import Any

from elh_rag.config import settings

logger = logging.getLogger(__name__)


class PineconeVectorStore:
    """VectorStore backed by a Pinecone serverless index."""

    def __init__(self, index_name: str | None = None) -> None:
        self._index_name = index_name or settings.pinecone_index_name
        self._index: Any | None = None

    @property
    def index(self) -> Any:
        """Lazily-initialised Pinecone index handle."""
        if self._index is None:
            from pinecone import Pinecone

            logger.info("Connecting to Pinecone index '%s'", self._index_name)
            pc = Pinecone(api_key=settings.pinecone_api_key)
            self._index = pc.Index(self._index_name)
        return self._index

    def upsert(self, vectors: list[dict[str, Any]]) -> None:
        if not vectors:
            return
        self.index.upsert(vectors=vectors)

    def query(
        self,
        embedding: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "vector": embedding,
            "top_k": top_k,
            "include_metadata": True,
        }
        if metadata_filter:
            params["filter"] = metadata_filter

        result = self.index.query(**params)
        return [
            {
                "id": match.id,
                "score": float(match.score),
                "metadata": dict(match.metadata) if match.metadata else {},
            }
            for match in result.matches
        ]

    def delete_all(self) -> None:
        logger.warning("Deleting ALL vectors from index '%s'", self._index_name)
        self.index.delete(delete_all=True)

    def count(self) -> int:
        stats = self.index.describe_index_stats()
        return int(stats.total_vector_count)
