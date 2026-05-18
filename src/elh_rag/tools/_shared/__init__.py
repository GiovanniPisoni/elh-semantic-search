"""Cross-tool helpers used by multiple tools.

Re-exports the common public API. Submodules remain importable
directly (e.g. ``from elh_rag.tools._shared.metro_lines import
LISBON_ZONE_TO_LINES``) for tests that need internals.
"""

from .db import DBExecutor, Psycopg2Executor
from .metro_lines import (
    ALL_METRO_LINE_INPUTS,
    ALL_METRO_LINES,
    PORTO_LETTER_TO_COLOUR,
    is_served_by_metro,
    lines_for_zone,
    normalize_line,
    zones_on_line,
)
from .pricing import (
    AUTUMN_MONTHS,
    SPRING_MONTHS,
    SUMMER_MONTHS,
    MonthlyPriceBreakdown,
    MonthRent,
    Season,
    StayCostBreakdown,
    compute_room_monthly_price,
    compute_stay_breakdown,
    iter_calendar_months,
    season_for_month,
)
from .room_id import (
    HouseIdParts,
    InvalidRoomIdError,
    RoomIdParts,
    decode_house_id,
    decode_room_id,
    encode_house_id,
    encode_room_id,
    is_house_id,
    is_room_id,
    normalize_id,
)

__all__ = [
    "ALL_METRO_LINES",
    "ALL_METRO_LINE_INPUTS",
    "AUTUMN_MONTHS",
    "PORTO_LETTER_TO_COLOUR",
    "SPRING_MONTHS",
    "SUMMER_MONTHS",
    "DBExecutor",
    "HouseIdParts",
    "InvalidRoomIdError",
    "MonthRent",
    "MonthlyPriceBreakdown",
    "Psycopg2Executor",
    "RoomIdParts",
    "Season",
    "StayCostBreakdown",
    "compute_room_monthly_price",
    "compute_stay_breakdown",
    "decode_house_id",
    "decode_room_id",
    "encode_house_id",
    "encode_room_id",
    "is_house_id",
    "is_room_id",
    "is_served_by_metro",
    "iter_calendar_months",
    "lines_for_zone",
    "normalize_id",
    "normalize_line",
    "season_for_month",
    "zones_on_line",
]
