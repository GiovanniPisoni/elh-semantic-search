"""Tool 3: ``compute_total_cost``.

Given a specific room and a stay window,
return the full cost picture the student needs at booking time:

    * amount payable at booking
        = security deposit
        + last-month advance (if lastmonthdeposit='Y')
        + reservation fee (9% of total rent, configurable)
        + extra-person cost (one-shot, opt-in)
    * monthly recurring amount (if all months bill at the same rate)
        or per-month breakdown (cross-season stays)
    * one-time amount paid to landlord at check-in (administrativetax)
    * utility coverage lists (informational, not a cost line)
    * notes explaining refundability, last-month semantics, who-pays-what
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from elh_rag.config import settings

from .._shared.db import DBExecutor
from .._shared.pricing import MonthRent, StayCostBreakdown, compute_stay_breakdown
from .._shared.room_id import decode_room_id, normalize_id
from ..base import register_tool
from ._expenses import UtilityCategorization, fetch_utility_categorization

_PRICE_QUANTUM = Decimal("0.01")
_MAX_STAY_DAYS = 3 * 366


# Input model


class ComputeTotalCostInput(BaseModel):
    """Inputs for total-cost computation on a specific room version."""

    encoded_room_id: str = Field(
        ...,
        description=(
            "Encoded room id from the output of find_rooms or "
            "find_available_rooms (format: 'house_id|room_id|dateupdate'). "
            "Identifies a specific versioned room row."
        ),
    )
    check_in_date: date = Field(
        ...,
        description="First day of the stay (inclusive).",
    )
    check_out_date: date = Field(
        ...,
        description=("Last day of the stay (inclusive). Must be strictly after check_in_date."),
    )
    extra_person: bool = Field(
        default=False,
        description=(
            "Whether an additional guest will share the room. Only adds "
            "to the booking total if the room actually allows it "
            "(extrapersonallowed='Y'); silently ignored otherwise."
        ),
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> ComputeTotalCostInput:
        if self.check_out_date <= self.check_in_date:
            raise ValueError(
                f"check_out_date ({self.check_out_date}) must be strictly "
                f"after check_in_date ({self.check_in_date})."
            )
        delta = (self.check_out_date - self.check_in_date).days
        if delta > _MAX_STAY_DAYS:
            raise ValueError(
                f"Requested stay is too long ({delta} days, max {_MAX_STAY_DAYS}). "
                "Erasmus contracts rarely exceed 36 months; split the request "
                "if a longer stay is genuinely needed."
            )
        return self


# Output model


class MonthRentOut(BaseModel):
    """Per-month rent line in the cost breakdown."""

    year: int
    month: int = Field(..., ge=1, le=12)
    season: str  # "spring" | "summer" | "autumn"
    rent_eur: Decimal


class ComputeTotalCostOutput(BaseModel):
    """Full cost breakdown returned to the orchestrator."""

    payable_at_booking_eur: Decimal = Field(
        ...,
        description=(
            "Single total the student pays to confirm the booking. "
            "Includes security deposit, last-month advance (when applicable), "
            "reservation fee, and extra-person cost (when opted in)."
        ),
    )
    total_stay_cost_eur: Decimal = Field(
        ...,
        description=(
            "Total cash outflow for the entire stay: every monthly rent + "
            "reservation fee + security deposit + extra-person cost + admin "
            "tax. Equivalent to summing the at-booking, at-check-in and all "
            "monthly payments; the last-month advance (when applicable) is "
            "already accounted for in the monthly rent total, so this is "
            "the gross amount the student parts with."
        ),
    )
    total_out_of_pocket_eur: Decimal = Field(
        ...,
        description=(
            "Net non-refundable spend: ``total_stay_cost_eur`` minus "
            "``refundable_at_checkout_eur``. This is the figure the "
            "student actually loses to ELH and the landlord."
        ),
    )
    refundable_at_checkout_eur: Decimal = Field(
        ...,
        description=(
            "Amount returned to the student at check-out: the security "
            "deposit (subject to landlord assessment). The reservation "
            "fee is refundable only in the rare case of a listing "
            "mismatch on arrival and is NOT included here; the last-month "
            "advance is a rent pre-payment, not refundable."
        ),
    )
    monthly_recurring_eur: Decimal | None = Field(
        default=None,
        description=(
            "Recurring monthly amount. Populated when every month of the "
            "stay bills at the same rate; otherwise ``None`` and "
            "``monthly_breakdown`` is populated instead."
        ),
    )
    monthly_breakdown: list[MonthRentOut] | None = Field(
        default=None,
        description=(
            "Per-month rent for cross-season stays. Populated when "
            "``monthly_recurring_eur`` is ``None``."
        ),
    )
    one_time_at_checkin_eur: Decimal | None = Field(
        default=None,
        description=(
            "Administrative fee paid by the student directly to the "
            "landlord at check-in (not to ELH). Populated only if the "
            "room has a non-zero administrativetax."
        ),
    )
    utilities_included: list[str] = Field(
        default_factory=list,
        description=(
            "Utilities covered by the rent up to their monthly cap, "
            "e.g. 'Gas (up to €25.00/mo)'. Informational only."
        ),
    )
    utilities_excluded: list[str] = Field(
        default_factory=list,
        description=(
            "Utilities the student must arrange and pay separately, "
            "e.g. 'Internet/WiFi (not included — paid to provider)'."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Human-readable disclosures: deposit refundability, "
            "last-month-advance semantics, admin-fee destination, etc."
        ),
    )
    is_fixed_price: bool = Field(
        ...,
        description="True if the room uses fixedprice='Y' (no seasonal variation).",
    )
    total_stay_months: int = Field(
        ...,
        description="Number of calendar months billed for the stay (model B).",
    )
    summary: str = Field(
        ...,
        description="One-line human-readable summary, suitable for LLM consumption.",
    )


# SQL


_ROOM_SQL = """\
SELECT DISTINCT ON (loc_idhouse, idroom)
    loc_idhouse, idroom, loc_dateupdate, dateupdate,
    springprice, summerprice, autumnprice, fixedprice,
    deposit, depositvalue, lastmonthdeposit,
    extrapersonallowed, extrapersoncost,
    administrativetax,
    roomname, status
