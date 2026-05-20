"""Tests for Tool 3 — ``compute_total_cost``.

These tests exercise the entry point with a ``FakeDbExecutor`` and pin
the business rules confirmed by ELH operations on 2026-05-19
(supersedes 2026-05-11):

    * AT BOOKING (to ELH) = first month rent + 9% reservation fee.
    * AT CHECK-IN (to landlord) = security deposit + last-month
      advance (if ``lastmonthdeposit='Y'`` and stay >= 2 months) +
      administrative tax (if ``administrativetax > 0``).
    * MONTHLY DURING STAY = rent for months 2..N (or 2..N-1 if a
      last-month advance applies), plus an extra-person surcharge on
      every month when ``extrapersonallowed='Y'`` and the user opted in.
    * Same-season stay -> ``monthly_recurring_eur`` populated and
      ``monthly_breakdown`` is None; cross-season stay flips that.
    * Utilities are informational (lists of strings), never a cost line.
    * VAT disclosure always present in notes.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from elh_rag.tools._shared.room_id import InvalidRoomIdError, encode_room_id
from elh_rag.tools.compute_total_cost import (
    ComputeTotalCostInput,
    compute_total_cost,
)

# Helpers


def _make_room_row(
    *,
    idhouse: str = "HSE_001",
    idroom: str = "RM_001",
    h_dateupdate: datetime = datetime(2024, 9, 15, 10, 30),
    r_dateupdate: datetime = datetime(2024, 9, 15, 10, 30),
    spring: str = "400.00",
    summer: str = "300.00",
    autumn: str = "550.00",
    fixed: str = "N",
    deposit: str = "Y",
    deposit_value: str = "550.00",
    lastmonth: str = "N",
    extra_allowed: str = "N",
    extra_cost: str = "0",
    admin_tax: str = "0",
) -> dict:
    """Build a fake room row matching the SELECT columns of _ROOM_SQL."""
    return {
        "loc_idhouse": idhouse,
        "idroom": idroom,
        "loc_dateupdate": h_dateupdate,
        "dateupdate": r_dateupdate,
        "springprice": Decimal(spring),
        "summerprice": Decimal(summer),
        "autumnprice": Decimal(autumn),
        "fixedprice": fixed,
        "deposit": deposit,
        "depositvalue": Decimal(deposit_value),
        "lastmonthdeposit": lastmonth,
        "extrapersonallowed": extra_allowed,
        "extrapersoncost": Decimal(extra_cost),
        "administrativetax": Decimal(admin_tax),
        "roomname": "Test Room",
        "status": "Available",
    }


def _encoded(
    house: str = "HSE_001",
    room: str = "RM_001",
    dt: datetime = datetime(2024, 9, 15, 10, 30),
) -> str:
    return encode_room_id(house, room, dt)


def _seed(fake_db, room: dict | None = None, expenses: list[dict] | None = None) -> None:
    """Convenience: seed FakeDbExecutor with room + expenses responses."""
    fake_db.add_response("FROM room", [room] if room is not None else [])
    fake_db.add_response("FROM expenses", expenses if expenses is not None else [])


# Input validation


class TestInputValidation:
    def test_checkout_before_checkin_raises(self):
        with pytest.raises(ValidationError, match="must be strictly after"):
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 30),
                check_out_date=date(2026, 9, 1),
            )

    def test_checkout_equals_checkin_raises(self):
        with pytest.raises(ValidationError, match="must be strictly after"):
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 9, 1),
            )

    def test_stay_over_three_years_raises(self):
        with pytest.raises(ValidationError, match="too long"):
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2030, 1, 1),
            )

    def test_extra_person_defaults_false(self):
        payload = ComputeTotalCostInput(
            encoded_room_id=_encoded(),
            check_in_date=date(2026, 9, 1),
            check_out_date=date(2026, 11, 30),
        )
        assert payload.extra_person is False

    def test_valid_input_passes(self):
        payload = ComputeTotalCostInput(
            encoded_room_id=_encoded(),
            check_in_date=date(2026, 9, 1),
            check_out_date=date(2026, 11, 30),
        )
        assert payload.check_in_date == date(2026, 9, 1)
        assert payload.check_out_date == date(2026, 11, 30)


# Booking total composition


class TestBookingTotal:
    def test_deposit_only(self, fake_db):
        """deposit=Y, lastmonth=N -> booking = first month rent + reservation."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="Y", deposit_value="550.00", lastmonth="N"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # total rent = 3 * 550 = 1650; reservation = 1650 * 0.09 = 148.50
        # Booking = first_month (550) + reservation (148.50) = 698.50
        # Deposit (550) moved to at-check-in bucket.
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.one_time_at_checkin_eur == Decimal("550.00")

    def test_lastmonth_only(self, fake_db):
        """deposit=N, lastmonth=Y -> booking = first month rent + reservation;
        last-month advance lives in at-check-in."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="N", deposit_value="0", lastmonth="Y"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # First month (Sep, autumn) = 550; booking = 550 + 148.50.
        # last-month advance (Nov, autumn) = 550 moves to one_time_at_checkin.
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.one_time_at_checkin_eur == Decimal("550.00")

    def test_both_deposit_and_lastmonth(self, fake_db):
        """Both Y -> booking still = first month + reservation; deposit and
        last-month advance both live in at-check-in."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="Y", deposit_value="600.00", lastmonth="Y"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # booking = first month (550, autumn) + reservation (148.50) = 698.50
        # check-in = deposit (600) + last-month (550) = 1150
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.one_time_at_checkin_eur == Decimal("1150.00")

    def test_neither_deposit_nor_lastmonth(self, fake_db):
        """Both N -> booking = first month + reservation; at-check-in = None."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="N"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # booking = 550 (first month) + 148.50 (reservation) = 698.50
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.one_time_at_checkin_eur is None

    def test_reservation_fee_is_nine_percent_of_total_rent(self, fake_db):
        """Reservation fee scales linearly with total rent and is paid at booking."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="N"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),  # Sep 2026
                check_out_date=date(2027, 8, 31),  # Aug 2027 -> 12 months
            ),
            ctx=fake_db,
        )
        # 6 autumn (550) + 4 spring (400) + 2 summer (300) = 5500
        # reservation = 5500 * 0.09 = 495.00
        # first month (Sep, autumn) = 550
        # booking = 550 + 495 = 1045
        assert result.payable_at_booking_eur == Decimal("1045.00")

    def test_extra_person_allowed_is_recurring_monthly(self, fake_db):
        """extra_person=True + extrapersonallowed=Y -> surcharge applies every
        month of the stay, NOT as a one-shot at booking (corrected 2026-05-19)."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="N",
                lastmonth="N",
                extra_allowed="Y",
                extra_cost="200.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
                extra_person=True,
            ),
            ctx=fake_db,
        )
        # Booking is just first month + reservation (no extra-person here)
        # = 550 + 148.50 = 698.50
        assert result.payable_at_booking_eur == Decimal("698.50")
        # Extra-person now folded into the monthly recurring amount
        assert result.monthly_recurring_eur == Decimal("750.00")  # 550 + 200
        # Total stay includes extra-person * 3 months = 600 (not 200)
        # 1650 rent + 148.50 reservation + 600 extra = 2398.50
        assert result.total_stay_cost_eur == Decimal("2398.50")

    def test_extra_person_allowed_but_not_requested_no_cost(self, fake_db):
        """Room allows extra person, user did not opt in -> cost not added."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="N",
                lastmonth="N",
                extra_allowed="Y",
                extra_cost="200.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
                extra_person=False,
            ),
            ctx=fake_db,
        )
        # first month + reservation, no extra
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.monthly_recurring_eur == Decimal("550.00")

    def test_extra_person_requested_but_not_allowed_silently_skipped(self, fake_db):
        """extra_person=True but extrapersonallowed=N -> cost ignored + note added."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="N",
                lastmonth="N",
                extra_allowed="N",
                extra_cost="200.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
                extra_person=True,
            ),
            ctx=fake_db,
        )
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.monthly_recurring_eur == Decimal("550.00")
        # User must be informed that the option was unavailable
        assert any("does not allow" in n for n in result.notes)


# Recurring vs breakdown


class TestRecurringVsBreakdown:
    def test_same_season_returns_recurring(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.monthly_recurring_eur == Decimal("550.00")
        assert result.monthly_breakdown is None
        assert result.total_stay_months == 3

    def test_cross_season_returns_breakdown(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2026, 4, 30),
            ),
            ctx=fake_db,
        )
        assert result.monthly_recurring_eur is None
        assert result.monthly_breakdown is not None
        assert len(result.monthly_breakdown) == 4
        # Jan, Feb autumn (550); Mar, Apr spring (400)
        seasons = [m.season for m in result.monthly_breakdown]
        rents = [m.rent_eur for m in result.monthly_breakdown]
        assert seasons == ["autumn", "autumn", "spring", "spring"]
        assert rents == [
            Decimal("550.00"),
            Decimal("550.00"),
            Decimal("400.00"),
            Decimal("400.00"),
        ]

    def test_fixed_price_uniform_even_when_crossing_seasons(self, fake_db):
        """fixedprice=Y -> all months bill at autumn column, regardless of season."""
        _seed(
            fake_db,
            room=_make_room_row(spring="600.00", summer="600.00", autumn="600.00", fixed="Y"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2026, 4, 30),
            ),
            ctx=fake_db,
        )
        assert result.monthly_recurring_eur == Decimal("600.00")
        assert result.monthly_breakdown is None
        assert result.is_fixed_price is True

    def test_total_stay_months_counts_calendar_months_mid_month_dates(self, fake_db):
        """Mid-month check-in/out still bills full calendar months (Model B)."""
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 28),  # late in month
                check_out_date=date(2027, 2, 3),  # early in month
            ),
            ctx=fake_db,
        )
        # Sep, Oct, Nov, Dec, Jan, Feb = 6 months
        assert result.total_stay_months == 6


# Admin fee


class TestAdminFee:
    def test_admin_fee_populated_when_positive(self, fake_db):
        """admin_tax > 0 -> at-check-in bucket includes it alongside the
        deposit (from the _make_room_row default of deposit='Y'/550)."""
        _seed(fake_db, room=_make_room_row(admin_tax="120.00"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # one_time_at_checkin = deposit (550) + admin (120) = 670
        assert result.one_time_at_checkin_eur == Decimal("670.00")
        assert any("Administrative fee" in n for n in result.notes)
        assert any("directly to the landlord" in n for n in result.notes)

    def test_admin_fee_excluded_from_booking_total(self, fake_db):
        """Admin fee MUST NOT appear in payable_at_booking_eur."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="N", lastmonth="N", admin_tax="120.00"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # booking = first month (550) + reservation (148.50) = 698.50
        # admin lives in at-check-in (and is the only thing, deposit=N and lastmonth=N)
        assert result.payable_at_booking_eur == Decimal("698.50")
        assert result.one_time_at_checkin_eur == Decimal("120.00")

    def test_admin_fee_none_when_zero(self, fake_db):
        """admin=0 + deposit=N + lastmonth=N -> at-check-in bucket is None."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="N", admin_tax="0"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.one_time_at_checkin_eur is None
        assert not any("Administrative fee" in n for n in result.notes)


# Utilities


class TestUtilities:
    def test_utilities_categorization_passed_through(self, fake_db):
        _seed(
            fake_db,
            room=_make_room_row(),
            expenses=[
                {"description": "Gas", "maximumvalue": Decimal("25.00")},
                {"description": "Internet/WiFi", "maximumvalue": None},
            ],
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert "Gas (up to €25.00/mo)" in result.utilities_included
        assert "Internet/WiFi (not included — paid to provider)" in result.utilities_excluded

    def test_no_utilities_returns_empty_lists(self, fake_db):
        _seed(fake_db, room=_make_room_row(), expenses=[])
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.utilities_included == []
        assert result.utilities_excluded == []

    def test_expenses_query_joined_on_house_version(self, fake_db):
        """Expenses must be looked up by room.loc_dateupdate, not r.dateupdate."""
        room = _make_room_row(
            h_dateupdate=datetime(2024, 1, 1, 0, 0),
            r_dateupdate=datetime(2025, 6, 1, 0, 0),  # different
        )
        _seed(fake_db, room=room, expenses=[])

        compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # 2 calls expected: 1 for room, 1 for expenses
        assert len(fake_db.calls) == 2
        expenses_call = fake_db.calls[1]
        # The expenses params must carry the HOUSE dateupdate
        assert expenses_call["params"] == ("HSE_001", datetime(2024, 1, 1, 0, 0))


# Notes


class TestNotes:
    def test_vat_disclosure_always_present(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert any("VAT" in n for n in result.notes)

    def test_deposit_refundability_note(self, fake_db):
        _seed(fake_db, room=_make_room_row(deposit="Y", deposit_value="550.00"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert any("Security deposit" in n and "refundable" in n for n in result.notes)

    def test_no_deposit_note_when_no_deposit(self, fake_db):
        _seed(fake_db, room=_make_room_row(deposit="N", deposit_value="0"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert not any("Security deposit" in n for n in result.notes)

    def test_reservation_fee_note(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert any("Reservation fee" in n for n in result.notes)

    def test_lastmonth_advance_note(self, fake_db):
        _seed(fake_db, room=_make_room_row(lastmonth="Y"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # User must understand that no payment is due for the final month
        assert any(
            "last month" in n.lower() and "no further payment" in n.lower() for n in result.notes
        )


# Error handling


class TestErrorHandling:
    def test_no_ctx_raises(self):
        with pytest.raises(RuntimeError, match="DBExecutor"):
            compute_total_cost(
                ComputeTotalCostInput(
                    encoded_room_id=_encoded(),
                    check_in_date=date(2026, 9, 1),
                    check_out_date=date(2026, 11, 30),
                ),
                ctx=None,
            )

    def test_room_not_found_raises(self, fake_db):
        # No room row -> _fetch_room returns None
        _seed(fake_db, room=None)
        with pytest.raises(ValueError, match="Room not found"):
            compute_total_cost(
                ComputeTotalCostInput(
                    encoded_room_id=_encoded(),
                    check_in_date=date(2026, 9, 1),
                    check_out_date=date(2026, 11, 30),
                ),
                ctx=fake_db,
            )

    def test_malformed_room_id_house_format_raises(self, fake_db):
        """A house-format id (2 segments) must NOT decode as a room id."""
        with pytest.raises(InvalidRoomIdError):
            compute_total_cost(
                ComputeTotalCostInput(
                    encoded_room_id="HSE_001|2024-09-15T10:30:00",
                    check_in_date=date(2026, 9, 1),
                    check_out_date=date(2026, 11, 30),
                ),
                ctx=fake_db,
            )

    def test_malformed_room_id_garbage_raises(self, fake_db):
        with pytest.raises(InvalidRoomIdError):
            compute_total_cost(
                ComputeTotalCostInput(
                    encoded_room_id="not-an-encoded-id",
                    check_in_date=date(2026, 9, 1),
                    check_out_date=date(2026, 11, 30),
                ),
                ctx=fake_db,
            )


# Summary


class TestSummary:
    def test_summary_same_season_mentions_monthly_rate(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert "3-month" in result.summary
        assert "550" in result.summary
        assert "due at booking" in result.summary

    def test_summary_cross_season_mentions_range(self, fake_db):
        _seed(fake_db, room=_make_room_row())
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2026, 4, 30),
            ),
            ctx=fake_db,
        )
        assert "cross-season" in result.summary
        assert "4-month" in result.summary
        # Both extremes of the monthly range visible
        assert "400" in result.summary
        assert "550" in result.summary

    def test_summary_fixed_price_labelled_correctly(self, fake_db):
        _seed(
            fake_db,
            room=_make_room_row(spring="600.00", summer="600.00", autumn="600.00", fixed="Y"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert "fixed rate" in result.summary


# Aggregate fields: total_stay_cost, refundable, out-of-pocket


class TestStructuredAggregates:
    """Verify the new aggregate fields are correct and internally consistent."""

    def test_total_stay_cost_matches_sum_of_components(self, fake_db):
        """Gross total = rent + deposit + reservation fee + extra + admin tax."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="Y",
                deposit_value="550.00",
                lastmonth="N",
                extra_allowed="N",
                admin_tax="0",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # 3 months autumn (550) -> rent = 1650
        # deposit = 550, reservation = 148.50, extra = 0, admin = 0
        # total = 1650 + 550 + 148.50 = 2348.50
        assert result.total_stay_cost_eur == Decimal("2348.50")

    def test_total_stay_cost_includes_admin_tax(self, fake_db):
        """The admin tax (paid to landlord at check-in) is part of the gross total."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="N",
                lastmonth="N",
                admin_tax="120.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # rent 1650 + reservation 148.50 + admin 120 = 1918.50
        assert result.total_stay_cost_eur == Decimal("1918.50")

    def test_total_stay_cost_no_double_count_when_lastmonth_advance(self, fake_db):
        """lastmonth='Y' pre-pays the final month but that month is still in
        breakdown.total_rent_eur; the aggregate must NOT add it twice."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="N", lastmonth="Y", admin_tax="0"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # 3 months autumn (550) -> rent = 1650
        # reservation = 148.50, deposit = 0, extra = 0, admin = 0
        # total = 1650 + 148.50 = 1798.50 (NOT 1798.50 + 550)
        assert result.total_stay_cost_eur == Decimal("1798.50")

    def test_refundable_equals_security_deposit(self, fake_db):
        """Only the security deposit is refundable. Reservation fee and
        last-month advance are NOT in the refundable bucket."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="Y",
                deposit_value="550.00",
                lastmonth="Y",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.refundable_at_checkout_eur == Decimal("550.00")

    def test_refundable_zero_when_no_deposit(self, fake_db):
        _seed(fake_db, room=_make_room_row(deposit="N", deposit_value="0"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.refundable_at_checkout_eur == Decimal("0")

    def test_out_of_pocket_equals_total_minus_refundable(self, fake_db):
        """Invariant: total_out_of_pocket = total_stay_cost - refundable."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="Y",
                deposit_value="550.00",
                lastmonth="Y",
                admin_tax="50.00",
                extra_allowed="Y",
                extra_cost="100.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
                extra_person=True,
            ),
            ctx=fake_db,
        )
        assert (
            result.total_out_of_pocket_eur
            == result.total_stay_cost_eur - result.refundable_at_checkout_eur
        )

    def test_aggregates_consistent_for_cross_season_stay(self, fake_db):
        """Cross-season stay: the aggregates must reconcile with
        per-month breakdown + booking + admin."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="Y", deposit_value="550.00", admin_tax="50.00"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2026, 4, 30),
            ),
            ctx=fake_db,
        )
        # months: Jan, Feb autumn 550 + Mar, Apr spring 400 = 1900
        # deposit 550 + reservation (1900 * 0.09 = 171) + admin 50
        # total = 1900 + 550 + 171 + 50 = 2671
        assert result.monthly_breakdown is not None
        per_month_sum = sum((m.rent_eur for m in result.monthly_breakdown), Decimal("0"))
        assert per_month_sum == Decimal("1900.00")
        assert result.total_stay_cost_eur == Decimal("2671.00")
        assert result.refundable_at_checkout_eur == Decimal("550.00")
        assert result.total_out_of_pocket_eur == Decimal("2121.00")


# Corrected payment schedule


class TestCorrectedPaymentSchedule:
    """Verify the payment schedule corresponds to ELH operations
    confirmation 2026-05-19 (supersedes 2026-05-11)."""

    def test_first_month_rent_in_payable_at_booking(self, fake_db):
        """Booking total = first month rent + reservation fee (no deposit,
        no last-month advance)."""
        _seed(
            fake_db,
            room=_make_room_row(
                spring="450.00",
                summer="450.00",
                autumn="450.00",
                fixed="Y",
                deposit="N",
                lastmonth="N",
                admin_tax="0",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2027, 2, 28),  # 6 months
            ),
            ctx=fake_db,
        )
        # rent = 6 * 450 = 2700; reservation = 2700 * 0.09 = 243
        # booking = first month (450) + reservation (243) = 693
        assert result.payable_at_booking_eur == Decimal("693.00")
        # No other check-in or refundable buckets
        assert result.one_time_at_checkin_eur is None
        assert result.refundable_at_checkout_eur == Decimal("0")

    def test_deposit_in_at_checkin(self, fake_db):
        """Deposit lives in one_time_at_checkin, not payable_at_booking."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="Y", deposit_value="500.00", lastmonth="N", admin_tax="0"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # 500 must NOT be in payable_at_booking (which has only first month +
        # reservation), but MUST be in one_time_at_checkin.
        assert Decimal("500.00") not in (
            result.payable_at_booking_eur,
            result.payable_at_booking_eur - Decimal("148.50"),
        )
        assert result.one_time_at_checkin_eur == Decimal("500.00")
        assert result.refundable_at_checkout_eur == Decimal("500.00")

    def test_last_month_advance_in_at_checkin(self, fake_db):
        """Last-month advance lives in one_time_at_checkin (paid to landlord)."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="Y", admin_tax="0"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        # Last month (Nov, autumn) = 550; at-check-in = 550 (no deposit, no admin)
        assert result.one_time_at_checkin_eur == Decimal("550.00")

    def test_admin_tax_in_at_checkin(self, fake_db):
        """Administrative tax lives in one_time_at_checkin (paid to landlord)."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="N", lastmonth="N", admin_tax="80.00"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.one_time_at_checkin_eur == Decimal("80.00")
        # And NOT in payable_at_booking
        assert result.payable_at_booking_eur == Decimal("698.50")  # 550 + 148.50

    def test_extra_person_is_recurring_monthly(self, fake_db):
        """Extra-person surcharge applies to every month, not just booking.
        For 6 months at €50/mo extra: total adds €300, NOT €50."""
        _seed(
            fake_db,
            room=_make_room_row(
                spring="450.00",
                summer="450.00",
                autumn="450.00",
                fixed="Y",
                deposit="N",
                lastmonth="N",
                extra_allowed="Y",
                extra_cost="50.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2027, 2, 28),  # 6 months
                extra_person=True,
            ),
            ctx=fake_db,
        )
        # rent 2700 + reservation 243 + extra (50 * 6) = 300 -> total 3243
        assert result.total_stay_cost_eur == Decimal("3243.00")
        # Recurring includes the surcharge
        assert result.monthly_recurring_eur == Decimal("500.00")  # 450 + 50

    def test_extra_person_zero_when_not_opted_in(self, fake_db):
        """payload.extra_person=False -> no surcharge regardless of room
        ``extrapersonallowed``."""
        _seed(
            fake_db,
            room=_make_room_row(
                deposit="N",
                lastmonth="N",
                extra_allowed="Y",
                extra_cost="200.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
                extra_person=False,
            ),
            ctx=fake_db,
        )
        # No extra anywhere
        assert result.monthly_recurring_eur == Decimal("550.00")  # rent only
        # Notes do NOT mention the surcharge
        assert not any("surcharge" in n.lower() for n in result.notes)

    def test_monthly_breakdown_includes_extra_person(self, fake_db):
        """In cross-season stays, each monthly_breakdown entry's rent_eur
        already folds in the extra-person surcharge."""
        _seed(
            fake_db,
            room=_make_room_row(extra_allowed="Y", extra_cost="50.00"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 1, 1),
                check_out_date=date(2026, 4, 30),
                extra_person=True,
            ),
            ctx=fake_db,
        )
        # Jan, Feb autumn 550 + 50 = 600; Mar, Apr spring 400 + 50 = 450
        assert result.monthly_breakdown is not None
        rents = [m.rent_eur for m in result.monthly_breakdown]
        assert rents == [
            Decimal("600.00"),
            Decimal("600.00"),
            Decimal("450.00"),
            Decimal("450.00"),
        ]

    def test_total_stay_cost_breakdown_consistent(self, fake_db):
        """total_stay_cost = at_booking + at_check_in + remaining months
        rent + extra_person_total. Verify the invariant on a stay with
        every component active."""
        _seed(
            fake_db,
            room=_make_room_row(
                spring="450.00",
                summer="450.00",
                autumn="450.00",
                fixed="Y",
                deposit="Y",
                deposit_value="450.00",
                lastmonth="Y",
                admin_tax="50.00",
                extra_allowed="Y",
                extra_cost="50.00",
            ),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2027, 2, 28),  # 6 months
                extra_person=True,
            ),
            ctx=fake_db,
        )
        # rent = 6 * 450 = 2700; reservation = 243
        # booking = 450 + 243 = 693
        # at_checkin = deposit 450 + last-month 450 + admin 50 = 950
        # remaining months 2..5 (lastmonth=Y so excludes month 6): 4 * 450 = 1800
        # extra: 6 * 50 = 300
        # total = 693 + 950 + 1800 + 300 = 3743
        assert result.payable_at_booking_eur == Decimal("693.00")
        assert result.one_time_at_checkin_eur == Decimal("950.00")
        assert result.total_stay_cost_eur == Decimal("3743.00")
        # Refundable = deposit only
        assert result.refundable_at_checkout_eur == Decimal("450.00")
        # Out of pocket = total - refundable
        assert result.total_out_of_pocket_eur == Decimal("3293.00")

    def test_one_month_stay_ignores_lastmonth_advance(self, fake_db):
        """Defensive guard: a 1-month stay with lastmonthdeposit='Y' would
        otherwise charge the same month twice (once at booking as first
        month, once at check-in as last-month advance). Treat as if
        lastmonth='N'."""
        _seed(
            fake_db,
            room=_make_room_row(deposit="N", lastmonth="Y", admin_tax="0"),
        )
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 9, 30),  # 1 month (Sep only)
            ),
            ctx=fake_db,
        )
        # rent = 550; reservation = 49.50; total = 599.50 (no double-count)
        assert result.total_stay_months == 1
        assert result.one_time_at_checkin_eur is None
        assert result.payable_at_booking_eur == Decimal("599.50")  # 550 + 49.50
        assert result.total_stay_cost_eur == Decimal("599.50")
