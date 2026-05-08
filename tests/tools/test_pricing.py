"""Tests for the season-aware monthly price helpers.

Two layers of testing:

    1. Pure-logic unit tests on ``_split_days_by_season`` (no Decimal,
       just calendar arithmetic).
    2. ``compute_room_monthly_price`` end-to-end with both fixed-price
       and variable-price paths, including the warning emitted when
       ``fixedprice='Y'`` but the three columns differ.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pytest

from elh_rag.tools._pricing import (
    AUTUMN_MONTHS,
    SPRING_MONTHS,
    SUMMER_MONTHS,
    MonthlyPriceBreakdown,
    _split_days_by_season,
    compute_room_monthly_price,
)

# Season constants are mutually exclusive and cover all 12 months


class TestSeasonConstants:
    def test_seasons_partition_the_year(self):
        all_months = SPRING_MONTHS | SUMMER_MONTHS | AUTUMN_MONTHS
        assert all_months == set(range(1, 13))

    def test_seasons_are_pairwise_disjoint(self):
        assert set() == SPRING_MONTHS & SUMMER_MONTHS
        assert set() == SPRING_MONTHS & AUTUMN_MONTHS
        assert set() == SUMMER_MONTHS & AUTUMN_MONTHS

    def test_canonical_assignments(self):
        """Spot-check the design-doc convention."""
        assert {3, 4, 5, 6} == SPRING_MONTHS
        assert {7, 8} == SUMMER_MONTHS
        assert {9, 10, 11, 12, 1, 2} == AUTUMN_MONTHS


# _split_days_by_season — calendar arithmetic


class TestSplitDaysBySeason:
    def test_single_pair_of_days_all_autumn(self):
        # 1 -> 2 Sept inclusive = 2 days, both in autumn
        assert _split_days_by_season(date(2026, 9, 1), date(2026, 9, 2)) == (0, 0, 2)

    def test_full_spring(self):
        # 1 Mar -> 30 Jun inclusive: all spring
        result = _split_days_by_season(date(2026, 3, 1), date(2026, 6, 30))
        assert result == (122, 0, 0)  # 31 + 30 + 31 + 30
        assert sum(result) == (date(2026, 6, 30) - date(2026, 3, 1)).days + 1

    def test_full_summer(self):
        # 1 Jul -> 31 Aug inclusive
        result = _split_days_by_season(date(2026, 7, 1), date(2026, 8, 31))
        assert result == (0, 62, 0)  # 31 + 31

    def test_full_autumn_cross_year(self):
        # Phase 3 design example: 1 Sept 2026 -> 31 Jan 2027 inclusive
        result = _split_days_by_season(date(2026, 9, 1), date(2027, 1, 31))
        assert result == (0, 0, 153)  # 30 + 31 + 30 + 31 + 31

    def test_phase3_design_doc_example(self):
        """Phase 3 doc: '15 May -> 31 Aug 2026 -> 47 spring + 62 summer'."""
        spring, summer, autumn = _split_days_by_season(date(2026, 5, 15), date(2026, 8, 31))
        assert (spring, summer, autumn) == (47, 62, 0)

    def test_cross_summer_autumn(self):
        # 1 Aug -> 30 Sept = 31 summer + 30 autumn
        assert _split_days_by_season(date(2026, 8, 1), date(2026, 9, 30)) == (0, 31, 30)

    def test_cross_autumn_spring(self):
        # 1 Jan -> 31 Mar 2026 = (Jan 31 + Feb 28) autumn + (Mar 31) spring
        assert _split_days_by_season(date(2026, 1, 1), date(2026, 3, 31)) == (31, 0, 59)

    def test_cross_spring_summer(self):
        # 1 Jun -> 31 Jul = 30 spring + 31 summer
        assert _split_days_by_season(date(2026, 6, 1), date(2026, 7, 31)) == (30, 31, 0)

    def test_year_boundary_autumn(self):
        # 30 Dec 2025 -> 2 Jan 2026 inclusive = 4 days, all autumn
        assert _split_days_by_season(date(2025, 12, 30), date(2026, 1, 2)) == (0, 0, 4)

    def test_leap_year_february(self):
        """Feb 2024 has 29 days; the split must respect that."""
        assert _split_days_by_season(date(2024, 2, 1), date(2024, 2, 29)) == (0, 0, 29)

    def test_non_leap_year_february(self):
        assert _split_days_by_season(date(2025, 2, 1), date(2025, 2, 28)) == (0, 0, 28)

    def test_full_year_starting_september(self):
        """A full Erasmus academic year, Sept -> Aug."""
        spring, summer, autumn = _split_days_by_season(date(2026, 9, 1), date(2027, 8, 31))
        # autumn = Sept(30) + Oct(31) + Nov(30) + Dec(31) + Jan(31) + Feb(28) = 181
        # spring = Mar(31) + Apr(30) + May(31) + Jun(30) = 122
        # summer = Jul(31) + Aug(31) = 62
        assert (spring, summer, autumn) == (122, 62, 181)
        assert spring + summer + autumn == 365

    def test_sum_invariant(self):
        """For any valid range, sum == (end - start).days + 1."""
        cases = [
            (date(2026, 1, 1), date(2026, 12, 31)),
            (date(2026, 2, 1), date(2026, 2, 1)),  # single-day
            (date(2025, 6, 15), date(2027, 3, 1)),
            (date(2024, 2, 28), date(2024, 3, 2)),  # leap-year boundary
        ]
        for start, end in cases:
            split = _split_days_by_season(start, end)
            expected_total = (end - start).days + 1
            assert sum(split) == expected_total, f"failed for {start} -> {end}"

    def test_single_day_period(self):
        """When start == end, a single day is counted (inclusive end)."""
        assert _split_days_by_season(date(2026, 7, 15), date(2026, 7, 15)) == (0, 1, 0)
        assert _split_days_by_season(date(2026, 4, 15), date(2026, 4, 15)) == (1, 0, 0)
        assert _split_days_by_season(date(2026, 11, 15), date(2026, 11, 15)) == (0, 0, 1)

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="empty period"):
            _split_days_by_season(date(2026, 12, 1), date(2026, 11, 1))


# compute_room_monthly_price — variable price


class TestVariablePrice:
    def test_all_autumn_returns_autumn_price(self):
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("500.00"),
            is_fixed=False,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result.monthly_eur == Decimal("500.00")
        assert result.is_fixed_price is False
        assert (result.spring_days, result.summer_days, result.autumn_days) == (0, 0, 153)

    def test_all_summer_returns_summer_price(self):
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("500.00"),
            is_fixed=False,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 8, 31),
        )
        assert result.monthly_eur == Decimal("300.00")

    def test_phase3_example_cross_season_weighted(self):
        """Phase 3 doc: 15 May -> 31 Aug -> 47 spring + 62 summer days.

        With spring=400, summer=300:
        weighted = (400*47 + 300*62) / 109 = (18800 + 18600) / 109
                 = 37400 / 109 = 343.119266...
        rounded ROUND_HALF_UP to 343.12.
        """
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("500.00"),
            is_fixed=False,
            period_start=date(2026, 5, 15),
            period_end=date(2026, 8, 31),
        )
        assert result.monthly_eur == Decimal("343.12")
        assert (result.spring_days, result.summer_days, result.autumn_days) == (47, 62, 0)

    def test_three_seasons_weighted(self):
        """Sept 1 -> Aug 31 (full academic year): 122 spring + 62 summer + 181 autumn.

        With prices (400, 300, 500):
        weighted = (400*122 + 300*62 + 500*181) / 365
                 = (48800 + 18600 + 90500) / 365
                 = 157900 / 365 = 432.6027...
        rounded to 432.60.
        """
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("500.00"),
            is_fixed=False,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 8, 31),
        )
        assert result.monthly_eur == Decimal("432.60")

    def test_decimal_input_preserves_precision(self):
        """Inputs with full DB precision (numeric(10,2)) round-trip cleanly."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("349.99"),
            summer_eur=Decimal("249.99"),
            autumn_eur=Decimal("449.99"),
            is_fixed=False,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        # All-autumn => exactly autumn_eur, quantized
        assert result.monthly_eur == Decimal("449.99")

    def test_fractional_cent_rounded_half_up(self):
        """Engineer a range giving a fractional-cent weighted average.

        30 Jun (1 spring day) + 1-2 Jul (2 summer days), prices 100 and 101:
        (100*1 + 101*2) / 3 = 302/3 = 100.666... -> 100.67 (HALF_UP).
        """
        result = compute_room_monthly_price(
            spring_eur=Decimal("100.00"),
            summer_eur=Decimal("101.00"),
            autumn_eur=Decimal("999.00"),  # unused, sentinel value
            is_fixed=False,
            period_start=date(2026, 6, 30),
            period_end=date(2026, 7, 2),
        )
        assert (result.spring_days, result.summer_days, result.autumn_days) == (1, 2, 0)
        assert result.monthly_eur == Decimal("100.67")


