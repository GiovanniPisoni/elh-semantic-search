"""SQL fragment builders for booking-stats metrics.

This module contains pure SQL-construction helpers used by every
metric in :mod:`._metrics`:

    * season / year / month time-dimension expressions
    * dynamic GROUP BY select clauses
    * label builder (DB row -> dict, used by every metric to build
      :class:`StatPoint.label`)
    * city/zone WHERE-clause helpers
    * the latest-active-room CTE used by occupancy_rate and
      room_inventory_count
    * seven full SQL builders, one per metric, each decorated with
      :func:`._safety.pii_safe_sql` to enforce the GDPR boundary at
      runtime
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from ._safety import pii_safe_sql

logger = logging.getLogger(__name__)

GroupByDim = Literal["city", "zone", "season", "year", "month"]


# Time-dimension SQL fragments


def _season_expr(date_col: str) -> str:
    """Map a date column to the ELH season label.

    Must match :data:`elh_rag.tools._shared.pricing.SPRING_MONTHS`
    and friends. Spring = Mar-Jun, Summer = Jul-Aug, Autumn = the
    rest (high Erasmus season).
    """
    return (
        f"CASE "
        f"WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 3 AND 6 THEN 'spring' "
        f"WHEN EXTRACT(MONTH FROM {date_col}) BETWEEN 7 AND 8 THEN 'summer' "
        f"ELSE 'autumn' END"
    )


def _year_expr(date_col: str) -> str:
    return f"EXTRACT(YEAR FROM {date_col})::int"


def _month_expr(date_col: str) -> str:
    return f"TO_CHAR({date_col}, 'YYYY-MM')"


def _group_by_select_clauses(dims: list[str], date_col: str) -> list[tuple[str, str]]:
    """Return ``(sql_expression, alias)`` pairs for each requested dim."""
    out: list[tuple[str, str]] = []
    for dim in dims:
        if dim == "city":
            out.append(("h.city", "city"))
        elif dim == "zone":
            out.append(("h.zone", "zone"))
        elif dim == "season":
            out.append((_season_expr(date_col), "season"))
        elif dim == "year":
            out.append((_year_expr(date_col), "year"))
        elif dim == "month":
            out.append((_month_expr(date_col), "month"))
        else:
            raise ValueError(f"Unsupported group_by dimension: {dim!r}")
    return out


# Row → label helper


def _build_label(row: dict[str, Any], dim_aliases: list[str]) -> dict[str, str]:
    """Extract dimension columns into the stat label, stringified + stripped."""
    label: dict[str, str] = {}
    for alias in dim_aliases:
        v = row.get(alias)
        label[alias] = "" if v is None else str(v).strip()
    return label


# WHERE-clause helpers


def _city_filter_clause(where_parts: list[str], params: list[Any], city: str | None) -> None:
    if city is not None:
        where_parts.append("h.city = %s")
        params.append(city)


def _zone_filter_clause(where_parts: list[str], params: list[Any], zone: str | None) -> None:
    if zone is not None:
        where_parts.append("h.zone = %s")
        params.append(zone)


# Latest active-room CTE

_LATEST_ACTIVE_ROOM_CTE = """\
WITH latest_room AS (
    SELECT DISTINCT ON (loc_idhouse, idroom)
        loc_idhouse, loc_dateupdate, idroom, status
    FROM room
    ORDER BY loc_idhouse, idroom, dateupdate DESC
)
"""


# Full SQL builders, one per metric.


# Metric 1: occupancy_rate (numerator)


@pii_safe_sql
def _build_occupancy_numerator_sql(
    *,
    city: str | None,
    zone: str | None,
    period_start: date,
    period_end: date,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build the numerator SQL for occupancy_rate.

    Counts distinct rooms with at least one booking overlapping the
    period, optionally grouped by dimensions.
    """
    select_dims = _group_by_select_clauses(group_by, date_col="r.blockeddatestart")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(
            str(i + 1) for i in range(len(dim_aliases))
        )

    where: list[str] = [
        "r.blockeddatestart <= %s",
        "r.blockeddataend >= %s",
    ]
    params: list[Any] = [period_end, period_start]
    _city_filter_clause(where, params, city)
    _zone_filter_clause(where, params, zone)

    sql = (
        f"SELECT {select_dim_prefix}"
        "COUNT(DISTINCT (r.loc_idhouse, r.idroom)) AS booked_rooms,\n"
        "    COUNT(*) AS booking_count\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"WHERE {' AND '.join(where)}\n"
        f"{group_clause}"
    )
    return sql, tuple(params), dim_aliases


# Metric 1: occupancy_rate (denominator)


