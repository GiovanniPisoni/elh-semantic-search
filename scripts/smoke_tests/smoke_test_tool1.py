"""End-to-end smoke test for Tool 1 (``find_rooms``) against live DB.

Six scenarios cover the main filtering axes:

    1. Baseline city filter (Lisbon)               -> sanity check
    2. Porto metro letter 'B' (=red) + accepts_pets -> letter normalisation
    3. Combo amenities (private bath + balcony + max EUR 600)
    4. Sort by price asc + max_results=3
    5. Impossible filter (min_price_eur=10000)     -> expect 0 matches
    6. Marketing query: Lisbon green-line couples-friendly female-only <500 EUR

Tool 1 has no date constraint: the displayed price is the autumn
seasonal column (Erasmus high season). The date-aware path is covered
by smoke_test_tool2.

Run::

    python scripts/smoke_tests/smoke_test_tool1.py

Requires a configured DB_URI in ``.env``.
"""

from __future__ import annotations

import sys

from elh_rag.config import settings
from elh_rag.tools._shared.db import Psycopg2Executor
from elh_rag.tools.find_rooms import (
    FindRoomsInput,
    FindRoomsOutput,
    find_rooms,
)

_SEP = "=" * 78


def _print_result(label: str, result: FindRoomsOutput) -> None:
    print(f"\n{_SEP}")
    print(f"SCENARIO: {label}")
    print(_SEP)
    print(f"Summary       : {result.query_summary}")
    print(f"Total matches : {result.total_matches}")
    print(f"Rooms ({len(result.rooms)}):")
    for rm in result.rooms[:5]:
        fixed_tag = "(fixed)" if rm.is_fixed_price else "       "
        line = (
            f"  [{rm.room_id[:22]:22}] "
            f"{rm.city:7} / {rm.zone:18} "
            f"\u20ac{rm.price_per_month_eur:>7.2f}/mo "
            f"{fixed_tag} "
            f"score={rm.match_score:.2f}"
        )
        print(line)
        if rm.nearest_metro_line:
            print(f"      metro: {rm.nearest_metro_line}")
        if rm.excerpt:
            print(f"      excerpt: {rm.excerpt[:110]}")
    if len(result.rooms) > 5:
        print(f"  ... and {len(result.rooms) - 5} more")


def _run(label: str, ctx: Psycopg2Executor, payload: FindRoomsInput) -> bool:
    """Return True if the scenario produced output (success or empty)."""
    try:
        result = find_rooms(payload, ctx=ctx)
        _print_result(label, result)
        return True
    except Exception as e:
        print(f"\n[FAIL] {label}: {type(e).__name__}: {e}")
        return False


def main() -> int:
    print(f"DB: {settings.db_uri.split('@')[-1] if '@' in settings.db_uri else '(local)'}")
    completed = 0
    with Psycopg2Executor(settings.db_uri) as ctx:
        # 1. Baseline city filter (Lisbon)
        if _run(
            "EN \u2014 baseline city filter (Lisbon)",
            ctx,
            FindRoomsInput(city="Lisbon"),
        ):
            completed += 1

        # 2. Porto metro letter normalisation + accepts_pets
        if _run(
            "EN \u2014 Porto metro letter 'B' (=red) + accepts_pets",
            ctx,
            FindRoomsInput(city="Porto", metro_line="B", accepts_pets=True),
        ):
            completed += 1

        # 3. Combo amenities + price cap
        if _run(
            "EN \u2014 amenity combo (private bath + balcony + max EUR 600)",
            ctx,
            FindRoomsInput(
                city="Lisbon",
                must_have_private_bathroom=True,
                must_have_balcony=True,
                max_price_eur=600,
            ),
        ):
            completed += 1

        # 4. Sort + limit
        if _run(
            "EN \u2014 sort by price asc, top 3 (Lisbon)",
            ctx,
            FindRoomsInput(city="Lisbon", sort_by="price_asc", max_results=3),
        ):
            completed += 1

        # 5. Impossible filter
        if _run(
            "EN \u2014 impossible filter (Lisbon, min_price_eur=10000)",
            ctx,
            FindRoomsInput(city="Lisbon", min_price_eur=10000),
        ):
            completed += 1

        # 6. Marketing-style multi-filter query
        if _run(
            "EN \u2014 marketing: Lisbon green-line couples-friendly female-only <500 EUR",
            ctx,
            FindRoomsInput(
                city="Lisbon",
                metro_line="green",
                accepts_couples=True,
                gender_preference="female_only",
                max_price_eur=500,
            ),
        ):
            completed += 1

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/6 scenarios produced output.")
    print(_SEP)
    return 0 if completed == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
