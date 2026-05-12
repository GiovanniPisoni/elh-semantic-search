"""End-to-end smoke test for Tool 2 (``find_available_rooms``) against live DB.

Six scenarios cover the main seasonal and reservation-overlap branches:

    1. Autumn-only semester (Sep 2026 -> Jan 2027)         -> all autumn
    2. Summer-only (Jul -> Aug 2026)                       -> all summer
    3. Cross-season spring+summer (May 15 -> Aug 31 2026)
    4. Full academic year (Sep 2026 -> Jul 2027)           -> 3-season mix
    5. Combo amenities + dates (Lisbon green + private bath, Sep -> Dec 2026)
    6. Impossible filter (Porto min_price=5000, Sep 2026 -> Jan 2027)

Validates the Model B seasonal pricing convention: every calendar
month touched by the stay is billed in full at its seasonal rate. The
displayed ``price_per_month_eur`` is the mean of the per-month rents
over the requested window; the per-room ``price_label`` carries the
user-facing per-month breakdown.

Run::

    python scripts/smoke_tests/smoke_test_tool2.py

Requires a configured DB_URI in ``.env``.
"""

from __future__ import annotations

import sys
from datetime import date

from elh_rag.config import settings
from elh_rag.tools._shared.db import Psycopg2Executor
from elh_rag.tools.find_available_rooms import (
    FindAvailableRoomsInput,
    find_available_rooms,
)
from elh_rag.tools.find_rooms import FindRoomsOutput

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
            f"avail_from={rm.available_from}"
        )
        print(line)
        # price_label may exist on Tool 2's enriched RoomMatch (context-rich).
        price_label = getattr(rm, "price_label", None)
        if price_label:
            print(f"      label: {price_label[:120]}")
        elif rm.nearest_metro_line:
            print(f"      metro: {rm.nearest_metro_line}")
    if len(result.rooms) > 5:
        print(f"  ... and {len(result.rooms) - 5} more")


def _run(
    label: str,
    ctx: Psycopg2Executor,
    payload: FindAvailableRoomsInput,
) -> bool:
    """Return True if the scenario produced output (success or empty)."""
    try:
        result = find_available_rooms(payload, ctx=ctx)
        _print_result(label, result)
        return True
    except Exception as e:
        print(f"\n[FAIL] {label}: {type(e).__name__}: {e}")
        return False


def main() -> int:
    print(f"DB: {settings.db_uri.split('@')[-1] if '@' in settings.db_uri else '(local)'}")
    completed = 0
    with Psycopg2Executor(settings.db_uri) as ctx:
        # 1. Autumn-only semester
        if _run(
            "EN \u2014 autumn-only semester (Sep 2026 -> Jan 2027, Lisbon)",
            ctx,
            FindAvailableRoomsInput(
                city="Lisbon",
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
        ):
            completed += 1

        # 2. Summer-only
        if _run(
            "EN \u2014 summer-only (Jul -> Aug 2026, Lisbon)",
            ctx,
            FindAvailableRoomsInput(
                city="Lisbon",
                available_from=date(2026, 7, 1),
                available_to=date(2026, 8, 31),
            ),
        ):
            completed += 1

        # 3. Cross-season spring + summer
        if _run(
            "EN \u2014 cross-season spring+summer (May 15 -> Aug 31 2026, Lisbon)",
            ctx,
            FindAvailableRoomsInput(
                city="Lisbon",
                available_from=date(2026, 5, 15),
                available_to=date(2026, 8, 31),
            ),
        ):
            completed += 1

        # 4. Full academic year, 3-season mix
        if _run(
            "EN \u2014 full academic year, 3-season mix (Sep 2026 -> Jul 2027, Lisbon)",
            ctx,
            FindAvailableRoomsInput(
                city="Lisbon",
                available_from=date(2026, 9, 1),
                available_to=date(2027, 7, 31),
            ),
        ):
            completed += 1

        # 5. Combo amenities + dates
        if _run(
            "EN \u2014 combo amenities + dates "
            "(Lisbon green-line + private bath, Sep -> Dec 2026)",
            ctx,
            FindAvailableRoomsInput(
                city="Lisbon",
                metro_line="green",
                must_have_private_bathroom=True,
                available_from=date(2026, 9, 1),
                available_to=date(2026, 12, 31),
            ),
        ):
            completed += 1

        # 6. Impossible filter
        if _run(
            "EN \u2014 impossible filter (Porto min_price_eur=5000, Sep 2026 -> Jan 2027)",
            ctx,
            FindAvailableRoomsInput(
                city="Porto",
                min_price_eur=5000,
                available_from=date(2026, 9, 1),
                available_to=date(2027, 1, 31),
            ),
        ):
            completed += 1

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/6 scenarios produced output.")
    print(_SEP)
    return 0 if completed == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
