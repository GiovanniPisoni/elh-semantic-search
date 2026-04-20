"""Tests for the RAGPipeline orchestration."""
from __future__ import annotations

from typing import Any

import pytest

from elh_rag.indexing.embeddings import Embedder
from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.pipeline import RAGPipeline
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.schemas import RAGResponse

from tests.conftest import FakeQueryRewriter, FakeVectorStore


# End-to-end happy path


def test_query_returns_rag_response_with_sources(
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
    fake_rewriter: QueryRewriter,
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=fake_rewriter,
    )

    response = pipeline.query("comfortable bed", top_k=5)

    assert isinstance(response, RAGResponse)
    assert response.query == "comfortable bed"
    assert response.answer == "The bed is comfortable, per Review 1."
    assert len(response.sources) == 1
    assert response.sources[0].metadata.city == "Lisbon"


def test_empty_retrieval_returns_no_results_message(
    fake_embedder: Embedder,
    fake_llm: LLMClient,
    fake_rewriter: QueryRewriter,
) -> None:
    empty_store = FakeVectorStore(canned_matches=[])
    pipeline = RAGPipeline(
        vector_store=empty_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=fake_rewriter,
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
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
    fake_rewriter: QueryRewriter,
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=fake_rewriter,
    )

    pipeline.query("anything")

    user_prompt = fake_llm.calls[0]["user"]  # type: ignore[attr-defined]
    assert "[Review 1]" in user_prompt
    assert "Casa do Sol" in user_prompt
    assert "Lisbon" in user_prompt


# Filter passes through to the store


def test_city_filter_propagates_to_store(
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
    fake_rewriter: QueryRewriter,
) -> None:
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=fake_rewriter,
    )

    pipeline.query("anything", city_filter="Porto", min_rating=4)

    last_call = fake_store.query_calls[-1]  # type: ignore[attr-defined]
    assert last_call["filter"] == {
        "city": {"$eq": "Porto"},
        "overall_rating": {"$gte": 4},
    }


# Query rewriting


def test_rewriting_disabled_bypasses_rewriter(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """When ENABLE_QUERY_REWRITING=false, the rewriter is never called."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", False)

    rewriter = FakeQueryRewriter(canned_output="should not be used")
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=rewriter,
    )

    response = pipeline.query("original question")

    assert rewriter.calls == []
    assert response.rewritten_query is None
    assert response.mode == "naive-pinecone"


def test_rewriting_enabled_feeds_rewritten_query_to_retriever(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """The retriever embeds the rewritten query, not the original one."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)

    rewriter = FakeQueryRewriter(canned_output="quiet, peaceful, no street noise")
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=rewriter,
    )

    response = pipeline.query("I need a quiet place to study")

    assert rewriter.calls == ["I need a quiet place to study"]
    assert response.rewritten_query == "quiet, peaceful, no street noise"
    assert response.mode == "advanced-rewriting"

    expected_embedding = fake_embedder.encode_query("quiet, peaceful, no street noise")
    assert fake_store.query_calls[-1]["embedding"] == expected_embedding  # type: ignore[attr-defined]


def test_llm_generation_uses_original_question_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """The generation LLM must receive the ORIGINAL question, not the rewritten one."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)

    rewriter = FakeQueryRewriter(canned_output="REWRITTEN VERSION")
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=rewriter,
    )

    pipeline.query("original user question")

    user_prompt = fake_llm.calls[0]["user"]  # type: ignore[attr-defined]
    assert "original user question" in user_prompt
    assert "REWRITTEN VERSION" not in user_prompt


def test_rewriting_skipped_when_rewriter_returns_identical_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """If the rewriter returns the exact same text, rewritten_query stays None."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)

    rewriter = FakeQueryRewriter(passthrough=True)
    pipeline = RAGPipeline(
        vector_store=fake_store,
        embedder=fake_embedder,
        llm_client=fake_llm,
        query_rewriter=rewriter,
    )

    response = pipeline.query("already optimal query")

    assert response.rewritten_query is None