# compute_room_monthly_price — fixed-price path


class TestFixedPrice:
    def test_fixed_price_returns_autumn_value(self):
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("400.00"),
            autumn_eur=Decimal("400.00"),
            is_fixed=True,
            period_start=date(2026, 5, 15),  # cross-season window
            period_end=date(2026, 8, 31),
        )
        assert result.monthly_eur == Decimal("400.00")
        assert result.is_fixed_price is True
        # Day split is still computed (Tool 3 will need it)
        assert (result.spring_days, result.summer_days, result.autumn_days) == (47, 62, 0)

    def test_fixed_price_no_warning_when_columns_agree(self, caplog):
        with caplog.at_level(logging.WARNING):
            compute_room_monthly_price(
                spring_eur=Decimal("400.00"),
                summer_eur=Decimal("400.00"),
                autumn_eur=Decimal("400.00"),
                is_fixed=True,
                period_start=date(2026, 5, 15),
                period_end=date(2026, 8, 31),
            )
        assert not caplog.records  # no warning emitted

    def test_fixed_price_warns_when_columns_differ(self, caplog):
        """Decision (C): log a warning, fall back to autumn value."""
        with caplog.at_level(logging.WARNING):
            result = compute_room_monthly_price(
                spring_eur=Decimal("350.00"),
                summer_eur=Decimal("300.00"),
                autumn_eur=Decimal("400.00"),
                is_fixed=True,
                period_start=date(2026, 5, 15),
                period_end=date(2026, 8, 31),
            )
        assert result.monthly_eur == Decimal("400.00")  # autumn fallback
        assert result.is_fixed_price is True
        # Exactly one warning, mentioning the divergence
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "fixedprice" in warnings[0].message
        assert "differ" in warnings[0].message

    def test_variable_with_identical_columns_does_not_set_fixed_flag(self):
        """is_fixed_price reflects the input flag, not the data shape."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("400.00"),
            autumn_eur=Decimal("400.00"),
            is_fixed=False,  # caller said variable
            period_start=date(2026, 5, 15),
            period_end=date(2026, 8, 31),
        )
        assert result.monthly_eur == Decimal("400.00")
        assert result.is_fixed_price is False  # echoes input


# MonthlyPriceBreakdown


class TestBreakdown:
    def test_total_days_property(self):
        bd = MonthlyPriceBreakdown(
            monthly_eur=Decimal("400.00"),
            is_fixed_price=False,
            spring_days=47,
            summer_days=62,
            autumn_days=0,
        )
        assert bd.total_days == 109

    def test_breakdown_is_frozen(self):
        import dataclasses

        bd = MonthlyPriceBreakdown(
            monthly_eur=Decimal("400.00"),
            is_fixed_price=False,
            spring_days=10,
            summer_days=10,
            autumn_days=10,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            bd.monthly_eur = Decimal("500.00")  # type: ignore[misc]
