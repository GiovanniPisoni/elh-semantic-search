"""Tests for room/house ID encoder-decoder.

The encoded format is opaque ``str``:
    * room: ``"{idhouse}|{idroom}|{ISO8601}"``
    * house: ``"{idhouse}|{ISO8601}"``

Encoders accept either ``int`` (test fakes) or ``str`` (production raw
``character()`` columns, possibly padded with whitespace). Decoders
always return ``str`` IDs.
"""

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
    normalize_id,
)

# normalize_id


class TestNormalizeId:
    def test_int_passes_through_as_str(self):
        assert normalize_id(42, name="x") == "42"

    def test_zero_int_allowed(self):
        assert normalize_id(0, name="x") == "0"

    def test_str_passes_through(self):
        assert normalize_id("HSE_001", name="x") == "HSE_001"

    def test_padded_str_stripped(self):
        """character(N) returns right-padded values."""
        assert normalize_id("HSE_00F7359B" + " " * 50, name="x") == "HSE_00F7359B"
        assert normalize_id("  42  ", name="x") == "42"

    def test_empty_str_raises(self):
        with pytest.raises(ValueError, match="empty"):
            normalize_id("", name="x")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            normalize_id("     ", name="x")

    def test_pipe_in_value_raises(self):
        """The pipe is reserved for the encoded format; reject loudly."""
        with pytest.raises(ValueError, match="separator"):
            normalize_id("HSE|001", name="x")

    def test_other_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="must be int or str"):
            normalize_id(3.14, name="x")  # type: ignore[arg-type]

    def test_bool_rejected_explicitly(self):
        """``bool`` is technically ``int`` but semantically wrong here."""
        with pytest.raises(TypeError, match="bool"):
            normalize_id(True, name="x")  # type: ignore[arg-type]

    def test_error_message_includes_field_name(self):
        with pytest.raises(ValueError, match="my_custom_field"):
            normalize_id("foo|bar", name="my_custom_field")


# Room ID — encoding


class TestEncodeRoomId:
    def test_int_inputs(self):
        result = encode_room_id(42, 3, datetime(2024, 9, 15, 10, 30, 0))
        assert result == "42|3|2024-09-15T10:30:00"

    def test_opaque_str_inputs(self):
        result = encode_room_id(
            "HSE_00F7359B", "RM_001", datetime(2024, 9, 15, 10, 30, 0)
        )
        assert result == "HSE_00F7359B|RM_001|2024-09-15T10:30:00"

    def test_padded_str_inputs(self):
        """Real psycopg2 row from character() columns."""
        result = encode_room_id(
            "HSE_00F7359B" + " " * 50,
            "RM_001" + " " * 14,
            datetime(2024, 9, 15, 10, 30, 0),
        )
        assert result == "HSE_00F7359B|RM_001|2024-09-15T10:30:00"

    def test_mixed_int_str_inputs(self):
        result = encode_room_id(42, "RM_001", datetime(2024, 9, 15, 10, 30, 0))
        assert result == "42|RM_001|2024-09-15T10:30:00"

    def test_microseconds_preserved(self):
        result = encode_room_id(1, 1, datetime(2024, 1, 1, 0, 0, 0, 123456))
        assert result == "1|1|2024-01-01T00:00:00.123456"

    def test_drops_timezone_info(self):
        utc_dt = datetime(2024, 9, 15, 10, 30, tzinfo=UTC)
        result = encode_room_id(42, 3, utc_dt)
        assert result == "42|3|2024-09-15T10:30:00"

    def test_zero_ids_allowed(self):
        result = encode_room_id(0, 0, datetime(2024, 1, 1))
        assert result == "0|0|2024-01-01T00:00:00"

    def test_pipe_in_house_id_raises(self):
        with pytest.raises(ValueError, match="separator"):
            encode_room_id("HSE|001", "RM_001", datetime(2024, 1, 1))

    def test_pipe_in_room_id_raises(self):
        with pytest.raises(ValueError, match="separator"):
            encode_room_id("HSE_001", "RM|001", datetime(2024, 1, 1))


# Room ID — decoding


