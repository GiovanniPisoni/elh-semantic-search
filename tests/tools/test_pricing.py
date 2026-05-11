"""Tests for the season-aware monthly price helpers."""

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
    MonthRent,
    StayCostBreakdown,
    compute_room_monthly_price,
    compute_stay_breakdown,
    iter_calendar_months,
    season_for_month,
)

# Season constants


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


# season_for_month


class TestSeasonForMonth:
    @pytest.mark.parametrize("month", [3, 4, 5, 6])
    def test_spring_months(self, month: int):
        assert season_for_month(month) == "spring"

    @pytest.mark.parametrize("month", [7, 8])
    def test_summer_months(self, month: int):
        assert season_for_month(month) == "summer"

    @pytest.mark.parametrize("month", [9, 10, 11, 12, 1, 2])
    def test_autumn_months(self, month: int):
        assert season_for_month(month) == "autumn"

    @pytest.mark.parametrize("bad", [0, -1, 13, 100])
    def test_invalid_month_raises(self, bad: int):
        with pytest.raises(ValueError, match="Invalid month"):
            season_for_month(bad)


# iter_calendar_months


class TestIterCalendarMonths:
    def test_same_month_yields_one_pair(self):
        result = list(iter_calendar_months(date(2025, 9, 5), date(2025, 9, 28)))
        assert result == [(2025, 9)]

    def test_check_in_and_out_on_same_day(self):
        """Edge case: 1-day stay still touches exactly one month."""
        result = list(iter_calendar_months(date(2025, 9, 15), date(2025, 9, 15)))
        assert result == [(2025, 9)]

    def test_two_adjacent_months(self):
        result = list(iter_calendar_months(date(2025, 9, 28), date(2025, 10, 3)))
        assert result == [(2025, 9), (2025, 10)]

    def test_crossing_year_boundary(self):
        result = list(iter_calendar_months(date(2025, 11, 15), date(2026, 2, 14)))
        assert result == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]

    def test_full_academic_year(self):
        """Sept 2025 → Aug 2026 = 12 calendar months."""
        result = list(iter_calendar_months(date(2025, 9, 1), date(2026, 8, 31)))
        assert len(result) == 12
        assert result[0] == (2025, 9)
        assert result[-1] == (2026, 8)

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="empty period"):
            list(iter_calendar_months(date(2025, 12, 1), date(2025, 11, 1)))

    def test_cross_season_autumn_to_spring(self):
        """Phase 3 stress case: Jan → April (autumn → spring boundary)."""
        result = list(iter_calendar_months(date(2026, 1, 5), date(2026, 4, 20)))
        assert result == [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]


# compute_stay_breakdown (Tool 3)


