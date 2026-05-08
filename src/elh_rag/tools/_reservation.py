"""Reservation overlap query for Tool 2.

Pure SQL helper: given a date window, returns the set of
``(loc_idhouse, idroom)`` pairs that have at least one reservation
overlapping the window.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ._db import DBExecutor

# Standard closed-interval overlap test
_OVERLAP_SQL = """\
SELECT DISTINCT loc_idhouse, idroom
FROM reservation
WHERE blockeddatestart <= %s
  AND blockeddataend   >= %s
"""


def _find_occupied_room_ids(
    db: DBExecutor,
    period_start: date,
    period_end: date,
) -> set[tuple[Any, Any]]:
    """Return ``(loc_idhouse, idroom)`` pairs with reservation overlap.

    Both ``period_start`` and ``period_end`` are treated as inclusive,
    matching the ``available_from`` / ``available_to`` convention on
    :class:`elh_rag.tools.find_available_rooms.FindAvailableRoomsInput`.
    """
    if period_end < period_start:
        raise ValueError(f"period_end ({period_end}) is before period_start ({period_start})")

    rows = db.execute(_OVERLAP_SQL, (period_end, period_start))

    return {(row["loc_idhouse"], row["idroom"]) for row in rows}
