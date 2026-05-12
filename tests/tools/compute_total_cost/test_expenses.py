"""Tests for ``elh_rag.tools._expenses.fetch_utility_categorization``.

The helper categorises rows of the ``expenses`` table into two
parallel human-readable lists:

    * ``included``: ``maximumvalue`` is non-NULL -> utility is bundled
      in the rent up to that monthly cap (per the ELH business
      clarification of 2026-05-11).
    * ``excluded``: ``maximumvalue`` is NULL -> utility is not bundled;
      the student pays the provider directly.

These tests pin both the split logic and the user-facing format
strings, since the strings are surfaced to the LLM and then to the
user verbatim.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from elh_rag.tools.compute_total_cost import (
    UtilityCategorization,
    fetch_utility_categorization,
)

_FIXED_DT = datetime(2024, 9, 15, 10, 30)


class TestFetchUtilityCategorization:
    def test_all_included_when_maximumvalue_set(self, fake_db):
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "Gas", "maximumvalue": Decimal("25.00")},
                {"description": "Water", "maximumvalue": Decimal("15.00")},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert len(result.included) == 2
        assert result.excluded == []
        assert "Gas (up to €25.00/mo)" in result.included
        assert "Water (up to €15.00/mo)" in result.included

    def test_all_excluded_when_maximumvalue_null(self, fake_db):
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "Internet/WiFi", "maximumvalue": None},
                {"description": "Electricity", "maximumvalue": None},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert result.included == []
        assert len(result.excluded) == 2
        assert "Internet/WiFi (not included — paid to provider)" in result.excluded
        assert "Electricity (not included — paid to provider)" in result.excluded

    def test_mixed_categorization(self, fake_db):
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "Gas", "maximumvalue": Decimal("25.00")},
                {"description": "Internet/WiFi", "maximumvalue": None},
                {"description": "Water", "maximumvalue": Decimal("10.00")},
                {"description": "Electricity", "maximumvalue": None},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert len(result.included) == 2
        assert len(result.excluded) == 2
        assert "Gas (up to €25.00/mo)" in result.included
        assert "Water (up to €10.00/mo)" in result.included
        assert "Internet/WiFi (not included — paid to provider)" in result.excluded
        assert "Electricity (not included — paid to provider)" in result.excluded

    def test_empty_result_returns_empty_lists(self, fake_db):
        # No add_response -> fake returns []
        result = fetch_utility_categorization(fake_db, "HSE_NOTFOUND", _FIXED_DT)
        assert result.included == []
        assert result.excluded == []

    def test_decimal_precision_quantized_to_two_places(self, fake_db):
        """25, 25.5, 25.50 must all render as a 2-decimal price."""
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "A", "maximumvalue": Decimal("25")},
                {"description": "B", "maximumvalue": Decimal("25.5")},
                {"description": "C", "maximumvalue": Decimal("25.50")},
                {"description": "D", "maximumvalue": Decimal("25.499")},
                {"description": "E", "maximumvalue": Decimal("25.501")},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert "A (up to €25.00/mo)" in result.included
        assert "B (up to €25.50/mo)" in result.included
        assert "C (up to €25.50/mo)" in result.included
        assert "D (up to €25.50/mo)" in result.included
        assert "E (up to €25.50/mo)" in result.included

    def test_description_whitespace_stripped(self, fake_db):
        """``character()`` columns are right-padded — must be stripped."""
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "Gas" + " " * 30, "maximumvalue": Decimal("25.00")},
                {"description": "   Water   ", "maximumvalue": None},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert "Gas (up to €25.00/mo)" in result.included
        assert "Water (not included — paid to provider)" in result.excluded

    def test_empty_or_whitespace_only_description_skipped(self, fake_db):
        fake_db.add_response(
            "FROM expenses",
            [
                {"description": "", "maximumvalue": Decimal("25.00")},
                {"description": "   ", "maximumvalue": None},
                {"description": "Gas", "maximumvalue": Decimal("25.00")},
            ],
        )
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert len(result.included) == 1
        assert result.excluded == []
        assert "Gas (up to €25.00/mo)" in result.included

    def test_sql_params_carry_house_id_and_dateupdate(self, fake_db):
        """The expenses join key must be the (idhouse, dateupdate) pair."""
        fake_db.add_response("FROM expenses", [])
        fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert len(fake_db.calls) == 1
        call = fake_db.calls[0]
        assert call["params"] == ("HSE_001", _FIXED_DT)
        assert "idhouse" in call["sql"]
        assert "dateupdate" in call["sql"]
        assert "FROM expenses" in call["sql"]

    def test_returns_utility_categorization_dataclass(self, fake_db):
        fake_db.add_response("FROM expenses", [])
        result = fetch_utility_categorization(fake_db, "HSE_001", _FIXED_DT)
        assert isinstance(result, UtilityCategorization)
        # Frozen
        import dataclasses

        try:
            result.included = ["mutated"]  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            pass
        else:
            raise AssertionError("UtilityCategorization should be frozen")
