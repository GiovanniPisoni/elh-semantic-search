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

import logging
from datetime import date
from typing import Any

from .._shared.db import DBExecutor
from ._models import StatPoint
from ._sql_builders import (
    _LATEST_ACTIVE_ROOM_CTE,
    _build_label,
    _city_filter_clause,
    _group_by_select_clauses,
    _zone_filter_clause,
)

logger = logging.getLogger(__name__)


# Metric 1 — occupancy_rate


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
    select_dims = _group_by_select_clauses(group_by, date_col="r.blockeddatestart")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_aliases)))

    where_num: list[str] = [
        "r.blockeddatestart <= %s",
        "r.blockeddataend >= %s",
    ]
    params_num: list[Any] = [period_end, period_start]
    _city_filter_clause(where_num, params_num, city)
    _zone_filter_clause(where_num, params_num, zone)

    sql_num = (
        f"SELECT {select_dim_prefix}"
        "COUNT(DISTINCT (r.loc_idhouse, r.idroom)) AS booked_rooms,\n"
        "    COUNT(*) AS booking_count\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"WHERE {' AND '.join(where_num)}\n"
        f"{group_clause}"
    )

    where_denom: list[str] = ["lr.status = 'Available'"]
    params_denom: list[Any] = []
    _city_filter_clause(where_denom, params_denom, city)
    _zone_filter_clause(where_denom, params_denom, zone)

    sql_denom = (
        _LATEST_ACTIVE_ROOM_CTE + f"SELECT {select_dim_prefix}"
        "COUNT(*) AS active_rooms\n"
        "FROM latest_room lr\n"
        "JOIN house h ON h.idhouse = lr.loc_idhouse "
        "AND h.dateupdate = lr.loc_dateupdate\n"
        f"WHERE {' AND '.join(where_denom)}\n"
        f"{group_clause}"
    )

    num_rows = db.execute(sql_num, tuple(params_num))
    denom_rows = db.execute(sql_denom, tuple(params_denom))

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


# Metric 2 — top_zones_by_bookings


def _compute_top_zones_by_bookings(
    db: DBExecutor,
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    top_n: int,
) -> list[StatPoint]:
    """Top-N zones by booking count, optionally restricted to one city/period."""
    where: list[str] = []
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    if period_start is not None:
        where.append("r.blockeddatestart >= %s")
        params.append(period_start)
    if period_end is not None:
        where.append("r.blockeddatestart <= %s")
        params.append(period_end)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    sql = (
        "SELECT h.zone AS zone, COUNT(*) AS value, COUNT(*) AS sample_size\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"{where_sql}\n"
        "GROUP BY 1\n"
        "ORDER BY value DESC, zone ASC\n"
        "LIMIT %s"
    )
    params.append(top_n)

    rows = db.execute(sql, tuple(params))
    return [
        StatPoint(
            label={"zone": str(r["zone"]).strip()},
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 3 — avg_booking_duration_months


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


# Metric 4 — avg_lead_time_days


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
    select_dims = _group_by_select_clauses(group_by, date_col="r.blockeddatestart")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    where: list[str] = []
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    _zone_filter_clause(where, params, zone)
    if period_start is not None:
        where.append("r.blockeddatestart >= %s")
        params.append(period_start)
    if period_end is not None:
        where.append("r.blockeddatestart <= %s")
        params.append(period_end)
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_aliases)))

    sql = (
        f"SELECT {select_dim_prefix}"
        f"{value_expr} AS value, COUNT(*) AS sample_size\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )

    rows = db.execute(sql, tuple(params))
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=round(float(r["value"] or 0.0), round_decimals),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 5 — seasonal_demand


def _compute_seasonal_demand(
    db: DBExecutor,
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Booking count by season (implicit primary dim) plus any extra group_by."""
    effective_group_by = ["season"] + [d for d in group_by if d != "season"]

    select_dims = _group_by_select_clauses(effective_group_by, date_col="r.blockeddatestart")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    where: list[str] = []
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    if period_start is not None:
        where.append("r.blockeddatestart >= %s")
        params.append(period_start)
    if period_end is not None:
        where.append("r.blockeddatestart <= %s")
        params.append(period_end)
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    group_clause = "GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_aliases)))

    sql = (
        f"SELECT {', '.join(select_dim_sql)}, "
        "COUNT(*) AS value, COUNT(*) AS sample_size\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}\n"
        "ORDER BY 1"
    )

    rows = db.execute(sql, tuple(params))
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 6 — avg_overall_rating


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
    select_dims = _group_by_select_clauses(group_by, date_col="rv.datereview")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    where: list[str] = ["rv.status = 'approved'"]
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    _zone_filter_clause(where, params, zone)
    if period_start is not None:
        where.append("rv.datereview >= %s")
        params.append(period_start)
    if period_end is not None:
        where.append("rv.datereview <= %s")
        params.append(period_end)
    where_sql = "WHERE " + " AND ".join(where)

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_aliases)))

    sql = (
        f"SELECT {select_dim_prefix}"
        "AVG(rv.overallratings) AS value, COUNT(*) AS sample_size\n"
        "FROM review rv\n"
        "JOIN house h ON h.idhouse = rv.loc_idhouse "
        "AND h.dateupdate = rv.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )

    rows = db.execute(sql, tuple(params))
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=round(float(r["value"] or 0.0), 2),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]


# Metric 7 — room_inventory_count


def _compute_room_inventory_count(
    db: DBExecutor,
    *,
    city: str | None,
    zone: str | None,
    group_by: list[str],
) -> list[StatPoint]:
    """Count of active rooms, optionally grouped by city/zone."""
    effective_group_by = [d for d in group_by if d in ("city", "zone")]
    dropped = [d for d in group_by if d not in ("city", "zone")]
    if dropped:
        logger.warning(
            "room_inventory_count: ignored non-applicable group_by dimensions %s",
            dropped,
        )

    select_dims = _group_by_select_clauses(effective_group_by, date_col="NULL")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    where: list[str] = ["lr.status = 'Available'"]
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    _zone_filter_clause(where, params, zone)
    where_sql = "WHERE " + " AND ".join(where)

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_aliases)))

    sql = (
        _LATEST_ACTIVE_ROOM_CTE + f"SELECT {select_dim_prefix}"
        "COUNT(*) AS value, COUNT(*) AS sample_size\n"
        "FROM latest_room lr\n"
        "JOIN house h ON h.idhouse = lr.loc_idhouse "
        "AND h.dateupdate = lr.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )

    rows = db.execute(sql, tuple(params))
    return [
        StatPoint(
            label=_build_label(r, dim_aliases),
            value=float(r["value"]),
            sample_size=int(r["sample_size"]),
        )
        for r in rows
    ]
