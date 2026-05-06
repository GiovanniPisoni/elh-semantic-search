"""Tests for the Reranker component (Phase 2, Step 2).

Tests use a FakeCrossEncoder that avoids downloading the real model.
"""

from __future__ import annotations

from typing import Any

from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RetrievalResult, ReviewMetadata

# Fake cross-encoder


class FakeCrossEncoder:
    """Stand-in for sentence_transformers.CrossEncoder.

    Scores each pair based on the content of the document text, giving us
    deterministic but non-trivial reordering to assert against.
    """

    def __init__(self, scoring: dict[str, float] | None = None) -> None:
        self._scoring = scoring or {}

    def predict(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 16,
        show_progress_bar: bool = False,
    ) -> list[float]:
        return [self._scoring.get(doc, 0.0) for _, doc in pairs]


def _make_results(texts_and_scores: list[tuple[str, float]]) -> list[RetrievalResult]:
    """Helper: build RetrievalResult list from (text, vector_score) pairs."""
    return [
        RetrievalResult(
            text=text,
            metadata=ReviewMetadata(id=f"id-{i}"),
            vector_score=vs,
        )
        for i, (text, vs) in enumerate(texts_and_scores)
    ]


def _make_reranker(model: Any) -> Reranker:
    """Build a Reranker with a pre-loaded fake model (bypasses lazy init)."""
    r = Reranker()
    r._model = model  # type: ignore[attr-defined]
    return r


# Core behaviour


def test_rerank_reorders_by_cross_encoder_score() -> None:
    candidates = _make_results(
        [
            ("doc-A bad match", 0.9),
            ("doc-B great match", 0.7),
            ("doc-C okay match", 0.5),
        ]
    )
    fake_model = FakeCrossEncoder(
        scoring={
            "doc-A bad match": 0.1,
            "doc-B great match": 0.95,
            "doc-C okay match": 0.5,
        }
    )
    reranker = _make_reranker(fake_model)

    result = reranker.rerank("any query", candidates, top_k=3)

    assert [r.text for r in result] == [
        "doc-B great match",
        "doc-C okay match",
        "doc-A bad match",
    ]


def test_rerank_preserves_vector_score_alongside_rerank_score() -> None:
    candidates = _make_results([("doc", 0.85)])
    fake_model = FakeCrossEncoder(scoring={"doc": 0.42})
    reranker = _make_reranker(fake_model)

    result = reranker.rerank("q", candidates, top_k=1)

    assert result[0].vector_score == 0.85
    assert result[0].rerank_score == 0.42


def test_rerank_truncates_to_top_k() -> None:
    candidates = _make_results([(f"d{i}", 0.9 - i * 0.1) for i in range(10)])
    fake_model = FakeCrossEncoder(scoring={f"d{i}": float(i) for i in range(10)})
    reranker = _make_reranker(fake_model)

    result = reranker.rerank("q", candidates, top_k=3)

    assert len(result) == 3
    assert [r.text for r in result] == ["d9", "d8", "d7"]


# Edge cases


def test_rerank_handles_empty_candidates() -> None:
    reranker = _make_reranker(FakeCrossEncoder())

    assert reranker.rerank("q", [], top_k=5) == []


def test_rerank_single_candidate_still_gets_rerank_score() -> None:
    """Single candidate passes through the model so rerank_score is populated."""
    candidates = _make_results([("only doc", 0.5)])
    fake_model = FakeCrossEncoder(scoring={"only doc": 0.77})
    reranker = _make_reranker(fake_model)

    result = reranker.rerank("q", candidates, top_k=5)

    assert len(result) == 1
    assert result[0].text == "only doc"
    assert result[0].rerank_score == 0.77


def test_rerank_falls_back_to_vector_order_on_model_error() -> None:
    candidates = _make_results([("doc-A", 0.9), ("doc-B", 0.7), ("doc-C", 0.5)])

    class BrokenModel(FakeCrossEncoder):
        def predict(self, *a: Any, **k: Any) -> list[float]:
            raise RuntimeError("model crashed")

    reranker = _make_reranker(BrokenModel())

    result = reranker.rerank("q", candidates, top_k=2)

    assert [r.text for r in result] == ["doc-A", "doc-B"]
    assert all(r.rerank_score is None for r in result)


def test_rerank_sorts_descending_by_rerank_score() -> None:
    """Highest rerank score comes first."""
    candidates = _make_results([("d1", 0.5), ("d2", 0.5), ("d3", 0.5)])
    fake_model = FakeCrossEncoder(scoring={"d1": 0.3, "d2": 0.9, "d3": 0.6})
    reranker = _make_reranker(fake_model)

    result = reranker.rerank("q", candidates, top_k=3)

    scores = [r.rerank_score for r in result]
    assert scores == sorted(scores, reverse=True)
