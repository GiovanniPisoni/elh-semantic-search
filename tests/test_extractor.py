"""Tests for the extractor's pure logic (no database calls)."""
from __future__ import annotations

from datetime import date

from elh_rag.data.extractor import _build_enriched_text, _row_to_document


# _build_enriched_text


def test_enriched_text_combines_location_property_and_review() -> None:
    row = {
        "city": "Lisbon",
        "zone": "Alfama",
        "flatname": "Casa do Sol",
        "roomname": "Blue Room",
        "review_title": "Loved it",
        "review_text": "Great experience overall.",
    }

    text = _build_enriched_text(row)

    assert "Lisbon, Alfama" in text
    assert "Casa do Sol — Blue Room" in text
    assert "Review: Loved it" in text
    assert "Great experience overall." in text


def test_enriched_text_skips_missing_fields_gracefully() -> None:
    row = {"city": "Porto", "review_text": "Nice place."}

    text = _build_enriched_text(row)

    assert "Porto" in text
    assert "Nice place." in text
    assert "—" not in text


def test_enriched_text_handles_none_values() -> None:
    row = {
        "city": None,
        "zone": "Bonfim",
        "flatname": None,
        "review_text": "Quiet area.",
    }

    text = _build_enriched_text(row)

    assert "Bonfim" in text
    assert "Quiet area." in text


# _row_to_document


def test_row_to_document_builds_typed_metadata() -> None:
    row = {
        "idreview": 42,
        "review_text": "Loved the bed.",
        "review_title": "Great",
        "datereview": date(2025, 4, 1),
        "overallratings": 5,
        "cleaningratings": 5,
        "communicationratings": 4,
        "locationratings": 5,
        "pricequalityratings": 4,
        "idhouse": 100,
        "city": "Lisbon",
        "zone": "Alfama",
        "neighboorhood": "Centro",
        "flatname": "Casa do Sol",
        "idroom": 200,
        "roomname": "Blue Room",
    }

    doc = _row_to_document(row)

    assert doc.metadata.id == "42"
    assert doc.metadata.city == "Lisbon"
    assert doc.metadata.overall_rating == 5
    assert doc.metadata.date_review == "2025-04-01"
    assert doc.metadata.review_text_original == "Loved the bed."
    assert "Loved the bed." in doc.text


def test_row_to_document_handles_null_ratings() -> None:
    row = {
        "idreview": 1,
        "review_text": "ok",
        "review_title": None,
        "datereview": None,
        "overallratings": None,
        "cleaningratings": None,
        "communicationratings": None,
        "locationratings": None,
        "pricequalityratings": None,
        "city": "Porto",
    }

    doc = _row_to_document(row)

    assert doc.metadata.overall_rating == 0
    assert doc.metadata.date_review == ""
    assert doc.metadata.review_title == ""
