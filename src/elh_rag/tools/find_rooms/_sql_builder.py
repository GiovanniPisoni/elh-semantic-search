"""SQL building and row → ``RoomMatch`` mapping for ``find_rooms``.

Pure logic against the validated input model and the amenity column
maps. No DB roundtrip happens here — ``_build_sql`` returns a
``(sql, params)`` tuple and ``_row_to_match`` maps a single result
row to the dataclass. The actual ``ctx.execute`` call lives in
``tool.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from .._metro_lines import lines_for_zone, normalize_line, zones_on_line
from .._room_id import encode_house_id, encode_room_id
from ._amenity_columns import (
    _EXPLICIT_AMENITY_COLUMN_MAP,
    _OTHER_AMENITY_COLUMN_MAP,
    _OTHER_AMENITY_INVERTED,
)
from ._inputs import FindRoomsInput
from ._schemas import RoomMatch

logger = logging.getLogger(__name__)


# Price column selection


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


# SQL builder


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
            "find_rooms: accepts_couples=True ignored — column not present in the ELH schema."
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
            "find_rooms: max_house_occupancy=%s ignored — column not present in the ELH schema.",
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
            # Inverted-logic amenities check 'N' instead of 'Y' (e.g.
            # non_smoking=True means smokingallowed='N').
            expected = "N" if amenity in _OTHER_AMENITY_INVERTED else "Y"
            where_parts.append(f"{table[0]}.{column} = '{expected}'")
        else:
            # Defensive: the Literal and the map are kept in sync (every
            # Literal value has an entry). This branch only fires if a
            # future Literal addition forgets the corresponding map entry.
            logger.warning(
                "find_rooms: amenity %r in vocabulary but not mapped — "
                "_OTHER_AMENITY_COLUMN_MAP is out of sync with the Literal.",
                amenity,
            )

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


# Query summary


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
