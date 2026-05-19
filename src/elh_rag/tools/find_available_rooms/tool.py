"""Tool 2: ``find_available_rooms``."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from .._shared.db import DBExecutor
from .._shared.pricing import MonthlyPriceBreakdown, compute_room_monthly_price
from .._shared.room_id import decode_room_id, normalize_id
from ..base import register_tool
from ..find_rooms import FindRoomsInput, FindRoomsOutput, RoomMatch, find_rooms
from ._reservation import _find_occupied_room_ids

# Input model

_MAX_PERIOD_YEARS = 3
_MAX_PERIOD_DAYS = _MAX_PERIOD_YEARS * 366


class FindAvailableRoomsInput(FindRoomsInput):
    """Search rooms with availability over a hard date window."""

    available_from: date = Field(
        ...,
        description="First day of the requested stay (inclusive). Required.",
    )
    available_to: date = Field(
        ...,
        description="Last day of the requested stay (inclusive). "
        "Must be strictly after available_from.",
    )

    @model_validator(mode="after")
    def check_period_bounds(self) -> FindAvailableRoomsInput:
        delta = (self.available_to - self.available_from).days
        if delta > _MAX_PERIOD_DAYS:
            raise ValueError(
                f"Requested period is too long ({delta} days, max {_MAX_PERIOD_DAYS}). "
                "Erasmus contracts rarely exceed 12 months; if a longer stay is genuinely "
                "needed, split the request."
            )
        return self


_PRICES_SQL_TEMPLATE = """\
SELECT DISTINCT ON (loc_idhouse, idroom)
       loc_idhouse, idroom,
       springprice, summerprice, autumnprice, fixedprice
FROM room
WHERE {where_clause}
ORDER BY loc_idhouse, idroom, dateupdate DESC
"""


def _fetch_seasonal_prices(
    db: DBExecutor,
    keys: list[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Fetch raw seasonal price columns for the given (loc_idhouse, idroom) pairs."""
    if not keys:
        return {}

    or_clauses = ["(loc_idhouse = %s AND idroom = %s)"] * len(keys)
    where_clause = " OR ".join(or_clauses)
    sql = _PRICES_SQL_TEMPLATE.format(where_clause=where_clause)

    params: list[Any] = []
    for loc_idhouse, idroom in keys:
        params.append(loc_idhouse)
        params.append(idroom)

    rows = db.execute(sql, tuple(params))

    return {
        (
            normalize_id(row["loc_idhouse"], name="loc_idhouse"),
            normalize_id(row["idroom"], name="idroom"),
        ): {
            "springprice": row["springprice"],
            "summerprice": row["summerprice"],
            "autumnprice": row["autumnprice"],
            "fixedprice": row["fixedprice"],
        }
        for row in rows
    }


# Helpers


def _room_match_keys(rm: RoomMatch) -> tuple[str, str]:
    """Extract the raw ``(loc_idhouse, idroom)`` pair from a RoomMatch."""
    parts = decode_room_id(rm.room_id)
    return (parts.house_id, parts.room_id)


def _format_price_label(
    monthly_eur: Decimal,
    breakdown: MonthlyPriceBreakdown,
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
) -> str:
    """Build a context-rich price label the LLM can quote verbatim."""
    if breakdown.is_fixed_price:
        return f"€{monthly_eur}/month (fixed rate, no seasonal variation)"

    season_parts: list[str] = []
    if breakdown.autumn_months > 0:
        season_parts.append(
            f"{breakdown.autumn_months} "
            f"month{'s' if breakdown.autumn_months != 1 else ''} "
            f"at autumn rate €{autumn_eur}"
        )
    if breakdown.spring_months > 0:
        season_parts.append(
            f"{breakdown.spring_months} "
            f"month{'s' if breakdown.spring_months != 1 else ''} "
            f"at spring rate €{spring_eur}"
        )
    if breakdown.summer_months > 0:
        season_parts.append(
            f"{breakdown.summer_months} "
            f"month{'s' if breakdown.summer_months != 1 else ''} "
            f"at summer rate €{summer_eur}"
        )

    total = breakdown.total_months

    # Same-season case: single label, no breakdown needed
    if len(season_parts) == 1:
        if breakdown.autumn_months > 0:
            season = "autumn"
        elif breakdown.spring_months > 0:
            season = "spring"
        else:
            season = "summer"
        return f"€{monthly_eur}/month for your {total}-month stay (all {season} rate)"

    # Cross-season case: average + composition
    return f"€{monthly_eur}/month average over {total} months: " + ", ".join(season_parts)