FROM room
WHERE loc_idhouse = %s AND idroom = %s
ORDER BY loc_idhouse, idroom, dateupdate DESC
"""


def _fetch_room(db: DBExecutor, house_id: str, room_id: str) -> dict[str, Any] | None:
    rows = db.execute(_ROOM_SQL, (house_id, room_id))
    return rows[0] if rows else None


# Quantization helper


def _q(d: Decimal) -> Decimal:
    """Round a Decimal to two decimal places, half-up."""
    return d.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any) -> Decimal:
    """Convert a DB numeric (possibly None / int / float / str / Decimal) to Decimal."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# Cost composition


def _compute(
    room: dict[str, Any],
    payload: ComputeTotalCostInput,
    utilities: UtilityCategorization,
) -> ComputeTotalCostOutput:
    """Assemble the full output from the room row + utilities + payload."""
    is_fixed = room["fixedprice"] == "Y"

    # 1. Per-month rent breakdown
    breakdown: StayCostBreakdown = compute_stay_breakdown(
        spring_eur=_to_decimal(room["springprice"]),
        summer_eur=_to_decimal(room["summerprice"]),
        autumn_eur=_to_decimal(room["autumnprice"]),
        is_fixed=is_fixed,
        check_in=payload.check_in_date,
        check_out=payload.check_out_date,
    )

    # 2. Reservation fee (% of total rent)
    pct = Decimal(str(settings.reservation_fee_pct))
    reservation_fee = _q(breakdown.total_rent_eur * pct)

    # 3. Security deposit
    deposit_required = room["deposit"] == "Y"
    security_deposit = _q(_to_decimal(room["depositvalue"])) if deposit_required else Decimal("0")

    # 4. Last-month advance (paid upfront, no payment due in final month)
    is_lastmonth = room["lastmonthdeposit"] == "Y"
    lastmonth_advance = breakdown.months[-1].rent_eur if is_lastmonth else Decimal("0")

    # 5. Extra-person cost — one-shot for the entire stay, only if allowed
    extra_person_cost = Decimal("0")
    if payload.extra_person and room["extrapersonallowed"] == "Y":
        extra_person_cost = _q(_to_decimal(room["extrapersoncost"]))

    # 6. Booking total
    payable_at_booking = _q(
        security_deposit + lastmonth_advance + reservation_fee + extra_person_cost
    )

    # 7. Admin fee at check-in (paid directly to landlord, not ELH)
    admin_raw = _to_decimal(room["administrativetax"])
    one_time_checkin: Decimal | None = _q(admin_raw) if admin_raw > 0 else None

    # 7b. Aggregates: gross spend, refundable portion, net out-of-pocket.
    # Note: ``breakdown.total_rent_eur`` already includes the last month's
    # rent, so adding it directly avoids double-counting the lastmonth
    # advance (which is just the last month's rent paid early).
    admin_amount = one_time_checkin or Decimal("0")
    total_stay_cost = _q(
        security_deposit
        + reservation_fee
        + extra_person_cost
        + breakdown.total_rent_eur
        + admin_amount
    )
    refundable_at_checkout = _q(security_deposit)
    total_out_of_pocket = _q(total_stay_cost - refundable_at_checkout)

    # 8. Recurring vs breakdown
    if breakdown.is_uniform_rent:
        monthly_recurring: Decimal | None = breakdown.months[0].rent_eur
        monthly_breakdown_out: list[MonthRentOut] | None = None
    else:
        monthly_recurring = None
        monthly_breakdown_out = [_to_month_out(m) for m in breakdown.months]

    # 9. Notes
    notes = _build_notes(
        security_deposit=security_deposit,
        lastmonth_advance=lastmonth_advance,
        reservation_fee=reservation_fee,
        extra_person_cost=extra_person_cost,
        extra_person_requested=payload.extra_person,
        extra_person_allowed=(room["extrapersonallowed"] == "Y"),
        one_time_checkin=one_time_checkin,
    )

    # 10. Summary
    summary = _compose_summary(
        breakdown=breakdown,
        payable_at_booking=payable_at_booking,
        monthly_recurring=monthly_recurring,
        is_fixed=is_fixed,
    )

    return ComputeTotalCostOutput(
        payable_at_booking_eur=payable_at_booking,
        total_stay_cost_eur=total_stay_cost,
        total_out_of_pocket_eur=total_out_of_pocket,
        refundable_at_checkout_eur=refundable_at_checkout,
        monthly_recurring_eur=monthly_recurring,
        monthly_breakdown=monthly_breakdown_out,
        one_time_at_checkin_eur=one_time_checkin,
        utilities_included=list(utilities.included),
        utilities_excluded=list(utilities.excluded),
        notes=notes,
        is_fixed_price=is_fixed,
        total_stay_months=breakdown.total_months,
        summary=summary,
    )