class TestComputeStayBreakdown:
    def test_all_autumn_three_months(self):
        """3-month autumn stay: all rates equal autumnprice."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2025, 9, 1),
            check_out=date(2025, 11, 30),
        )
        assert isinstance(result, StayCostBreakdown)
        assert result.total_months == 3
        assert result.is_uniform_rent is True
        assert result.total_rent_eur == Decimal("1650.00")  # 3 x 550
        assert all(m.season == "autumn" for m in result.months)
        assert all(m.rent_eur == Decimal("550.00") for m in result.months)

    def test_all_summer_two_months(self):
        result = compute_stay_breakdown(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2025, 7, 1),
            check_out=date(2025, 8, 31),
        )
        assert result.total_months == 2
        assert result.total_rent_eur == Decimal("600.00")  # 2 x 300
        assert result.is_uniform_rent is True

    def test_cross_season_autumn_to_spring(self):
        """4 months Jan-Apr: 2 autumn (Jan,Feb) + 2 spring (Mar,Apr)."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("450.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2026, 1, 1),
            check_out=date(2026, 4, 30),
        )
        assert result.total_months == 4
        assert result.is_uniform_rent is False
        assert result.total_rent_eur == Decimal("2000.00")  # 2x550 + 2x450
        # Verify per-month seasons
        seasons = [m.season for m in result.months]
        assert seasons == ["autumn", "autumn", "spring", "spring"]

    def test_mid_month_check_in_billed_as_full_month(self):
        """Check-in on the 28th still bills the full month (Model B)."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2025, 9, 28),  # late in the month
            check_out=date(2025, 11, 2),  # early in the month
        )
        assert result.total_months == 3  # Sep, Oct, Nov — all full
        assert result.total_rent_eur == Decimal("1650.00")

    def test_eight_month_cross_season_sep_to_apr(self):
        """Classic Erasmus academic stay Sep-Apr: 6 autumn + 2 spring."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("450.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2025, 9, 1),
            check_out=date(2026, 4, 30),
        )
        assert result.total_months == 8
        # 6 x 550 + 2 x 450 = 3300 + 900 = 4200
        assert result.total_rent_eur == Decimal("4200.00")

    def test_fixed_price_ignores_seasons(self):
        """Fixed-price room: every month bills at the autumn-column value."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("600.00"),
            summer_eur=Decimal("600.00"),
            autumn_eur=Decimal("600.00"),
            is_fixed=True,
            check_in=date(2026, 1, 1),
            check_out=date(2026, 4, 30),
        )
        assert result.total_months == 4
        assert result.is_uniform_rent is True
        assert result.total_rent_eur == Decimal("2400.00")
        # Even though Jan/Feb are autumn and Mar/Apr are spring, all
        # are billed at the same rate
        assert all(m.rent_eur == Decimal("600.00") for m in result.months)

    def test_fixed_price_with_divergent_columns_falls_back_to_autumn(self, caplog):
        """If fixedprice='Y' but cols differ, autumn wins (with warning)."""
        with caplog.at_level(logging.WARNING):
            result = compute_stay_breakdown(
                spring_eur=Decimal("500.00"),
                summer_eur=Decimal("400.00"),
                autumn_eur=Decimal("600.00"),
                is_fixed=True,
                check_in=date(2026, 1, 1),
                check_out=date(2026, 3, 31),
            )
        assert result.total_rent_eur == Decimal("1800.00")  # 3 x 600
        # Warning emitted (one per month — the helper is called per row)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "fixedprice" in warnings[0].message

    def test_inverted_dates_raises(self):
        with pytest.raises(ValueError, match="empty stay"):
            compute_stay_breakdown(
                spring_eur=Decimal("400.00"),
                summer_eur=Decimal("300.00"),
                autumn_eur=Decimal("550.00"),
                is_fixed=False,
                check_in=date(2026, 4, 1),
                check_out=date(2026, 1, 1),
            )

    def test_single_day_stay_bills_one_month(self):
        """1-day stay: 1 calendar month, full rate."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            check_in=date(2025, 9, 15),
            check_out=date(2025, 9, 15),
        )
        assert result.total_months == 1
        assert result.total_rent_eur == Decimal("550.00")

    def test_decimal_precision_preserved(self):
        """Non-round prices preserve full Decimal precision."""
        result = compute_stay_breakdown(
            spring_eur=Decimal("449.99"),
            summer_eur=Decimal("299.99"),
            autumn_eur=Decimal("549.99"),
            is_fixed=False,
            check_in=date(2025, 9, 1),
            check_out=date(2025, 11, 30),
        )
        assert result.total_rent_eur == Decimal("1649.97")


# compute_room_monthly_price (Tool 2 display)


