"""Tool 2: ``find_available_rooms``.

Specialisation of :func:`find_rooms` with **dates as a hard constraint**.

The base tool (Tool 1) treats ``available_from`` / ``available_to`` as
soft hints: if absent, it falls back to autumn pricing and ignores
reservation overlap. Tool 2 makes them mandatory and adds two pieces
of logic on top of Tool 1's structural filtering:

    1. **Reservation overlap exclusion** — rooms with any
       ``reservation`` row whose ``[blockeddatestart, blockeddataend)``
       interval overlaps the requested window are removed from the
       result.

    2. **Season-aware weighted pricing** — instead of selecting a single
       seasonal column (``springprice`` / ``summerprice`` /
       ``autumnprice``), the monthly price is the weighted average over
       the days of the requested period that fall in each season.
       Rooms with ``fixedprice = 'Y'`` keep their flat price and are
       flagged via ``is_fixed_price`` on the output.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .find_rooms import FindRoomsInput

# Input model

_MAX_PERIOD_YEARS = 3
_MAX_PERIOD_DAYS = _MAX_PERIOD_YEARS * 366  # 366 to be safe across leap years


class FindAvailableRoomsInput(FindRoomsInput):
    """Search rooms with availability over a hard date window."""

    available_from: date = Field(
        ...,
        description="First day of the requested stay (inclusive). Required.",
    )
    available_to: date = Field(
        ...,
        description="Last day of the requested stay (inclusive). "
        "Must be strictly after available_from.",
    )

    @model_validator(mode="after")
    def check_period_bounds(self) -> FindAvailableRoomsInput:
        """Reject pathological periods (zero-length already caught upstream)."""
        delta = (self.available_to - self.available_from).days
        if delta > _MAX_PERIOD_DAYS:
            raise ValueError(
                f"Requested period is too long ({delta} days, max {_MAX_PERIOD_DAYS}). "
                "Erasmus contracts rarely exceed 12 months; if a longer stay is genuinely "
                "needed, split the request."
            )
        return self
