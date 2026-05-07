"""
Database executor protocol for SQL-backed tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class DBExecutor(Protocol):
    """Protocol for a SQL execution callable.

    Implementations must be synchronous and return rows as a list of dicts
    keyed by column name. Empty result sets return an empty list, not None.
    """

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run ``sql`` with ``params`` and return rows as dicts."""
        ...


class FakeDbExecutor:
    """Minimal in-memory ``DbExecutor`` for tests.

    Stores a list of ``(sql_pattern, response)`` mappings and returns
    the response of the first pattern that appears as a substring in
    the executed SQL. Matching is intentionally loose — tests assert
    on the high-level behaviour of the tool, not on exact SQL strings.

    Records every call into ``calls`` so tests can assert on the SQL
    and parameters that were issued.
    """

    def __init__(self) -> None:
        self._responses: list[tuple[str, list[dict[str, Any]]]] = []
        self.calls: list[dict[str, Any]] = []

    def add_response(self, sql_substring: str, response: list[dict[str, Any]]) -> None:
        """Register a canned response for any SQL containing ``sql_substring``."""
        self._responses.append((sql_substring, response))

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"sql": sql, "params": params})
        for pattern, response in self._responses:
            if pattern in sql:
                return response
        # No match -> empty result. Tests that didn't register a pattern
        # exercise the "no rows" code path naturally.
        return []

    def reset(self) -> None:
        """Clear recorded calls and responses (for fixture cleanup)."""
        self._responses.clear()
        self.calls.clear()
