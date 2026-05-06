"""Tests for the typed schemas, especially Pinecone round-tripping."""

from __future__ import annotations

from elh_rag.schemas import (
    Document,
    DocumentSource,
    HouseMetadata,
    RAGResponse,
    RetrievalResult,
    ReviewMetadata,
    RoomMetadata,
    metadata_from_pinecone_dict,
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


# HouseMetadata


def test_house_metadata_default_source_is_house() -> None:
    meta = HouseMetadata(id="house:HSE_001")
    assert meta.source == DocumentSource.HOUSE


def test_house_metadata_round_trip_preserves_fields() -> None:
    original = HouseMetadata(
        id="house:HSE_712D9E74",
        idhouse="HSE_712D9E74",
        flatname="Graca Student Flat",
        city="Lisbon",
        zone="Graca",
        neighbourhood="Jardim Botto Machado",
    )

    restored = HouseMetadata.from_pinecone_dict(original.to_pinecone_dict())

    assert restored == original
    assert restored.source == DocumentSource.HOUSE


def test_house_metadata_to_pinecone_dict_is_json_safe() -> None:
    import json

    meta = HouseMetadata(id="house:X", idhouse="X", flatname="Name", city="Porto")
    json.dumps(meta.to_pinecone_dict())


# RoomMetadata


def test_room_metadata_default_source_is_room() -> None:
    meta = RoomMetadata(id="room:RM_001")
    assert meta.source == DocumentSource.ROOM


def test_room_metadata_round_trip_preserves_fields() -> None:
    original = RoomMetadata(
        id="room:RM_HSE_DE976537_3",
        idroom="RM_HSE_DE976537_3",
        roomname="Garden View Room",
        idhouse="HSE_DE976537",
        flatname="Residencia Alfama",
        city="Lisbon",
        zone="Alfama",
    )

    restored = RoomMetadata.from_pinecone_dict(original.to_pinecone_dict())

    assert restored == original
    assert restored.source == DocumentSource.ROOM


# metadata_from_pinecone_dict dispatcher


def test_dispatcher_routes_review_source_to_review_metadata() -> None:
    payload = {"id": "r1", "source": "review", "city": "Lisbon"}
    meta = metadata_from_pinecone_dict(payload)

    assert isinstance(meta, ReviewMetadata)
    assert meta.city == "Lisbon"


def test_dispatcher_routes_house_source_to_house_metadata() -> None:
    payload = {"id": "h1", "source": "house", "idhouse": "HSE_001", "flatname": "X"}
    meta = metadata_from_pinecone_dict(payload)

    assert isinstance(meta, HouseMetadata)
    assert meta.flatname == "X"


def test_dispatcher_routes_room_source_to_room_metadata() -> None:
    payload = {"id": "rm1", "source": "room", "idroom": "RM_001", "roomname": "A"}
    meta = metadata_from_pinecone_dict(payload)

    assert isinstance(meta, RoomMetadata)
    assert meta.roomname == "A"


def test_dispatcher_defaults_to_review_when_source_missing() -> None:
    """Backward compatibility: pre-Step 4 records have no 'source' field."""
    payload = {"id": "legacy", "city": "Porto"}
    meta = metadata_from_pinecone_dict(payload)

    assert isinstance(meta, ReviewMetadata)


# DocumentMetadata union accepts all three types


def test_document_accepts_all_three_metadata_types() -> None:
    """Document.metadata: DocumentMetadata accepts ReviewMetadata, HouseMetadata, RoomMetadata."""
    review_doc = Document(text="rev", metadata=ReviewMetadata(id="r"))
    house_doc = Document(text="house desc", metadata=HouseMetadata(id="h"))
    room_doc = Document(text="room desc", metadata=RoomMetadata(id="rm"))

    assert review_doc.metadata.source == DocumentSource.REVIEW
    assert house_doc.metadata.source == DocumentSource.HOUSE
    assert room_doc.metadata.source == DocumentSource.ROOM


def test_retrieval_result_accepts_all_three_metadata_types() -> None:
    for meta in [
        ReviewMetadata(id="r"),
        HouseMetadata(id="h"),
        RoomMetadata(id="rm"),
    ]:
        result = RetrievalResult(text="t", metadata=meta, vector_score=0.5)
        assert result.score == 0.5


# RetrievalResult


def test_retrieval_result_distance_is_one_minus_vector_score() -> None:
    meta = ReviewMetadata(id="x")
    result = RetrievalResult(text="hello", metadata=meta, vector_score=0.8)

    assert result.distance == 0.2


def test_retrieval_result_score_prefers_rerank_when_present() -> None:
    meta = ReviewMetadata(id="x")
    vector_only = RetrievalResult(text="t", metadata=meta, vector_score=0.6)
    reranked = RetrievalResult(text="t", metadata=meta, vector_score=0.6, rerank_score=0.92)

    assert vector_only.score == 0.6
    assert reranked.score == 0.92


# RAGResponse


def test_rag_response_to_dict_is_json_serialisable() -> None:
    import json

    meta = ReviewMetadata(id="x", city="Lisbon")
    response = RAGResponse(
        query="any question",
        answer="any answer",
        sources=[RetrievalResult(text="t", metadata=meta, vector_score=0.9)],
    )

    payload = response.to_dict()
    json.dumps(payload)

    assert payload["query"] == "any question"
    assert payload["sources"][0]["metadata"]["city"] == "Lisbon"
    assert payload["sources"][0]["vector_score"] == 0.9
    assert payload["sources"][0]["rerank_score"] is None


def test_rag_response_to_dict_exposes_both_scores_when_reranked() -> None:
    meta = ReviewMetadata(id="x")
    response = RAGResponse(
        query="q",
        answer="a",
        sources=[RetrievalResult(text="t", metadata=meta, vector_score=0.7, rerank_score=0.95)],
    )

    src = response.to_dict()["sources"][0]
    assert src["vector_score"] == 0.7
    assert src["rerank_score"] == 0.95


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
