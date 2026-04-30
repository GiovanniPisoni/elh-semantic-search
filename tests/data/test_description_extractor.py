"""Tests for DescriptionExtractor (Phase 2, Step 4).

Two layers of testing:
    1. Pure-logic unit tests on the text builders and row→Document helpers
    2. Integration tests on the extract() method with psycopg2 patched
       out
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from elh_rag.data.description_extractor import (
    DescriptionExtractor,
    _build_house_text,
    _build_room_text,
    _format_location,
    _house_row_to_document,
    _room_row_to_document,
)
from elh_rag.data.extractor import Extractor
from elh_rag.schemas import (
    Document,
    DocumentSource,
    HouseMetadata,
    RoomMetadata,
)


# _format_location


def test_format_location_joins_all_non_empty_parts() -> None:
    assert _format_location("Lisbon", "Alfama", "Centro") == "Lisbon, Alfama, Centro"


def test_format_location_skips_empty_parts() -> None:
    assert _format_location("Porto", "", "Ramalde") == "Porto, Ramalde"
    assert _format_location("", "Graca", "") == "Graca"


def test_format_location_returns_empty_when_all_empty() -> None:
    assert _format_location("", "", "") == ""


# _build_house_text


def test_house_text_contains_narrative_header() -> None:
    text = _build_house_text(
        flatname="Casa Verde",
        city="Porto",
        zone="Foz do Douro",
        neighbourhood="Foz",
        description="A beautiful flat near the sea.",
    )
    assert text.startswith("[HOUSE — Casa Verde]")
    assert "Location: Porto, Foz do Douro, Foz" in text
    assert "A beautiful flat near the sea." in text


def test_house_text_handles_missing_flatname() -> None:
    text = _build_house_text(
        flatname="",
        city="Lisbon",
        zone="Alfama",
        neighbourhood="",
        description="Nice place.",
    )
    assert text.startswith("[HOUSE]")
    assert "Location: Lisbon, Alfama" in text


def test_house_text_handles_missing_location() -> None:
    text = _build_house_text(
        flatname="Casa X",
        city="",
        zone="",
        neighbourhood="",
        description="Some description.",
    )
    assert "[HOUSE — Casa X]" in text
    assert "Location:" not in text
    assert "Some description." in text


# _build_room_text


def test_room_text_contains_house_context_in_header() -> None:
    text = _build_room_text(
        roomname="Garden View Room",
        flatname="Residencia Alfama",
        city="Lisbon",
        zone="Alfama",
        neighbourhood="",
        description="A 23m² room with a queen-size bed.",
    )
    assert text.startswith("[ROOM — Garden View Room in Residencia Alfama]")
    assert "Location: Lisbon, Alfama" in text
    assert "A 23m² room with a queen-size bed." in text


def test_room_text_handles_missing_flatname() -> None:
    text = _build_room_text(
        roomname="Double",
        flatname="",
        city="Porto",
        zone="",
        neighbourhood="",
        description="A double room.",
    )
    assert text.startswith("[ROOM — Double]")


def test_room_text_handles_missing_everything_except_description() -> None:
    text = _build_room_text(
        roomname="",
        flatname="",
        city="",
        zone="",
        neighbourhood="",
        description="Just a description.",
    )
    assert text.startswith("[ROOM]")
    assert "Just a description." in text


# _house_row_to_document


def test_house_row_to_document_builds_typed_metadata() -> None:
    row = {
        "idhouse": "HSE_712D9E74",
        "flatname": "Graca Student Flat",
        "city": "Lisbon",
        "zone": "Graca",
        "neighboorhood": "Jardim Botto Machado",
        "description": "Amazing 82m² flat in Graca — a village within the city.",
    }

    doc = _house_row_to_document(row)

    assert isinstance(doc, Document)
    assert isinstance(doc.metadata, HouseMetadata)
    assert doc.metadata.id == "house:HSE_712D9E74"
    assert doc.metadata.source == DocumentSource.HOUSE
    assert doc.metadata.flatname == "Graca Student Flat"
    assert doc.metadata.city == "Lisbon"
    assert doc.metadata.neighbourhood == "Jardim Botto Machado"
    assert "[HOUSE — Graca Student Flat]" in doc.text
    assert "Amazing 82m² flat" in doc.text


def test_house_row_to_document_strips_whitespace() -> None:
    """Supabase character(100) fields are right-padded with spaces."""
    row = {
        "idhouse": "HSE_001   ",
        "flatname": "Name   ",
        "city": "Porto  ",
        "zone": "",
        "neighboorhood": None,
        "description": "  Description.  ",
    }

    doc = _house_row_to_document(row)

    assert doc.metadata.id == "house:HSE_001"
    assert doc.metadata.idhouse == "HSE_001"
    assert doc.metadata.flatname == "Name"
    assert doc.metadata.city == "Porto"
    assert doc.metadata.zone == ""
    assert doc.metadata.neighbourhood == ""


# _room_row_to_document


def test_room_row_to_document_builds_typed_metadata() -> None:
    row = {
        "idroom": "RM_HSE_DE976537_3",
        "roomname": "Garden View Room",
        "idhouse": "HSE_DE976537",
        "flatname": "Residencia Alfama",
        "city": "Lisbon",
        "zone": "Alfama",
        "neighboorhood": "",
        "description": "A generously sized 23m² room with a queen-size bed.",
    }

    doc = _room_row_to_document(row)

    assert isinstance(doc, Document)
    assert isinstance(doc.metadata, RoomMetadata)
    assert doc.metadata.id == "room:RM_HSE_DE976537_3"
    assert doc.metadata.source == DocumentSource.ROOM
    assert doc.metadata.roomname == "Garden View Room"
    assert doc.metadata.idhouse == "HSE_DE976537"
    assert doc.metadata.flatname == "Residencia Alfama"
    assert "[ROOM — Garden View Room in Residencia Alfama]" in doc.text
    assert "A generously sized 23m² room" in doc.text


def test_room_row_to_document_handles_none_values() -> None:
    row = {
        "idroom": "RM_1",
        "roomname": None,
        "idhouse": "HSE_1",
        "flatname": None,
        "city": "Porto",
        "zone": None,
        "neighboorhood": None,
        "description": "A room.",
    }

    doc = _room_row_to_document(row)

    assert doc.metadata.roomname == ""
    assert doc.metadata.flatname == ""
    assert doc.metadata.zone == ""


# DescriptionExtractor class


def test_description_extractor_conforms_to_protocol() -> None:
    extractor = DescriptionExtractor(db_uri="fake", min_text_length=1)
    assert isinstance(extractor, Extractor)


def test_description_extractor_source_is_house() -> None:
    """The extractor advertises HOUSE as its 'parent' source.

    The actual source per document is on each Document's metadata.
    """
    extractor = DescriptionExtractor(db_uri="fake", min_text_length=1)
    assert extractor.source == DocumentSource.HOUSE


# extract() with patched psycopg2


def _mock_psycopg2_connection(
    monkeypatch: pytest.MonkeyPatch,
    house_rows: list[dict[str, Any]],
    room_rows: list[dict[str, Any]],
) -> MagicMock:
    """Patch psycopg2.connect to return canned results for the two queries.

    The cursor alternates between house_rows and room_rows based on call
    order: first execute() + fetchall() returns house_rows, second
    returns room_rows. This matches DescriptionExtractor's query sequence.
    """
    fetch_results = [house_rows, room_rows]
    fetch_iter = iter(fetch_results)

    cursor = MagicMock()
    cursor.execute = MagicMock(return_value=None)
    cursor.fetchall = MagicMock(side_effect=lambda: next(fetch_iter))
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=None)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)

    connect_mock = MagicMock(return_value=conn)
    monkeypatch.setattr(
        "elh_rag.data.description_extractor.psycopg2.connect", connect_mock
    )
    return cursor


def test_extract_merges_house_and_room_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house_rows = [
        {
            "idhouse": "HSE_001",
            "flatname": "Casa Verde",
            "city": "Porto",
            "zone": "Foz",
            "neighboorhood": "",
            "description": "A beautiful flat near the sea in Foz.",
        },
        {
            "idhouse": "HSE_002",
            "flatname": "Casa Azul",
            "city": "Lisbon",
            "zone": "Alfama",
            "neighboorhood": "",
            "description": "An authentic flat in the historic centre.",
        },
    ]
    room_rows = [
        {
            "idroom": "RM_HSE_001_1",
            "roomname": "Double",
            "idhouse": "HSE_001",
            "flatname": "Casa Verde",
            "city": "Porto",
            "zone": "Foz",
            "neighboorhood": "",
            "description": "A comfortable double room with sea view.",
        },
    ]

    _mock_psycopg2_connection(monkeypatch, house_rows, room_rows)

    extractor = DescriptionExtractor(db_uri="fake", min_text_length=10)
    docs = list(extractor.extract())

    assert len(docs) == 3

    # House documents first
    assert isinstance(docs[0].metadata, HouseMetadata)
    assert isinstance(docs[1].metadata, HouseMetadata)
    assert docs[0].metadata.id == "house:HSE_001"
    assert docs[1].metadata.id == "house:HSE_002"

    # Room documents after
    assert isinstance(docs[2].metadata, RoomMetadata)
    assert docs[2].metadata.id == "room:RM_HSE_001_1"


def test_extract_skips_rows_with_text_shorter_than_min_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A description that's below threshold must not produce a Document.

    Note: min_text_length compares against the *built* text (header +
    location + body), not just the description, so we need very short
    descriptions to trigger the filter.
    """
    house_rows = [
        {
            "idhouse": "X",
            "flatname": "",
            "city": "",
            "zone": "",
            "neighboorhood": "",
            "description": "",
        },
    ]
    room_rows: list[dict[str, Any]] = []

    _mock_psycopg2_connection(monkeypatch, house_rows, room_rows)

    extractor = DescriptionExtractor(db_uri="fake", min_text_length=100)
    docs = list(extractor.extract())

    # [HOUSE] is 7 chars, well below 100 → skipped
    assert docs == []


def test_extract_handles_empty_result_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_psycopg2_connection(monkeypatch, [], [])

    extractor = DescriptionExtractor(db_uri="fake", min_text_length=1)
    docs = list(extractor.extract())

    assert docs == []


def test_extract_passes_status_and_min_length_to_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the two parametrised queries receive the right arguments.

    House and room have different status values in the ELH schema:
    house uses 'Validated', room uses 'Available'. The extractor must
    route each status to the correct query.
    """
    cursor = _mock_psycopg2_connection(monkeypatch, [], [])

    extractor = DescriptionExtractor(
        db_uri="fake",
        house_status_filter="Validated",
        room_status_filter="Available",
        min_text_length=50,
    )
    list(extractor.extract())

    # Two execute() calls: first house with 'Validated', then room with 'Available'
    assert cursor.execute.call_count == 2

    first_call_params = cursor.execute.call_args_list[0].args[1]
    second_call_params = cursor.execute.call_args_list[1].args[1]

    assert first_call_params == ("Validated", 50)
    assert second_call_params == ("Available", 50)