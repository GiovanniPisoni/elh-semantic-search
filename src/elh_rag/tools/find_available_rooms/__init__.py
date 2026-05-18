"""Tool 2: ``find_available_rooms``.

Package layout (mirrors :mod:`elh_rag.tools.find_rooms`):

    * :mod:`._reservation` — reservation-overlap query
    * :mod:`.tool`         — registered entry point, price-enrichment,
                             output composition
"""

from ._reservation import _find_occupied_room_ids
from .tool import (
    _MAX_PERIOD_DAYS,
    FindAvailableRoomsInput,
    _fetch_seasonal_prices,
    _room_match_keys,
    find_available_rooms,
)

__all__ = [
    "_MAX_PERIOD_DAYS",
    "FindAvailableRoomsInput",
    "_fetch_seasonal_prices",
    "_find_occupied_room_ids",
    "_room_match_keys",
    "find_available_rooms",
]
