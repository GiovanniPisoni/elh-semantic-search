"""
RAG corpora exposed as tool-callable functions.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from elh_rag.tools.base import register_tool

logger = logging.getLogger(__name__)


# Input models


class SearchDescriptionsInput(BaseModel):
    """Inputs for semantic search over the house+room descriptions corpus."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "Natural-language query describing what to find in the property descriptions."
        ),
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top matches to return.",
    )
    city: Literal["Lisbon", "Porto"] | None = Field(
        default=None,
        description=" If set, restrict matches to descriptions from this city.",
    )


class SearchReviewsInput(BaseModel):
    """Inputs for semantic search over the student-reviews corpus."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description=("Natural-language query describing what to find in the student reviews."),
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top matches to return.",
    )
    city: Literal["Lisbon", "Porto"] | None = Field(
        default=None,
        description="If set, restrict matches to reviews from this city.",
    )
    min_rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "If set, only return reviews whose overall_rating (1-5 scale) is at least this value."
        ),
    )


# Output models


class RAGSearchHit(BaseModel):
    """One retrieved chunk from a RAG corpus."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., description="The retrived text chunk.")
    score: float = Field(
        ...,
        description="vector-similarity score, rounded to 3 decimals.",
    )
    source_id: str = Field(
        ...,
        description="Unique identifier of the source chunk (vector id).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Full metadata of the chunk (city, flatname, etc.).",
    )


class RAGSearchOutput(BaseModel):
    """Result of a RAG-corpus search tool call."""

    model_config = ConfigDict(frozen=True)

    hits: list[RAGSearchHit] = Field(
        default_factory=list,
        description="Top-k matches, ordered by descending score.",
    )
    total_hits: int = Field(
        ...,
        ge=0,
        description="Number of hits returned (equals len(hits)).",
    )
    corpus: Literal["descriptions", "reviews"] = Field(
        ...,
        description="Which corpus produced these hits.",
    )
    query_used: str = Field(
        ...,
        description="The query string embedded against the corpus.",
    )


# Filter builders


def _build_descriptions_filter(city: str | None) -> dict[str, Any] | None:
    """Compose a Pinecone metadata filter for the descriptions corpus."""
    if not city:
        return None
    return {"city": {"$eq": city}}


def _build_reviews_filter(
    city: str | None,
    min_rating: int | None,
) -> dict[str, Any] | None:
    """Compose a Pinecone metadata filter for the reviews corpus."""
    f: dict[str, Any] = {}
    if city:
        f["city"] = {"$eq": city}
    if min_rating:
        f["overall_rating"] = {"$gte": min_rating}
    return f or None


# Match-hit converter


def _match_to_hit(match: dict[str, Any]) -> RAGSearchHit:
    """Convert one Pinecone match dict into a :class:`RAGSearchHit`."""
    metadata = match.get("metadata", {})
    return RAGSearchHit(
        text=metadata.get("text", ""),
        score=round(match["score"], 3),
        source_id=match["id"],
        metadata=metadata,
    )


# Tool: search_descriptions

_SEARCH_DESCRIPTIONS_DESCRIPTION = (
    "Search the house+room descriptions corpus for chunks matching "
    "the given query. Use this tool when the user asks about FACTUAL "
    "PROPERTY DETAILS: amenities, location, room features, services "
    "included, neighborhood description, etc. Returns top_k chunks "
    "ranked by semantic similarity. Each hit contains the chunk text, "
    "similarity score, source id, and metadata (city, flatname, "
    "roomname, etc.) usable for follow-up queries with other tools "
    "such as get_property_details."
)


# Tool registration


@register_tool(
    name="search_descriptions",
    description=_SEARCH_DESCRIPTIONS_DESCRIPTION,
    input_model=SearchDescriptionsInput,
)
def search_descriptions(
    payload: SearchDescriptionsInput,
    ctx: Any,
) -> RAGSearchOutput:
    """Retrieve relevant house/room description chunks via vector search."""
    logger.debug(
        "search_descriptions: query=%r top_k=%d, city=%r",
        payload.query,
        payload.top_k,
        payload.city,
    )

    embedding = ctx.embedder.encode_query(payload.query)
    metadata_filter = _build_descriptions_filter(payload.city)

    matches = ctx.descriptions_store.query(
        embedding=embedding,
        top_k=payload.top_k,
        metadata_filter=metadata_filter,
    )

    hits = [_match_to_hit(m) for m in matches]

    return RAGSearchOutput(
        hits=hits,
        total_hits=len(hits),
        corpus="descriptions",
        query_used=payload.query,
    )


# Tool: search_reviews

_SEARCH_REVIEWS_DESCRIPTION = (
    "Search the student-reviews corpus for chunks matching the given "
    "query. Use this tool when the user asks about EXPERIENCES, "
    "OPINIONS, COMPLAINTS, recommendations, or subjective qualities "
    "of a property or neighborhood. Optionally filter by city and "
    "minimum overall rating. Returns top_k chunks ranked by semantic "
    "similarity. Each hit includes the review text, similarity score, "
    "source id, and metadata (city, overall_rating, review_title, etc.)."
)


@register_tool(
    name="search_reviews",
    description=_SEARCH_REVIEWS_DESCRIPTION,
    input_model=SearchReviewsInput,
)
def search_reviews(
    payload: SearchReviewsInput,
    ctx: Any,
) -> RAGSearchOutput:
    """Retrieve relevant student-review chunks via vector search."""
    logger.debug(
        "search_reviews: query=%r top_k=%d city=%r min_rating=%r",
        payload.query,
        payload.top_k,
        payload.city,
        payload.min_rating,
    )

    embedding = ctx.embedder.encode_query(payload.query)
    metadata_filter = _build_reviews_filter(payload.city, payload.min_rating)

    matches = ctx.reviews_store.query(
        embedding=embedding,
        top_k=payload.top_k,
        metadata_filter=metadata_filter,
    )

    hits = [_match_to_hit(m) for m in matches]

    return RAGSearchOutput(
        hits=hits,
        total_hits=len(hits),
        corpus="reviews",
        query_used=payload.query,
    )
