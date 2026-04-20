"""Tests for the typed schemas, especially Pinecone round-tripping."""
from __future__ import annotations

from elh_rag.schemas import (
    Document,
    DocumentSource,
    RAGResponse,
    RetrievalResult,
    ReviewMetadata,
)


# ReviewMetadata


def test_metadata_to_pinecone_dict_serialises_enum_as_string() -> None:
    meta = ReviewMetadata(id="x", source=DocumentSource.REVIEW)
    d = meta.to_pinecone_dict()

    assert d["source"] == "review"
    assert isinstance(d["source"], str)


def test_metadata_round_trip_preserves_all_fields() -> None:
    original = ReviewMetadata(
        id="rev-42",
        city="Porto",
        zone="Bonfim",
        flatname="Casa Verde",
        overall_rating=4,
        review_title="Nice place",
        review_text_original="Loved the natural light.",
    )

    restored = ReviewMetadata.from_pinecone_dict(original.to_pinecone_dict())

    assert restored == original
    assert restored.source == DocumentSource.REVIEW


def test_metadata_from_pinecone_dict_ignores_unknown_keys() -> None:
    """Pinecone may return extra metadata; we should not crash on it."""
    payload = {
        "id": "rev-1",
        "source": "review",
        "city": "Lisbon",
        "unexpected_field": "should be ignored",
    }

    meta = ReviewMetadata.from_pinecone_dict(payload)

    assert meta.id == "rev-1"
    assert meta.city == "Lisbon"


# RetrievalResult


def test_retrieval_result_distance_is_one_minus_score() -> None:
    meta = ReviewMetadata(id="x")
    result = RetrievalResult(text="hello", metadata=meta, score=0.8)

    assert result.distance == 0.2


# RAGResponse


def test_rag_response_to_dict_is_json_serialisable() -> None:
    import json

    meta = ReviewMetadata(id="x", city="Lisbon")
    response = RAGResponse(
        query="any question",
        answer="any answer",
        sources=[RetrievalResult(text="t", metadata=meta, score=0.9)],
    )

    payload = response.to_dict()
    json.dumps(payload)

    assert payload["query"] == "any question"
    assert payload["sources"][0]["metadata"]["city"] == "Lisbon"


def test_rag_response_includes_rewritten_query_when_present() -> None:
    response = RAGResponse(
        query="original",
        answer="answer",
        sources=[],
        rewritten_query="rewritten version",
    )

    payload = response.to_dict()

    assert payload["rewritten_query"] == "rewritten version"


def test_rag_response_rewritten_query_is_none_by_default() -> None:
    response = RAGResponse(query="q", answer="a", sources=[])

    assert response.rewritten_query is None
    assert response.to_dict()["rewritten_query"] is None


# Document


def test_document_is_immutable() -> None:
    """Frozen dataclasses prevent accidental mutation."""
    import dataclasses

    doc = Document(text="t", metadata=ReviewMetadata(id="x"))

    try:
        doc.text = "modified"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Document should be frozen")
