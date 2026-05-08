"""Tests for the Tool 2 input model (``FindAvailableRoomsInput``).

Step 1 scope: input validation only. SQL building, reservation overlap,
weighted pricing, and dispatch are covered in later steps.

Three things to verify here:

    1. The new fields ``available_from`` / ``available_to`` are required
       (they were optional on the parent ``FindRoomsInput``).
    2. The parent's ``check_consistency`` validator still fires
       (``available_to > available_from``).
    3. The new ``check_period_bounds`` validator rejects pathological
       multi-year periods.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from elh_rag.tools.find_available_rooms import (
    _MAX_PERIOD_DAYS,
    FindAvailableRoomsInput,
)
from elh_rag.tools.find_rooms import FindRoomsInput

# Required fields


class TestRequiredFields:
    def test_minimal_valid_input(self):
        """Only the two date fields are required; everything else inherits defaults."""
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2027, 1, 31),
        )
        assert p.available_from == date(2026, 9, 1)
        assert p.available_to == date(2027, 1, 31)
        # Inherited defaults still apply
        assert p.num_rooms_needed == 1
        assert p.max_results == 10
        assert p.sort_by == "default"
        assert p.city is None

    def test_missing_available_from_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(available_to=date(2027, 1, 31))  # type: ignore[call-arg]
        # Pydantic's "Field required" wording is stable in v2
        assert "available_from" in str(exc_info.value)

    def test_missing_available_to_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(available_from=date(2026, 9, 1))  # type: ignore[call-arg]
        assert "available_to" in str(exc_info.value)

    def test_both_dates_missing_rejected(self):
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput()  # type: ignore[call-arg]

    def test_explicit_none_rejected_for_required_fields(self):
        """Passing None must NOT slip through — required means non-null."""
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=None,  # type: ignore[arg-type]
                available_to=date(2027, 1, 31),
            )


# Inheritance from FindRoomsInput


class TestInheritance:
    def test_is_subclass_of_find_rooms_input(self):
        assert issubclass(FindAvailableRoomsInput, FindRoomsInput)

    def test_inherited_fields_accept_values(self):
        """Smoke check: a sample of parent fields work on the subclass."""
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2027, 1, 31),
            city="Lisbon",
            metro_line="green",
            max_price_eur=500,
            gender_preference="female_only",
            accepts_couples=True,
            num_rooms_needed=3,
            required_other_amenities=["pool", "gym"],
            sort_by="price_asc",
            max_results=20,
        )
        assert p.city == "Lisbon"
        assert p.metro_line == "green"
        assert p.max_price_eur == 500
        assert p.gender_preference == "female_only"
        assert p.num_rooms_needed == 3
        assert p.required_other_amenities == ["pool", "gym"]
        assert p.sort_by == "price_asc"
        assert p.max_results == 20

    def test_inherited_constraints_still_apply(self):
        """Parent-level Field constraints (e.g. num_rooms_needed >= 1) survive."""
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


# Date ordering (parent's check_consistency)


class TestDateOrdering:
    def test_dates_inverted_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            FindAvailableRoomsInput(
                available_from=date(2027, 1, 31),
                available_to=date(2026, 9, 1),
            )
        assert "available_to must be after available_from" in str(exc_info.value)

    def test_same_day_rejected(self):
        """Period must be strictly positive — same-day = empty stay."""
        with pytest.raises(ValidationError):
            FindAvailableRoomsInput(
                available_from=date(2026, 9, 1),
                available_to=date(2026, 9, 1),
            )

    def test_minimum_one_day_period_accepted(self):
        """A period of exactly one calendar day (n+1 - n = 1) is valid."""
        p = FindAvailableRoomsInput(
            available_from=date(2026, 9, 1),
            available_to=date(2026, 9, 2),
        )
        assert (p.available_to - p.available_from).days == 1


# Period upper bound


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
        """Sanity: the periods we actually expect from real users all pass."""
        cases = [
            # 1-month summer
            (date(2026, 7, 1), date(2026, 7, 31)),
            # Full Erasmus semester (Sep -> Jan)
            (date(2026, 9, 1), date(2027, 1, 31)),
            # Full academic year (Sep -> Jul)
            (date(2026, 9, 1), date(2027, 7, 31)),
            # Cross-season (May -> Aug)
            (date(2026, 5, 15), date(2026, 8, 31)),
        ]
        for start, end in cases:
            p = FindAvailableRoomsInput(available_from=start, available_to=end)
            assert p.available_from == start
            assert p.available_to == end


# Type coercion


class TestTypeCoercion:
    def test_iso_string_dates_coerced(self):
        """Pydantic coerces ISO-8601 strings to date — useful when the LLM
        sends JSON with string dates."""
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
