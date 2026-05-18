"""Runtime PII-safety wrapper for get_booking_stats SQL builders.

Tool 5 (``get_booking_stats``) is restricted by GDPR to aggregate reads over
``reservation``, ``house``, ``room``, and ``review`` only.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from typing import Any, TypeVar

from elh_rag.tools.errors import ToolExecutionError

# Tables containing or referencing PII. Tool 5 must never query these.
FORBIDDEN_TABLES: tuple[str, ...] = (
    "users",
    "payment",
    "email",
    "question",
    "reply",
)


_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in FORBIDDEN_TABLES
)


_TOOL_NAME = "get_booking_stats"


class PIISafetyError(ToolExecutionError):
    """Raised when a SQL builder produces a query referencing a forbidden table.

    Subclass of :class:`ToolExecutionError` so it integrates with the
    Phase 3 normalised error handling.
    """


F = TypeVar("F", bound=Callable[..., Any])


def pii_safe_sql[F: Callable[..., Any]](func: F) -> F:
    """Validate that a SQL builder does not reference forbidden PII tables.

    The decorated function must return either:

    * a SQL string (``str``), or
    * a tuple whose first element is the SQL string.

    On detection of a forbidden table, raises :class:`PIISafetyError`
    with the builder name and the offending table for diagnostic clarity.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = func(*args, **kwargs)

        if isinstance(result, str):
            sql = result
        elif isinstance(result, tuple) and result and isinstance(result[0], str):
            sql = result[0]
        else:
            raise TypeError(
                f"{func.__name__} decorated with @pii_safe_sql must return a "
                f"SQL string or a tuple starting with the SQL string; "
                f"got {type(result).__name__}"
            )

        for pattern in _FORBIDDEN_PATTERNS:
            match = pattern.search(sql)
            if match is not None:
                raise PIISafetyError(
                    _TOOL_NAME,
                    f"PII guard: builder '{func.__name__}' returned SQL "
                    f"referencing forbidden table '{match.group()}'. "
                    f"Tool 5 is restricted to reservation, house, room, and "
                    f"review (design decision D3.9).",
                )

        return result

    return wrapper  # type: ignore[return-value]
