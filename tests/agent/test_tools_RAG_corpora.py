"""Tests for :mod:`elh_rag.agent.tools_RAG_corpora`."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from elh_rag.agent.tools_RAG_corpora import (
    RAGSearchHit,
    RAGSearchOutput,
    SearchDescriptionsInput,
    SearchReviewsInput,
    _build_descriptions_filter,
    _build_reviews_filter,
    _match_to_hit,
    search_descriptions,
    search_reviews,
)


@pytest.fixture
def pinecone_match() -> dict[str, Any]:
    """A canonical Pinecone match dict for the RAG corpora tests."""
    return {
        "id": "house_42_room_3_chunk_2",
        "score": 0.85674321,  # rounds to 0.857
        "metadata": {
            "text": "Cozy private room near Parque das Nacoes.",
            "city": "Lisbon",
            "flatname": "Alfama 3",
            "roomname": "Bedroom A",
        },
    }


@pytest.fixture
def stub_embedding() -> list[float]:
    """A short stand-in embedding vector."""
    return [0.1, 0.2, 0.3]


@pytest.fixture
def stub_ctx_for_descriptions(stub_embedding: list[float]) -> SimpleNamespace:
    """Mock AgentContext with embedder + descriptions_store."""
    embedder = MagicMock()
    embedder.encode_query.return_value = stub_embedding
    descriptions_store = MagicMock()
    descriptions_store.query.return_value = []  # tests override per-case
    return SimpleNamespace(embedder=embedder, descriptions_store=descriptions_store)


@pytest.fixture
def stub_ctx_for_reviews(stub_embedding: list[float]) -> SimpleNamespace:
    """Mock AgentContext with embedder + reviews_store."""
    embedder = MagicMock()
    embedder.encode_query.return_value = stub_embedding
    reviews_store = MagicMock()
    reviews_store.query.return_value = []
    return SimpleNamespace(embedder=embedder, reviews_store=reviews_store)


# Filter builders


class TestFilterBuilders:
    def test_descriptions_filter_none_when_city_is_none(self) -> None:
        assert _build_descriptions_filter(None) is None

    def test_descriptions_filter_with_city(self) -> None:
        assert _build_descriptions_filter("Lisbon") == {"city": {"$eq": "Lisbon"}}

    def test_reviews_filter_none_when_no_args(self) -> None:
        assert _build_reviews_filter(None, None) is None

    def test_reviews_filter_with_city_only(self) -> None:
        assert _build_reviews_filter("Porto", None) == {"city": {"$eq": "Porto"}}

    def test_reviews_filter_with_min_rating_only(self) -> None:
        assert _build_reviews_filter(None, 4) == {"overall_rating": {"$gte": 4}}

    def test_reviews_filter_combined(self) -> None:
        assert _build_reviews_filter("Lisbon", 3) == {
            "city": {"$eq": "Lisbon"},
            "overall_rating": {"$gte": 3},
        }


# match-hit converter


class TestMatchToHit:
    def test_score_rounded_to_three_decimals(self, pinecone_match: dict[str, Any]) -> None:
        hit = _match_to_hit(pinecone_match)
        assert hit.score == 0.857

    def test_all_fields_populated(self, pinecone_match: dict[str, Any]) -> None:
        hit = _match_to_hit(pinecone_match)
        assert hit.text == "Cozy private room near Parque das Nacoes."
        assert hit.source_id == "house_42_room_3_chunk_2"
        assert hit.metadata == pinecone_match["metadata"]

    def test_handles_missing_text_in_metadata(self) -> None:
        match = {
            "id": "x",
            "score": 0.5,
            "metadata": {"city": "Lisbon"},  # no 'text' key
        }
        hit = _match_to_hit(match)
        assert hit.text == ""
        assert hit.metadata == {"city": "Lisbon"}


# search_descriptions


class TestSearchDescriptions:
    def test_returns_rag_search_output_with_correct_corpus(
        self,
        stub_ctx_for_descriptions: SimpleNamespace,
        pinecone_match: dict[str, Any],
    ) -> None:
        stub_ctx_for_descriptions.descriptions_store.query.return_value = [pinecone_match]
        payload = SearchDescriptionsInput(query="cozy room")

        out = search_descriptions(payload, ctx=stub_ctx_for_descriptions)

        assert isinstance(out, RAGSearchOutput)
        assert out.corpus == "descriptions"
        assert out.query_used == "cozy room"
        assert out.total_hits == 1
        assert isinstance(out.hits[0], RAGSearchHit)
        assert out.hits[0].score == 0.857

    def test_embeds_the_query(self, stub_ctx_for_descriptions: SimpleNamespace) -> None:
        payload = SearchDescriptionsInput(query="balcony view")
        search_descriptions(payload, ctx=stub_ctx_for_descriptions)
        stub_ctx_for_descriptions.embedder.encode_query.assert_called_once_with("balcony view")

    def test_passes_top_k_and_filter_to_store(
        self,
        stub_ctx_for_descriptions: SimpleNamespace,
        stub_embedding: list[float],
    ) -> None:
        payload = SearchDescriptionsInput(query="quiet area", top_k=7, city="Porto")
        search_descriptions(payload, ctx=stub_ctx_for_descriptions)
        stub_ctx_for_descriptions.descriptions_store.query.assert_called_once_with(
            embedding=stub_embedding,
            top_k=7,
            metadata_filter={"city": {"$eq": "Porto"}},
        )

    def test_no_filter_when_city_none(
        self,
        stub_ctx_for_descriptions: SimpleNamespace,
        stub_embedding: list[float],
    ) -> None:
        payload = SearchDescriptionsInput(query="balcony")
        search_descriptions(payload, ctx=stub_ctx_for_descriptions)
        stub_ctx_for_descriptions.descriptions_store.query.assert_called_once_with(
            embedding=stub_embedding,
            top_k=5,  # default
            metadata_filter=None,
        )

    def test_empty_results_returns_empty_output(
        self, stub_ctx_for_descriptions: SimpleNamespace
    ) -> None:
        # store.query already returns [] by default
        payload = SearchDescriptionsInput(query="nothing matches")
        out = search_descriptions(payload, ctx=stub_ctx_for_descriptions)
        assert out.hits == []
        assert out.total_hits == 0

    def test_query_max_length_500_chars_raises(self) -> None:
        with pytest.raises(ValueError):  # Pydantic v2 raises ValidationError
            SearchDescriptionsInput(query="x" * 501)

    def test_top_k_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchDescriptionsInput(query="ok", top_k=25)


# search_reviews


class TestSearchReviews:
    def test_returns_rag_search_output_with_correct_corpus(
        self,
        stub_ctx_for_reviews: SimpleNamespace,
        pinecone_match: dict[str, Any],
    ) -> None:
        stub_ctx_for_reviews.reviews_store.query.return_value = [pinecone_match]
        payload = SearchReviewsInput(query="noisy at night")

        out = search_reviews(payload, ctx=stub_ctx_for_reviews)

        assert isinstance(out, RAGSearchOutput)
        assert out.corpus == "reviews"
        assert out.query_used == "noisy at night"
        assert out.total_hits == 1

    def test_combines_city_and_min_rating_filters(
        self,
        stub_ctx_for_reviews: SimpleNamespace,
        stub_embedding: list[float],
    ) -> None:
        payload = SearchReviewsInput(
            query="great location",
            top_k=10,
            city="Lisbon",
            min_rating=4,
        )
        search_reviews(payload, ctx=stub_ctx_for_reviews)
        stub_ctx_for_reviews.reviews_store.query.assert_called_once_with(
            embedding=stub_embedding,
            top_k=10,
            metadata_filter={
                "city": {"$eq": "Lisbon"},
                "overall_rating": {"$gte": 4},
            },
        )

    def test_only_min_rating_no_city(
        self,
        stub_ctx_for_reviews: SimpleNamespace,
        stub_embedding: list[float],
    ) -> None:
        payload = SearchReviewsInput(query="quiet", min_rating=3)
        search_reviews(payload, ctx=stub_ctx_for_reviews)
        stub_ctx_for_reviews.reviews_store.query.assert_called_once_with(
            embedding=stub_embedding,
            top_k=5,
            metadata_filter={"overall_rating": {"$gte": 3}},
        )

    def test_min_rating_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchReviewsInput(query="ok", min_rating=6)
