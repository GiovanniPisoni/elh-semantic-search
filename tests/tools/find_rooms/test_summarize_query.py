"""Tests for :func:`elh_rag.tools.find_rooms._sql_builder._summarize_query`."""

from __future__ import annotations

from elh_rag.tools.find_rooms._inputs import FindRoomsInput
from elh_rag.tools.find_rooms._sql_builder import _summarize_query


# Baseline: empty input, simple filters


def test_empty_input_returns_no_filters_message() -> None:
    """No filters set → fallback message, not 'Filters: '."""
    summary = _summarize_query(FindRoomsInput())
    assert summary == "All available rooms (no filters)"


def test_city_and_price_appear_in_summary() -> None:
    """Sanity check for the simplest filter combination."""
    payload = FindRoomsInput(city="Lisbon", max_price_eur=600)
    summary = _summarize_query(payload)
    assert "city=Lisbon" in summary
    assert "≤€600" in summary


# must_have_* filters have to appear


def test_must_have_filters_appear_when_true() -> None:
    """must_have_* filters must be included in the summary."""
    payload = FindRoomsInput(
        city="Lisbon",
        must_have_private_bathroom=True,
        must_have_balcony=True,
        max_price_eur=600,
    )
    summary = _summarize_query(payload)
    assert "private bathroom" in summary
    assert "balcony" in summary
    # Pre-existing fields still present
    assert "city=Lisbon" in summary
    assert "≤€600" in summary


def test_must_have_false_appears_as_negation() -> None:
    """must_have_X=False is a deliberate exclusion and is rendered as 'no X'."""
    payload = FindRoomsInput(must_have_window=False)
    summary = _summarize_query(payload)
    assert "no window" in summary


def test_must_have_none_omitted_from_summary() -> None:
    """must_have_X=None means 'no preference' and must NOT appear."""
    payload = FindRoomsInput(city="Lisbon")  # all must_have_* default to None
    summary = _summarize_query(payload)
    # No amenity-derived term should leak in
    assert "private bathroom" not in summary
    assert "balcony" not in summary
    # No bare "no <amenity>" negation either
    assert "no " not in summary


def test_must_have_air_conditioning_label_derivation() -> None:
    """Multi-word amenities: underscore -> space, prefix stripped."""
    payload = FindRoomsInput(must_have_air_conditioning=True)
    summary = _summarize_query(payload)
    assert "air conditioning" in summary
    assert "must_have" not in summary


def test_must_have_label_for_each_explicit_amenity() -> None:
    """Spot-check the full set: each must_have_* produces a human label."""

    expected_labels = [
        "private bathroom",
        "balcony",
        "elevator",
        "air conditioning",
        "heating",
        "washing machine",
        "dishwasher",
        "parking",
        "internet",
        "desk",
        "window",
    ]
    for field, label in zip(
        [
            "must_have_private_bathroom",
            "must_have_balcony",
            "must_have_elevator",
            "must_have_air_conditioning",
            "must_have_heating",
            "must_have_washing_machine",
            "must_have_dishwasher",
            "must_have_parking",
            "must_have_internet",
            "must_have_desk",
            "must_have_window",
        ],
        expected_labels,
    ):
        payload = FindRoomsInput(**{field: True})
        summary = _summarize_query(payload)
        assert label in summary, f"label {label!r} missing for field {field!r}"


# Silent-skipped filters omitted

def test_accepts_couples_silent_skip_omitted_from_summary() -> None:
    """accepts_couples is silently skipped at SQL build time
    (column absent from the ELH schema), so it must NOT appear in the
    summary. Showing it would mislead the LLM consumer."""
    payload = FindRoomsInput(city="Lisbon", accepts_couples=True)
    summary = _summarize_query(payload)
    assert "couples" not in summary.lower()
    # But the genuinely-applied filter remains.
    assert "city=Lisbon" in summary


def test_max_house_occupancy_silent_skip_omitted_from_summary() -> None:
    """max_house_occupancy is also silently skipped (column absent in
    schema). It was never in the summary, but verifying explicitly to
    lock the invariant for future regressions."""
    payload = FindRoomsInput(city="Lisbon", max_house_occupancy=5)
    summary = _summarize_query(payload)
    assert "5" not in summary
    assert "occupancy" not in summary.lower()


# Regression guard: filters that ARE applied still appear


def test_accepts_pets_still_appears() -> None:
    """accepts_pets IS applied (h.allowpets='Y' clause in SQL), so it MUST
    stay in the summary. Sanity check that we removed only accepts_couples,
    not the whole occupancy section."""
    payload = FindRoomsInput(accepts_pets=True)
    summary = _summarize_query(payload)
    assert "pets-friendly" in summary


def test_gender_preference_still_appears() -> None:
    """gender_preference female_only / male_only must remain in the summary."""
    payload = FindRoomsInput(gender_preference="female_only")
    summary = _summarize_query(payload)
    assert "female_only" in summary


def test_gender_preference_any_omitted() -> None:
    """gender_preference='any' is not a real filter and must not appear."""
    payload = FindRoomsInput(gender_preference="any")
    summary = _summarize_query(payload)
    assert "any" not in summary
    assert summary == "All available rooms (no filters)"


# Realistic combined scenarios


def test_combo_amenities_scenario() -> None:
    """Tool 1 smoke scenario 3: combo private bath + balcony + price cap."""
    payload = FindRoomsInput(
        city="Lisbon",
        must_have_private_bathroom=True,
        must_have_balcony=True,
        max_price_eur=600,
    )
    summary = _summarize_query(payload)
    assert summary == "Filters: city=Lisbon, ≤€600, private bathroom, balcony"


def test_marketing_scenario_with_silent_skip() -> None:
    """Tool 1 smoke scenario 6: 5-filter marketing query.

    Verifies the combined behaviour: applied filters appear in order,
    silently-skipped accepts_couples does not appear.
    """
    payload = FindRoomsInput(
        city="Lisbon",
        metro_line="green",
        accepts_couples=True,  # silently skipped -> omitted
        gender_preference="female_only",
        max_price_eur=500,
    )
    summary = _summarize_query(payload)
    # Applied filters present
    assert "city=Lisbon" in summary
    assert "metro=green" in summary
    assert "female_only" in summary
    assert "≤€500" in summary
    # Silently-skipped filter absent
    assert "couples" not in summary.lower()
