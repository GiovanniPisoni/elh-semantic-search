"""House and room detail assembly for Tool 4 (``get_property_details``)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from ._shared.db import DBExecutor
from ._shared.metro_lines import lines_for_zone
from ._shared.room_id import encode_house_id, encode_room_id

logger = logging.getLogger(__name__)


# Amenity column maps


# House amenities
_HOUSE_AMENITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("furnished", "Furnished"),
    ("sharedspace", "Shared space"),
    ("balcony", "Balcony"),
    ("cityview", "City view"),
    ("fieldview", "Field view"),
    ("seaview", "Sea view"),
    ("cctv", "CCTV"),
    ("codeentry", "Code entry"),
    ("security24h", "24h security"),
    ("smokedetector", "Smoke detector"),
    ("armoreddoor", "Armoured door"),
    ("elevator", "Elevator"),
    ("reducedmobilityaccess", "Reduced mobility access"),
    ("parking", "Parking"),
    ("centralheating", "Central heating"),
    ("airconditioning", "Air conditioning"),
    ("thermalinsulation", "Thermal insulation"),
    ("doubleglazedwindows", "Double-glazed windows"),
    ("kitchenequipment", "Kitchen equipment"),
    ("fridge", "Fridge"),
    ("microwaveoven", "Microwave oven"),
    ("gaselectricstove", "Gas/electric stove"),
    ("dishwasher", "Dishwasher"),
    ("washerdrier", "Washer/drier"),
    ("internet", "Internet"),
    ("cabletv", "Cable TV"),
    ("smarttv", "Smart TV"),
)

# Room-level amenities.
_ROOM_AMENITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("privatebathroom", "Private bathroom"),
    ("balcony", "Balcony"),
    ("desk", "Desk"),
    ("closet", "Closet"),
    ("heating", "Heating"),
    ("haswindow", "Has window"),
    ("bedlinen", "Bed linen provided"),
    ("pillows", "Pillows provided"),
    ("airconditioning", "Air conditioning"),
)

# Bed configuration columns.
_ROOM_BED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("singlebed", "Single bed"),
    ("doublebed", "Double bed"),
    ("kingbed", "King bed"),
    ("queenbed", "Queen bed"),
    ("couchbed", "Couch bed"),
    ("secondbed", "Second bed (sleeps 2)"),
)


_MAX_HOUSEMATE_ROOMS = 30


# Output models


class HousemateRoom(BaseModel):
    """Brief info on a room sharing the same house, embedded in house lookups."""

    encoded_room_id: str
    room_name: str
    status: str
    area_sqm: float | None
    private_bathroom: bool
    is_fixed_price: bool
    spring_price_eur: Decimal
    summer_price_eur: Decimal
    autumn_price_eur: Decimal


class HouseDetails(BaseModel):
    """Full house lookup payload — all amenities, all rooms, full text."""

    encoded_house_id: str
    flat_name: str
    city: str
    zone: str
    neighborhood: str
    latitude: float
    longitude: float
    distance_to_transport_m: int | None
    nearest_metro_lines: list[str] = Field(default_factory=list)
    full_description: str
    bathroom_count: int
    area_sqm: float | None
    internet_speed_mbps: float | None
    amenities: list[str] = Field(default_factory=list)
    other_amenities_text: str = ""
    night_guests_allowed: bool
    pets_allowed: bool
    smoking_allowed: bool
    gender_preference: Literal["female_only", "male_only", "any"]
    status: str
    rooms_summary: list[HousemateRoom] = Field(default_factory=list)
    rooms_total: int = 0


class RoomDetails(BaseModel):
    """Full room lookup payload — all amenities, all-season pricing, booking policy."""

    encoded_room_id: str
    room_name: str
    full_description: str
    area_sqm: float | None
    amenities: list[str] = Field(default_factory=list)
    bed_types: list[str] = Field(default_factory=list)
    is_fixed_price: bool
    spring_price_eur: Decimal
    summer_price_eur: Decimal
    autumn_price_eur: Decimal
    extra_person_allowed: bool
    extra_person_cost_eur: Decimal | None
    deposit_required: bool
    deposit_value_eur: Decimal
    last_month_deposit: bool
    administrative_tax_eur: Decimal
    status: str


# SQL


_ROOM_LATEST_SQL = """\
SELECT DISTINCT ON (loc_idhouse, idroom) *
FROM room
WHERE loc_idhouse = %s AND idroom = %s
ORDER BY loc_idhouse, idroom, dateupdate DESC
"""

_HOUSE_AT_VERSION_SQL = """\
SELECT *
FROM house
WHERE idhouse = %s AND dateupdate = %s
"""

_HOUSEMATE_ROOMS_SQL = """\
SELECT DISTINCT ON (loc_idhouse, idroom) *
FROM room
WHERE loc_idhouse = %s AND loc_dateupdate = %s
ORDER BY loc_idhouse, idroom, dateupdate DESC
"""


# Fetchers


def fetch_room_latest(db: DBExecutor, house_id: str, room_id: str) -> dict[str, Any] | None:
    """Return the most recent version of the room, or None if not found."""
    rows = db.execute(_ROOM_LATEST_SQL, (house_id, room_id))
    return rows[0] if rows else None


def fetch_house_at_version(
    db: DBExecutor, house_id: str, house_dateupdate: date
) -> dict[str, Any] | None:
    """Return the house row at the specified version, or None if not found."""
    rows = db.execute(_HOUSE_AT_VERSION_SQL, (house_id, house_dateupdate))
    return rows[0] if rows else None


def fetch_housemate_rooms(
    db: DBExecutor, house_id: str, house_dateupdate: date
) -> list[dict[str, Any]]:
    """Return latest version of every room attached to this house version.

    The query joins by ``(loc_idhouse, loc_dateupdate)``: every room
    that points to this specific house version, regardless of the
    room's own ``dateupdate``.
    """
    return db.execute(_HOUSEMATE_ROOMS_SQL, (house_id, house_dateupdate))


# Assembly helpers


def _y_columns_to_labels(
    row: dict[str, Any],
    columns: tuple[tuple[str, str], ...],
) -> list[str]:
    """Map ``Y/N`` columns in a row to the matching human labels, sorted."""
    return sorted(label for col, label in columns if row.get(col) == "Y")


def _gender_preference(
    row: dict[str, Any],
) -> Literal["female_only", "male_only", "any"]:
    """Derive a single gender enum from the three boolean columns."""
    female = row.get("femalepreferred") == "Y"
    male = row.get("malepreferred") == "Y"
    if female and not male:
        return "female_only"
    if male and not female:
        return "male_only"
    return "any"


def _safe_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _safe_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _safe_str(value: Any) -> str:
    """Strip and stringify (handles ``character()`` right-padding)."""
    return "" if value is None else str(value).strip()


def _to_datetime(value: Any) -> datetime:
    """Coerce a ``date`` or ``datetime`` to ``datetime`` (midnight on a bare date).

    PostgreSQL DATE columns surface as ``datetime.date``; the room-id
    encoders require ``datetime``. This adapter sits between them.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time())
    raise TypeError(f"Cannot coerce {type(value).__name__} to datetime: {value!r}")


