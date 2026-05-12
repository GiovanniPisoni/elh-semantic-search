"""End-to-end smoke test for Tool 4 (``get_property_details``)."""

from __future__ import annotations

import sys
from datetime import date

from elh_rag.config import settings
from elh_rag.tools._shared.db import Psycopg2Executor
from elh_rag.tools.find_available_rooms import (
    FindAvailableRoomsInput,
    find_available_rooms,
)
from elh_rag.tools.get_property_details import (
    GetPropertyDetailsInput,
    GetPropertyDetailsOutput,
    get_property_details,
)

_SEP = "=" * 78


def _print_result(label: str, result: GetPropertyDetailsOutput) -> None:
    print(f"\n{_SEP}")
    print(f"SCENARIO: {label}")
    print(_SEP)
    print(f"Summary             : {result.summary}")
    print()
    h = result.house
    print(f"House               : {h.flat_name}")
    print(f"  encoded_house_id  : {h.encoded_house_id}")
    print(f"  city / zone       : {h.city} / {h.zone} ({h.neighborhood})")
    print(f"  area / bathrooms  : {h.area_sqm} mÂ² / {h.bathroom_count} bathroom(s)")
    print(f"  metro lines       : {h.nearest_metro_lines or '(none)'}")
    print(f"  distance transp.  : {h.distance_to_transport_m} m")
    print(f"  internet speed    : {h.internet_speed_mbps} Mbps")
    print(f"  gender pref       : {h.gender_preference}")
    print(
        f"  rules             : night_guests={h.night_guests_allowed}, "
        f"pets={h.pets_allowed}, smoking={h.smoking_allowed}"
    )
    print(f"  amenities ({len(h.amenities)}): {', '.join(h.amenities) or '(none)'}")
    if h.other_amenities_text:
        print(f"  other amenities   : {h.other_amenities_text}")
    print(f"  rooms_total       : {h.rooms_total} (summarised: {len(h.rooms_summary)})")
    for hr in h.rooms_summary[:5]:
        print(
            f"     - {hr.room_name} ({hr.status}): "
            f"â‚¬{hr.spring_price_eur}/â‚¬{hr.summer_price_eur}/â‚¬{hr.autumn_price_eur} "
            f"(spring/summer/autumn)" + (", fixed" if hr.is_fixed_price else "")
        )

    if result.room is not None:
        r = result.room
        print()
        print(f"Room                : {r.room_name}")
        print(f"  area              : {r.area_sqm} mÂ²")
        print(f"  beds              : {', '.join(r.bed_types) or '(none)'}")
        print(f"  amenities         : {', '.join(r.amenities) or '(none)'}")
        print(
            f"  pricing (s/s/a)   : "
            f"â‚¬{r.spring_price_eur} / â‚¬{r.summer_price_eur} / "
            f"â‚¬{r.autumn_price_eur}" + (" [fixed]" if r.is_fixed_price else "")
        )
        print(
            f"  deposit           : "
            f"required={r.deposit_required}, value=â‚¬{r.deposit_value_eur}, "
            f"last_month={r.last_month_deposit}"
        )
        print(f"  admin tax         : â‚¬{r.administrative_tax_eur}")
        print(
            f"  extra person      : "
            f"allowed={r.extra_person_allowed}"
            + (f", cost=â‚¬{r.extra_person_cost_eur}" if r.extra_person_cost_eur is not None else "")
        )

    if result.reviews is not None:
        rv = result.reviews
        print()
        print(f"Reviews             : {rv.count} approved")
        if rv.count > 0:
            print(
                f"  averages          : overall={rv.average_overall_rating}, "
                f"cleaning={rv.average_cleaning_rating}, "
                f"comm={rv.average_communication_rating}, "
                f"location={rv.average_location_rating}, "
                f"price/quality={rv.average_price_quality_rating}"
            )
            print("  most recent       :")
            for s in rv.recent_reviews:
                print(f"     [{s.date_review} â˜…{s.overall_rating}] {s.title}")
                print(f'        "{s.excerpt[:120]}{"..." if len(s.excerpt) > 120 else ""}"')
    else:
        print()
        print("Reviews             : (skipped â€” include_reviews=False)")


def _pick_room(ctx: Psycopg2Executor) -> tuple[str, str] | None:
    """Pick (encoded_room_id, encoded_house_id) for the smoke test."""
    out = find_available_rooms(
        FindAvailableRoomsInput(
            city="Lisbon",
            available_from=date(2026, 9, 1),
            available_to=date(2026, 11, 30),
            max_results=1,
        ),
        ctx=ctx,
    )
    if not out.rooms:
        print("No rooms found â€” cannot run smoke. Aborting.")
        return None
    rm = out.rooms[0]
    print(f"Picked: {rm.house_name}")
    print(f"  encoded_room_id  : {rm.room_id}")
    print(f"  encoded_house_id : {rm.house_id}")
    return rm.room_id, rm.house_id


def main() -> int:
    print(f"DB: {settings.db_uri.split('@')[-1] if '@' in settings.db_uri else '(local)'}")
    completed = 0
    with Psycopg2Executor(settings.db_uri) as ctx:
        picked = _pick_room(ctx)
        if picked is None:
            return 1
        room_id, house_id = picked

        # Scenario 1 â€” room lookup with reviews
        try:
            result = get_property_details(
                GetPropertyDetailsInput(encoded_id=room_id, include_reviews=True),
                ctx=ctx,
            )
            _print_result("Room lookup + reviews", result)
            completed += 1
        except Exception as e:
            print(f"\n[FAIL] Scenario 1: {e}")

        # Scenario 2 â€” room lookup without reviews
        try:
            result = get_property_details(
                GetPropertyDetailsInput(encoded_id=room_id, include_reviews=False),
                ctx=ctx,
            )
            _print_result("Room lookup â€” reviews disabled", result)
            completed += 1
        except Exception as e:
            print(f"\n[FAIL] Scenario 2: {e}")

        # Scenario 3 â€” house lookup
        try:
            result = get_property_details(
                GetPropertyDetailsInput(encoded_id=house_id, include_reviews=True),
                ctx=ctx,
            )
            _print_result("House lookup + reviews (all rooms)", result)
            completed += 1
        except Exception as e:
            print(f"\n[FAIL] Scenario 3: {e}")

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/3 scenarios succeeded.")
    print(_SEP)
    return 0 if completed == 3 else 1


if __name__ == "__main__":
    sys.exit(main())

