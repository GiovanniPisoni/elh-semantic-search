"""Knowledge-base store and semantic search for Tool 6."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from elh_rag.indexing.embeddings import Embedder

logger = logging.getLogger(__name__)


Audience = Literal["student", "landlord", "both"]


# Models


class KBEntry(BaseModel):
    """One policy entry as loaded from YAML."""

    id: str
    category: str
    audience: Audience
    canonical_question: str
    question_variants: list[str] = Field(default_factory=list)
    answer: str
    sources: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class IndexedEntry:
    """A KB entry with its variant embeddings precomputed."""

    entry: KBEntry
    variant_embeddings: list[list[float]]


# YAML loader


_DEFAULT_KB_PATH = Path(__file__).parent / "kb" / "policies.yaml"


def load_entries(path: Path | None = None) -> list[KBEntry]:
    """Read the YAML file and validate every entry."""
    p = path or _DEFAULT_KB_PATH
    if not p.is_file():
        raise FileNotFoundError(f"KB YAML not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "entries" not in data:
        raise ValueError(f"KB YAML at {p} must be a mapping with an 'entries' key")
    raw_entries = data["entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("KB YAML 'entries' must be a list")
    entries = [KBEntry.model_validate(item) for item in raw_entries]
    _validate_cross_refs(entries)
    return entries


def _validate_cross_refs(entries: list[KBEntry]) -> None:
    """Warn (don't fail) on dangling ``related`` IDs."""
    known_ids = {e.id for e in entries}
    for e in entries:
        for ref in e.related:
            if ref not in known_ids:
                logger.warning(
                    "KB entry %r references unknown related id %r",
                    e.id,
                    ref,
                )


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


def _audience_matches(entry_audience: str, requested: str) -> bool:
    """Return True if ``entry_audience`` is visible to ``requested``."""
    if requested == "both":
        return True
    if entry_audience == "both":
        return True
    return entry_audience == requested


# KBStore


class KBStore:
    """In-memory KB with precomputed variant embeddings."""

    def __init__(self, indexed: list[IndexedEntry]) -> None:
        self._indexed = list(indexed)
        self._by_id: dict[str, KBEntry] = {ie.entry.id: ie.entry for ie in indexed}

    @classmethod
    def from_yaml(
        cls,
        embedder: Embedder,
        path: Path | None = None,
    ) -> KBStore:
        """Load YAML, embed every (canonical + variants), return ready store."""
        entries = load_entries(path)
        indexed: list[IndexedEntry] = []
        for entry in entries:
            texts = [entry.canonical_question, *entry.question_variants]
            embeddings = embedder.encode_batch(texts)
            indexed.append(IndexedEntry(entry=entry, variant_embeddings=embeddings))
        logger.info(
            "KB loaded: %d entries, %d total variant embeddings",
            len(indexed),
            sum(len(ie.variant_embeddings) for ie in indexed),
        )
        return cls(indexed)

    def search(
        self,
        query_embedding: list[float],
        *,
        audience: Audience = "student",
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> list[tuple[KBEntry, float]]:
        """Return up to ``top_k`` entries, max-scored per entry."""
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


# KBContext


class KBContext:
    """Bundle of (KBStore + embedder) injected as ``ctx`` for Tool 6."""

    def __init__(self, kb_store: KBStore, embedder: Embedder) -> None:
        self.kb_store = kb_store
        self.embedder = embedder

    def search(
        self,
        question: str,
        *,
        audience: Audience = "student",
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> list[tuple[KBEntry, float]]:
        """Embed the question and delegate to :meth:`KBStore.search`."""
        query_embedding = self.embedder.encode_query(question)
        return self.kb_store.search(
            query_embedding,
            audience=audience,
            top_k=top_k,
            threshold=threshold,
        )

    @classmethod
    def from_default_yaml(cls, embedder: Embedder) -> KBContext:
        """Convenience factory: load the bundled ``policies.yaml``."""
        return cls(KBStore.from_yaml(embedder), embedder)
