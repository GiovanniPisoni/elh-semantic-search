"""End-to-end smoke test for Tool 3 (compute_total_cost) against live DB.

Chains Tool 2 -> Tool 3:
    1. find_available_rooms with a target date window -> picks a real
       encoded_room_id.
    2. compute_total_cost on that room id over the same window -> prints
       the full booking + monthly breakdown.

Three scenarios cover the main branches:

    * Same-season 3 months (autumn) -> ``monthly_recurring`` populated.
    * Cross-season 4 months (Jan-Apr) -> ``monthly_breakdown`` populated.
    * Autumn 6 months + ``extra_person=True`` -> verifies that
      extra-person cost is added when ``extrapersonallowed='Y'``.

Run::

    python scripts/smoke_test_tool3.py

Requires a configured DB_URI in ``.env``.
"""

from __future__ import annotations

import sys
from datetime import date

from elh_rag.config import settings
from elh_rag.tools._db import Psycopg2Executor
from elh_rag.tools.compute_total_cost import (
    ComputeTotalCostInput,
    ComputeTotalCostOutput,
    compute_total_cost,
)
from elh_rag.tools.find_available_rooms import (
    FindAvailableRoomsInput,
    find_available_rooms,
)

_SEP = "=" * 78


def _print_result(label: str, result: ComputeTotalCostOutput) -> None:
    print(f"\n{_SEP}")
    print(f"SCENARIO: {label}")
    print(_SEP)
    print(f"Summary               : {result.summary}")
    print(f"Payable at booking    : €{result.payable_at_booking_eur}")
    if result.monthly_recurring_eur is not None:
        print(f"Monthly recurring     : €{result.monthly_recurring_eur}")
    else:
        assert result.monthly_breakdown is not None  # narrow for mypy
        print(f"Monthly breakdown ({len(result.monthly_breakdown)} months):")
        for m in result.monthly_breakdown:
            print(f"  {m.year}-{m.month:02d} ({m.season:>6}): €{m.rent_eur}")
    if result.one_time_at_checkin_eur is not None:
        print(f"One-time at check-in  : €{result.one_time_at_checkin_eur}")
    print(f"Total stay months     : {result.total_stay_months}")
    print(f"Fixed price           : {result.is_fixed_price}")
    print(f"Utilities included    : {result.utilities_included or '(none)'}")
    print(f"Utilities excluded    : {result.utilities_excluded or '(none)'}")
    print("Notes:")
    for n in result.notes:
        print(f"  - {n}")


def _pick_room(
    ctx: Psycopg2Executor,
    available_from: date,
    available_to: date,
    city: str = "Lisbon",
) -> str | None:
    """Use Tool 2 to find a real room available in the window. None if no inventory."""
    out = find_available_rooms(
        FindAvailableRoomsInput(
            city=city,
            available_from=available_from,
            available_to=available_to,
            max_results=1,
        ),
        ctx=ctx,
    )
    if not out.rooms:
        print(f"  [skip] No rooms for {city} on {available_from} -> {available_to}")
        return None
    rm = out.rooms[0]
    print(f"  Picked: {rm.house_name} (room_id={rm.room_id})")
    print(f"  Tool 2 label: {rm.price_label}")
    return rm.room_id


def _run_scenario(
    ctx: Psycopg2Executor,
    *,
    label: str,
    check_in: date,
    check_out: date,
    extra_person: bool = False,
) -> bool:
    """Return True if the scenario produced a result, False if skipped."""
    print(f"\n--- Selecting room for: {label} ---")
    encoded = _pick_room(ctx, check_in, check_out)
    if encoded is None:
        return False
    result = compute_total_cost(
        ComputeTotalCostInput(
            encoded_room_id=encoded,
            check_in_date=check_in,
            check_out_date=check_out,
            extra_person=extra_person,
        ),
        ctx=ctx,
    )
    _print_result(label, result)
    return True


def main() -> int:
    print(f"DB: {settings.db_uri.split('@')[-1] if '@' in settings.db_uri else '(local)'}")
    completed = 0
    with Psycopg2Executor(settings.db_uri) as ctx:
        # Scenario 1 — same-season autumn 3 months
        if _run_scenario(
            ctx,
            label="Same-season autumn (Sep-Nov 2026)",
            check_in=date(2026, 9, 1),
            check_out=date(2026, 11, 30),
        ):
            completed += 1

        # Scenario 2 — cross-season Jan-Apr
        if _run_scenario(
            ctx,
            label="Cross-season Jan-Apr 2027 (2 autumn + 2 spring)",
            check_in=date(2027, 1, 1),
            check_out=date(2027, 4, 30),
        ):
            completed += 1

        # Scenario 3 — autumn 6 months + extra_person
        if _run_scenario(
            ctx,
            label="Autumn 6 months + extra_person=True",
            check_in=date(2026, 9, 1),
            check_out=date(2027, 2, 28),
            extra_person=True,
        ):
            completed += 1

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/3 scenarios produced output.")
    print(_SEP)
    return 0 if completed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