def _to_month_out(m: MonthRent) -> MonthRentOut:
    return MonthRentOut(year=m.year, month=m.month, season=m.season, rent_eur=m.rent_eur)


def _build_notes(
    *,
    security_deposit: Decimal,
    lastmonth_advance: Decimal,
    reservation_fee: Decimal,
    extra_person_cost: Decimal,
    extra_person_requested: bool,
    extra_person_allowed: bool,
    one_time_checkin: Decimal | None,
) -> list[str]:
    """Compose user-facing disclosures from the cost components."""
    notes: list[str] = []
    if security_deposit > 0:
        notes.append(
            f"Security deposit of €{security_deposit} is refundable at the "
            "end of the stay, subject to landlord assessment."
        )
    if lastmonth_advance > 0:
        notes.append(
            f"The last month's rent (€{lastmonth_advance}) has been paid "
            "upfront at booking; no further payment is due for the final "
            "month of the stay."
        )
    if reservation_fee > 0:
        notes.append(
            f"Reservation fee of €{reservation_fee} is refundable only if "
            "the room does not match the listing upon arrival."
        )
    if extra_person_cost > 0:
        notes.append(
            f"Extra-person cost (€{extra_person_cost}) is a one-time fee "
            "for the entire stay, not a recurring monthly charge."
        )
    elif extra_person_requested and not extra_person_allowed:
        notes.append(
            "Extra-person option requested but this room does not allow "
            "additional guests (extrapersonallowed='N')."
        )
    if one_time_checkin is not None:
        notes.append(
            f"Administrative fee of €{one_time_checkin} is paid directly "
            "to the landlord at check-in, not to ELH. Request an invoice "
            "from the landlord if needed."
        )
    notes.append("All prices include VAT.")
    return notes


