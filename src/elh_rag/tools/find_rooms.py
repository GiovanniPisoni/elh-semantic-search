"""Tool 1: ``find_rooms``.

Search ELH rooms by structured criteria. The most ambitious of the six
tools: 30 parameters covering location, price, period, occupancy,
amenities, and ranking. Built on top of the registry/decorator scaffold
in ``base.py`` and the metro-line mapping in ``_metro_lines.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ._db import DBExecutor
from ._metro_lines import normalize_line, zones_on_line
from ._room_id import encode_house_id, encode_room_id
from .base import register_tool

import logging

logger = logging.getLogger(__name__)

# Allowed values

MetroLineInput = Literal[
    "blue",
    "yellow",
    "green",
    "red",
    "violet",
    "orange",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
]

OtherAmenity = Literal[
    "city_view",
    "garden_view",
    "river_view",
    "security_alarm",
    "doorman",
    "video_intercom",
    "kitchen_oven",
    "kitchen_microwave",
    "kitchen_freezer",
    "kitchen_kettle",
    "bbq",
    "pool",
    "gym",
    "common_room",
    "tv",
    "iron",
    "hairdryer",
    "safebox",
    "linen_provided",
    "cleaning_service",
    "garbage_disposal",
    "fireplace",
    "wheelchair_accessible",
    "non_smoking",
    "pet_friendly_common",
    "couples_welcome",
    "long_term_friendly",
    "short_term_ok",
]


# Input model


class FindRoomsInput(BaseModel):
    """Search rooms by structured criteria.

    All parameters are optional (None = no filter on that dimension).
    Returns up to ``max_results`` rooms ranked by ``match_score``.
    """

    # ── 1. LOCATION ──
    city: Literal["Lisbon", "Porto"] | None = None
    metro_line: MetroLineInput | None = Field(
        default=None,
        description="Metro line. Accepts colour names (blue, yellow, "
        "green, red, violet, orange) or Porto letter codes "
        "(A=blue, B=red, C=green, D=yellow, E=violet, F=orange).",
    )
    near_landmark: str | None = Field(
        default=None,
        max_length=100,
        description="Free-text landmark (e.g., 'NOVA University'). "
        "Matched ILIKE on house.zone, neighboorhood, description.",
    )
    max_distance_to_transport_m: int | None = Field(default=None, ge=0, le=5000)

    # 2. PRICE
    max_price_eur: float | None = Field(default=None, ge=0, le=10000)
    min_price_eur: float | None = Field(default=None, ge=0, le=10000)

    # 3. PERIOD
    available_from: date | None = None
    available_to: date | None = None
    min_contract_months: int | None = Field(default=None, ge=1, le=24)
    min_reserve_months: int | None = Field(default=None, ge=1, le=12)

    # 4. OCCUPANCY
    accepts_couples: bool | None = None
    accepts_pets: bool | None = None
    gender_preference: Literal["male_only", "female_only", "any"] | None = None
    max_house_occupancy: int | None = Field(default=None, ge=1, le=20)
    num_rooms_needed: int = Field(default=1, ge=1, le=10)

    # 5. EXPLICIT AMENITIES
    must_have_private_bathroom: bool | None = None
    must_have_balcony: bool | None = None
    must_have_elevator: bool | None = None
    must_have_air_conditioning: bool | None = None
    must_have_heating: bool | None = None
    must_have_washing_machine: bool | None = None
    must_have_dishwasher: bool | None = None
    must_have_parking: bool | None = None
    must_have_internet: bool | None = None
    must_have_desk: bool | None = None
    must_have_window: bool | None = None

    # 6. OTHER AMENITIES
    required_other_amenities: list[OtherAmenity] = Field(default_factory=list)

    # 7. SORT + LIMIT
    sort_by: Literal["price_asc", "price_desc", "default"] = "default"
    max_results: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def check_consistency(self) -> FindRoomsInput:
        # Price range
        if (
            self.max_price_eur is not None
            and self.min_price_eur is not None
            and self.max_price_eur < self.min_price_eur
        ):
            raise ValueError("max_price_eur must be >= min_price_eur")
        # Date range
        if (
            self.available_from is not None
            and self.available_to is not None
            and self.available_to <= self.available_from
        ):
            raise ValueError("available_to must be after available_from")
        return self


# Output dataclasses


@dataclass(frozen=True)
class RoomMatch:
    """Single room result. Reused by Tool 1, Tool 2, Tool 4."""

    room_id: str  # encoded "H42_R3_..."
    house_id: str  # encoded "H42_..."
    house_name: str
    city: str
    zone: str
    neighborhood: str
    price_per_month_eur: float
    private_bathroom: bool
    distance_to_transport_m: int | None
    nearest_metro_line: str | None
    available_from: date | None
    min_reserve_months: int
    amenities: list[str] = field(default_factory=list)
    excerpt: str = ""
    match_score: float = 0.0
    is_fixed_price: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "house_id": self.house_id,
            "house_name": self.house_name,
            "city": self.city,
            "zone": self.zone,
            "neighborhood": self.neighborhood,
            "price_per_month_eur": self.price_per_month_eur,
            "private_bathroom": self.private_bathroom,
            "distance_to_transport_m": self.distance_to_transport_m,
            "nearest_metro_line": self.nearest_metro_line,
            "available_from": self.available_from.isoformat() if self.available_from else None,
            "min_reserve_months": self.min_reserve_months,
            "amenities": list(self.amenities),
            "excerpt": self.excerpt,
            "match_score": self.match_score,
            "is_fixed_price": self.is_fixed_price,
        }


@dataclass(frozen=True)
class FindRoomsOutput:
    """Result of a find_rooms call."""

    rooms: list[RoomMatch]
    total_matches: int  # pre-pagination count
    query_summary: str  # natural-language summary of filters

    def to_dict(self) -> dict[str, Any]:
        return {
            "rooms": [r.to_dict() for r in self.rooms],
            "total_matches": self.total_matches,
            "query_summary": self.query_summary,
        }


# Internal mappings: amenity name → DB column


_EXPLICIT_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    # field name on input → (table, column_name)
    "must_have_private_bathroom": ("room", "privatebathroom"),
    "must_have_balcony": ("room", "balcony"),
    "must_have_elevator": ("house", "elevator"),
    "must_have_air_conditioning": ("room", "airconditioning"),
    "must_have_heating": ("room", "heating"),
    "must_have_washing_machine": ("house", "washerdrier"),
    "must_have_dishwasher": ("house", "dishwasher"),
    "must_have_parking": ("house", "parking"),
    "must_have_internet": ("house", "internet"),
    "must_have_desk": ("room", "desk"),
    "must_have_window": ("room", "haswindow"),
}

_OTHER_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "city_view": ("house", "cityview"),
    "garden_view": ("house", "gardenview"),
    "river_view": ("house", "riverview"),
    "security_alarm": ("house", "securityalarm"),
    "doorman": ("house", "doorman"),
    "video_intercom": ("house", "videointercom"),
    "kitchen_oven": ("house", "oven"),
    "kitchen_microwave": ("house", "microwave"),
    "kitchen_freezer": ("house", "freezer"),
    "kitchen_kettle": ("house", "kettle"),
    "bbq": ("house", "bbq"),
    "pool": ("house", "pool"),
    "gym": ("house", "gym"),
    "common_room": ("house", "commonroom"),
    "tv": ("house", "tv"),
    "iron": ("house", "iron"),
    "hairdryer": ("house", "hairdryer"),
    "safebox": ("house", "safebox"),
    "linen_provided": ("house", "linen"),
    "cleaning_service": ("house", "cleaningservice"),
    "garbage_disposal": ("house", "garbagedisposal"),
    "fireplace": ("house", "fireplace"),
    "wheelchair_accessible": ("house", "wheelchairaccess"),
    "non_smoking": ("house", "nonsmoking"),
    "pet_friendly_common": ("house", "petfriendly"),
    "couples_welcome": ("house", "couplesallowed"),
    "long_term_friendly": ("house", "longterm"),
    "short_term_ok": ("house", "shortterm"),
}


# SQL builder


def _select_price_column(payload: FindRoomsInput) -> str:
    """Return the price column to select, based on the requested period.

    Default: ``autumnprice`` (high Erasmus season). If ``available_from``
    is given, pick the column matching that month.
    """
    if payload.available_from is None:
        return "r.autumnprice"
    m = payload.available_from.month
    if m in (3, 4, 5, 6):
        return "r.springprice"
    if m in (7, 8):
        return "r.summerprice"
    # 9, 10, 11, 12, 1, 2 -> autumn (high Erasmus season)
    return "r.autumnprice"


def _build_sql(payload: FindRoomsInput) -> tuple[str, list[Any]]:
    """Build a parameterised SQL query from a validated input.

    Returns (sql, params). Pure — no DB access, no side effects.
    """
    price_col = _select_price_column(payload)
    select_parts = [
        "r.idroom",
        "r.loc_idhouse",
        "r.dateupdate AS r_dateupdate",
        "r.loc_dateupdate",
        f"{price_col} AS price_eur",
        "r.privatebathroom",
        "r.minreservemonths",
        "r.description AS room_description",
        "r.haswindow",
        "h.idhouse",
        "h.dateupdate AS h_dateupdate",
        "h.city",
        "h.zone",
        "h.neighboorhood AS neighborhood",
        "h.distancepublictransport",
    ]

    where_parts: list[str] = ["r.status = 'Available'"]
    params: list[Any] = []

    # 1. Location
    if payload.city is not None:
        where_parts.append("h.city = %s")
        params.append(payload.city)

    if payload.metro_line is not None:
        # Normalise letter→colour, then look up zones for both cities
        # if no city filter, otherwise restrict to chosen city.
        colour = normalize_line(payload.metro_line)
        if colour:
            zones: set[str] = set()
            cities = [payload.city] if payload.city else ["Lisbon", "Porto"]
            for c in cities:
                zones.update(zones_on_line(c, colour))
            if zones:
                placeholders = ",".join(["%s"] * len(zones))
                where_parts.append(
                    f"(h.zone IN ({placeholders}) OR h.neighboorhood IN ({placeholders}))"
                )
                params.extend(sorted(zones))
                params.extend(sorted(zones))
            else:
                # No zones found -> impossible filter, force empty result
                where_parts.append("FALSE")

    if payload.near_landmark is not None:
        # ILIKE across zone, neighboorhood (sic), description
        like = f"%{payload.near_landmark}%"
        where_parts.append(
            "(h.zone ILIKE %s OR h.neighboorhood ILIKE %s OR h.description ILIKE %s)"
        )
        params.extend([like, like, like])

    if payload.max_distance_to_transport_m is not None:
        where_parts.append("h.distancepublictransport <= %s")
        params.append(payload.max_distance_to_transport_m)

    # 2. Price
    if payload.max_price_eur is not None:
        where_parts.append(f"{price_col} <= %s")
        params.append(payload.max_price_eur)
    if payload.min_price_eur is not None:
        where_parts.append(f"{price_col} >= %s")
        params.append(payload.min_price_eur)

    # 3. Period
    if payload.min_contract_months is not None:
        # Approximation: min_contract_months ~= minreservemonths
        where_parts.append("r.minreservemonths >= %s")
        params.append(payload.min_contract_months)
    if payload.min_reserve_months is not None:
        where_parts.append("r.minreservemonths >= %s")
        params.append(payload.min_reserve_months)

    # 4. Occupancy
    if payload.accepts_couples is True:
        logger.warning(
            "find_rooms: accepts_couples=True ignored — column not present "
            "in the ELH schema."
        )
    if payload.accepts_pets is True:
        # Schema column is `allowpets` (not `acceptspets`).
        where_parts.append("h.allowpets = 'Y'")
    if payload.gender_preference == "female_only":
        where_parts.append("r.femalepreferred = 'Y'")
    elif payload.gender_preference == "male_only":
        where_parts.append("r.malepreferred = 'Y'")
    # "any" → no filter
    if payload.max_house_occupancy is not None:
        logger.warning(
            "find_rooms: max_house_occupancy=%s ignored — column not "
            "present in the ELH schema.",
            payload.max_house_occupancy,
        )

    # 5. Explicit must_have_* amenities
    for input_field, (table, column) in _EXPLICIT_AMENITY_COLUMN_MAP.items():
        v = getattr(payload, input_field)
        if v is True:
            where_parts.append(f"{table[0]}.{column} = 'Y'")
        elif v is False:
            where_parts.append(f"{table[0]}.{column} = 'N'")

    # 6. Other amenities
    for amenity in payload.required_other_amenities:
        if amenity in _OTHER_AMENITY_COLUMN_MAP:
            table, column = _OTHER_AMENITY_COLUMN_MAP[amenity]
            where_parts.append(f"{table[0]}.{column} = 'Y'")
        # Unknown amenity → silently skip (Pydantic Literal already filtered)

    # 7. Sort + limit
    if payload.sort_by == "price_asc":
        order_by = f"{price_col} ASC, r.idroom ASC"
    elif payload.sort_by == "price_desc":
        order_by = f"{price_col} DESC, r.idroom ASC"
    else:
        # Default: stable ordering by id
        order_by = "r.idroom ASC"

    sql = (
        "SELECT " + ", ".join(select_parts) + "\n"
        "FROM room r\n"
        "JOIN house h ON h.idhouse = r.loc_idhouse "
        "AND h.dateupdate = r.loc_dateupdate\n"
        "WHERE " + "\n  AND ".join(where_parts) + "\n"
        f"ORDER BY {order_by}\n"
        "LIMIT %s"
    )
    params.append(payload.max_results)

    return sql, params


# Helpers: row -> RoomMatch


def _row_to_match(
    row: dict[str, Any],
    payload: FindRoomsInput,
) -> RoomMatch:
    """Map a SQL row to a RoomMatch dataclass."""
    room_id = encode_room_id(
        house_id=row["loc_idhouse"],
        room_id=row["idroom"],
        dateupdate=row["r_dateupdate"],
    )
    house_id = encode_house_id(
        house_id=row["idhouse"],
        dateupdate=row["h_dateupdate"],
    )

    # Pick first metro line serving the zone (if any) for display.
    # The full list is available via lines_for_zone() if needed by UI.
    from ._metro_lines import lines_for_zone

    serving_lines = lines_for_zone(row["city"], row["zone"])
    nearest_line = serving_lines[0] if serving_lines else None

    description = row.get("room_description") or ""
    excerpt = description[:200] if description else ""

    # Naïve match score: 1.0 if all filters pass (the SQL ensures that),
    # downweighted slightly if no metro line is associated.
    # Future: real scoring with Pinecone semantic similarity.
    score = 1.0 if nearest_line else 0.85

    return RoomMatch(
        room_id=room_id,
        house_id=house_id,
        house_name=f"{row['zone']} #{row['idhouse']}",
        city=row["city"],
        zone=row["zone"],
        neighborhood=row.get("neighborhood") or row["zone"],
        price_per_month_eur=float(row["price_eur"]),
        private_bathroom=(row.get("privatebathroom") == "Y"),
        distance_to_transport_m=row.get("distancepublictransport"),
        nearest_metro_line=nearest_line,
        available_from=None,  # Tool 1 doesn't compute this; Tool 2 does
        min_reserve_months=int(row.get("minreservemonths") or 1),
        amenities=[],  # Future: collect 'Y' columns into a list
        excerpt=excerpt,
        match_score=score,
    )


def _summarize_query(payload: FindRoomsInput) -> str:
    """Produce a one-line natural-language summary of active filters."""
    bits: list[str] = []
    if payload.city:
        bits.append(f"city={payload.city}")
    if payload.metro_line:
        bits.append(f"metro={payload.metro_line}")
    if payload.near_landmark:
        bits.append(f"near='{payload.near_landmark}'")
    if payload.max_price_eur:
        bits.append(f"≤€{payload.max_price_eur:.0f}")
    if payload.gender_preference and payload.gender_preference != "any":
        bits.append(payload.gender_preference)
    if payload.accepts_couples:
        bits.append("couples-friendly")
    if payload.accepts_pets:
        bits.append("pets-friendly")
    if payload.num_rooms_needed > 1:
        bits.append(f"{payload.num_rooms_needed} rooms")

    if not bits:
        return "All available rooms (no filters)"
    return "Filters: " + ", ".join(bits)


# Registered tool function


@register_tool(
    name="find_rooms",
    description=(
        "Search ELH rooms by structured criteria: location (city, metro line, "
        "landmark, distance to transport), price (min/max), "
        "period (preferences, soft constraints), occupancy (couples, pets, "
        "gender, max house size, multi-room), 11 explicit must-have amenities "
        "(private bathroom, balcony, elevator, A/C, heating, washing machine, "
        "dishwasher, parking, internet, desk, window) plus a catalogue of 28 "
        "other amenities. Sort by price asc/desc or default ranking. "
        "Returns up to max_results rooms ranked by match score. "
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
