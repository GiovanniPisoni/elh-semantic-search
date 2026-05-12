"""Registered entry point for ``find_rooms``.

Wires the input model, the SQL builder, and the row mapper to the
shared registry decorator. The actual ``ctx.execute`` happens here.
"""

from __future__ import annotations

from .._shared.db import DBExecutor
from ..base import register_tool
from ._inputs import FindRoomsInput
from ._schemas import FindRoomsOutput
from ._sql_builder import _build_sql, _row_to_match, _summarize_query


@register_tool(
    name="find_rooms",
    description=(
        "Search ELH rooms by structured criteria: location (city, metro line, "
        "landmark, distance to transport), price (min/max), "
        "period (preferences, soft constraints), occupancy (couples, pets, "
        "gender, max house size, multi-room), 11 explicit must-have amenities "
        "(private bathroom, balcony, elevator, A/C, heating, washing machine, "
        "dishwasher, parking, internet, desk, window), and a 26-entry "
        "amenity catalogue covering views (city/sea/countryside), security "
        "(cctv, security_24h, smoke_detector, armored_door, coded_entry), "
        "comfort (central_heating, thermal_insulation, double_glazed_windows, "
        "furnished), kitchen (equipped_kitchen, fridge, stove, microwave), "
        "entertainment (cable_tv, smart_tv), social (shared_space, "
        "night_guests_allowed, non_smoking), accessibility "
        "(wheelchair_accessible), and room-level extras (closet, bedlinen, "
        "pillows, extra_person_allowed). Sort by price asc/desc or default "
        "ranking. Returns up to max_results rooms ranked by match score. "
        "Use this for queries with search criteria but no hard date constraints — "
        "for date-filtered availability use find_available_rooms instead."
    ),
    input_model=FindRoomsInput,
)
def find_rooms(payload: FindRoomsInput, ctx: DBExecutor | None) -> FindRoomsOutput:
    """Execute a find_rooms search against the DB."""
    if ctx is None:
        raise RuntimeError(
            "find_rooms requires a DBExecutor in ctx. "
            "Bootstrap the orchestrator with a configured executor."
        )

    sql, params = _build_sql(payload)
    rows = ctx.execute(sql, tuple(params))

    rooms = [_row_to_match(row, payload) for row in rows]

    return FindRoomsOutput(
        rooms=rooms,
        total_matches=len(rooms),  # Future: separate COUNT(*) for true total
        query_summary=_summarize_query(payload),
    )
