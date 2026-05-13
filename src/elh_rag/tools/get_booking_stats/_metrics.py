"""The seven aggregate-stats compute functions.

The seven metrics:

    1. ``_compute_occupancy_rate``           — booked_rooms / active_rooms
    2. ``_compute_top_zones_by_bookings``    — top-N zones by booking count
    3. ``_compute_avg_booking_duration_months`` — mean stay length
    4. ``_compute_avg_lead_time_days``       — mean booking-to-check-in days
    5. ``_compute_seasonal_demand``          — booking count by season
    6. ``_compute_avg_overall_rating``       — mean review.overallratings
    7. ``_compute_room_inventory_count``     — active room count
"""

from __future__ import annotations

from datetime import date

from .._shared.db import DBExecutor
from ._models import StatPoint
from ._sql_builders import (
    _build_avg_overall_rating_sql,
    _build_avg_reservation_sql,
    _build_label,
    _build_occupancy_denominator_sql,
    _build_occupancy_numerator_sql,
    _build_room_inventory_sql,
    _build_seasonal_demand_sql,
    _build_top_zones_sql,
)

# Metric 1: occupancy_rate


def _compute_occupancy_rate(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    period_start: date,
    period_end: date,
    group_by: list[str],
) -> list[StatPoint]:
    """% of rooms that had at least one booking overlapping the period."""
    sql_num, params_num, dim_aliases = _build_occupancy_numerator_sql(
        city=city,
        zone=zone,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
    )
    sql_denom, params_denom, _ = _build_occupancy_denominator_sql(
        city=city,
        zone=zone,
        group_by=group_by,
    )

    num_rows = db.execute(sql_num, params_num)
    denom_rows = db.execute(sql_denom, params_denom)

    denom_by_key: dict[tuple[str, ...], int] = {}
    for row in denom_rows:
        key = tuple(_build_label(row, dim_aliases).values())
        denom_by_key[key] = int(row["active_rooms"])

    points: list[StatPoint] = []
    for row in num_rows:
        label = _build_label(row, dim_aliases)
        key = tuple(label.values())
        active = denom_by_key.get(key, 0)
        if active == 0:
            continue
        booked = int(row["booked_rooms"])
        booking_count = int(row["booking_count"])
        points.append(
            StatPoint(
                label=label,
                value=round(booked / active, 4),
                sample_size=booking_count,
            )
        )
    return points


# Metric 2: top_zones_by_bookings


def _compute_top_zones_by_bookings(
    db: DBExecutor,
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    top_n: int,
) -> list[StatPoint]:
    """Top-N zones by booking count, optionally restricted to one city/period."""
    sql, params = _build_top_zones_sql(
        city=city,
        period_start=period_start,
        period_end=period_end,
        top_n=top_n,
    )
    rows = db.execute(sql, params)
    return [
        StatPoint(
            label={"zone": str(r["zone"]).strip()},
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 3: avg_booking_duration_months


def _compute_avg_booking_duration_months(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Average stay length in months (blockeddataend - blockeddatestart)/30.44."""
    return _avg_reservation_metric(
        db,
        value_expr=("AVG((r.blockeddataend - r.blockeddatestart)::numeric / 30.44)"),
        city=city,
        zone=zone,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
        round_decimals=2,
    )


# Metric 4: avg_lead_time_days


def _compute_avg_lead_time_days(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Average days between datereservation and blockeddatestart (check-in)."""
    return _avg_reservation_metric(
        db,
        value_expr="AVG((r.blockeddatestart - r.datereservation)::numeric)",
        city=city,
        zone=zone,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
        round_decimals=1,
    )


# Shared helper for AVG-style reservation metrics


def _avg_reservation_metric(
    db: DBExecutor,
    *,
    value_expr: str,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
    round_decimals: int,
) -> list[StatPoint]:
    """Shared body for AVG-style reservation metrics."""
    sql, params, dim_aliases = _build_avg_reservation_sql(
        value_expr=value_expr,
        city=city,
        zone=zone,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
    )
    rows = db.execute(sql, params)
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=round(float(r["value"] or 0.0), round_decimals),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 5: seasonal_demand


def _compute_seasonal_demand(
    db: DBExecutor,
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Booking count by season (implicit primary dim) plus any extra group_by."""
    sql, params, dim_aliases = _build_seasonal_demand_sql(
        city=city,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
    )
    rows = db.execute(sql, params)
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 6: avg_overall_rating


def _compute_avg_overall_rating(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Average review.overallratings across approved reviews."""
    sql, params, dim_aliases = _build_avg_overall_rating_sql(
        city=city,
        zone=zone,
        period_start=period_start,
        period_end=period_end,
        group_by=group_by,
    )
    rows = db.execute(sql, params)
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=round(float(r["value"] or 0.0), 2),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 7: room_inventory_count


def _compute_room_inventory_count(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Count of active rooms, optionally grouped by city/zone."""
    sql, params, dim_aliases = _build_room_inventory_sql(
        city=city,
        zone=zone,
        group_by=group_by,
    )
    rows = db.execute(sql, params)
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]
