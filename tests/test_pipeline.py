"""Tests for the RAGPipeline orchestration."""
from __future__ import annotations

from typing import Any

import pytest

from elh_rag.indexing.embeddings import Embedder
from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import RAGResponse


# End-to-end happy path


def test_query_returns_rag_response_with_sources(
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store, embedder=fake_embedder, llm_client=fake_llm
    )

    response = pipeline.query("comfortable bed", top_k=5)

    assert isinstance(response, RAGResponse)
    assert response.query == "comfortable bed"
    assert response.answer == "The bed is comfortable, per Review 1."
    assert len(response.sources) == 1
    assert response.sources[0].metadata.city == "Lisbon"


def test_empty_retrieval_returns_no_results_message(
    fake_embedder: Embedder, fake_llm: LLMClient
) -> None:
    from tests.conftest import FakeVectorStore

    empty_store = FakeVectorStore(canned_matches=[])
    pipeline = RAGPipeline(
        vector_store=empty_store, embedder=fake_embedder, llm_client=fake_llm
    )

    response = pipeline.query("question with no matches")

    assert response.sources == []
    assert "No relevant reviews" in response.answer


# Metadata filter composition


@pytest.mark.parametrize(
    "city,rating,expected",
    [
        (None, None, None),
        ("Lisbon", None, {"city": {"$eq": "Lisbon"}}),
        (None, 4, {"overall_rating": {"$gte": 4}}),
        (
            "Porto",
            3,
            {"city": {"$eq": "Porto"}, "overall_rating": {"$gte": 3}},
        ),
    ],
)
def test_metadata_filter_composition(
    city: str | None, rating: int | None, expected: dict[str, Any] | None
) -> None:
    assert RAGPipeline._build_metadata_filter(city, rating) == expected


# Context formatting


def test_context_includes_review_header(
    fake_store: VectorStore, fake_embedder: Embedder, fake_llm: LLMClient
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store, embedder=fake_embedder, llm_client=fake_llm
    )

    pipeline.query("anything")

    user_prompt = fake_llm.calls[0]["user"]  # type: ignore[attr-defined]
    assert "[Review 1]" in user_prompt
    assert "Casa do Sol" in user_prompt
    assert "Lisbon" in user_prompt


# Filter passes through to the store


def test_city_filter_propagates_to_store(
    fake_store: VectorStore, fake_embedder: Embedder, fake_llm: LLMClient
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store, embedder=fake_embedder, llm_client=fake_llm
    )

    pipeline.query("anything", city_filter="Porto", min_rating=4)

    last_call = fake_store.query_calls[-1]  # type: ignore[attr-defined]
    assert last_call["filter"] == {
        "city": {"$eq": "Porto"},
        "overall_rating": {"$gte": 4},
    }
