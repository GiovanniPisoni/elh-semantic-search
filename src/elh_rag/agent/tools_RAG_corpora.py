"""
RAG corpora exposed as tool-callable functions.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# Input models


class SearchDescriptionsInput(BaseModel):
    """Inputs for semantic search over the house+room descriptions corpus."""

    model_config = ConfigDict(frozen=True)

    # TODO: fields - query (str, max_length=500), top_k (int, 1-20),
    # city (Literal["Lisbon", "Porto"] | None).


class SearchReviewsInput(BaseModel):
    """Inputs for semantic search over the student-reviews corpus."""

    model_config = ConfigDict(frozen=True)

    # TODO: fields - query (str, max_length=500), top_k (int, 1-20),
    # city (Literal["Lisbon", "Porto"] | None), min_rating (int | None, 1-5).


# Output dataclass


class RAGSearchHit(BaseModel):
    """Single retrieved document chunk, returned by both Phase 2 tools."""

    model_config = ConfigDict(frozen=True)

    # TODO: fields - text (str), score (float), corpus (str),
    # source_id (str), metadata (dict[str, Any]).


class RAGSearchOutput(BaseModel):
    """List of hits + summary, returned by both Phase 2 tools."""

    model_config = ConfigDict(frozen=True)

    # TODO: fields - hits (list[Phase2SearchHit]),
    # total_hits (int), corpus (str), query_used (str).


# Tool registration


# TODO:
# @register_tool(
#     name="search_descriptions",
#     description=(...),
#     input_model=SearchDescriptionsInput,
# )
def search_descriptions(
    payload: Any,
    ctx: Any,
) -> Any:
    """Retrieve relevant house/room description chunks via vector search."""
    raise NotImplementedError("Implemented in next steps")


# TODO:
# @register_tool(
#     name="search_reviews",
#     description=(...),
#     input_model=SearchReviewsInput,
# )
def search_reviews(
    payload: Any,
    ctx: Any,
) -> Any:
    """Retrieve relevant student-review chunks via vector search."""
    raise NotImplementedError("Implemented in next steps")