def _compose_summary(
    *,
    breakdown: StayCostBreakdown,
    payable_at_booking: Decimal,
    monthly_recurring: Decimal | None,
    is_fixed: bool,
) -> str:
    """One-line summary for the LLM to quote back to the user."""
    months = breakdown.total_months
    rate_descr = "fixed rate" if is_fixed else "seasonal rate"
    if monthly_recurring is not None:
        return (
            f"{months}-month stay at €{monthly_recurring}/month ({rate_descr}); "
            f"€{payable_at_booking} due at booking."
        )
    # Cross-season — show min/max
    rents = [m.rent_eur for m in breakdown.months]
    return (
        f"{months}-month cross-season stay (€{min(rents)}-€{max(rents)}/month, {rate_descr}); "
        f"€{payable_at_booking} due at booking."
    )


# Registered tool


@register_tool(
    name="compute_total_cost",
    description=(
        "Compute the full cost breakdown for staying in a specific ELH "
        "room over a date window. Takes an encoded room id (from "
        "find_rooms or find_available_rooms output) and check-in/check-out "
        "dates. Returns: amount payable at booking (security deposit + "
        "9% reservation fee + last-month advance if applicable + "
        "extra-person cost if opted in), monthly recurring rent OR per-month "
        "breakdown when the stay spans seasons with different rates, the "
        "administrative fee paid to the landlord at check-in, and which "
        "utilities are included up to a monthly cap vs which the student "
        "must pay the provider directly. Use this tool when the user asks "
        "'how much does X cost in total', 'what do I pay at booking', "
        "or 'total cost for N months in this flat'. Always run find_rooms "
        "or find_available_rooms first to obtain the encoded_room_id."
    ),
    input_model=ComputeTotalCostInput,
    ctx_attr="db",
)
def compute_total_cost(
    payload: ComputeTotalCostInput,
    ctx: DBExecutor | None,
) -> ComputeTotalCostOutput:
    """Compute the full cost picture for a specific room and stay window."""
    if ctx is None:
        raise RuntimeError(
            "compute_total_cost requires a DBExecutor in ctx. "
            "Bootstrap the orchestrator with a configured executor."
        )

    parts = decode_room_id(payload.encoded_room_id)

    room = _fetch_room(ctx, parts.house_id, parts.room_id)
    if room is None:
        raise ValueError(
            f"Room not found for encoded id {payload.encoded_room_id!r}. "
            "It may have been deactivated since the search ran."
        )

    # Use loc_dateupdate (the house version this room version is attached
    # to) for the expenses join, not the room's own dateupdate.
    utilities = fetch_utility_categorization(
        ctx,
        house_id=normalize_id(room["loc_idhouse"], name="loc_idhouse"),
        house_dateupdate=room["loc_dateupdate"],
    )

    return _compute(room=room, payload=payload, utilities=utilities)