def _housemate_from_row(row: dict[str, Any]) -> HousemateRoom:
    return HousemateRoom(
        encoded_room_id=encode_room_id(
            house_id=row["loc_idhouse"],
            room_id=row["idroom"],
            dateupdate=_to_datetime(row["dateupdate"]),
        ),
        room_name=_safe_str(row.get("roomname")),
        status=_safe_str(row.get("status")),
        area_sqm=_safe_float(row.get("area")),
        private_bathroom=(row.get("privatebathroom") == "Y"),
        is_fixed_price=(row.get("fixedprice") == "Y"),
        spring_price_eur=Decimal(str(row.get("springprice") or "0")),
        summer_price_eur=Decimal(str(row.get("summerprice") or "0")),
        autumn_price_eur=Decimal(str(row.get("autumnprice") or "0")),
    )


def build_house_details(
    house_row: dict[str, Any],
    housemate_rows: list[dict[str, Any]],
) -> HouseDetails:
    """Assemble a :class:`HouseDetails` from one house row + N housemate rows."""
    city = _safe_str(house_row.get("city"))
    zone = _safe_str(house_row.get("zone"))

    if len(housemate_rows) > _MAX_HOUSEMATE_ROOMS:
        logger.warning(
            "get_property_details: house has %d rooms; capping rooms_summary at %d",
            len(housemate_rows),
            _MAX_HOUSEMATE_ROOMS,
        )
    capped = housemate_rows[:_MAX_HOUSEMATE_ROOMS]

    return HouseDetails(
        encoded_house_id=encode_house_id(
            house_id=house_row["idhouse"],
            dateupdate=_to_datetime(house_row["dateupdate"]),
        ),
        flat_name=_safe_str(house_row.get("flatname")),
        city=city,
        zone=zone,
        neighborhood=_safe_str(house_row.get("neighboorhood")),
        latitude=float(house_row.get("latitude") or 0.0),
        longitude=float(house_row.get("longitude") or 0.0),
        distance_to_transport_m=_safe_int(house_row.get("distancepublictransport")),
        nearest_metro_lines=lines_for_zone(city, zone),
        full_description=_safe_str(house_row.get("description")),
        bathroom_count=int(house_row.get("bathroom") or 0),
        area_sqm=_safe_float(house_row.get("area")),
        internet_speed_mbps=_safe_float(house_row.get("internetspeed")),
        amenities=_y_columns_to_labels(house_row, _HOUSE_AMENITY_COLUMNS),
        other_amenities_text=_safe_str(house_row.get("otherameneties")),
        night_guests_allowed=(house_row.get("allownightguests") == "Y"),
        pets_allowed=(house_row.get("allowpets") == "Y"),
        smoking_allowed=(house_row.get("smokingallowed") == "Y"),
        gender_preference=_gender_preference(house_row),
        status=_safe_str(house_row.get("status")),
        rooms_summary=[_housemate_from_row(r) for r in capped],
        rooms_total=len(housemate_rows),
    )


