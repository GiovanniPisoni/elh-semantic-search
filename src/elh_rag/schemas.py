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
        known = {f.name for f in cls.__dataclass_fields__.values()}
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
        known = {f.name for f in cls.__dataclass_fields__.values()}
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
        known = {f.name for f in cls.__dataclass_fields__.values()}
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


# Document wrapper


@dataclass(frozen=True, slots=True)
class Document:
    """A document ready to be embedded and indexed."""

    text: str
    metadata: DocumentMetadata