def _enrich_with_seasonal_price(
    rm: RoomMatch,
    raw_prices: dict[str, Any],
    period_start: date,
    period_end: date,
) -> RoomMatch:
    """Return a copy of ``rm`` with average monthly price + contextual label."""
    spring_eur = Decimal(str(raw_prices["springprice"]))
    summer_eur = Decimal(str(raw_prices["summerprice"]))
    autumn_eur = Decimal(str(raw_prices["autumnprice"]))
    is_fixed = raw_prices["fixedprice"] == "Y"

    breakdown = compute_room_monthly_price(
        spring_eur=spring_eur,
        summer_eur=summer_eur,
        autumn_eur=autumn_eur,
        is_fixed=is_fixed,
        period_start=period_start,
        period_end=period_end,
    )

    label = _format_price_label(
        monthly_eur=breakdown.monthly_eur,
        breakdown=breakdown,
        spring_eur=spring_eur,
        summer_eur=summer_eur,
        autumn_eur=autumn_eur,
    )

    return replace(
        rm,
        price_per_month_eur=float(breakdown.monthly_eur),
        price_label=label,
        is_fixed_price=breakdown.is_fixed_price,
        available_from=period_start,
    )


# Registered tool function


@register_tool(
    name="find_available_rooms",
    description=(
        "Search ELH rooms genuinely free over a specific date window. "
        "Same 30 structural parameters as find_rooms (location, price, "
        "amenities, occupancy, ...) but with available_from and "
        "available_to as REQUIRED hard constraints. "
        "Excludes rooms with overlapping reservations and computes a "
        "season-aware monthly price for the stay: every calendar month "
        "touched is rated at its seasonal tariff (autumn Sep-Feb, "
        "spring Mar-Jun, summer Jul-Aug), and price_per_month_eur is "
        "the average across those months. The price_label field carries "
        "a human-readable explanation of the calculation that you "
        "should quote verbatim to the user, so the user always sees "
        "the basis of the number (e.g. 'X/month average over 8 months: "
        "6 months at autumn rate Y, 2 months at spring rate Z'). "
        "Rooms with fixedprice='Y' return a flat price and is_fixed_price=True. "
        "Use this tool for queries like 'rooms free from Aug 20 till Dec 31' "
        "or '3 bedrooms available next semester'. For queries without "
        "explicit date ranges, use find_rooms instead."
    ),
    input_model=FindAvailableRoomsInput,
    ctx_attr="db",
)
def find_available_rooms(
    payload: FindAvailableRoomsInput,
    ctx: DBExecutor | None,
) -> FindRoomsOutput:
    """Execute a date-constrained room search."""
    if ctx is None:
        raise RuntimeError(
            "find_available_rooms requires a DBExecutor in ctx. "
            "Bootstrap the orchestrator with a configured executor."
        )

    # Re-use Tool 1's structural filtering.
    structural = find_rooms(payload, ctx=ctx)
    if not structural.rooms:
        return _empty_output(payload, structural.query_summary, total_matches=0)

    # Find rooms with reservation overlap on the requested window.
    occupied = _find_occupied_room_ids(
        ctx,
        period_start=payload.available_from,
        period_end=payload.available_to,
    )

    available = [rm for rm in structural.rooms if _room_match_keys(rm) not in occupied]
    if not available:
        return _empty_output(
            payload,
            structural.query_summary,
            total_matches=structural.total_matches,
        )

    # Fetch raw seasonal prices for the survivors and recompute the
    # monthly price + contextual label.
    keys = [_room_match_keys(rm) for rm in available]
    raw_by_key = _fetch_seasonal_prices(ctx, keys)

    enriched: list[RoomMatch] = []
    for rm in available:
        raw = raw_by_key.get(_room_match_keys(rm))
        if raw is None:
            # Room disappeared between the two queries (race) or the
            # price row was unfetchable. Skip rather than guess.
            continue
        enriched.append(
            _enrich_with_seasonal_price(
                rm,
                raw,
                period_start=payload.available_from,
                period_end=payload.available_to,
            )
        )

    return FindRoomsOutput(
        rooms=enriched,
        total_matches=structural.total_matches,
        query_summary=_compose_summary(payload, structural.query_summary),
    )


# Output helpers


def _empty_output(
    payload: FindAvailableRoomsInput,
    base_summary: str,
    *,
    total_matches: int,
) -> FindRoomsOutput:
    """Return an empty FindRoomsOutput with a contextualised summary."""
    return FindRoomsOutput(
        rooms=[],
        total_matches=total_matches,
        query_summary=_compose_summary(payload, base_summary),
    )


def _compose_summary(payload: FindAvailableRoomsInput, base_summary: str) -> str:
    """Append the date-window suffix to Tool 1's summary."""
    return f"{base_summary} | available {payload.available_from} → {payload.available_to}"
