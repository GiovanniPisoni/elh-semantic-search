"""Tests for Tool 2 (``find_available_rooms``).

Covers:
    * Input model validation (Step 1 — preserved).
    * Tool registration & dispatch.
    * End-to-end orchestration: 3-query sequence with FakeDbExecutor,
      reservation filtering, price enrichment.
    * Edge cases: empty Tool 1 result, all-occupied, race condition.

The deep calendar arithmetic of the overlap and the weighted-price
math live in ``test_reservation.py`` and ``test_pricing.py`` and are
not duplicated here.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from tests.conftest import FakeDbExecutor

from elh_rag.tools import TOOLS_REGISTRY, execute_tool
from elh_rag.tools._shared.room_id import encode_house_id, encode_room_id
from elh_rag.tools.find_available_rooms import (
    _MAX_PERIOD_DAYS,
    FindAvailableRoomsInput,
    _fetch_seasonal_prices,
    find_available_rooms,
)
from elh_rag.tools.find_rooms import FindRoomsInput

# Step 1 tests — input validation


class TestRequiredFields:
    def test_minimal_valid_input(self):
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2027, 1, 31),
        )
        assert p.available_from == date(2026, 9, 1)
        assert p.available_to == date(2027, 1, 31)
        assert p.num_rooms_needed == 1
        assert p.max_results == 10
        assert p.sort_by == "default"
        assert p.city is None

    def test_missing_available_from_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(available_to=date(2027, 1, 31))  # type: ignore[call-arg]
        assert "available_from" in str(exc_info.value)

    def test_missing_available_to_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(available_from=date(2026, 9, 1))  # type: ignore[call-arg]
        assert "available_to" in str(exc_info.value)

    def test_both_dates_missing_rejected(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput()  # type: ignore[call-arg]

    def test_explicit_none_rejected_for_required_fields(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=None,  # type: ignore[arg-type]
                available_to=date(2027, 1, 31),
            )


class TestInheritance:
    def test_is_subclass_of_find_rooms_input(self):
        assert issubclass(FindAvailableRoomsInput, FindRoomsInput)

    def test_inherited_fields_accept_values(self):
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2027, 1, 31),
            city="Lisbon",
            metro_line="green",
            max_price_eur=500,
            gender_preference="female_only",
            accepts_couples=True,
            num_rooms_needed=3,
            required_other_amenities=["shared_space", "wheelchair_accessible"],
            sort_by="price_asc",
            max_results=20,
        )
        assert p.city == "Lisbon"
        assert p.metro_line == "green"
        assert p.max_price_eur == 500
        assert p.gender_preference == "female_only"
        assert p.num_rooms_needed == 3
        assert p.required_other_amenities == ["shared_space", "wheelchair_accessible"]
        assert p.sort_by == "price_asc"
        assert p.max_results == 20

    def test_inherited_constraints_still_apply(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
                num_rooms_needed=0,
            )
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
                max_price_eur=-50,
            )


class TestDateOrdering:
    def test_dates_inverted_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(
                available_from=date(2027, 1, 31),
                available_to=date(2026, 9, 1),
            )
        assert "available_to must be after available_from" in str(exc_info.value)

    def test_same_day_rejected(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2026, 9, 1),
            )

    def test_minimum_one_day_period_accepted(self):
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2026, 9, 2),
        )
        assert (p.available_to - p.available_from).days == 1


class TestPeriodBounds:
    def test_period_exactly_at_limit_accepted(self):
        from datetime import timedelta

        start = date(2026, 1, 1)
        end = start + timedelta(days=_MAX_PERIOD_DAYS)
        p = FindAvailableRoomsInput(available_from=start, available_to=end)
        assert (p.available_to - p.available_from).days == _MAX_PERIOD_DAYS

    def test_period_one_day_over_limit_rejected(self):
        from datetime import timedelta

        start = date(2026, 1, 1)
        end = start + timedelta(days=_MAX_PERIOD_DAYS + 1)
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(available_from=start, available_to=end)
        assert "too long" in str(exc_info.value).lower()

    def test_typical_erasmus_periods_accepted(self):
        cases = [
            (date(2026, 7, 1), date(2026, 7, 31)),
            (date(2026, 9, 1), date(2027, 1, 31)),
            (date(2026, 9, 1), date(2027, 7, 31)),
            (date(2026, 5, 15), date(2026, 8, 31)),
        ]
        for start, end in cases:
            p = FindAvailableRoomsInput(available_from=start, available_to=end)
            assert p.available_from == start
            assert p.available_to == end


class TestTypeCoercion:
    def test_iso_string_dates_coerced(self):
        p = FindAvailableRoomsInput(
            available_from="2026-09-01",  # type: ignore[arg-type]
            available_to="2027-01-31",  # type: ignore[arg-type]
        )
        assert p.available_from == date(2026, 9, 1)
        assert p.available_to == date(2027, 1, 31)

    def test_malformed_date_string_rejected(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from="not-a-date",  # type: ignore[arg-type]
                available_to=date(2027, 1, 31),
            )


# Step 4 tests — orchestration

# Helpers


def _make_room_row(idroom: int, idhouse: int = 42, **overrides: Any) -> dict[str, Any]:
    """Build a fake row matching find_rooms' SELECT projection.

    Defaults are sane and overridable for per-test customisation. The
    encoded room_id is then ``f"H{idhouse}_R{idroom}_..."`` after
    Tool 1's ``_row_to_match`` runs.
    """
    base = {
        "idroom": idroom,
        "loc_idhouse": idhouse,
        "r_dateupdate": datetime(2024, 9, 15, 10, 30),
        "loc_dateupdate": datetime(2024, 9, 15, 10, 30),
        "price_eur": 450.0,
        "privatebathroom": "Y",
        "minreservemonths": 5,
        "room_description": f"Room {idroom} in house {idhouse}",
        "haswindow": "Y",
        "idhouse": idhouse,
        "h_dateupdate": datetime(2024, 9, 15, 10, 30),
        "city": "Lisbon",
        "zone": "Chiado",
        "neighborhood": "Chiado",
        "distancepublictransport": 200,
        "maxoccupancy": 5,
    }
    base.update(overrides)
    return base


def _make_price_row(
    idroom: int,
    idhouse: int = 42,
    spring: str = "400.00",
    summer: str = "300.00",
    autumn: str = "500.00",
    fixed: str = "N",
) -> dict[str, Any]:
    """Build a row for the seasonal prices SELECT."""
    return {
        "loc_idhouse": idhouse,
        "idroom": idroom,
        "springprice": Decimal(spring),
        "summerprice": Decimal(summer),
        "autumnprice": Decimal(autumn),
        "fixedprice": fixed,
    }


# Registration


class TestRegistration:
    def test_tool_is_registered(self):
        assert "find_available_rooms" in TOOLS_REGISTRY

    def test_tool_accepts_ctx(self):
        spec = TOOLS_REGISTRY["find_available_rooms"]
        assert spec.accepts_ctx is True

    def test_tool_input_model_is_correct_class(self):
        spec = TOOLS_REGISTRY["find_available_rooms"]
        assert spec.input_model is FindAvailableRoomsInput

    def test_tool_description_mentions_date_window(self):
        spec = TOOLS_REGISTRY["find_available_rooms"]
        # Sanity check: the LLM-facing description should make the
        # difference vs find_rooms obvious.
        desc_lower = spec.description.lower()
        assert "date" in desc_lower or "available_from" in desc_lower
        assert "find_rooms" in spec.description  # cross-references


# End-to-end orchestration


class TestOrchestration:
    def test_no_structural_matches_returns_empty(self):
        """Tool 1 returns 0 rooms → skip overlap and price queries."""
        db = FakeDbExecutor()
        # Tool 1 SQL contains "JOIN house h"
        db.add_response("JOIN house h", [])

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
            ctx=db,
        )

        assert result.rooms == []
        assert result.total_matches == 0
        # Only the Tool 1 query was issued — no reservation, no prices
        assert len(db.calls) == 1
        assert "available 2026-09-01 → 2027-01-31" in result.query_summary

    def test_all_rooms_occupied_returns_empty(self):
        """Tool 1 returns rooms but every one is occupied → skip prices."""
        db = FakeDbExecutor()
        db.add_response("JOIN house h", [_make_room_row(idroom=3)])
        db.add_response("FROM reservation", [{"loc_idhouse": 42, "idroom": 3}])

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
            ctx=db,
        )

        assert result.rooms == []
        # Only 2 queries: structural + reservation. NO price lookup.
        assert len(db.calls) == 2

    def test_no_occupancy_returns_all_with_weighted_price(self):
        """Three rooms, none occupied, all-autumn period → autumn price."""
        db = FakeDbExecutor()
        db.add_response(
            "JOIN house h",
            [
                _make_room_row(idroom=3),
                _make_room_row(idroom=4),
                _make_room_row(idroom=5),
            ],
        )
        db.add_response("FROM reservation", [])
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [
                _make_price_row(idroom=3, autumn="500.00"),
                _make_price_row(idroom=4, autumn="600.00"),
                _make_price_row(idroom=5, autumn="450.00"),
            ],
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),  # 100% autumn
            ),
            ctx=db,
        )

        assert len(result.rooms) == 3
        prices = {rm.price_per_month_eur for rm in result.rooms}
        assert prices == {500.00, 600.00, 450.00}
        # All 3 queries fired
        assert len(db.calls) == 3

    def test_partial_occupancy_filters_correctly(self):
        """Three rooms, one occupied → two survive."""
        db = FakeDbExecutor()
        db.add_response(
            "JOIN house h",
            [
                _make_room_row(idroom=3),
                _make_room_row(idroom=4),
                _make_room_row(idroom=5),
            ],
        )
        db.add_response("FROM reservation", [{"loc_idhouse": 42, "idroom": 4}])
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [_make_price_row(idroom=3), _make_price_row(idroom=5)],
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
            ctx=db,
        )

        assert len(result.rooms) == 2
        room_ids = {_decoded_idroom(rm.room_id) for rm in result.rooms}
        assert room_ids == {"3", "5"}

    def test_average_price_cross_season(self):
        """15 May → 31 Aug = 4 calendar months (May, Jun spring + Jul, Aug summer).

        Model B: each calendar month bills at its seasonal rate, the display
        price is the arithmetic mean of those rents.
            (2 x 400 + 2 x 300) / 4 = 1400 / 4 = 350.00
        """
        db = FakeDbExecutor()
        db.add_response("JOIN house h", [_make_room_row(idroom=3)])
        db.add_response("FROM reservation", [])
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [_make_price_row(idroom=3, spring="400.00", summer="300.00")],
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 5, 15),
                available_to=date(2026, 8, 31),
            ),
            ctx=db,
        )

        assert len(result.rooms) == 1
        # Model B billing: May+Jun at spring rate, Jul+Aug at summer rate
        assert result.rooms[0].price_per_month_eur == 350.00
        # Sanity: the contextual label exposes the seasonal composition
        label = result.rooms[0].price_label
        assert "spring rate €400.00" in label
        assert "summer rate €300.00" in label
        assert "average over 4 months" in label

    def test_fixed_price_room_flagged(self):
        db = FakeDbExecutor()
        db.add_response("JOIN house h", [_make_room_row(idroom=3)])
        db.add_response("FROM reservation", [])
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [
                _make_price_row(
                    idroom=3,
                    spring="400.00",
                    summer="400.00",
                    autumn="400.00",
                    fixed="Y",
                )
            ],
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 5, 15),
                available_to=date(2026, 8, 31),
            ),
            ctx=db,
        )

        assert len(result.rooms) == 1
        assert result.rooms[0].price_per_month_eur == 400.00
        assert result.rooms[0].is_fixed_price is True

    def test_available_from_propagated_to_room_match(self):
        """RoomMatch.available_from should reflect the query window, not None."""
        db = FakeDbExecutor()
        db.add_response("JOIN house h", [_make_room_row(idroom=3)])
        db.add_response("FROM reservation", [])
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [_make_price_row(idroom=3)],
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
            ctx=db,
        )

        assert result.rooms[0].available_from == date(2026, 9, 1)


# Defensive guards


class TestGuards:
    def test_missing_ctx_raises_via_dispatcher(self):
        """ctx=None → execute_tool wraps the RuntimeError as ToolExecutionError."""
        from elh_rag.tools import ToolExecutionError

        with pytest.raises(ToolExecutionError) as exc_info:
            execute_tool(
                "find_available_rooms",
                {
                    "available_from": "2026-09-01",
                    "available_to": "2027-01-31",
                },
                ctx=None,
            )
        assert "DBExecutor" in str(exc_info.value)

    def test_race_condition_room_disappears_between_queries(self):
        """If a room is in Tool 1's result but missing from price lookup,
        skip rather than guess. Defensive: should never happen in practice."""
        db = FakeDbExecutor()
        db.add_response(
            "JOIN house h",
            [_make_room_row(idroom=3), _make_room_row(idroom=4)],
        )
        db.add_response("FROM reservation", [])
        # Only one of the two rooms shows up in the price lookup
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [_make_price_row(idroom=3)],  # idroom=4 missing
        )

        result = find_available_rooms(
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
            ctx=db,
        )

        assert len(result.rooms) == 1
        assert _decoded_idroom(result.rooms[0].room_id) == "3"


# _fetch_seasonal_prices unit tests


class TestFetchSeasonalPrices:
    def test_empty_keys_returns_empty_dict_no_db_call(self):
        db = FakeDbExecutor()
        result = _fetch_seasonal_prices(db, [])
        assert result == {}
        assert db.calls == []

    def test_single_key_dispatches_correct_sql(self):
        db = FakeDbExecutor()
        db.add_response(
            "DISTINCT ON (loc_idhouse, idroom)",
            [_make_price_row(idroom=3)],
        )

        result = _fetch_seasonal_prices(db, [("42", "3")])

        assert ("42", "3") in result
        assert result[("42", "3")]["springprice"] == Decimal("400.00")
        assert result[("42", "3")]["fixedprice"] == "N"

    def test_sql_has_distinct_on_for_versioning(self):
        """Anti-regression sentinel: DISTINCT ON must be present to dedupe versions."""
        db = FakeDbExecutor()
        db.add_response("DISTINCT ON", [])
        _fetch_seasonal_prices(db, [(42, 3)])

        sql = db.calls[0]["sql"]
        assert "DISTINCT ON (loc_idhouse, idroom)" in sql
        assert "ORDER BY" in sql
        assert "dateupdate DESC" in sql

    def test_param_count_matches_keys(self):
        """For N keys, 2N params (loc_idhouse, idroom for each)."""
        db = FakeDbExecutor()
        db.add_response("DISTINCT ON", [])
        keys = [(42, 1), (42, 2), (100, 3)]
        _fetch_seasonal_prices(db, keys)

        params = db.calls[0]["params"]
        assert len(params) == 6  # 3 keys x 2
        assert params == (42, 1, 42, 2, 100, 3)


# Helper used by orchestration tests


def _decoded_idroom(encoded_id: str) -> str:
    """Quick helper to extract the room number from an encoded room_id."""
    from elh_rag.tools._shared.room_id import decode_room_id

    return decode_room_id(encoded_id).room_id


# Sanity: encoded IDs are exactly what the tool produces


def test_room_match_keys_round_trip_with_helper():
    """Sanity: the helper used internally agrees with manual encoding."""
    from elh_rag.tools.find_available_rooms import _room_match_keys
    from elh_rag.tools.find_rooms import RoomMatch

    rm = RoomMatch(
        room_id=encode_room_id(42, 3, datetime(2024, 9, 15, 10, 30)),
        house_id=encode_house_id(42, datetime(2024, 9, 15, 10, 30)),
        house_name="x",
        city="Lisbon",
        zone="Chiado",
        neighborhood="Chiado",
        price_per_month_eur=400.0,
        private_bathroom=True,
        distance_to_transport_m=200,
        nearest_metro_line=None,
        available_from=None,
        min_reserve_months=5,
    )
    assert _room_match_keys(rm) == ("42", "3")


def test_find_rooms_sql_uses_db_correct_neighboorhood_spelling():
    """Tool 1's SQL must reference the actual DB column name."""
    from elh_rag.tools.find_rooms import FindRoomsInput, _build_sql

    sql, _ = _build_sql(FindRoomsInput(metro_line="green", near_landmark="NOVA"))
    # The DB column has two 'o's. If anyone "corrects" this, the smoke
    # test against Supabase will crash. Pin it here.
    assert "neighboorhood" in sql, (
        "find_rooms SQL must use 'neighboorhood' (DB column with original "
        "ELH typo). Detected the wrong spelling 'neighbourhood'."
    )
    assert "h.neighbourhood" not in sql, (
        "find_rooms SQL must NOT use 'neighbourhood' (English-correct but "
        "absent in the ELH DB). Use 'neighboorhood' to match the column."
    )
