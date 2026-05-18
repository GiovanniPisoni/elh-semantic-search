"""Season-aware price computation.

This module hosts pricing logic for two tools that read the ELH room
table's seasonal columns.
Both tools use the same billing convention (calendar months
billed in full at their seasonal rate). Tool 2 collapses it to a single
average for the search listing; Tool 3 keeps the per-month detail for
the final quote.

ELH season boundaries:

    * ``springprice`` — March, April, May, June     (medium season)
    * ``summerprice`` — July, August                 (low season,
                                                      Erasmus students
                                                      typically away)
    * ``autumnprice`` — Sept-Feb                     (high season,
                                                      academic year)

Rooms flagged ``fixedprice = 'Y'`` ignore the seasonal split and use a
single non-seasonal value (canonical: the autumn column).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

logger = logging.getLogger(__name__)


# Season boundaries

SPRING_MONTHS: frozenset[int] = frozenset({3, 4, 5, 6})
SUMMER_MONTHS: frozenset[int] = frozenset({7, 8})
AUTUMN_MONTHS: frozenset[int] = frozenset({9, 10, 11, 12, 1, 2})

Season = Literal["spring", "summer", "autumn"]

_PRICE_QUANTUM = Decimal("0.01")


def season_for_month(month: int) -> Season:
    """Map a calendar month (1-12) to its ELH season label."""
    if month in SPRING_MONTHS:
        return "spring"
    if month in SUMMER_MONTHS:
        return "summer"
    if month in AUTUMN_MONTHS:
        return "autumn"
    raise ValueError(f"Invalid month {month!r}; expected 1-12.")


def iter_calendar_months(start: date, end: date) -> Iterator[tuple[int, int]]:
    """Yield ``(year, month)`` for every calendar month touched by ``[start, end]``.

    Inclusive on both ends. A stay from 2025-09-15 to 2026-02-14 yields
    six pairs: Sep, Oct, Nov, Dec, Jan, Feb (each in its respective year).
    """
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start}): empty period not allowed")
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    while (y, m) <= (end_y, end_m):
        yield (y, m)
        m += 1
        if m > 12:
            m = 1
            y += 1


# TOOL 3 — Billing breakdown (calendar-month model, "Model B")


@dataclass(frozen=True)
class MonthRent:
    """Rent for a single calendar month, with its season label."""

    year: int
    month: int  # 1-12
    season: Season
    rent_eur: Decimal


@dataclass(frozen=True)
class StayCostBreakdown:
    """Full per-month rent breakdown for a stay (Tool 3 billing model)."""

    months: list[MonthRent]
    total_rent_eur: Decimal
    is_uniform_rent: bool  # True iff every month has the same rent

    @property
    def total_months(self) -> int:
        return len(self.months)


def compute_stay_breakdown(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
    is_fixed: bool,
    check_in: date,
    check_out: date,
) -> StayCostBreakdown:
    """Compute the full billing breakdown for the stay (Model B).

    ELH billing model: every calendar month touched by the stay is
    billed in full at that month's seasonal rate. Partial months
    (check-in mid-month, check-out mid-month) count as full months.

    A stay from 2025-09-15 to 2026-02-14 bills six full months
    (Sep, Oct, Nov, Dec, Jan, Feb), all at the autumn rate.

    For fixed-price rooms, every month is billed at the autumn-column
    value (canonical fixed-price column).
    """
    if check_out < check_in:
        raise ValueError(
            f"check_out ({check_out}) is before check_in ({check_in}); empty stay not allowed"
        )

    season_to_rate: dict[Season, Decimal] = {
        "spring": spring_eur,
        "summer": summer_eur,
        "autumn": autumn_eur,
    }

    months_list: list[MonthRent] = []
    for y, m in iter_calendar_months(check_in, check_out):
        season = season_for_month(m)
        if is_fixed:
            raw_rate = _resolve_fixed_price(spring_eur, summer_eur, autumn_eur)
        else:
            raw_rate = season_to_rate[season]
        months_list.append(
            MonthRent(
                year=y,
                month=m,
                season=season,
                rent_eur=raw_rate.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP),
            )
        )

    if not months_list:
        raise ValueError(f"No calendar months in [{check_in}, {check_out}] — should be unreachable")

    total = sum((mr.rent_eur for mr in months_list), Decimal("0"))
    is_uniform = len({mr.rent_eur for mr in months_list}) == 1

    return StayCostBreakdown(
        months=months_list,
        total_rent_eur=total.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP),
        is_uniform_rent=is_uniform,
    )


# TOOL 2 — Display price (Model B average across calendar months)


@dataclass(frozen=True)
class MonthlyPriceBreakdown:
    """Display-side breakdown used by Tool 2.

    ``monthly_eur`` is the **average** rent across the calendar months
    of the stay, using the same Model B billing rates as Tool 3. The
    per-season month counters expose how the average was composed.
    """

    monthly_eur: Decimal
    is_fixed_price: bool
    spring_months: int
    summer_months: int
    autumn_months: int

    @property
    def total_months(self) -> int:
        return self.spring_months + self.summer_months + self.autumn_months


def compute_room_monthly_price(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
    is_fixed: bool,
    period_start: date,
    period_end: date,
) -> MonthlyPriceBreakdown:
    """Return the *displayed* monthly price for a stay."""
    breakdown = compute_stay_breakdown(
        spring_eur=spring_eur,
        summer_eur=summer_eur,
        autumn_eur=autumn_eur,
        is_fixed=is_fixed,
        check_in=period_start,
        check_out=period_end,
    )

    avg = breakdown.total_rent_eur / Decimal(breakdown.total_months)
    avg = avg.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)

    counts = _count_months_by_season(breakdown.months)

    return MonthlyPriceBreakdown(
        monthly_eur=avg,
        is_fixed_price=is_fixed,
        spring_months=counts["spring"],
        summer_months=counts["summer"],
        autumn_months=counts["autumn"],
    )


def _count_months_by_season(months: list[MonthRent]) -> dict[Season, int]:
    """Count how many calendar months in the breakdown belong to each season."""
    counts: dict[Season, int] = {"spring": 0, "summer": 0, "autumn": 0}
    for m in months:
        counts[m.season] += 1
    return counts


# Shared helpers


def _resolve_fixed_price(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
) -> Decimal:
    """Canonical price for a fixed-price room — returns autumn, warns on mismatch."""
    if not (spring_eur == summer_eur == autumn_eur):
        logger.warning(
            "fixedprice='Y' but seasonal columns differ "
            "(spring=%s, summer=%s, autumn=%s) — falling back to autumn value",
            spring_eur,
            summer_eur,
            autumn_eur,
        )
    return autumn_eur
