"""End-to-end smoke test for Tool 5 (``get_booking_stats``)."""

from __future__ import annotations

import sys
from datetime import date

from elh_rag.config import settings
from elh_rag.tools._shared.db import Psycopg2Executor
from elh_rag.tools.get_booking_stats import (
    GetBookingStatsInput,
    GetBookingStatsOutput,
    get_booking_stats,
)

_SEP = "=" * 78


def _print_result(label: str, result: GetBookingStatsOutput) -> None:
    print(f"\n{_SEP}")
    print(f"SCENARIO: {label}")
    print(_SEP)
    print(f"Metric                  : {result.metric}")
    print(f"Summary                 : {result.summary}")
    print(f"Total underlying rows   : {result.total_underlying_rows}")
    print(f"Suppressed buckets      : {result.suppressed_buckets}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")
    print(f"Data points ({len(result.data_points)}):")
    for p in result.data_points[:15]:
        label_str = ", ".join(f"{k}={v}" for k, v in p.label.items()) if p.label else "(overall)"
        print(f"  {label_str:50s} | value={p.value:>10} | n={p.sample_size}")
    if len(result.data_points) > 15:
        print(f"  ... and {len(result.data_points) - 15} more")
    print(f"Disclaimer: {result.disclaimer[:100]}...")


def _run(
    label: str,
    ctx: Psycopg2Executor,
    payload: GetBookingStatsInput,
) -> bool:
    """Return True if the scenario produced any output (success or warning)."""
    try:
        result = get_booking_stats(payload, ctx=ctx)
        _print_result(label, result)
        return True
    except Exception as e:
        print(f"\n[FAIL] {label}: {type(e).__name__}: {e}")
        return False


def main() -> int:
    print(f"DB: {settings.db_uri.split('@')[-1] if '@' in settings.db_uri else '(local)'}")
    completed = 0
    with Psycopg2Executor(settings.db_uri) as ctx:
        # 1. occupancy_rate (Lisbon, 2024)
        if _run(
            "occupancy_rate - Lisbon 2024 full year",
            ctx,
            GetBookingStatsInput(
                metric="occupancy_rate",
                city="Lisbon",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
        ):
            completed += 1

        # 2. top_zones_by_bookings (top 5)
        if _run(
            "top_zones_by_bookings - top 5",
            ctx,
            GetBookingStatsInput(metric="top_zones_by_bookings", top_n=5),
        ):
            completed += 1

        # 3. avg_booking_duration_months (by city)
        if _run(
            "avg_booking_duration_months - by city",
            ctx,
            GetBookingStatsInput(
                metric="avg_booking_duration_months",
                group_by=["city"],
            ),
        ):
            completed += 1

        # 4. avg_lead_time_days (by season)
        if _run(
            "avg_lead_time_days - by season",
            ctx,
            GetBookingStatsInput(
                metric="avg_lead_time_days",
                group_by=["season"],
            ),
        ):
            completed += 1

        # 5. seasonal_demand (by season, all cities)
        if _run(
            "seasonal_demand - by season",
            ctx,
            GetBookingStatsInput(metric="seasonal_demand"),
        ):
            completed += 1

        # 6. avg_overall_rating (by zone in Lisbon)
        if _run(
            "avg_overall_rating - Lisbon zones",
            ctx,
            GetBookingStatsInput(
                metric="avg_overall_rating",
                city="Lisbon",
                group_by=["zone"],
            ),
        ):
            completed += 1

        # 7. room_inventory_count (by city)
        if _run(
            "room_inventory_count - by city",
            ctx,
            GetBookingStatsInput(
                metric="room_inventory_count",
                group_by=["city"],
            ),
        ):
            completed += 1

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/7 scenarios produced output.")
    print(_SEP)
    return 0 if completed == 7 else 1


if __name__ == "__main__":
    sys.exit(main())
