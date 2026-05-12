"""Utility expenses lookup for Tool 3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ._shared.db import DBExecutor

_EXPENSES_SQL = """\
SELECT description, maximumvalue
FROM expenses
WHERE idhouse = %s AND dateupdate = %s
ORDER BY description
"""

_CAP_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class UtilityCategorization:
    """Two parallel lists of human-readable utility descriptors."""

    included: list[str]
    excluded: list[str]


def fetch_utility_categorization(
    db: DBExecutor,
    house_id: str,
    house_dateupdate: date,
) -> UtilityCategorization:
    """Fetch and categorize the expenses rows attached to a house version."""
    rows: list[dict[str, Any]] = db.execute(_EXPENSES_SQL, (house_id, house_dateupdate))

    included: list[str] = []
    excluded: list[str] = []

    for row in rows:
        description = str(row["description"]).strip()
        if not description:
            continue
        max_value = row["maximumvalue"]

        if max_value is None:
            excluded.append(f"{description} (not included — paid to provider)")
        else:
            cap = Decimal(str(max_value)).quantize(_CAP_QUANTUM)
            included.append(f"{description} (up to €{cap}/mo)")

    return UtilityCategorization(included=included, excluded=excluded)
