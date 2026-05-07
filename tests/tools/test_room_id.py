"""Tests for room/house ID encoder-decoder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from elh_rag.tools._room_id import (
    HouseIdParts,
    InvalidRoomIdError,
    RoomIdParts,
    decode_house_id,
    decode_room_id,
    encode_house_id,
    encode_room_id,
    is_house_id,
    is_room_id,
)

# Room ID


class TestEncodeRoomId:
    def test_basic_encoding(self):
        result = encode_room_id(42, 3, datetime(2024, 9, 15, 10, 30, 0))
        assert result == "H42_R3_2024-09-15T10:30:00"

    def test_encoding_with_microseconds(self):
        result = encode_room_id(1, 1, datetime(2024, 1, 1, 0, 0, 0, 123456))
        assert result == "H1_R1_2024-01-01T00:00:00.123456"

    def test_encoding_drops_timezone_info(self):
        """Aware datetimes are normalised to naive (DB has no tz)."""
        utc_dt = datetime(2024, 9, 15, 10, 30, tzinfo=UTC)
        result = encode_room_id(42, 3, utc_dt)
        # No '+00:00' suffix in result
        assert result == "H42_R3_2024-09-15T10:30:00"

    def test_zero_ids_allowed(self):
        result = encode_room_id(0, 0, datetime(2024, 1, 1))
        assert result == "H0_R0_2024-01-01T00:00:00"

    def test_negative_house_id_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            encode_room_id(-1, 3, datetime(2024, 1, 1))

    def test_negative_room_id_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            encode_room_id(42, -1, datetime(2024, 1, 1))


class TestDecodeRoomId:
    def test_basic_decoding(self):
        result = decode_room_id("H42_R3_2024-09-15T10:30:00")
        assert result == RoomIdParts(
            house_id=42,
            room_id=3,
            dateupdate=datetime(2024, 9, 15, 10, 30, 0),
        )

    def test_decoding_with_microseconds(self):
        result = decode_room_id("H1_R1_2024-01-01T00:00:00.123456")
        assert result.dateupdate == datetime(2024, 1, 1, 0, 0, 0, 123456)

    def test_round_trip(self):
        """Encoding then decoding must give back the original."""
        original = (42, 3, datetime(2024, 9, 15, 10, 30, 0))
        encoded = encode_room_id(*original)
        decoded = decode_room_id(encoded)
        assert (decoded.house_id, decoded.room_id, decoded.dateupdate) == original

    def test_round_trip_large_ids(self):
        original = (999999, 12345, datetime(2099, 12, 31, 23, 59, 59))
        encoded = encode_room_id(*original)
        decoded = decode_room_id(encoded)
        assert (decoded.house_id, decoded.room_id, decoded.dateupdate) == original

    def test_empty_string_raises(self):
        with pytest.raises(InvalidRoomIdError, match="empty"):
            decode_room_id("")

    def test_non_string_raises(self):
        with pytest.raises(InvalidRoomIdError, match="must be a string"):
            decode_room_id(42)  # type: ignore[arg-type]

    def test_missing_h_prefix_raises(self):
        with pytest.raises(InvalidRoomIdError, match="expected format"):
            decode_room_id("42_R3_2024-09-15T10:30:00")

    def test_missing_r_prefix_raises(self):
        with pytest.raises(InvalidRoomIdError, match="expected format"):
            decode_room_id("H42_3_2024-09-15T10:30:00")

    def test_missing_separator_raises(self):
        with pytest.raises(InvalidRoomIdError, match="expected format"):
            decode_room_id("H42-R3-2024-09-15T10:30:00")

    def test_invalid_iso_date_raises(self):
        # Pattern is matched but date is invalid (Feb 30)
        with pytest.raises(InvalidRoomIdError, match="invalid ISO8601"):
            decode_room_id("H42_R3_2024-02-30T10:30:00")

    def test_house_id_format_rejected_by_room_decoder(self):
        """A house ID must not be accepted as a room ID."""
        with pytest.raises(InvalidRoomIdError, match="expected format"):
            decode_room_id("H42_2024-09-15T10:30:00")

    def test_extra_suffix_rejected(self):
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("H42_R3_2024-09-15T10:30:00_extra")

    def test_negative_ids_in_string_rejected(self):
        # Regex doesn't allow '-' in id slots
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("H-1_R3_2024-09-15T10:30:00")


# House ID


class TestHouseId:
    def test_encode_basic(self):
        result = encode_house_id(42, datetime(2024, 9, 15, 10, 30))
        assert result == "H42_2024-09-15T10:30:00"

    def test_decode_basic(self):
        result = decode_house_id("H42_2024-09-15T10:30:00")
        assert result == HouseIdParts(house_id=42, dateupdate=datetime(2024, 9, 15, 10, 30))

    def test_round_trip(self):
        original = (42, datetime(2024, 9, 15, 10, 30))
        encoded = encode_house_id(*original)
        decoded = decode_house_id(encoded)
        assert (decoded.house_id, decoded.dateupdate) == original

    def test_negative_house_id_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            encode_house_id(-1, datetime(2024, 1, 1))

    def test_room_id_format_rejected_by_house_decoder(self):
        """A room ID must not be accepted as a house ID."""
        with pytest.raises(InvalidRoomIdError):
            decode_house_id("H42_R3_2024-09-15T10:30:00")

    def test_empty_raises(self):
        with pytest.raises(InvalidRoomIdError):
            decode_house_id("")


# Predicates


class TestPredicates:
    def test_is_room_id_true(self):
        assert is_room_id("H42_R3_2024-09-15T10:30:00") is True

    def test_is_room_id_false_for_house(self):
        assert is_room_id("H42_2024-09-15T10:30:00") is False

    def test_is_room_id_false_for_garbage(self):
        assert is_room_id("hello world") is False

    def test_is_room_id_false_for_non_string(self):
        assert is_room_id(42) is False  # type: ignore[arg-type]

    def test_is_house_id_true(self):
        assert is_house_id("H42_2024-09-15T10:30:00") is True

    def test_is_house_id_false_for_room(self):
        """A room ID must NOT be reported as a valid house ID,
        even though parts of it look house-like."""
        assert is_house_id("H42_R3_2024-09-15T10:30:00") is False

    def test_is_house_id_false_for_garbage(self):
        assert is_house_id("foo") is False
