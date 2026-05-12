"""In-memory KB store + cosine-based semantic search.

:class:`KBStore` holds a list of :class:`IndexedEntry` and implements
the matching primitive used by Tool 6: given a query embedding, score
every entry's variants by cosine similarity, take the max per entry,
apply audience filter + threshold, return top-K.
"""

from __future__ import annotations

import math

from ._models import Audience, IndexedEntry, KBEntry

# Cosine similarity (inline to avoid numpy dependency for a 1-liner)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# Audience matcher


def _audience_matches(entry_audience: str, requested: str) -> bool:
    """Return True if ``entry_audience`` is visible to ``requested``."""
    if requested == "both":
        return True
    if entry_audience == "both":
        return True
    return entry_audience == requested


# KBStore


class KBStore:
    """In-memory KB with precomputed variant embeddings.

    Construct directly from a list of :class:`IndexedEntry` (used by
    tests with hand-crafted vectors) or via
    :meth:`._loader.build_store_from_yaml` for the production path.
    """

    def __init__(self, indexed: list[IndexedEntry]) -> None:
        self._indexed = list(indexed)
        self._by_id: dict[str, KBEntry] = {ie.entry.id: ie.entry for ie in indexed}

    def search(
        self,
        query_embedding: list[float],
        *,
        audience: Audience = "student",
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> list[tuple[KBEntry, float]]:
        """Return up to ``top_k`` entries above threshold, max-scored per entry.

        Audience filter is applied BEFORE scoring (skips disqualified
        entries entirely). Within each entry, the variant with the
        highest cosine similarity wins.
        """
        scored: list[tuple[KBEntry, float]] = []
        for ie in self._indexed:
            if not _audience_matches(ie.entry.audience, audience):
                continue
            if not ie.variant_embeddings:
                continue
            best = max(_cosine_similarity(query_embedding, v) for v in ie.variant_embeddings)
            if best >= threshold:
                scored.append((ie.entry, best))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get(self, entry_id: str) -> KBEntry | None:
        return self._by_id.get(entry_id)

    def __len__(self) -> int:
        return len(self._indexed)
