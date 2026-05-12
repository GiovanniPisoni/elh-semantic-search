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
"""

from __future__ import annotations

from typing import Any, Literal

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

# Used by occupancy_rate (denominator) and room_inventory_count.
# Joins to ``house`` happen in the metric SQL via
# ``JOIN house h ON h.idhouse = lr.loc_idhouse AND h.dateupdate = lr.loc_dateupdate``.
_LATEST_ACTIVE_ROOM_CTE = """\
WITH latest_room AS (
    SELECT DISTINCT ON (loc_idhouse, idroom)
        loc_idhouse, loc_dateupdate, idroom, status
    FROM room
    ORDER BY loc_idhouse, idroom, dateupdate DESC
)
"""