class TestComputeRoomMonthlyPrice:
    def test_same_season_returns_seasonal_column(self):
        """3-month autumn stay → display average == autumnprice."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("400.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            period_start=date(2025, 9, 1),
            period_end=date(2025, 11, 30),
        )
        assert result.monthly_eur == Decimal("550.00")
        assert result.is_fixed_price is False
        assert (result.spring_months, result.summer_months, result.autumn_months) == (0, 0, 3)
        assert result.total_months == 3

    def test_cross_season_returns_arithmetic_average(self):
        """Jan-Apr stay: 2 autumn (550) + 2 spring (450) → avg 500."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("450.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 4, 30),
        )
        # (2x550 + 2x450) / 4 = 2000 / 4 = 500
        assert result.monthly_eur == Decimal("500.00")
        assert (result.spring_months, result.summer_months, result.autumn_months) == (2, 0, 2)

    def test_eight_month_cross_season_average(self):
        """Sep-Apr stay: 6x550 + 2x450 = 4200, avg = 525."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("450.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            period_start=date(2025, 9, 1),
            period_end=date(2026, 4, 30),
        )
        # (6x550 + 2x450) / 8 = 4200 / 8 = 525
        assert result.monthly_eur == Decimal("525.00")
        assert (result.spring_months, result.summer_months, result.autumn_months) == (2, 0, 6)

    def test_three_season_full_year_average(self):
        """Full Sep-Aug year: 6 autumn + 4 spring + 2 summer."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("450.00"),
            summer_eur=Decimal("300.00"),
            autumn_eur=Decimal("550.00"),
            is_fixed=False,
            period_start=date(2025, 9, 1),
            period_end=date(2026, 8, 31),
        )
        # (6x550 + 4x450 + 2x300) / 12 = (3300 + 1800 + 600) / 12 = 5700/12 = 475
        assert result.monthly_eur == Decimal("475.00")
        assert (result.spring_months, result.summer_months, result.autumn_months) == (4, 2, 6)
        assert result.total_months == 12

    def test_fixed_price_returns_autumn_column(self):
        result = compute_room_monthly_price(
            spring_eur=Decimal("600.00"),
            summer_eur=Decimal("600.00"),
            autumn_eur=Decimal("600.00"),
            is_fixed=True,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 4, 30),
        )
        assert result.monthly_eur == Decimal("600.00")
        assert result.is_fixed_price is True

    def test_fixed_price_with_divergent_columns_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = compute_room_monthly_price(
                spring_eur=Decimal("500.00"),
                summer_eur=Decimal("400.00"),
                autumn_eur=Decimal("600.00"),
                is_fixed=True,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
            )
        assert result.monthly_eur == Decimal("600.00")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "fixedprice" in warnings[0].message

    def test_variable_with_identical_columns_keeps_input_flag(self):
        """is_fixed_price reflects the input flag, not the data shape."""
        result = compute_room_monthly_price(
            spring_eur=Decimal("500.00"),
            summer_eur=Decimal("500.00"),
            autumn_eur=Decimal("500.00"),
            is_fixed=False,
            period_start=date(2026, 5, 15),
            period_end=date(2026, 8, 31),
        )
        assert result.monthly_eur == Decimal("500.00")
        assert result.is_fixed_price is False

    def test_rounding_half_up_on_fractional_average(self):
        """Engineer a 3-month split that yields a fractional average.

        2 x 100 + 1 x 101 = 301, avg = 301/3 = 100.333... → 100.33.
        """
        # Use real seasonal boundaries: Jun (spring, 100), Jul (summer, 101)
        # — span 3 months: Jun (spring), Jul + Aug (summer).
        # 1x100 + 2x101 = 302, avg = 302/3 = 100.666... → 100.67 (HALF_UP)
        result = compute_room_monthly_price(
            spring_eur=Decimal("100.00"),
            summer_eur=Decimal("101.00"),
            autumn_eur=Decimal("999.00"),  # unused
            is_fixed=False,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 8, 31),
        )
        assert (result.spring_months, result.summer_months, result.autumn_months) == (1, 2, 0)
        assert result.monthly_eur == Decimal("100.67")


# Dataclasses — frozen + computed properties


class TestMonthlyPriceBreakdown:
    def test_total_months_property(self):
        bd = MonthlyPriceBreakdown(
            monthly_eur=Decimal("500.00"),
            is_fixed_price=False,
            spring_months=2,
            summer_months=0,
            autumn_months=6,
        )
        assert bd.total_months == 8

    def test_breakdown_is_frozen(self):
        import dataclasses

        bd = MonthlyPriceBreakdown(
            monthly_eur=Decimal("500.00"),
            is_fixed_price=False,
            spring_months=1,
            summer_months=1,
            autumn_months=1,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            bd.monthly_eur = Decimal("999.00")  # type: ignore[misc]


class TestStayCostBreakdown:
    def test_total_months_property(self):
        bd = StayCostBreakdown(
            months=[
                MonthRent(2025, 9, "autumn", Decimal("550.00")),
                MonthRent(2025, 10, "autumn", Decimal("550.00")),
            ],
            total_rent_eur=Decimal("1100.00"),
            is_uniform_rent=True,
        )
        assert bd.total_months == 2

    def test_breakdown_is_frozen(self):
        import dataclasses

        bd = StayCostBreakdown(
            months=[MonthRent(2025, 9, "autumn", Decimal("550.00"))],
            total_rent_eur=Decimal("550.00"),
            is_uniform_rent=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            bd.total_rent_eur = Decimal("999.00")  # type: ignore[misc]


class TestMonthRent:
    def test_is_frozen(self):
        import dataclasses

        m = MonthRent(2025, 9, "autumn", Decimal("550.00"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.rent_eur = Decimal("999.00")  # type: ignore[misc]

    def test_holds_year_month_season_rent(self):
        m = MonthRent(year=2026, month=3, season="spring", rent_eur=Decimal("450.00"))
        assert m.year == 2026
        assert m.month == 3
        assert m.season == "spring"
        assert m.rent_eur == Decimal("450.00")