def build_room_details(room_row: dict[str, Any]) -> RoomDetails:
    """Assemble a :class:`RoomDetails` from one room row."""
    extra_allowed = room_row.get("extrapersonallowed") == "Y"
    return RoomDetails(
        encoded_room_id=encode_room_id(
            house_id=room_row["loc_idhouse"],
            room_id=room_row["idroom"],
            dateupdate=_to_datetime(room_row["dateupdate"]),
        ),
        room_name=_safe_str(room_row.get("roomname")),
        full_description=_safe_str(room_row.get("description")),
        area_sqm=_safe_float(room_row.get("area")),
        amenities=_y_columns_to_labels(room_row, _ROOM_AMENITY_COLUMNS),
        bed_types=_y_columns_to_labels(room_row, _ROOM_BED_COLUMNS),
        is_fixed_price=(room_row.get("fixedprice") == "Y"),
        spring_price_eur=Decimal(str(room_row.get("springprice") or "0")),
        summer_price_eur=Decimal(str(room_row.get("summerprice") or "0")),
        autumn_price_eur=Decimal(str(room_row.get("autumnprice") or "0")),
        extra_person_allowed=extra_allowed,
        extra_person_cost_eur=(
            Decimal(str(room_row.get("extrapersoncost") or "0")) if extra_allowed else None
        ),
        deposit_required=(room_row.get("deposit") == "Y"),
        deposit_value_eur=Decimal(str(room_row.get("depositvalue") or "0")),
        last_month_deposit=(room_row.get("lastmonthdeposit") == "Y"),
        administrative_tax_eur=Decimal(str(room_row.get("administrativetax") or "0")),
        status=_safe_str(room_row.get("status")),
    )
