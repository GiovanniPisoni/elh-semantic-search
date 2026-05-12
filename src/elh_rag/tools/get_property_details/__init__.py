"""Tool 4: ``get_property_details``.

Full drill-down on a specific room or house given an encoded id from
the output of :func:`elh_rag.tools.find_rooms.find_rooms` or
:func:`elh_rag.tools.find_available_rooms.find_available_rooms`. See
:mod:`.tool` for the registered entry point.

Package layout:

    * :mod:`._property_details`   — Pydantic models (HouseDetails,
                                    RoomDetails, HousemateRoom),
                                    fetchers + builders.
    * :mod:`._reviews_aggregate`  — review stats aggregator (count,
                                    averages across 5 dimensions, top
                                    3 recent excerpts).
    * :mod:`.tool`                — registered entry point, branch
                                    dispatch (room id vs house id),
                                    summary composition.
"""

from ._property_details import (
    _MAX_HOUSEMATE_ROOMS,
    HouseDetails,
    HousemateRoom,
    RoomDetails,
    build_house_details,
    build_room_details,
    fetch_house_at_version,
    fetch_housemate_rooms,
    fetch_room_latest,
)
from ._reviews_aggregate import (
    ReviewsAggregate,
    ReviewSummary,
    fetch_reviews_aggregate,
)
from .tool import (
    GetPropertyDetailsInput,
    GetPropertyDetailsOutput,
    get_property_details,
)

__all__ = [
    "_MAX_HOUSEMATE_ROOMS",
    "GetPropertyDetailsInput",
    "GetPropertyDetailsOutput",
    "HouseDetails",
    "HousemateRoom",
    "ReviewSummary",
    "ReviewsAggregate",
    "RoomDetails",
    "build_house_details",
    "build_room_details",
    "fetch_house_at_version",
    "fetch_housemate_rooms",
    "fetch_reviews_aggregate",
    "fetch_room_latest",
    "get_property_details",
]
