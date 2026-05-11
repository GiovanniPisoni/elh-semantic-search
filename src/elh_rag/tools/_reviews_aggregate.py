"""Review aggregation for Tool 4 (``get_property_details``)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from ._db import DBExecutor

_REVIEW_STATUS_APPROVED = "Approved"
_EXCERPT_LENGTH = 200
_MAX_RECENT_REVIEWS = 3


# Output models


class ReviewSummary(BaseModel):
    """A single review's surfaced fields (title + short excerpt + ratings)."""

    date_review: date
    title: str
    overall_rating: float
    excerpt: str  # up to 200 chars from description, no padding


class ReviewsAggregate(BaseModel):
    """Aggregated review stats for a (house, room?) scope."""

    count: int
    average_overall_rating: float | None = None
    average_cleaning_rating: float | None = None
    average_communication_rating: float | None = None
    average_location_rating: float | None = None
    average_price_quality_rating: float | None = None
    recent_reviews: list[ReviewSummary] = Field(default_factory=list)


# SQL


_REVIEWS_ROOM_SQL = """\
SELECT
    datereview, title, description, status,
    overallratings, cleaningratings, communicationratings,
    locationratings, pricequalityratings
FROM review
WHERE loc_idhouse = %s
  AND loc_dateupdate = %s
  AND idroom = %s
  AND status = %s
ORDER BY datereview DESC
"""

_REVIEWS_HOUSE_SQL = """\
SELECT
    datereview, title, description, status,
    overallratings, cleaningratings, communicationratings,
    locationratings, pricequalityratings
FROM review
WHERE loc_idhouse = %s
  AND loc_dateupdate = %s
  AND status = %s
ORDER BY datereview DESC
"""


# Helpers


def _safe_str(value: Any) -> str:
    """Strip and stringify (handles ``character()`` right-padding)."""
    return "" if value is None else str(value).strip()


def _avg(values: list[Any]) -> float | None:
    """Arithmetic mean of non-null numeric values, or ``None`` if empty."""
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _row_to_summary(row: dict[str, Any]) -> ReviewSummary:
    description = _safe_str(row.get("description"))
    excerpt = description[:_EXCERPT_LENGTH]
    if len(description) > _EXCERPT_LENGTH:
        excerpt = excerpt.rstrip() + "…"
    return ReviewSummary(
        date_review=row["datereview"],
        title=_safe_str(row.get("title")),
        overall_rating=float(row.get("overallratings") or 0.0),
        excerpt=excerpt,
    )


# Entry point


def fetch_reviews_aggregate(
    db: DBExecutor,
    *,
    house_id: str,
    house_dateupdate: date,
    room_id: str | None = None,
) -> ReviewsAggregate:
    """Fetch approved reviews scoped to a house version (and optionally a room).

    Empty scope returns ``count=0`` and ``None`` averages.
    """
    if room_id is not None:
        rows = db.execute(
            _REVIEWS_ROOM_SQL,
            (house_id, house_dateupdate, room_id, _REVIEW_STATUS_APPROVED),
        )
    else:
        rows = db.execute(
            _REVIEWS_HOUSE_SQL,
            (house_id, house_dateupdate, _REVIEW_STATUS_APPROVED),
        )

    if not rows:
        return ReviewsAggregate(count=0)

    recent = [_row_to_summary(r) for r in rows[:_MAX_RECENT_REVIEWS]]

    return ReviewsAggregate(
        count=len(rows),
        average_overall_rating=_avg([r.get("overallratings") for r in rows]),
        average_cleaning_rating=_avg([r.get("cleaningratings") for r in rows]),
        average_communication_rating=_avg(
            [r.get("communicationratings") for r in rows]
        ),
        average_location_rating=_avg([r.get("locationratings") for r in rows]),
        average_price_quality_rating=_avg(
            [r.get("pricequalityratings") for r in rows]
        ),
        recent_reviews=recent,
    )