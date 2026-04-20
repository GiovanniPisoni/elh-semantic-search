"""
Typed data schemas used across the RAG pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class DocumentSource(str, Enum):
    """Where a document originated in the ELH database."""

    REVIEW = "review"
    HOUSE_DESCRIPTION = "house_description"
    ROOM_DESCRIPTION = "room_description"


@dataclass(frozen=True, slots=True)
class ReviewMetadata:
    """Metadata attached to a single review document."""

    id: str
    source: DocumentSource = DocumentSource.REVIEW
    city: str = ""
    zone: str = ""
    neighbourhood: str = ""
    flatname: str = ""
    roomname: str = ""
    idhouse: str = ""
    idroom: str = ""
    overall_rating: int = 0
    cleaning_rating: int = 0
    communication_rating: int = 0
    location_rating: int = 0
    pricequality_rating: int = 0
    date_review: str = ""
    review_title: str = ""
    review_text_original: str = ""

    def to_pinecone_dict(self) -> dict[str, Any]:
        """Convert to a Pinecone-safe dict (str/int/float/bool/list[str] only)."""
        d = asdict(self)
        d["source"] = self.source.value
        return d

    @classmethod
    def from_pinecone_dict(cls, data: dict[str, Any]) -> "ReviewMetadata":
        """Reconstruct from a Pinecone match.metadata dict."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        if "source" in clean and isinstance(clean["source"], str):
            clean["source"] = DocumentSource(clean["source"])
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class Document:
    """A document ready to be embedded and indexed."""

    text: str
    metadata: ReviewMetadata


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """A single document returned by the retriever.
    
    Carries both the originale vector-similarity score and (optionally) the
    corss-encoder rerank score.
    """

    text: str
    metadata: ReviewMetadata
    vector_score: float
    rerank_score: float | None = None

    @property
    def score(self) -> float:
        """The score used for final ranking"""
        return self.rerank_score if self.rerank_score is not None else self.vector_score

    @property
    def distance(self) -> float:
        """Cosine distance, derived from score."""
        return round(1.0 - self.vector_score, 3)


@dataclass(frozen=True, slots=True)
class RAGResponse:
    """The final response returned by the RAG pipeline."""

    query: str
    answer: str
    sources: list[RetrievalResult]
    mode: str = "naive-pinecone"
    rewritten_query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dict representation."""
        return {
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "answer": self.answer,
            "mode": self.mode,
            "sources": [
                {
                    "text": s.text,
                    "vector_score": s.vector_score,
                    "rerank_score": s.rerank_score,
                    "metadata": s.metadata.to_pinecone_dict(),
                }
                for s in self.sources
            ],
        }
