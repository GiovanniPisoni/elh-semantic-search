"""Tests for the RAGPipeline orchestration."""
from __future__ import annotations

from typing import Any

import pytest

from elh_rag.indexing.embeddings import Embedder
from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.pipeline import RAGPipeline
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RAGResponse, ReviewMetadata

from tests.conftest import FakeQueryRewriter, FakeReranker, FakeVectorStore


# Helpers


def _disable_advanced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn off both optional steps — pipeline behaves as Phase 1 Naive RAG."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", False)
    monkeypatch.setattr(cfg.settings, "enable_reranking", False)


def _make_pipeline(
    store: VectorStore,
    embedder: Embedder,
    llm: LLMClient,
    rewriter: QueryRewriter | None = None,
    reranker: Reranker | None = None,
) -> RAGPipeline:
    return RAGPipeline(
        vector_store=store,
        embedder=embedder,
        llm_client=llm,
        query_rewriter=rewriter or FakeQueryRewriter(passthrough=True),
        reranker=reranker or FakeReranker(reverse=False),
    )


# End-to-end happy path


def test_query_returns_rag_response_with_sources(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_advanced(monkeypatch)
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm)

    response = pipeline.query("comfortable bed", top_k=5)

    assert isinstance(response, RAGResponse)
    assert response.query == "comfortable bed"
    assert response.answer == "The bed is comfortable, per Review 1."
    assert len(response.sources) == 1
    assert response.sources[0].metadata.city == "Lisbon"
    assert response.mode == "naive-pinecone"


def test_empty_retrieval_returns_no_results_message(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_advanced(monkeypatch)
    empty_store = FakeVectorStore(canned_matches=[])
    pipeline = _make_pipeline(empty_store, fake_embedder, fake_llm)

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
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_advanced(monkeypatch)
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm)

    pipeline.query("anything")

    user_prompt = fake_llm.calls[0]["user"]  # type: ignore[attr-defined]
    assert "[Review 1]" in user_prompt
    assert "Casa do Sol" in user_prompt
    assert "Lisbon" in user_prompt


# Filter passes through to the store


def test_city_filter_propagates_to_store(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_advanced(monkeypatch)
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm)

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
    _disable_advanced(monkeypatch)

    rewriter = FakeQueryRewriter(canned_output="should not be used")
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm, rewriter=rewriter)

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
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", False)

    rewriter = FakeQueryRewriter(canned_output="quiet, peaceful, no street noise")
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm, rewriter=rewriter)

    response = pipeline.query("I need a quiet place to study")

    assert rewriter.calls == ["I need a quiet place to study"]
    assert response.rewritten_query == "quiet, peaceful, no street noise"
    assert response.mode == "advanced-rewrite"

    expected_embedding = fake_embedder.encode_query("quiet, peaceful, no street noise")
    assert fake_store.query_calls[-1]["embedding"] == expected_embedding  # type: ignore[attr-defined]


def test_llm_generation_uses_original_question_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", False)

    rewriter = FakeQueryRewriter(canned_output="REWRITTEN VERSION")
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm, rewriter=rewriter)

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
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", False)

    rewriter = FakeQueryRewriter(passthrough=True)
    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm, rewriter=rewriter)

    response = pipeline.query("already optimal query")

    assert response.rewritten_query is None


# ── Re-ranking (Phase 2, Step 2) ──────────────────────────────────────────


def _make_matches(n: int) -> list[dict[str, Any]]:
    """Build n distinct Pinecone-shaped matches for reranking tests."""
    matches = []
    for i in range(n):
        meta = ReviewMetadata(
            id=f"rev-{i:03d}",
            city="Lisbon",
            flatname=f"House {i}",
            review_text_original=f"Review content number {i}",
        )
        matches.append(
            {
                "id": meta.id,
                "score": 0.9 - i * 0.05,
                "metadata": meta.to_pinecone_dict(),
            }
        )
    return matches


def test_reranking_disabled_preserves_vector_order(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_advanced(monkeypatch)
    store = FakeVectorStore(canned_matches=_make_matches(5))
    reranker = FakeReranker(reverse=True)
    pipeline = _make_pipeline(store, fake_embedder, fake_llm, reranker=reranker)

    response = pipeline.query("q", top_k=3)

    assert reranker.calls == []
    assert [s.metadata.id for s in response.sources] == ["rev-000", "rev-001", "rev-002"]
    assert all(s.rerank_score is None for s in response.sources)


def test_reranking_enabled_reorders_results(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", False)
    monkeypatch.setattr(cfg.settings, "enable_reranking", True)
    monkeypatch.setattr(cfg.settings, "reranker_pool_size", 5)

    store = FakeVectorStore(canned_matches=_make_matches(5))
    reranker = FakeReranker(reverse=True)
    pipeline = _make_pipeline(store, fake_embedder, fake_llm, reranker=reranker)

    response = pipeline.query("q", top_k=3)

    assert len(reranker.calls) == 1
    assert [s.metadata.id for s in response.sources] == ["rev-004", "rev-003", "rev-002"]
    assert all(s.rerank_score is not None for s in response.sources)
    assert all(s.vector_score is not None for s in response.sources)
    assert response.mode == "advanced-rerank"


def test_reranking_fetches_pool_size_candidates_from_store(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """With reranking on, the store is queried for `pool_size` candidates, not top_k."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", False)
    monkeypatch.setattr(cfg.settings, "enable_reranking", True)
    monkeypatch.setattr(cfg.settings, "reranker_pool_size", 20)

    store = FakeVectorStore(canned_matches=_make_matches(20))
    pipeline = _make_pipeline(
        store, fake_embedder, fake_llm, reranker=FakeReranker(reverse=False)
    )

    pipeline.query("q", top_k=5)

    assert store.query_calls[-1]["top_k"] == 20  # type: ignore[attr-defined]


def test_reranking_uses_retrieval_query_not_original_when_rewriting_also_on(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """The reranker receives the rewritten query, matching what the retriever used."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", True)
    monkeypatch.setattr(cfg.settings, "reranker_pool_size", 5)

    store = FakeVectorStore(canned_matches=_make_matches(5))
    rewriter = FakeQueryRewriter(canned_output="rewritten text")
    reranker = FakeReranker(reverse=False)
    pipeline = _make_pipeline(
        store, fake_embedder, fake_llm, rewriter=rewriter, reranker=reranker
    )

    pipeline.query("original question")

    assert reranker.calls[-1][0] == "rewritten text"


def test_mode_label_includes_all_active_flags(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: VectorStore,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", True)

    pipeline = _make_pipeline(fake_store, fake_embedder, fake_llm)

    response = pipeline.query("q")

    assert response.mode == "advanced-rewrite+rerank"