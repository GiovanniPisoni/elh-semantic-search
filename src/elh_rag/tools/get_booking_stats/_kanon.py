"""K-anonymity filter for Tool 5 aggregate statistics."""

from __future__ import annotations

from typing import Any

# ELH-mandated minimum number of underlying records per bucket.
K_THRESHOLD: int = 5


def filter_by_k_anonymity(
    data_points: list[Any],
    threshold: int = K_THRESHOLD,
) -> tuple[list[Any], int]:
    """Drop points with ``sample_size < threshold``."""
    kept = [p for p in data_points if getattr(p, "sample_size", 0) >= threshold]
    return kept, len(data_points) - len(kept)