class TestDecodeRoomId:
    def test_round_trip_with_int(self):
        encoded = encode_room_id(42, 3, datetime(2024, 9, 15, 10, 30))
        result = decode_room_id(encoded)
        assert isinstance(result, RoomIdParts)
        assert result.house_id == "42"
        assert result.room_id == "3"
        assert result.dateupdate == datetime(2024, 9, 15, 10, 30)

    def test_round_trip_with_opaque(self):
        encoded = encode_room_id(
            "HSE_00F7359B", "RM_001", datetime(2024, 9, 15, 10, 30)
        )
        result = decode_room_id(encoded)
        assert result.house_id == "HSE_00F7359B"
        assert result.room_id == "RM_001"
        assert result.dateupdate == datetime(2024, 9, 15, 10, 30)

    def test_microseconds_round_trip(self):
        result = decode_room_id("1|1|2024-01-01T00:00:00.123456")
        assert result.dateupdate == datetime(2024, 1, 1, 0, 0, 0, 123456)

    def test_invalid_format_no_pipes(self):
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("garbage")

    def test_invalid_format_one_pipe(self):
        """A house ID format must NOT decode as a room ID."""
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("42|2024-09-15T10:30:00")

    def test_invalid_format_extra_pipe(self):
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("42|3|2024-09-15T10:30:00|extra")

    def test_invalid_iso_timestamp(self):
        with pytest.raises(InvalidRoomIdError):
            decode_room_id("42|3|2024-02-30T10:30:00")  # invalid date

    def test_empty_string_raises(self):
        with pytest.raises(InvalidRoomIdError, match="empty"):
            decode_room_id("")

    def test_non_string_raises(self):
        with pytest.raises(InvalidRoomIdError):
            decode_room_id(42)  # type: ignore[arg-type]


# House ID — encoding


class TestEncodeHouseId:
    def test_int_input(self):
        result = encode_house_id(42, datetime(2024, 9, 15, 10, 30))
        assert result == "42|2024-09-15T10:30:00"

    def test_opaque_str_input(self):
        result = encode_house_id("HSE_00F7359B", datetime(2024, 9, 15, 10, 30))
        assert result == "HSE_00F7359B|2024-09-15T10:30:00"

    def test_padded_str_input(self):
        result = encode_house_id(
            "HSE_001" + " " * 50, datetime(2024, 9, 15, 10, 30)
        )
        assert result == "HSE_001|2024-09-15T10:30:00"

    def test_pipe_in_id_raises(self):
        with pytest.raises(ValueError, match="separator"):
            encode_house_id("HSE|001", datetime(2024, 1, 1))


# House ID — decoding


class TestDecodeHouseId:
    def test_round_trip_int(self):
        encoded = encode_house_id(42, datetime(2024, 9, 15, 10, 30))
        result = decode_house_id(encoded)
        assert isinstance(result, HouseIdParts)
        assert result.house_id == "42"
        assert result.dateupdate == datetime(2024, 9, 15, 10, 30)

    def test_round_trip_opaque(self):
        encoded = encode_house_id("HSE_001", datetime(2024, 9, 15, 10, 30))
        result = decode_house_id(encoded)
        assert result.house_id == "HSE_001"

    def test_room_id_format_rejected(self):
        """A room ID format (3 segments) must NOT decode as a house ID."""
        with pytest.raises(InvalidRoomIdError):
            decode_house_id("42|3|2024-09-15T10:30:00")

    def test_invalid_iso(self):
        with pytest.raises(InvalidRoomIdError):
            decode_house_id("42|2024-13-99T10:30:00")


# Predicates


class TestPredicates:
    def test_is_room_id_true_for_int_format(self):
        assert is_room_id("42|3|2024-09-15T10:30:00") is True

    def test_is_room_id_true_for_opaque_format(self):
        assert is_room_id("HSE_001|RM_001|2024-09-15T10:30:00") is True

    def test_is_room_id_false_for_house(self):
        assert is_room_id("42|2024-09-15T10:30:00") is False

    def test_is_room_id_false_for_garbage(self):
        assert is_room_id("hello world") is False

    def test_is_room_id_false_for_non_string(self):
        assert is_room_id(42) is False  # type: ignore[arg-type]

    def test_is_house_id_true(self):
        assert is_house_id("42|2024-09-15T10:30:00") is True

    def test_is_house_id_true_opaque(self):
        assert is_house_id("HSE_001|2024-09-15T10:30:00") is True

    def test_is_house_id_false_for_room(self):
        """A room ID must NOT be reported as a valid house ID."""
        assert is_house_id("42|3|2024-09-15T10:30:00") is False

    def test_is_house_id_false_for_garbage(self):
        assert is_house_id("foo") is False