@pii_safe_sql
def _build_occupancy_denominator_sql(
    *,
    city: str | None,
    zone: str | None,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build the denominator SQL for occupancy_rate.

    Counts active rooms in the inventory, optionally grouped by
    dimensions.
    """
    select_dims = _group_by_select_clauses(group_by, date_col="r.blockeddatestart")
    select_dim_sql = [expr + " AS " + alias for expr, alias in select_dims]
    dim_aliases = [alias for _, alias in select_dims]

    select_dim_prefix = ", ".join(select_dim_sql) + ", " if select_dim_sql else ""
    group_clause = ""
    if dim_aliases:
        group_clause = "GROUP BY " + ", ".join(
            str(i + 1) for i in range(len(dim_aliases))
        )

    where: list[str] = ["lr.status = 'Available'"]
    params: list[Any] = []
    _city_filter_clause(where, params, city)
    _zone_filter_clause(where, params, zone)

    sql = (
        _LATEST_ACTIVE_ROOM_CTE + f"SELECT {select_dim_prefix}"
        "COUNT(*) AS active_rooms\n"
        "FROM latest_room lr\n"
        "JOIN house h ON h.idhouse = lr.loc_idhouse "
        "AND h.dateupdate = lr.loc_dateupdate\n"
        f"WHERE {' AND '.join(where)}\n"
        f"{group_clause}"
    )
    return sql, tuple(params), dim_aliases


# Metric 2: top_zones_by_bookings


@pii_safe_sql
def _build_top_zones_sql(
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    top_n: int,
) -> tuple[str, tuple]:
    """Build SQL for top_zones_by_bookings.

    Top-N zones by booking count, optionally restricted to a city or
    period.
    """
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
    return sql, tuple(params)


# Metric 3 & 4: shared AVG-style reservation metric


@pii_safe_sql
def _build_avg_reservation_sql(
    *,
    value_expr: str,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build SQL for AVG-style reservation metrics (duration, lead time, …).

    The ``value_expr`` parameter is the SQL expression to average.
    """
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
        group_clause = "GROUP BY " + ", ".join(
            str(i + 1) for i in range(len(dim_aliases))
        )

    sql = (
        f"SELECT {select_dim_prefix}"
        f"{value_expr} AS value, COUNT(*) AS sample_size\n"
        "FROM reservation r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )
    return sql, tuple(params), dim_aliases


# Metric 5: seasonal_demand


@pii_safe_sql
def _build_seasonal_demand_sql(
    *,
    city: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build SQL for seasonal_demand.

    Always groups by ``season`` as the primary dimension, plus any
    additional dimensions in ``group_by``.
    """
    effective_group_by = ["season"] + [d for d in group_by if d != "season"]

    select_dims = _group_by_select_clauses(
        effective_group_by, date_col="r.blockeddatestart"
    )
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

    group_clause = "GROUP BY " + ", ".join(
        str(i + 1) for i in range(len(dim_aliases))
    )

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
    return sql, tuple(params), dim_aliases


# Metric 6: avg_overall_rating


@pii_safe_sql
def _build_avg_overall_rating_sql(
    *,
    city: str | None,
    zone: str | None,
    period_start: date | None,
    period_end: date | None,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build SQL for avg_overall_rating across approved reviews."""
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
        group_clause = "GROUP BY " + ", ".join(
            str(i + 1) for i in range(len(dim_aliases))
        )

    sql = (
        f"SELECT {select_dim_prefix}"
        "AVG(rv.overallratings) AS value, COUNT(*) AS sample_size\n"
        "FROM review rv\n"
        "JOIN house h ON h.idhouse = rv.loc_idhouse "
        "AND h.dateupdate = rv.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )
    return sql, tuple(params), dim_aliases


# Metric 7: room_inventory_count


@pii_safe_sql
def _build_room_inventory_sql(
    *,
    city: str | None,
    zone: str | None,
    group_by: list[str],
) -> tuple[str, tuple, list[str]]:
    """Build SQL for room_inventory_count.

    Filters ``group_by`` to ``city`` and ``zone`` only — other dimensions
    do not apply to a static inventory count. Logs a warning for any
    dropped dimensions.
    """
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
        group_clause = "GROUP BY " + ", ".join(
            str(i + 1) for i in range(len(dim_aliases))
        )

    sql = (
        _LATEST_ACTIVE_ROOM_CTE + f"SELECT {select_dim_prefix}"
        "COUNT(*) AS value, COUNT(*) AS sample_size\n"
        "FROM latest_room lr\n"
        "JOIN house h ON h.idhouse = lr.loc_idhouse "
        "AND h.dateupdate = lr.loc_dateupdate\n"
        f"{where_sql}\n"
        f"{group_clause}"
    )
    return sql, tuple(params), dim_aliases
