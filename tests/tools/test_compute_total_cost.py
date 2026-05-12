"""Tests for Tool 3 — ``compute_total_cost``.

These tests exercise the entry point with a ``FakeDbExecutor`` and pin
the business rules confirmed by ELH on 2026-05-11:

    * Booking total = security deposit + last-month advance (if
      ``lastmonthdeposit='Y'``) + reservation fee (9% of total rent) +
      extra-person cost (one-shot, only if ``extrapersonallowed='Y'``).
    * Same-season stay -> ``monthly_recurring_eur`` populated and
      ``monthly_breakdown`` is None; cross-season stay flips that.
    * Admin fee (``administrativetax``) is paid directly to the
      landlord at check-in; it is NOT included in
      ``payable_at_booking_eur``.
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
        """deposit=Y, lastmonth=N -> booking = deposit + reservation_fee."""
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
        # total rent = 3 * 550 = 1650
        # reservation = 1650 * 0.09 = 148.50
        # booking = deposit (550) + reservation (148.50) = 698.50
        assert result.payable_at_booking_eur == Decimal("698.50")

    def test_lastmonth_only(self, fake_db):
        """deposit=N, lastmonth=Y -> booking = last-month rent + reservation."""
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
        # last month (Nov) = autumn = 550
        # booking = 550 + 148.50 = 698.50
        assert result.payable_at_booking_eur == Decimal("698.50")

    def test_both_deposit_and_lastmonth(self, fake_db):
        """Both Y -> both amounts contribute to booking total."""
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
        # 600 (deposit) + 550 (last-month) + 148.50 (reservation) = 1298.50
        assert result.payable_at_booking_eur == Decimal("1298.50")

    def test_neither_deposit_nor_lastmonth(self, fake_db):
        """Both N -> booking = reservation only."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="N"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.payable_at_booking_eur == Decimal("148.50")

    def test_reservation_fee_is_nine_percent_of_total_rent(self, fake_db):
        """Reservation fee scales linearly with total rent."""
        _seed(fake_db, room=_make_room_row(deposit="N", lastmonth="N"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),  # Sep 2026
                check_out_date=date(2027, 8, 31),  # Aug 2027 -> 12 months
            ),
            ctx=fake_db,
        )
        # 6 autumn (550) + 4 spring (400) + 2 summer (300)
        # = 3300 + 1600 + 600 = 5500
        # reservation = 5500 * 0.09 = 495.00
        assert result.payable_at_booking_eur == Decimal("495.00")

    def test_extra_person_allowed_adds_one_shot_cost(self, fake_db):
        """extra_person=True + extrapersonallowed=Y -> cost added once to booking."""
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
        # reservation (148.50) + extra (200) = 348.50
        assert result.payable_at_booking_eur == Decimal("348.50")

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
        # only reservation
        assert result.payable_at_booking_eur == Decimal("148.50")

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
        assert result.payable_at_booking_eur == Decimal("148.50")
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
        _seed(fake_db, room=_make_room_row(admin_tax="120.00"))
        result = compute_total_cost(
            ComputeTotalCostInput(
                encoded_room_id=_encoded(),
                check_in_date=date(2026, 9, 1),
                check_out_date=date(2026, 11, 30),
            ),
            ctx=fake_db,
        )
        assert result.one_time_at_checkin_eur == Decimal("120.00")
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
        # booking only contains reservation; admin is one_time_at_checkin
        assert result.payable_at_booking_eur == Decimal("148.50")
        assert result.one_time_at_checkin_eur == Decimal("120.00")

    def test_admin_fee_none_when_zero(self, fake_db):
        _seed(fake_db, room=_make_room_row(admin_tax="0"))
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
