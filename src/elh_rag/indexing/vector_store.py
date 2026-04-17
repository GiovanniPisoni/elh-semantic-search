"""
Vector store abstraction.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """Minimal interface every vector store backend must implement."""

    def upsert(self, vectors: list[dict[str, Any]]) -> None:
        """Insert or update a batch of vectors.

        Each vector must be a dict with keys: 'id', 'values', 'metadata'.
        """
        ...

    def query(
        self,
        embedding: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top_k matches as dicts with keys 'id', 'score', 'metadata'."""
        ...

    def delete_all(self) -> None:
        """Remove all vectors from the store."""
        ...

    def count(self) -> int:
        """Return the total number of vectors currently stored."""
        ...
