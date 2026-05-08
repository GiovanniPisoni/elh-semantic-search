"""Tool 1: ``find_rooms``.

Search ELH rooms by structured criteria. The most ambitious of the six
tools: 30 parameters covering location, price, period, occupancy,
amenities, and ranking.

This package's contents:

* :mod:`._inputs` — :class:`FindRoomsInput` (Pydantic model)
* :mod:`._schemas` — :class:`RoomMatch`, :class:`FindRoomsOutput`
* :mod:`._amenity_columns` — name → column maps
* :mod:`._sql_builder` — pure SQL construction + row mapping
* :mod:`.tool` — registered entry point
"""

from __future__ import annotations

from ._inputs import FindRoomsInput, MetroLineInput, OtherAmenity
from ._schemas import FindRoomsOutput, RoomMatch
from ._sql_builder import _build_sql, _select_price_column
from .tool import find_rooms

__all__ = [
    "FindRoomsInput",
    "FindRoomsOutput",
    "MetroLineInput",
    "OtherAmenity",
    "RoomMatch",
    "find_rooms",
    # Test-only re-exports (kept stable for tests/tools/test_find_rooms.py)
    "_build_sql",
    "_select_price_column",
]