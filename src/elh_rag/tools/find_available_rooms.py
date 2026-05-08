"""Tool 2: ``find_available_rooms``.

Specialisation of :func:`find_rooms` with **dates as a hard constraint**.

The base tool (Tool 1) treats ``available_from`` / ``available_to`` as
soft hints: if absent it falls back to autumn pricing and ignores
reservation overlap. Tool 2 promotes both fields to required and adds
two pieces of logic on top of Tool 1's structural filtering:

    1. **Reservation overlap exclusion** — rooms whose
       ``[blockeddatestart, blockeddataend]`` interval overlaps the
       requested window are removed from the result. Implemented in
       :mod:`elh_rag.tools._reservation`.

    2. **Season-aware weighted pricing** — instead of a single seasonal
       column, the monthly price is computed by
       :func:`elh_rag.tools._pricing.compute_room_monthly_price`.
       Rooms with ``fixedprice = 'Y'`` keep their flat price and are
       flagged via ``RoomMatch.is_fixed_price``.

DB roundtrips: this tool issues **up to 3 queries** in sequence:

    1. Tool 1's structural filter   (always, unless 0 rows)
    2. Reservation overlap          (skipped if step 1 returned 0)
    3. Seasonal price lookup        (skipped if step 2 emptied result)

The Pydantic input model is intentionally a subclass of
:class:`FindRoomsInput`, so the same payload can be forwarded straight
to Tool 1's raw function (skipping its registry dispatcher to avoid
double-validation).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from ._db import DBExecutor
from ._pricing import compute_room_monthly_price
from ._reservation import _find_occupied_room_ids
from ._room_id import decode_room_id, normalize_id
from .base import register_tool
from .find_rooms import FindRoomsInput, FindRoomsOutput, RoomMatch, find_rooms

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


def _enrich_with_seasonal_price(
    rm: RoomMatch,
    raw_prices: dict[str, Any],
    period_start: date,
    period_end: date,
) -> RoomMatch:
    """Return a copy of ``rm`` with weighted/fixed monthly price applied."""
    breakdown = compute_room_monthly_price(
        spring_eur=Decimal(str(raw_prices["springprice"])),
        summer_eur=Decimal(str(raw_prices["summerprice"])),
        autumn_eur=Decimal(str(raw_prices["autumnprice"])),
        is_fixed=(raw_prices["fixedprice"] == "Y"),
        period_start=period_start,
        period_end=period_end,
    )
    return replace(
        rm,
        price_per_month_eur=float(breakdown.monthly_eur),
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
        "season-aware weighted monthly price over the requested period "
        "(rooms with fixedprice='Y' return a flat price flagged via "
        "is_fixed_price). "
        "Use this tool for queries like 'rooms free from Aug 20 till Dec 31' "
        "or '3 bedrooms available next semester'. For queries without "
        "explicit date ranges, use find_rooms instead."
    ),
    input_model=FindAvailableRoomsInput,
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
        return _empty_output(payload, structural.query_summary)

    # Find rooms with reservation overlap on the requested window.
    occupied = _find_occupied_room_ids(
        ctx,
        period_start=payload.available_from,
        period_end=payload.available_to,
    )

    available = [rm for rm in structural.rooms if _room_match_keys(rm) not in occupied]
    if not available:
        return _empty_output(payload, structural.query_summary)

    # Fetch raw seasonal prices for the survivors and recompute the
    # monthly price.
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
        total_matches=len(enriched),
        query_summary=_compose_summary(payload, structural.query_summary),
    )


# Output helpers


def _empty_output(payload: FindAvailableRoomsInput, base_summary: str) -> FindRoomsOutput:
    """Return an empty FindRoomsOutput with a contextualised summary."""
    return FindRoomsOutput(
        rooms=[],
        total_matches=0,
        query_summary=_compose_summary(payload, base_summary),
    )


def _compose_summary(payload: FindAvailableRoomsInput, base_summary: str) -> str:
    """Append the date-window suffix to Tool 1's summary."""
    return f"{base_summary} | available {payload.available_from} → {payload.available_to}"
