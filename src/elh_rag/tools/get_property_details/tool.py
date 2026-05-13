"""Tool 4: ``get_property_details``."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .._shared.db import DBExecutor
from .._shared.room_id import (
    InvalidRoomIdError,
    decode_house_id,
    decode_room_id,
    is_house_id,
    is_room_id,
    normalize_id,
)
from ..base import register_tool
from ._property_details import (
    HouseDetails,
    RoomDetails,
    build_house_details,
    build_room_details,
    fetch_house_at_version,
    fetch_housemate_rooms,
    fetch_room_latest,
)
from ._reviews_aggregate import ReviewsAggregate, fetch_reviews_aggregate

logger = logging.getLogger(__name__)


# Input model


class GetPropertyDetailsInput(BaseModel):
    """Inputs for a property-details lookup."""

    encoded_id: str = Field(
        ...,
        description=(
            "Encoded id of the target room (3 segments: house|room|date) "
            "or house (2 segments: house|date). Obtained from the output "
            "of find_rooms or find_available_rooms (room_id or house_id "
            "fields)."
        ),
    )
    include_reviews: bool = Field(
        default=True,
        description=(
            "Include a reviews aggregate (count, average ratings, top 3 "
            "most recent excerpts). Set to False for a faster lookup when "
            "review context is not needed."
        ),
    )


# Output model


class GetPropertyDetailsOutput(BaseModel):
    """Complete property lookup result."""

    house: HouseDetails = Field(
        ...,
        description=(
            "The house — always present. Populated from the room's "
            "loc_idhouse/loc_dateupdate when the input was a room id."
        ),
    )
    room: RoomDetails | None = Field(
        default=None,
        description=(
            "The specific room. Populated only when the input was a "
            "room id; ``None`` for house-id lookups."
        ),
    )
    reviews: ReviewsAggregate | None = Field(
        default=None,
        description=(
            "Reviews scoped to the room (if room lookup) or to the whole "
            "house version (if house lookup). ``None`` iff "
            "``include_reviews=False`` was passed."
        ),
    )
    summary: str = Field(
        ...,
        description="One-line human-readable summary, suitable for LLM quoting.",
    )


# Summary composition


def _compose_summary(
    house: HouseDetails,
    room: RoomDetails | None,
    reviews: ReviewsAggregate | None,
) -> str:
    """One-line LLM-quotable summary of the lookup result."""
    if room is not None:
        bits = [f"Room '{room.room_name}' in {house.flat_name} ({house.zone}, {house.city})"]
        bits.append(
            f"autumn rate €{room.autumn_price_eur}"
            if not room.is_fixed_price
            else f"fixed rate €{room.autumn_price_eur}"
        )
        if room.amenities:
            bits.append(f"{len(room.amenities)} amenities")
    else:
        bits = [
            f"{house.flat_name} in {house.zone}, {house.city}",
            f"{house.rooms_total} room{'s' if house.rooms_total != 1 else ''}",
            f"{len(house.amenities)} house amenities",
        ]

    if reviews is not None and reviews.count > 0:
        bits.append(
            f"{reviews.count} review{'s' if reviews.count != 1 else ''} "
            f"(avg {reviews.average_overall_rating}/5)"
        )

    return "; ".join(bits) + "."


# Lookup branches


def _lookup_by_room_id(
    ctx: DBExecutor, encoded: str, include_reviews: bool
) -> tuple[HouseDetails, RoomDetails, ReviewsAggregate | None]:
    parts = decode_room_id(encoded)

    room_row = fetch_room_latest(
        ctx,
        house_id=parts.house_id,
        room_id=parts.room_id,
    )
    if room_row is None:
        raise ValueError(
            f"Room not found for encoded id {encoded!r}. "
            "It may have been deactivated since the search ran."
        )

    house_id_str = normalize_id(room_row["loc_idhouse"], name="loc_idhouse")
    house_dateupdate = room_row["loc_dateupdate"]
    room_id_str = normalize_id(room_row["idroom"], name="idroom")

    house_row = fetch_house_at_version(
        ctx, house_id=house_id_str, house_dateupdate=house_dateupdate
    )
    if house_row is None:
        # Data-integrity issue: room points to a house version that does
        # not exist. Surface explicitly rather than silently returning
        # partial data.
        raise ValueError(
            f"Data integrity issue: room {encoded!r} references house "
            f"({house_id_str}, {house_dateupdate}) which does not exist."
        )

    housemate_rows = fetch_housemate_rooms(
        ctx, house_id=house_id_str, house_dateupdate=house_dateupdate
    )

    house = build_house_details(house_row, housemate_rows)
    room = build_room_details(room_row)

    reviews: ReviewsAggregate | None = None
    if include_reviews:
        reviews = fetch_reviews_aggregate(
            ctx,
            house_id=house_id_str,
            house_dateupdate=house_dateupdate,
            room_id=room_id_str,
        )

    return house, room, reviews


def _lookup_by_house_id(
    ctx: DBExecutor, encoded: str, include_reviews: bool
) -> tuple[HouseDetails, None, ReviewsAggregate | None]:
    parts = decode_house_id(encoded)

    house_row = fetch_house_at_version(
        ctx,
        house_id=parts.house_id,
        house_dateupdate=parts.dateupdate,
    )
    if house_row is None:
        raise ValueError(
            f"House not found for encoded id {encoded!r}. "
            "It may have been deactivated since the search ran."
        )

    housemate_rows = fetch_housemate_rooms(
        ctx,
        house_id=parts.house_id,
        house_dateupdate=parts.dateupdate,
    )

    house = build_house_details(house_row, housemate_rows)

    reviews: ReviewsAggregate | None = None
    if include_reviews:
        reviews = fetch_reviews_aggregate(
            ctx,
            house_id=parts.house_id,
            house_dateupdate=parts.dateupdate,
            room_id=None,
        )

    return house, None, reviews


# Registered tool


@register_tool(
    name="get_property_details",
    description=(
        "Look up the full details of a specific ELH room or house given "
        "an encoded id (from find_rooms or find_available_rooms output). "
        "Returns the complete picture distinct from the summary cards "
        "produced by Tool 1 and Tool 2: full description, complete "
        "amenity list, all three seasonal prices, bed types, deposit "
        "and admin-fee policy, and either the room's house context or "
        "all rooms belonging to the house. When include_reviews is True "
        "(the default), also returns a reviews aggregate with total "
        "count, average ratings across five dimensions (cleaning, "
        "communication, location, price/quality, overall) and the three "
        "most recent approved reviews with title and a 200-char excerpt. "
        "Use this tool when the user asks 'tell me more about that one', "
        "'what's included in #X', 'show me the full description', or to "
        "drill into one specific result after a search. For monetary "
        "totals across a stay window, use compute_total_cost instead. "
        "For free-text semantic search across reviews, use the Phase 2 "
        "RAG fallback (do not call this tool with broad questions)."
    ),
    input_model=GetPropertyDetailsInput,
)
def get_property_details(
    payload: GetPropertyDetailsInput,
    ctx: DBExecutor | None,
) -> GetPropertyDetailsOutput:
    """Resolve an encoded id to a full house/room detail payload."""
    if ctx is None:
        raise RuntimeError(
            "get_property_details requires a DBExecutor in ctx. "
            "Bootstrap the orchestrator with a configured executor."
        )

    encoded = payload.encoded_id.strip()

    house: HouseDetails
    room: RoomDetails | None
    reviews: ReviewsAggregate | None

    if is_room_id(encoded):
        house, room, reviews = _lookup_by_room_id(ctx, encoded, payload.include_reviews)
    elif is_house_id(encoded):
        house, room, reviews = _lookup_by_house_id(ctx, encoded, payload.include_reviews)
    else:
        raise InvalidRoomIdError(
            encoded,
            "does not match a room (3 segments) or house (2 segments) format",
        )

    summary = _compose_summary(house, room, reviews)

    return GetPropertyDetailsOutput(
        house=house,
        room=room,
        reviews=reviews,
        summary=summary,
    )
