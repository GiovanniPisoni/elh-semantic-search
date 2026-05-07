"""
Encoder/decoder for room and house identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Errors


class InvalidRoomIdError(ValueError):
    """Raised when a room/house ID string cannot be parsed."""

    def __init__(self, raw: str, reason: str) -> None:
        self.raw = raw
        self.reason = reason
        super().__init__(f"Invalid ID {raw!r}: {reason}")


# Data classes


@dataclass(frozen=True)
class RoomIdParts:
    """Decoded room identifier components."""

    house_id: int
    room_id: int
    dateupdate: datetime


@dataclass(frozen=True)
class HouseIdParts:
    """Decoded house identifier components."""

    house_id: int
    dateupdate: datetime


# Patterns

_ISO_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"

_ROOM_ID_RE = re.compile(rf"^H(\d+)_R(\d+)_({_ISO_PATTERN})$")
_HOUSE_ID_RE = re.compile(rf"^H(\d+)_({_ISO_PATTERN})$")


# Room ID encoder/decoder


def encode_room_id(house_id: int, room_id: int, dateupdate: datetime) -> str:
    """Encode a composite room key into the opaque string format."""
    if house_id < 0 or room_id < 0:
        raise ValueError(
            f"house_id and room_id must be non-negative "
            f"(got house_id={house_id}, room_id={room_id})"
        )

    if dateupdate.tzinfo is not None:
        dateupdate = dateupdate.replace(tzinfo=None)

    return f"H{house_id}_R{room_id}_{dateupdate.isoformat()}"


def decode_room_id(raw: str) -> RoomIdParts:
    """Parse an encoded room ID string."""
    if not isinstance(raw, str):
        raise InvalidRoomIdError(str(raw), "must be a string")
    if not raw:
        raise InvalidRoomIdError(raw, "empty string")

    match = _ROOM_ID_RE.match(raw)
    if match is None:
        raise InvalidRoomIdError(
            raw, "expected format 'H{house_id}_R{room_id}_{ISO8601_dateupdate}'"
        )

    house_id_str, room_id_str, iso = match.groups()
    try:
        dateupdate = datetime.fromisoformat(iso)
    except ValueError as e:
        raise InvalidRoomIdError(raw, f"invalid ISO8601 timestamp {iso!r}") from e

    return RoomIdParts(
        house_id=int(house_id_str),
        room_id=int(room_id_str),
        dateupdate=dateupdate,
    )


# House ID encoder/decoder


def encode_house_id(house_id: int, dateupdate: datetime) -> str:
    """Encode a composite house key into the opaque string format."""
    if house_id < 0:
        raise ValueError(f"house_id must be non-negative (got {house_id})")
    if dateupdate.tzinfo is not None:
        dateupdate = dateupdate.replace(tzinfo=None)
    return f"H{house_id}_{dateupdate.isoformat()}"


def decode_house_id(raw: str) -> HouseIdParts:
    """Parse an encoded house ID string."""
    if not isinstance(raw, str):
        raise InvalidRoomIdError(str(raw), "must be a string")
    if not raw:
        raise InvalidRoomIdError(raw, "empty string")

    match = _HOUSE_ID_RE.match(raw)
    if match is None:
        raise InvalidRoomIdError(raw, "expected format 'H{house_id}_{ISO8601_dateupdate}'")

    house_id_str, iso = match.groups()
    try:
        dateupdate = datetime.fromisoformat(iso)
    except ValueError as e:
        raise InvalidRoomIdError(raw, f"invalid ISO8601 timestamp {iso!r}") from e

    return HouseIdParts(house_id=int(house_id_str), dateupdate=dateupdate)


# Convenience predicates


def is_room_id(raw: str) -> bool:
    """Return True id ``raw`` matches the room ID format."""
    return isinstance(raw, str) and bool(_ROOM_ID_RE.match(raw))


def is_house_id(raw: str) -> bool:
    """Return True if ``raw`` matches the house ID format (and not room)."""
    if not isinstance(raw, str):
        return False

    return bool(_HOUSE_ID_RE.match(raw)) and not _ROOM_ID_RE.match(raw)
