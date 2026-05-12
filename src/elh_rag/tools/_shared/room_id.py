"""
Encoder/decoder for room and house identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

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

    house_id: str
    room_id: str
    dateupdate: datetime


@dataclass(frozen=True)
class HouseIdParts:
    """Decoded house identifier components."""

    house_id: str
    dateupdate: datetime


# Constants

_SEP = "|"

_ISO_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"

_ROOM_ID_RE = re.compile(rf"^(.+?)\|(.+?)\|({_ISO_PATTERN})$")
_HOUSE_ID_RE = re.compile(rf"^(.+?)\|({_ISO_PATTERN})$")


# ID normalization


def normalize_id(value: int | str, name: str = "id") -> str:
    """Normalize a DB-side identifier to a clean opaque ``str``."""
    if isinstance(value, bool):  # bool subclasses int; reject for clarity
        raise TypeError(f"{name} must be int or str, got bool")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{name} must be non-negative (got {value})")
        s = str(value)
    elif isinstance(value, str):
        s = value.strip()
    else:
        raise TypeError(f"{name} must be int or str, got {type(value).__name__}")

    if not s:
        raise ValueError(f"{name} must not be empty")
    if _SEP in s:
        raise ValueError(
            f"{name}={s!r} contains the reserved separator {_SEP!r} "
            f"used by encode_room_id/encode_house_id"
        )
    return s


def _coerce_dateupdate(value: date | datetime) -> datetime:
    """Coerce a Postgres ``date`` or ``timestamp`` cell to a naive ``datetime``."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raise TypeError(f"dateupdate must be date or datetime, got {type(value).__name__}")


# Room ID encoder/decoder


def encode_room_id(house_id: int | str, room_id: int | str, dateupdate: date | datetime) -> str:
    """Encode a composite room key into the opaque string format."""
    h = normalize_id(house_id, name="house_id")
    r = normalize_id(room_id, name="room_id")
    dt = _coerce_dateupdate(dateupdate)

    return f"{h}{_SEP}{r}{_SEP}{dt.isoformat()}"


def decode_room_id(raw: str) -> RoomIdParts:
    """Parse an encoded room ID string."""
    if not isinstance(raw, str):
        raise InvalidRoomIdError(str(raw), "must be a string")
    if not raw:
        raise InvalidRoomIdError(raw, "empty string")

    match = _ROOM_ID_RE.match(raw)
    if match is None:
        raise InvalidRoomIdError(
            raw,
            f"expected format '{{house_id}}{_SEP}{{room_id}}{_SEP}{{ISO8601_dateupdate}}'",
        )

    house_id, room_id, iso = match.groups()
    try:
        dateupdate = datetime.fromisoformat(iso)
    except ValueError as e:
        raise InvalidRoomIdError(raw, f"invalid ISO8601 timestamp {iso!r}") from e

    return RoomIdParts(
        house_id=house_id,
        room_id=room_id,
        dateupdate=dateupdate,
    )


# House ID encoder/decoder


def encode_house_id(house_id: int | str, dateupdate: date | datetime) -> str:
    """Encode a composite house key into the opaque string format.

    Format: ``"{house_id}|{ISO8601_dateupdate}"``.
    """
    h = normalize_id(house_id, name="house_id")
    dt = _coerce_dateupdate(dateupdate)
    return f"{h}{_SEP}{dt.isoformat()}"


def decode_house_id(raw: str) -> HouseIdParts:
    """Parse an encoded house ID string."""
    if not isinstance(raw, str):
        raise InvalidRoomIdError(str(raw), "must be a string")
    if not raw:
        raise InvalidRoomIdError(raw, "empty string")

    if _ROOM_ID_RE.match(raw):
        raise InvalidRoomIdError(raw, "looks like a room ID; use decode_room_id instead")

    match = _HOUSE_ID_RE.match(raw)
    if match is None:
        raise InvalidRoomIdError(
            raw,
            f"expected format '{{house_id}}{_SEP}{{ISO8601_dateupdate}}'",
        )

    house_id, iso = match.groups()
    try:
        dateupdate = datetime.fromisoformat(iso)
    except ValueError as e:
        raise InvalidRoomIdError(raw, f"invalid ISO8601 timestamp {iso!r}") from e

    return HouseIdParts(house_id=house_id, dateupdate=dateupdate)


# Convenience predicates


def is_room_id(raw: str) -> bool:
    """Return True if ``raw`` matches the room ID format."""
    return isinstance(raw, str) and bool(_ROOM_ID_RE.match(raw))


def is_house_id(raw: str) -> bool:
    """Return True if ``raw`` matches the house ID format (and not room)."""
    if not isinstance(raw, str):
        return False
    return bool(_HOUSE_ID_RE.match(raw)) and not _ROOM_ID_RE.match(raw)
