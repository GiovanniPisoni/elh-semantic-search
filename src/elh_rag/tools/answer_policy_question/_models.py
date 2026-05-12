"""Data models for the policy KB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

Audience = Literal["student", "landlord", "both"]


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
    """A KB entry with its variant embeddings precomputed.

    The embeddings list contains one vector per text matcher:
    ``[canonical_question, *question_variants]``. At query time
    :meth:`._store.KBStore.search` scores each variant individually
    and takes the max per entry.
    """

    entry: KBEntry
    variant_embeddings: list[list[float]]
