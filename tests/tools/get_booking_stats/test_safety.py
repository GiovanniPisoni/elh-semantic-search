"""Tests for :mod:`elh_rag.tools.get_booking_stats._safety`.

Covers the ``@pii_safe_sql`` decorator and the :class:`PIISafetyError`
exception. Decision D6.2 of the Phase 3 agent design.
"""

from __future__ import annotations

import pytest

from elh_rag.tools.errors import ToolExecutionError
from elh_rag.tools.get_booking_stats._safety import (
    FORBIDDEN_TABLES,
    PIISafetyError,
    pii_safe_sql,
)

 
# Exception type hierarchy


def test_pii_safety_error_subclasses_tool_execution_error() -> None:
    """PIISafetyError must integrate with existing Phase 3 error normalisation."""
    assert issubclass(PIISafetyError, ToolExecutionError)


# Happy path


def test_passes_when_sql_uses_allowed_tables_only() -> None:
    """Allowed tables (reservation, house, room, review) must not trip the guard."""

    @pii_safe_sql
    def safe_builder() -> tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM reservation r "
            "JOIN house h ON h.idhouse = r.loc_idhouse "
            "JOIN room rm ON rm.idroom = r.idroom "
            "JOIN review rv ON rv.idroom = r.idroom",
            (),
        )

    sql, params = safe_builder()
    assert "reservation" in sql
    assert params == ()


def test_accepts_plain_str_return() -> None:
    """A builder may return just a SQL string instead of a tuple."""

    @pii_safe_sql
    def string_builder() -> str:
        return "SELECT * FROM reservation"

    assert string_builder() == "SELECT * FROM reservation"


# Forbidden-table detection


@pytest.mark.parametrize("table", FORBIDDEN_TABLES)
def test_raises_for_each_forbidden_table(table: str) -> None:
    """Every forbidden table must be detected (one parametrised case per table)."""

    @pii_safe_sql
    def bad_builder() -> tuple[str, tuple]:
        return f"SELECT * FROM {table} WHERE 1=1", ()

    with pytest.raises(PIISafetyError) as exc_info:
        bad_builder()
    assert table in str(exc_info.value).lower()
    assert "bad_builder" in str(exc_info.value)


def test_raises_case_insensitive() -> None:
    """Forbidden-table detection must be case-insensitive."""

    @pii_safe_sql
    def uppercase_users() -> tuple[str, tuple]:
        return "SELECT * FROM USERS", ()

    with pytest.raises(PIISafetyError):
        uppercase_users()


def test_string_return_is_still_checked() -> None:
    """The check applies to plain-string returns too, not only tuples."""

    @pii_safe_sql
    def bad_string_builder() -> str:
        return "SELECT * FROM payment"

    with pytest.raises(PIISafetyError):
        bad_string_builder()


# Word boundary correctness — no false positives on compound identifiers


def test_respects_word_boundaries() -> None:
    """Compound identifiers (users_count, external_users) must NOT trip."""

    @pii_safe_sql
    def compound_identifier() -> tuple[str, tuple]:
        return "SELECT users_count, external_users FROM reservation", ()

    # Should not raise — users_count and external_users have no word
    # boundary on one side, so \busers\b does not match.
    sql, _ = compound_identifier()
    assert "users_count" in sql


# Programmer-error detection (unsupported return shape)


def test_raises_type_error_on_unsupported_return() -> None:
    """Non-string, non-tuple-starting-with-string returns are programmer errors."""

    @pii_safe_sql
    def wrong_shape() -> int:  # type: ignore[misc]
        return 42  # type: ignore[return-value]

    with pytest.raises(TypeError, match="must return"):
        wrong_shape()


def test_raises_type_error_on_empty_tuple_return() -> None:
    """Empty tuple is not a valid return shape."""

    @pii_safe_sql
    def empty_tuple() -> tuple:  # type: ignore[misc]
        return ()

    with pytest.raises(TypeError, match="must return"):
        empty_tuple()


def test_raises_type_error_on_tuple_with_non_string_first() -> None:
    """Tuple whose first element is not a string is a programmer error."""

    @pii_safe_sql
    def numeric_first() -> tuple:  # type: ignore[misc]
        return 42, "SELECT 1"

    with pytest.raises(TypeError, match="must return"):
        numeric_first()


# Metadata preservation + diagnostic quality


def test_preserves_function_metadata() -> None:
    """functools.wraps preserves __name__, __doc__, etc."""

    @pii_safe_sql
    def my_builder() -> str:
        """My docstring."""
        return "SELECT * FROM reservation"

    assert my_builder.__name__ == "my_builder"
    assert my_builder.__doc__ == "My docstring."


def test_error_message_includes_diagnostic_info() -> None:
    """PIISafetyError must name the builder and the offending table."""

    @pii_safe_sql
    def diagnostic_builder() -> str:
        return "SELECT * FROM email WHERE id = 1"

    with pytest.raises(PIISafetyError) as exc_info:
        diagnostic_builder()
    msg = str(exc_info.value)
    assert "diagnostic_builder" in msg
    assert "email" in msg.lower()
    assert "D3.9" in msg  # references the design decision
