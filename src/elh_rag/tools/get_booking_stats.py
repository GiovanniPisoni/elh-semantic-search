"""Tool 5: ``get_booking_stats``.

Aggregate statistics endpoint for the **internal ELH team**.

Permission gating is OUT of scope: the tool
always returns aggregates when called. Restricting access lives in the
orchestrator.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ._booking_stats import (
    GroupByDim,
    StatPoint,
    _compute_avg_booking_duration_months,
    _compute_avg_lead_time_days,
    _compute_avg_overall_rating,
    _compute_occupancy_rate,
    _compute_room_inventory_count,
    _compute_seasonal_demand,
    _compute_top_zones_by_bookings,
)
from ._kanon import K_THRESHOLD, filter_by_k_anonymity
from ._shared.db import DBExecutor
from .base import register_tool

logger = logging.getLogger(__name__)


Metric = Literal[
    "occupancy_rate",
    "top_zones_by_bookings",
    "avg_booking_duration_months",
    "avg_lead_time_days",
    "seasonal_demand",
    "avg_overall_rating",
    "room_inventory_count",
]

_DISCLAIMER = (
    "Internal aggregate statistics with k-anonymity (k=5) applied. "
    "Buckets representing fewer than 5 underlying records have been "
    "suppressed to protect individual privacy. Sample sizes shown are "
    "post-suppression. Intended for internal ELH operational use; not "
    "for external distribution."
)


# Input model


class GetBookingStatsInput(BaseModel):
    """Inputs for an aggregate-stats query."""

    metric: Metric = Field(
        ...,
        description=(
            "One of the supported aggregate metrics. "
            "occupancy_rate, top_zones_by_bookings, "
            "avg_booking_duration_months, avg_lead_time_days, "
            "seasonal_demand, avg_overall_rating, room_inventory_count."
        ),
    )
    city: Literal["Lisbon", "Porto"] | None = Field(
        default=None,
        description="Restrict to a single city.",
    )
    zone: str | None = Field(
        default=None,
        description="Restrict to a single zone within the city.",
    )
    period_start: date | None = Field(
        default=None,
        description=(
            "Lower bound on the time anchor (blockeddatestart for "
            "reservation metrics, datereview for rating metrics, "
            "not applicable to room_inventory_count). Required for "
            "occupancy_rate; optional elsewhere."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description="Upper bound on the time anchor. Inclusive.",
    )
    top_n: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Result cap for top-N metrics (currently only top_zones_by_bookings).",
    )
    group_by: list[GroupByDim] = Field(
        default_factory=list,
        description=(
            "Optional aggregation dimensions. Valid values: city, zone, "
            "season, year, month. Some metrics have an implicit primary "
            "dimension that's always included (e.g. seasonal_demand "
            "always groups by season). For room_inventory_count, only "
            "city and zone are honoured; time dimensions are ignored."
        ),
    )

    @model_validator(mode="after")
    def _validate_period(self) -> GetBookingStatsInput:
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError(
                f"period_end ({self.period_end}) must be on or after "
                f"period_start ({self.period_start})."
            )
        if self.metric == "occupancy_rate" and (
            self.period_start is None or self.period_end is None
        ):
            raise ValueError(
                "occupancy_rate requires both period_start and "
                "period_end. The rate is undefined without an "
                "explicit time window."
            )
        return self


# Output model


class GetBookingStatsOutput(BaseModel):
    """Aggregate-stats payload with k-anonymity applied."""

    metric: str
    data_points: list[StatPoint] = Field(
        default_factory=list,
        description=(
            "One entry per surviving group bucket. Empty if every "
            "computed bucket was below the k-anonymity threshold."
        ),
    )
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        ...,
        description="GDPR/k-anonymity disclaimer; always present.",
    )
    summary: str
    total_underlying_rows: int = Field(
        default=0,
        description=(
            "Sum of sample_size across ALL buckets (before suppression). "
            "Informative: lets the caller see how much raw data backed "
            "the query."
        ),
    )
    suppressed_buckets: int = Field(
        default=0,
        description=(
            "Number of buckets dropped by the k-anonymity filter. If "
            "this is high relative to len(data_points), the requested "
            "group_by granularity may be too fine for the available "
            "data."
        ),
    )


# Dispatch


def _dispatch(payload: GetBookingStatsInput, ctx: DBExecutor) -> list[StatPoint]:
    """Route to the right ``_compute_*`` helper based on ``payload.metric``."""
    if payload.metric == "occupancy_rate":
        assert payload.period_start is not None
        assert payload.period_end is not None
        return _compute_occupancy_rate(
            ctx,
            city=payload.city,
            zone=payload.zone,
            period_start=payload.period_start,
            period_end=payload.period_end,
            group_by=list(payload.group_by),
        )
    if payload.metric == "top_zones_by_bookings":
        return _compute_top_zones_by_bookings(
            ctx,
            city=payload.city,
            period_start=payload.period_start,
            period_end=payload.period_end,
            top_n=payload.top_n,
        )
    if payload.metric == "avg_booking_duration_months":
        return _compute_avg_booking_duration_months(
            ctx,
            city=payload.city,
            zone=payload.zone,
            period_start=payload.period_start,
            period_end=payload.period_end,
            group_by=list(payload.group_by),
        )
    if payload.metric == "avg_lead_time_days":
        return _compute_avg_lead_time_days(
            ctx,
            city=payload.city,
            zone=payload.zone,
            period_start=payload.period_start,
            period_end=payload.period_end,
            group_by=list(payload.group_by),
        )
    if payload.metric == "seasonal_demand":
        return _compute_seasonal_demand(
            ctx,
            city=payload.city,
            period_start=payload.period_start,
            period_end=payload.period_end,
            group_by=list(payload.group_by),
        )
    if payload.metric == "avg_overall_rating":
        return _compute_avg_overall_rating(
            ctx,
            city=payload.city,
            zone=payload.zone,
            period_start=payload.period_start,
            period_end=payload.period_end,
            group_by=list(payload.group_by),
        )
    if payload.metric == "room_inventory_count":
        return _compute_room_inventory_count(
            ctx,
            city=payload.city,
            zone=payload.zone,
            group_by=list(payload.group_by),
        )
    raise ValueError(f"Unsupported metric: {payload.metric!r}")


# Summary composition


def _compose_summary(
    payload: GetBookingStatsInput,
    points: list[StatPoint],
    suppressed: int,
) -> str:
    """One-line LLM-quotable summary."""
    if not points:
        if suppressed > 0:
            return (
                f"{payload.metric}: no data points survived k-anonymity "
                f"filter ({suppressed} buckets suppressed); insufficient "
                "data for privacy-safe aggregation."
            )
        return f"{payload.metric}: no data matched the query filters."

    n = len(points)
    if n == 1:
        p = points[0]
        label_str = ", ".join(f"{k}={v}" for k, v in p.label.items()) if p.label else "overall"
        return (
            f"{payload.metric} for {label_str}: {p.value} "
            f"(based on {p.sample_size} record{'s' if p.sample_size != 1 else ''})."
        )

    bits = f"{payload.metric}: {n} bucket{'s' if n != 1 else ''}"
    if suppressed > 0:
        bits += f" ({suppressed} suppressed for k-anonymity)"
    return bits + "."


# Registered tool


@register_tool(
    name="get_booking_stats",
    description=(
        "Aggregate statistics endpoint for INTERNAL ELH OPERATIONAL "
        "USE ONLY (team analytics: occupancy, demand patterns, average "
        "ratings, inventory). Not a student-facing tool. GDPR-locked: "
        "returns only aggregates (count, average, distribution) with "
        "k-anonymity (k=5) applied — buckets representing fewer than 5 "
        "underlying records are suppressed. Every output carries a "
        "mandatory disclaimer. "
        "\n\nSupported metrics: occupancy_rate (% of rooms booked, "
        "requires period_start and period_end), top_zones_by_bookings "
        "(top-N zones by booking volume, optional period), "
        "avg_booking_duration_months (mean stay length), avg_lead_time_days "
        "(mean days between booking creation and check-in), "
        "seasonal_demand (booking count grouped by season), "
        "avg_overall_rating (mean review score, joins review table), "
        "room_inventory_count (count of active rooms). "
        "\n\nGrouping: optional group_by dimensions (city, zone, season, "
        "year, month). Some metrics always include an implicit primary "
        "dimension (e.g. seasonal_demand by season). Room inventory "
        "ignores time dimensions. "
        "\n\nUse this tool for queries like 'how busy is Lisbon', "
        "'most popular zones in Porto', 'when do students book', "
        "'how many rooms do we have in Alfama'. Do NOT use it for "
        "individual booking listings, user data, or anything row-level — "
        "those are out of scope by design."
    ),
    input_model=GetBookingStatsInput,
)
def get_booking_stats(
    payload: GetBookingStatsInput,
    ctx: DBExecutor | None,
) -> GetBookingStatsOutput:
    """Compute one aggregate statistic with k-anonymity guarantees."""
    if ctx is None:
        raise RuntimeError(
            "get_booking_stats requires a DBExecutor in ctx. "
            "Bootstrap the orchestrator with a configured executor."
        )

    raw_points = _dispatch(payload, ctx)
    total_underlying = sum(p.sample_size for p in raw_points)

    kept, suppressed = filter_by_k_anonymity(raw_points)

    warnings: list[str] = []
    if not kept:
        if raw_points:
            warnings.append(
                f"insufficient data for privacy-safe aggregation: "
                f"all {len(raw_points)} bucket(s) below k={K_THRESHOLD}"
            )
        else:
            warnings.append(
                "no data matched the query filters (empty result before k-anonymity filter)"
            )
    elif suppressed > 0:
        warnings.append(
            f"{suppressed} bucket(s) suppressed by k-anonymity filter (k={K_THRESHOLD})"
        )

    summary = _compose_summary(payload, kept, suppressed)

    return GetBookingStatsOutput(
        metric=payload.metric,
        data_points=kept,
        warnings=warnings,
        disclaimer=_DISCLAIMER,
        summary=summary,
        total_underlying_rows=total_underlying,
        suppressed_buckets=suppressed,
    )
