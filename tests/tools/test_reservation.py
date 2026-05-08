"""Tests for the reservation overlap helper.

What these tests can and cannot prove:

    * **Can prove offline:** the function dispatches the right SQL
      pattern, with parameters in the right order; the result is
      converted into a ``set`` of tuples; duplicates from the DB are
      collapsed (in addition to DISTINCT at the SQL level); empty
      results yield an empty set.

    * **Cannot prove offline:** that the SQL ``WHERE`` clause actually
      computes overlap correctly — that's a property of Postgres, not
      of our Python code. The smoke test in Step 5 will verify this
      against the real Supabase database.

The split is intentional: the calendar-arithmetic edge cases (touch-
at-boundary, fully-contained, etc.) belong to the SQL engine, and
testing them against ``FakeDbExecutor`` would only test the fake.
"""

from __future__ import annotations

from datetime import date

import pytest

from elh_rag.tools._db import FakeDbExecutor
from elh_rag.tools._reservation import _find_occupied_room_ids

# Dispatch + result conversion


class TestDispatch:
    def test_empty_db_returns_empty_set(self):
        db = FakeDbExecutor()
        # No canned response -> FakeDbExecutor returns []

        result = _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result == set()
        assert isinstance(result, set)

    def test_single_overlap_returns_one_tuple(self):
        db = FakeDbExecutor()
        db.add_response(
            "FROM reservation",
            [{"loc_idhouse": 42, "idroom": 3}],
        )

        result = _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result == {(42, 3)}

    def test_multiple_overlaps_returned_as_set(self):
        db = FakeDbExecutor()
        db.add_response(
            "FROM reservation",
            [
                {"loc_idhouse": 42, "idroom": 3},
                {"loc_idhouse": 42, "idroom": 5},
                {"loc_idhouse": 100, "idroom": 1},
            ],
        )

        result = _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result == {(42, 3), (42, 5), (100, 1)}

    def test_duplicate_rows_collapsed_in_set(self):
        """Defensive: even if DISTINCT didn't fire, we'd still dedupe."""
        db = FakeDbExecutor()
        db.add_response(
            "FROM reservation",
            [
                {"loc_idhouse": 42, "idroom": 3},
                {"loc_idhouse": 42, "idroom": 3},
                {"loc_idhouse": 42, "idroom": 3},
            ],
        )

        result = _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result == {(42, 3)}

    def test_string_id_columns_round_trip(self):
        """Schema declares character(20); test that strings flow through.

        find_rooms.py's tests use int IDs, but the real schema uses
        character(20). Either should be tolerated — the function is
        agnostic.
        """
        db = FakeDbExecutor()
        db.add_response(
            "FROM reservation",
            [{"loc_idhouse": "HSE_001", "idroom": "RM_HSE_001_3"}],
        )

        result = _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2027, 1, 31),
        )
        assert result == {("HSE_001", "RM_HSE_001_3")}


# SQL contract


class TestSqlContract:
    def test_query_targets_reservation_table(self):
        db = FakeDbExecutor()
        _find_occupied_room_ids(db, date(2026, 9, 1), date(2027, 1, 31))

        assert len(db.calls) == 1
        sql = db.calls[0]["sql"]
        assert "reservation" in sql

    def test_query_uses_distinct(self):
        """A room with multiple back-to-back reservations must come back once."""
        db = FakeDbExecutor()
        _find_occupied_room_ids(db, date(2026, 9, 1), date(2027, 1, 31))

        sql = db.calls[0]["sql"]
        assert "DISTINCT" in sql.upper()

    def test_query_filters_by_overlap_columns(self):
        db = FakeDbExecutor()
        _find_occupied_room_ids(db, date(2026, 9, 1), date(2027, 1, 31))

        sql = db.calls[0]["sql"]
        assert "blockeddatestart" in sql
        assert "blockeddataend" in sql

    def test_param_order_matches_placeholders(self):
        """Critical contract: params must align with the WHERE clause.

        The SQL is:
            blockeddatestart <= %s   ← period_end
            blockeddataend   >= %s   ← period_start

        Swapping these would produce a SQL that always returns 0 rows
        (or worse, returns wrong rows). This test locks in the order.
        """
        db = FakeDbExecutor()
        period_start = date(2026, 9, 1)
        period_end = date(2027, 1, 31)

        _find_occupied_room_ids(db, period_start, period_end)

        params = db.calls[0]["params"]
        assert params == (period_end, period_start)

    def test_query_does_not_filter_on_dateupdate(self):
        """Design decision: the version-agnostic match must NOT
        constrain on loc_dateupdate or dateupdate (otherwise reservations
        on older room versions wouldn't block newer versions)."""
        db = FakeDbExecutor()
        _find_occupied_room_ids(db, date(2026, 9, 1), date(2027, 1, 31))

        sql = db.calls[0]["sql"]
        # If anyone "fixes" this by adding dateupdate filtering, this test
        # fires immediately — forcing them to read the design comment.
        assert "loc_dateupdate" not in sql
        assert "dateupdate" not in sql

    def test_query_uses_inclusive_overlap_operators(self):
        """Locks in the <= / >= choice (vs < / >).

        Switching to half-open semantics would change behaviour at the
        boundary days; if that ever becomes desirable (e.g. ELH confirms
        exclusive checkout), this test must be updated explicitly along
        with the design comment.
        """
        db = FakeDbExecutor()
        _find_occupied_room_ids(db, date(2026, 9, 1), date(2027, 1, 31))

        sql = db.calls[0]["sql"]
        assert "<=" in sql
        assert ">=" in sql


# Defensive guards


class TestGuards:
    def test_inverted_period_raises(self):
        """The Pydantic validator catches this upstream, but we guard
        the helper too in case it's called directly."""
        db = FakeDbExecutor()
        with pytest.raises(ValueError, match="before"):
            _find_occupied_room_ids(
                db,
                period_start=date(2026, 12, 31),
                period_end=date(2026, 1, 1),
            )

    def test_same_day_period_does_not_raise(self):
        """A single-day period is unusual but logically valid."""
        db = FakeDbExecutor()
        _find_occupied_room_ids(
            db,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 1),
        )
        assert len(db.calls) == 1
