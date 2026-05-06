"""
Pinecone implementation of the VectorStore protocol.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from elh_rag.config import settings

logger = logging.getLogger(__name__)


_UPSERT_CHUNK_SIZE = 50

_UPSERT_SLEEP_SEC = 0.1

_MAX_RETRIES = 3
_BACKOFF_BASE_SEC = 1.0


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
        """Upsert vectors into the index, chunked and retried."""
        if not vectors:
            return

        total_upserted = 0
        total_chunks = (len(vectors) + _UPSERT_CHUNK_SIZE - 1) // _UPSERT_CHUNK_SIZE

        for chunk_idx, start in enumerate(range(0, len(vectors), _UPSERT_CHUNK_SIZE)):
            chunk = vectors[start : start + _UPSERT_CHUNK_SIZE]
            self._upsert_chunk_with_retry(chunk, chunk_idx + 1, total_chunks)
            total_upserted += len(chunk)

            # Skip sleep after the last chunk — the caller is done.
            if chunk_idx + 1 < total_chunks:
                time.sleep(_UPSERT_SLEEP_SEC)

        logger.debug("Upserted %d vectors in %d chunks", total_upserted, total_chunks)

    def _upsert_chunk_with_retry(
        self,
        chunk: list[dict[str, Any]],
        chunk_num: int,
        total_chunks: int,
    ) -> None:
        """Send a single chunk, retrying on failure."""
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self.index.upsert(vectors=chunk)
                return
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    backoff = _BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                    logger.warning(
                        "Upsert chunk %d/%d failed (attempt %d/%d): %s — retrying in %.1fs",
                        chunk_num,
                        total_chunks,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)

        logger.error(
            "Upsert chunk %d/%d failed after %d attempts: %s",
            chunk_num,
            total_chunks,
            _MAX_RETRIES,
            last_error,
        )
        raise RuntimeError(
            f"Failed to upsert chunk {chunk_num}/{total_chunks} after {_MAX_RETRIES} attempts"
        ) from last_error

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
