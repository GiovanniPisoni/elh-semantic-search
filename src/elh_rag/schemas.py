"""
Typed data schemas used across the RAG pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class DocumentSource(StrEnum):
    """Where a document originated in the ELH database."""

    REVIEW = "review"
    HOUSE = "house"
    ROOM = "room"


class Intent(StrEnum):
    """Which corpus the IntentRouter decide to target.

    - REVIEWS: user asks about experience, atmosphere, landlord, issues
    - DESCRIPTIONS: user asks about facts, amenities, prices, location
    - BOTH: intent is ambiguous or multi-faceted, query both corpora
    """

    REVIEWS = "reviews"
    DESCRIPTIONS = "descriptions"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """The output of the IntentRouter."""

    intent: Intent
    confidence: float
    reasoning: str = ""
    source: str = "llm"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A single (question, answer) pair in a conversation."""

    question: str
    answer: str


# Metadata: one frozen dataclass per source


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
    def from_pinecone_dict(cls, data: dict[str, Any]) -> ReviewMetadata:
        """Reconstruct from a Pinecone match.metadata dict."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        if "source" in clean and isinstance(clean["source"], str):
            clean["source"] = DocumentSource(clean["source"])
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class HouseMetadata:
    """Metadata attached to a single house description document."""

    id: str
    source: DocumentSource = DocumentSource.HOUSE
    idhouse: str = ""
    flatname: str = ""
    city: str = ""
    zone: str = ""
    neighbourhood: str = ""

    def to_pinecone_dict(self) -> dict[str, Any]:
        """Convert to a Pinecone-safe dict (str/int/float/bool/list[str] only)"""
        d = asdict(self)
        d["source"] = self.source.value
        return d

    @classmethod
    def from_pinecone_dict(cls, data: dict[str, Any]) -> HouseMetadata:
        """Reconstruct from a Pinecone match.metadata dict."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        if "source" in clean and isinstance(clean["source"], str):
            clean["source"] = DocumentSource(clean["source"])
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class RoomMetadata:
    """Metadata attached to a single room description document"""

    id: str
    source: DocumentSource = DocumentSource.ROOM
    idroom: str = ""
    roomname: str = ""
    idhouse: str = ""
    flatname: str = ""
    city: str = ""
    zone: str = ""
    neighbourhood: str = ""

    def to_pinecone_dict(self) -> dict[str, Any]:
        """Convert to a Pinecone-safe dict (str/int/float/bool/list[str] only)."""
        d = asdict(self)
        d["source"] = self.source.value
        return d

    @classmethod
    def from_pinecone_dict(cls, data: dict[str, Any]) -> RoomMetadata:
        """Reconstruct from a Pinecone match.metadata dict."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        if "source" in clean and isinstance(clean["source"], str):
            clean["source"] = DocumentSource(clean["source"])
        return cls(**clean)


# Union type for any metadata

DocumentMetadata = ReviewMetadata | HouseMetadata | RoomMetadata
"""Type alias for any metadata type in the system."""


def metadata_from_pinecone_dict(data: dict[str, Any]) -> DocumentMetadata:
    """
    Dispatch-by-source reconstruction of metadata from a Pinecone record.

    Looks at the `source` field and delegates to the right class.
    """
    source_str = data.get("source", DocumentSource.REVIEW.value)
    if source_str == DocumentSource.HOUSE.value:
        return HouseMetadata.from_pinecone_dict(data)
    if source_str == DocumentSource.ROOM.value:
        return RoomMetadata.from_pinecone_dict(data)
    return ReviewMetadata.from_pinecone_dict(data)


# Document and retrievl wrappers


@dataclass(frozen=True, slots=True)
class Document:
    """A document ready to be embedded and indexed."""

    text: str
    metadata: DocumentMetadata


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """A single document returned by the retriever.

    Carries both the original vector-similarity score and (optionally) the
    cross-encoder rerank score.
    """

    text: str
    metadata: DocumentMetadata
    vector_score: float
    rerank_score: float | None = None

    @property
    def score(self) -> float:
        """
        The score used for final ranking

        Prefers the rerank score when available, falls back to the raw
        vector score.
        """
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
    sources_by_source: dict[str, list[RetrievalResult]] | None = None
    routing: RoutingDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dict representation."""
        payload: dict[str, Any] = {
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
        if self.sources_by_source is not None:
            payload["sources_by_source"] = {
                source_name: [
                    {
                        "text": s.text,
                        "vector_score": s.vector_score,
                        "rerank_score": s.rerank_score,
                        "metadata": s.metadata.to_pinecone_dict(),
                    }
                    for s in sources
                ]
                for source_name, sources in self.sources_by_source.items()
            }
        if self.routing is not None:
            payload["routing"] = {
                "intent": self.routing.intent.value,
                "confidence": self.routing.confidence,
                "reasoning": self.routing.reasoning,
                "source": self.routing.source,
            }
        return payload
