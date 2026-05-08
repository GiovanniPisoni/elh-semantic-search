"""Season-aware monthly price computation for Tool 2.

ELH rooms have three seasonal price columns in the database:

    * ``springprice`` — March, April, May, June     (medium season)
    * ``summerprice`` — July, August                 (low season,
                                                      Erasmus students
                                                      typically away)
    * ``autumnprice`` — Sept-Feb                     (high season,
                                                      academic year)

For a stay overlapping multiple seasons, the displayed monthly price is
the **weighted average** of the three columns over the days of the
period that fall in each season.

Rooms flagged ``fixedprice = 'Y'`` ignore the seasonal split and use a
single non-seasonal value. In well-formed data the three columns are
identical for fixed-price rooms; we still return the autumn value (the
canonical Erasmus column) and emit a warning if they happen to differ.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)


# Season boundaries


SPRING_MONTHS: frozenset[int] = frozenset({3, 4, 5, 6})
SUMMER_MONTHS: frozenset[int] = frozenset({7, 8})
AUTUMN_MONTHS: frozenset[int] = frozenset({9, 10, 11, 12, 1, 2})

_PRICE_QUANTUM = Decimal("0.01")


# Output dataclass


@dataclass(frozen=True)
class MonthlyPriceBreakdown:
    """Breakdown of the seasonal price computation."""

    monthly_eur: Decimal
    is_fixed_price: bool
    spring_days: int
    summer_days: int
    autumn_days: int

    @property
    def total_days(self) -> int:
        return self.spring_days + self.summer_days + self.autumn_days


# Day split (testable in isolation)


def _split_days_by_season(start: date, end: date) -> tuple[int, int, int]:
    """Count days in ``[start, end]`` (both inclusive) per season."""
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start}): empty period not allowed")

    spring = summer = autumn = 0
    cur = start
    one_day = timedelta(days=1)
    while cur <= end:
        m = cur.month
        if m in SPRING_MONTHS:
            spring += 1
        elif m in SUMMER_MONTHS:
            summer += 1
        else:
            autumn += 1
        cur += one_day
    return spring, summer, autumn


# Weighted price (public API)


def compute_room_monthly_price(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
    is_fixed: bool,
    period_start: date,
    period_end: date,
) -> MonthlyPriceBreakdown:
    """Return the monthly price the user should see for a stay."""
    spring_days, summer_days, autumn_days = _split_days_by_season(period_start, period_end)
    total_days = spring_days + summer_days + autumn_days

    if total_days <= 0:
        raise ValueError(
            f"Cannot compute monthly price over a zero-length period "
            f"({period_start} -> {period_end})"
        )

    if is_fixed:
        monthly = _resolve_fixed_price(spring_eur, summer_eur, autumn_eur)
    else:
        monthly = _weighted_average(
            spring_eur,
            summer_eur,
            autumn_eur,
            spring_days,
            summer_days,
            autumn_days,
            total_days,
        )

    return MonthlyPriceBreakdown(
        monthly_eur=monthly.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP),
        is_fixed_price=is_fixed,
        spring_days=spring_days,
        summer_days=summer_days,
        autumn_days=autumn_days,
    )


# Internal helpers


def _resolve_fixed_price(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
) -> Decimal:
    """Return the canonical monthly price for a fixed-price room.

    Well-formed data: the three columns are equal — pick any.
    Anomalous data: log a warning and return ``autumn_eur`` (the
    column most callers would expect).
    """
    if not (spring_eur == summer_eur == autumn_eur):
        logger.warning(
            "fixedprice='Y' but seasonal columns differ "
            "(spring=%s, summer=%s, autumn=%s) — falling back to autumn value",
            spring_eur,
            summer_eur,
            autumn_eur,
        )
    return autumn_eur


def _weighted_average(
    spring_eur: Decimal,
    summer_eur: Decimal,
    autumn_eur: Decimal,
    spring_days: int,
    summer_days: int,
    autumn_days: int,
    total_days: int,
) -> Decimal:
    """Compute Σ(price x days) / total_days with full Decimal precision."""
    weighted_sum = spring_eur * spring_days + summer_eur * summer_days + autumn_eur * autumn_days
    return weighted_sum / Decimal(total_days)
