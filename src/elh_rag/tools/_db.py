"""Database executor protocol and concrete psycopg2 implementation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import psycopg2
import psycopg2.extras


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


class Psycopg2Executor:
    """Concrete DBExecutor backed by a long-lived psycopg2 connection."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Any = None  # psycopg2 connection, lazily initialized

    def _ensure_conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = True
        return self._conn

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tuple(params) if params is not None else None)
            if cur.description is None:
                # Non-SELECT statement returned no result set.
                return []
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        """Close the underlying connection if open. Idempotent."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Psycopg2Executor:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()