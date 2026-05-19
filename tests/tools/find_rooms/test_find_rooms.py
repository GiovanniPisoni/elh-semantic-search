"""Integration tests for the find_rooms tool.

Tests the full flow: input validation -> SQL build -> dispatch via the
registry -> row mapping -> output dataclass. Uses FakeDbExecutor so no
real Postgres is needed.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError
from tests.conftest import FakeDbExecutor

from elh_rag.tools import (
    ToolExecutionError,
    ToolValidationError,
    execute_tool,
)
from elh_rag.tools.find_rooms import (
    FindRoomsInput,
    FindRoomsOutput,
    RoomMatch,
    _build_sql,
    _select_price_column,
)

# Fixtures


@pytest.fixture
def fake_row():
    """One canonical row matching the SELECT projection."""
    return {
        "idroom": 3,
        "loc_idhouse": 42,
        "r_dateupdate": datetime(2024, 9, 15, 10, 30),
        "loc_dateupdate": datetime(2024, 9, 15, 10, 30),
        "price_eur": 450.0,
        "privatebathroom": "Y",
        "minreservemonths": 5,
        "room_description": "Bright single room with private bathroom in a renovated apartment in Chiado.",
        "haswindow": "Y",
        "idhouse": 42,
        "h_dateupdate": datetime(2024, 9, 15, 10, 30),
        "city": "Lisbon",
        "zone": "Chiado",
        "neighborhood": "Chiado",
        "distancepublictransport": 200,
        "total_matches": 1,
    }


@pytest.fixture
def fake_db(fake_row):
    """A FakeDbExecutor pre-loaded to return [fake_row] for any SELECT."""
    db = FakeDbExecutor()
    db.add_response("SELECT", [fake_row])
    return db


# Input validation


class TestFindRoomsInput:
    def test_empty_input_is_valid(self):
        """All parameters optional” empty input is a valid 'find anything'."""
        p = FindRoomsInput()
        assert p.city is None
        assert p.max_results == 10
        assert p.num_rooms_needed == 1
        assert p.sort_by == "default"

    def test_full_input(self):
        p = FindRoomsInput(
            city="Lisbon",
            metro_line="green",
            near_landmark="NOVA",
            max_price_eur=500,
            min_price_eur=300,
            available_from=date(2026, 9, 1),
            available_to=date(2027, 1, 31),
            min_reserve_months=4,
            accepts_couples=True,
            gender_preference="female_only",
            max_house_occupancy=6,
            num_rooms_needed=3,
            must_have_private_bathroom=True,
            must_have_window=True,
            required_other_amenities=["shared_space", "wheelchair_accessible"],
            sort_by="price_asc",
            max_results=20,
        )
        assert p.metro_line == "green"
        assert p.required_other_amenities == ["shared_space", "wheelchair_accessible"]

    def test_porto_letter_metro_line(self):
        p = FindRoomsInput(metro_line="A")
        assert p.metro_line == "A"

    def test_invalid_metro_line(self):
        with pytest.raises(ValidationError):
            FindRoomsInput(metro_line="purple")  # type: ignore[arg-type]

    def test_price_inversion_raises(self):
        with pytest.raises(ValidationError, match="max_price_eur must be"):
            FindRoomsInput(max_price_eur=300, min_price_eur=500)

    def test_date_inversion_raises(self):
        with pytest.raises(ValidationError, match="available_to must be after"):
            FindRoomsInput(
                available_from=date(2026, 12, 1),
                available_to=date(2026, 11, 1),
            )

    def test_negative_price_raises(self):
        with pytest.raises(ValidationError):
            FindRoomsInput(max_price_eur=-100)

    def test_max_results_bounds(self):
        with pytest.raises(ValidationError):
            FindRoomsInput(max_results=0)
        with pytest.raises(ValidationError):
            FindRoomsInput(max_results=51)

    def test_num_rooms_needed_default_1(self):
        p = FindRoomsInput()
        assert p.num_rooms_needed == 1

    def test_invalid_other_amenity_rejected(self):
        with pytest.raises(ValidationError):
            FindRoomsInput(required_other_amenities=["unicorn"])  # type: ignore[list-item]

    def test_long_landmark_rejected(self):
        with pytest.raises(ValidationError):
            FindRoomsInput(near_landmark="x" * 101)


# Price column selection (season-aware)


class TestSelectPriceColumn:
    def test_default_is_autumn(self):
        """No date -> autumn (high Erasmus season)."""
        p = FindRoomsInput()
        assert _select_price_column(p) == "r.autumnprice"

    @pytest.mark.parametrize(
        "month,expected",
        [
            (3, "r.springprice"),
            (4, "r.springprice"),
            (5, "r.springprice"),
            (6, "r.springprice"),
            (7, "r.summerprice"),
            (8, "r.summerprice"),
            (9, "r.autumnprice"),
            (10, "r.autumnprice"),
            (11, "r.autumnprice"),
            (12, "r.autumnprice"),
            (1, "r.autumnprice"),
            (2, "r.autumnprice"),
        ],
    )
    def test_per_month(self, month, expected):
        p = FindRoomsInput(available_from=date(2026, month, 15))
        assert _select_price_column(p) == expected


# SQL builder


class TestBuildSql:
    def test_empty_input_produces_minimal_sql(self):
        sql, params = _build_sql(FindRoomsInput())
        # Always present: status filter + max_results
        assert "r.status = 'Available'" in sql
        assert "LIMIT %s" in sql
        assert params[-1] == 10

    def test_city_filter(self):
        sql, params = _build_sql(FindRoomsInput(city="Lisbon"))
        assert "h.city = %s" in sql
        assert "Lisbon" in params

    def test_max_price_filter(self):
        sql, params = _build_sql(FindRoomsInput(max_price_eur=500))
        assert "r.autumnprice <= %s" in sql
        assert 500.0 in params

    def test_summer_uses_summer_price(self):
        sql, _params = _build_sql(
            FindRoomsInput(
                available_from=date(2026, 7, 15),
                max_price_eur=400,
            )
        )
        assert "r.summerprice <= %s" in sql
        assert "r.autumnprice" not in sql

    def test_metro_line_lisbon_green(self):
        """green line -> IN clause with Lisbon green-line zones."""
        sql, params = _build_sql(FindRoomsInput(metro_line="green"))
        assert "h.zone IN" in sql
        assert "h.neighboorhood IN" in sql
        # Some green-line zone must appear in params
        assert "Chiado" in params or "Alvalade" in params

    def test_metro_line_porto_letter_normalised(self):
        """Porto letter B -> red colour -> red-line Porto zones."""
        _sql, params = _build_sql(FindRoomsInput(city="Porto", metro_line="B"))
        # B = red on Porto -> Boavista, Bonfim, etc. should appear
        assert "Boavista" in params or "Bonfim" in params

    def test_metro_line_with_no_zones_returns_empty(self):
        """If a line has no zones in the chosen city, the SQL must
        still be valid (force FALSE clause)."""
        # Porto doesn't have a 'pink' line, but it doesn't matter:
        # the Pydantic Literal would have rejected it. We test the
        # internal path: city=Lisbon + line=violet (Lisbon has none).
        sql, _params = _build_sql(FindRoomsInput(city="Lisbon", metro_line="violet"))
        # Must produce a FALSE clause to ensure no rows match
        assert "FALSE" in sql

    def test_landmark_uses_ilike(self):
        sql, params = _build_sql(FindRoomsInput(near_landmark="NOVA"))
        assert "ILIKE" in sql
        assert "%NOVA%" in params

    def test_pets_filter(self):
        """The schema column is `allowpets`, not `acceptspets`."""
        sql, _ = _build_sql(FindRoomsInput(accepts_pets=True))
        assert "h.allowpets = 'Y'" in sql
        assert "acceptspets" not in sql

    def test_gender_female_only(self):
        sql, _ = _build_sql(FindRoomsInput(gender_preference="female_only"))
        assert "h.femalepreferred = 'Y'" in sql

    def test_gender_male_only(self):
        sql, _ = _build_sql(FindRoomsInput(gender_preference="male_only"))
        assert "h.malepreferred = 'Y'" in sql

    def test_gender_any_no_filter(self):
        sql, _ = _build_sql(FindRoomsInput(gender_preference="any"))
        assert "femalepreferred" not in sql
        assert "malepreferred" not in sql

    def test_must_have_window_true(self):
        sql, _ = _build_sql(FindRoomsInput(must_have_window=True))
        assert "haswindow = 'Y'" in sql

    def test_must_have_window_false(self):
        """Internal room: must_have_window=False -> haswindow = 'N'"""
        sql, _ = _build_sql(FindRoomsInput(must_have_window=False))
        assert "haswindow = 'N'" in sql

    def test_must_have_private_bathroom(self):
        sql, _ = _build_sql(FindRoomsInput(must_have_private_bathroom=True))
        assert "privatebathroom = 'Y'" in sql

    def test_other_amenities_house_columns(self):
        """House-level amenities use the `h.` alias."""
        sql, _ = _build_sql(
            FindRoomsInput(
                required_other_amenities=[
                    "city_view",
                    "shared_space",
                    "microwave",
                    "wheelchair_accessible",
                ]
            )
        )
        assert "h.cityview = 'Y'" in sql
        assert "h.sharedspace = 'Y'" in sql
        assert "h.microwaveoven = 'Y'" in sql
        assert "h.reducedmobilityaccess = 'Y'" in sql

    def test_other_amenities_room_columns(self):
        """Room-level amenities use the `r.` alias."""
        sql, _ = _build_sql(
            FindRoomsInput(
                required_other_amenities=[
                    "closet",
                    "bedlinen",
                    "pillows",
                    "extra_person_allowed",
                ]
            )
        )
        assert "r.closet = 'Y'" in sql
        assert "r.bedlinen = 'Y'" in sql
        assert "r.pillows = 'Y'" in sql
        assert "r.extrapersonallowed = 'Y'" in sql

    def test_gender_preference_uses_house_alias(self):
        """Schema bug fix: malepreferred/femalepreferred live on `house`,
        not `room`. The previous `r.femalepreferred` produced a runtime
        error on real DB calls."""
        sql_f, _ = _build_sql(FindRoomsInput(gender_preference="female_only"))
        assert "h.femalepreferred = 'Y'" in sql_f
        assert "r.femalepreferred" not in sql_f

        sql_m, _ = _build_sql(FindRoomsInput(gender_preference="male_only"))
        assert "h.malepreferred = 'Y'" in sql_m
        assert "r.malepreferred" not in sql_m

    def test_non_smoking_uses_inverse_logic(self):
        """``non_smoking=True`` filters smokingallowed='N', not 'Y'."""
        sql, _ = _build_sql(FindRoomsInput(required_other_amenities=["non_smoking"]))
        assert "h.smokingallowed = 'N'" in sql
        assert "h.smokingallowed = 'Y'" not in sql

    def test_dropped_amenities_rejected_by_pydantic(self):
        """Schema-audited Literal rejects fictional amenity names."""
        for dropped in ("pool", "gym", "fireplace", "doorman", "bbq"):
            with pytest.raises(ValidationError):
                FindRoomsInput(required_other_amenities=[dropped])  # type: ignore[list-item]

    def test_sort_by_price_asc(self):
        sql, _ = _build_sql(FindRoomsInput(sort_by="price_asc"))
        assert "ORDER BY r.autumnprice ASC" in sql

    def test_sort_by_price_desc(self):
        sql, _ = _build_sql(FindRoomsInput(sort_by="price_desc"))
        assert "ORDER BY r.autumnprice DESC" in sql

    def test_max_results_in_limit(self):
        _, params = _build_sql(FindRoomsInput(max_results=25))
        assert params[-1] == 25

    def test_distance_filter(self):
        sql, params = _build_sql(FindRoomsInput(max_distance_to_transport_m=500))
        assert "h.distancepublictransport <= %s" in sql
        assert 500 in params

    def test_min_reserve_months_filter(self):
        sql, params = _build_sql(FindRoomsInput(min_reserve_months=6))
        assert "r.minreservemonths >= %s" in sql
        assert 6 in params

    def test_combined_complex_query(self, caplog):
        """Marketing Q1: green line + couples + max 5 ppl."""
        import logging

        with caplog.at_level(logging.WARNING, logger="elh_rag.tools.find_rooms"):
            sql, params = _build_sql(
                FindRoomsInput(
                    city="Lisbon",
                    metro_line="green",
                    accepts_couples=True,
                    max_house_occupancy=5,
                )
            )

        # Working filters
        assert "h.city = %s" in sql
        assert "Lisbon" in params

        # Skipped filters (no SQL impact, warnings emitted)
        assert "acceptscouples" not in sql
        assert "maxoccupancy" not in sql
        warning_messages = [r.message for r in caplog.records]
        assert any("accepts_couples" in m for m in warning_messages)
        assert any("max_house_occupancy" in m for m in warning_messages)

    def test_marketing_q3_porto_year_metro_pets(self):
        """Marketing Q3: Porto + year contract + metro + accepts cat"""
        sql, params = _build_sql(
            FindRoomsInput(
                city="Porto",
                min_contract_months=12,
                max_distance_to_transport_m=500,
                accepts_pets=True,
            )
        )
        assert "h.city = %s" in sql
        assert "Porto" in params
        assert "r.minreservemonths >= %s" in sql
        assert 12 in params
        assert "h.allowpets = 'Y'" in sql
        assert "h.distancepublictransport <= %s" in sql

    def test_marketing_q10_cheapest_internal_ok(self):
        """Marketing Q10: 'Cheapest rooms in Lisbon, internal ok'"""
        sql, _params = _build_sql(
            FindRoomsInput(
                city="Lisbon",
                sort_by="price_asc",
                must_have_window=False,
            )
        )
        assert "ORDER BY r.autumnprice ASC" in sql
        assert "haswindow = 'N'" in sql


# Tool dispatch (registry + ctx injection + execution)


class TestFindRoomsDispatch:
    def test_registered_in_registry(self):
        from elh_rag.tools import list_tools

        assert "find_rooms" in list_tools()

    def test_executes_with_fake_db(self, fake_db):
        result = execute_tool(
            "find_rooms",
            {"city": "Lisbon"},
            ctx=fake_db,
        )
        assert isinstance(result, FindRoomsOutput)
        assert result.total_matches == 1
        assert len(result.rooms) == 1

    def test_returns_room_match(self, fake_db):
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=fake_db)
        match = result.rooms[0]
        assert isinstance(match, RoomMatch)
        assert match.city == "Lisbon"
        assert match.zone == "Chiado"
        assert match.price_per_month_eur == 450.0
        assert match.private_bathroom is True
        assert match.min_reserve_months == 5

    def test_room_id_encoded(self, fake_db):
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=fake_db)
        room_id = result.rooms[0].room_id
        assert room_id.startswith("42|3|")
        assert "2024-09-15T10:30:00" in room_id

    def test_house_id_encoded(self, fake_db):
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=fake_db)
        house_id = result.rooms[0].house_id
        assert house_id.startswith("42|")

    def test_excerpt_extracted(self, fake_db):
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=fake_db)
        assert "Bright single room" in result.rooms[0].excerpt

    def test_nearest_metro_line_for_chiado(self, fake_db):
        """Chiado is on blue and green; nearest_line is the first sorted."""
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=fake_db)
        # Chiado serves blue+green -> sorted = [blue, green] -> first = blue
        assert result.rooms[0].nearest_metro_line == "blue"

    def test_no_results_returns_empty(self):
        empty_db = FakeDbExecutor()  # No responses configured -> []
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=empty_db)
        assert result.total_matches == 0
        assert result.rooms == []

    def test_query_summary_describes_filters(self, fake_db):
        """Summary reflects only the filters that are actually applied to SQL."""
        result = execute_tool(
            "find_rooms",
            {
                "city": "Lisbon",
                "max_price_eur": 500,
                "accepts_couples": True,
                "must_have_private_bathroom": True,
            },
            ctx=fake_db,
        )
        summary = result.query_summary
        assert "Lisbon" in summary
        assert "500" in summary
        # must_have_* IS applied -> must appear (Bug 1 fix)
        assert "private bathroom" in summary
        # accepts_couples is silently skipped -> must NOT appear (Bug 2 fix)
        assert "couples" not in summary.lower()

    def test_no_filters_summary(self, fake_db):
        result = execute_tool("find_rooms", {}, ctx=fake_db)
        assert "no filters" in result.query_summary.lower()

    def test_invalid_payload_raises_validation_error(self, fake_db):
        with pytest.raises(ToolValidationError):
            execute_tool(
                "find_rooms",
                {"max_price_eur": -100},  # negative
                ctx=fake_db,
            )

    def test_missing_ctx_raises_execution_error(self):
        with pytest.raises(ToolExecutionError, match="DBExecutor"):
            execute_tool("find_rooms", {"city": "Lisbon"}, ctx=None)

    def test_db_call_was_recorded(self, fake_db):
        execute_tool("find_rooms", {"city": "Porto"}, ctx=fake_db)
        assert len(fake_db.calls) == 1
        assert "Porto" in fake_db.calls[0]["params"]


# Output serialisation


class TestOutputSerialisation:
    def test_room_match_to_dict(self):
        m = RoomMatch(
            room_id="H1_R1_2024-01-01T00:00:00",
            house_id="H1_2024-01-01T00:00:00",
            house_name="Test House",
            city="Lisbon",
            zone="Chiado",
            neighborhood="Chiado",
            price_per_month_eur=400.0,
            private_bathroom=False,
            distance_to_transport_m=100,
            nearest_metro_line="blue",
            available_from=date(2026, 9, 1),
            min_reserve_months=5,
            amenities=["pool"],
            excerpt="...",
            match_score=0.9,
        )
        d = m.to_dict()
        assert d["room_id"] == "H1_R1_2024-01-01T00:00:00"
        assert d["available_from"] == "2026-09-01"
        assert d["amenities"] == ["pool"]

    def test_room_match_none_available_from(self):
        m = RoomMatch(
            room_id="x",
            house_id="y",
            house_name="z",
            city="Lisbon",
            zone="Chiado",
            neighborhood="Chiado",
            price_per_month_eur=400,
            private_bathroom=False,
            distance_to_transport_m=100,
            nearest_metro_line=None,
            available_from=None,
            min_reserve_months=5,
        )
        d = m.to_dict()
        assert d["available_from"] is None

    def test_find_rooms_output_to_dict(self):
        out = FindRoomsOutput(rooms=[], total_matches=0, query_summary="test")
        d = out.to_dict()
        assert d == {"rooms": [], "total_matches": 0, "query_summary": "test"}


# total_matches semantics (pre-LIMIT row count via COUNT(*) OVER ())


class TestTotalMatches:
    """Verify the tool surfaces the true pre-LIMIT match count."""

    def test_sql_includes_count_window_function(self):
        """SQL must include `COUNT(*) OVER () AS total_matches`."""
        sql, _ = _build_sql(FindRoomsInput())
        assert "COUNT(*) OVER () AS total_matches" in sql

    def test_total_matches_reflects_count_column(self, fake_row):
        """When the SQL returns N rows each carrying total_matches=M,
        the output's total_matches must be M, not N."""
        # Simulate "47 matched, here are the top 3" by giving every row
        # the same large count.
        rows = []
        for idroom in (1, 2, 3):
            r = dict(fake_row)
            r["idroom"] = idroom
            r["total_matches"] = 47
            rows.append(r)
        db = FakeDbExecutor()
        db.add_response("SELECT", rows)

        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=db)

        assert result.total_matches == 47
        assert len(result.rooms) == 3  # the rows the SQL returned

    def test_total_matches_zero_when_no_rows(self):
        """No rows -> total_matches must be 0, not raise."""
        empty_db = FakeDbExecutor()
        result = execute_tool("find_rooms", {"city": "Lisbon"}, ctx=empty_db)
        assert result.total_matches == 0
        assert result.rooms == []
