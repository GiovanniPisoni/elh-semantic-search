"""Tests for Tool 6 — ``answer_policy_question``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elh_rag.tools._kb import IndexedEntry, KBContext, KBEntry, KBStore
from elh_rag.tools.answer_policy_question import (
    AnswerPolicyQuestionInput,
    AnswerPolicyQuestionOutput,
    answer_policy_question,
)

# Stub embedder / KBContext


class _DictEmbedder:
    """Embedder shim: returns a precomputed vector per known string.

    Lets tests assert on cosine behaviour without depending on the
    real SentenceTransformer model.
    """

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping
        self.dimension = next(iter(mapping.values())).__len__() if mapping else 0

    def encode_query(self, text: str) -> list[float]:
        if text not in self._mapping:
            raise KeyError(f"No precomputed embedding for {text!r}")
        return self._mapping[text]

    def encode_batch(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        return [self._mapping[t] for t in texts]


def _entry(
    id: str,
    *,
    category: str = "test",
    audience: str = "student",
    canonical: str = "Test?",
    variants: list[str] | None = None,
    answer: str = "Test answer.",
    sources: list[str] | None = None,
    related: list[str] | None = None,
) -> KBEntry:
    return KBEntry(
        id=id,
        category=category,
        audience=audience,  # type: ignore[arg-type]
        canonical_question=canonical,
        question_variants=variants or [],
        answer=answer,
        sources=sources or [],
        related=related or [],
    )


def _build_ctx(
    entries_with_embeddings: list[tuple[KBEntry, list[list[float]]]],
    query_embeddings: dict[str, list[float]],
) -> KBContext:
    indexed = [
        IndexedEntry(entry=e, variant_embeddings=embs) for e, embs in entries_with_embeddings
    ]
    store = KBStore(indexed)
    embedder = _DictEmbedder(query_embeddings)
    return KBContext(kb_store=store, embedder=embedder)  # type: ignore[arg-type]


# Input validation


class TestInputValidation:
    def test_question_min_length(self):
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="ab")  # < 3

    def test_question_max_length(self):
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="a" * 501)

    def test_audience_literal_enforced(self):
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(
                question="What is the policy?",
                audience="alien",  # type: ignore[arg-type]
            )

    def test_max_results_bounded(self):
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="Question?", max_results=0)
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="Question?", max_results=11)

    def test_threshold_bounded(self):
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="Question?", confidence_threshold=1.5)
        with pytest.raises(ValidationError):
            AnswerPolicyQuestionInput(question="Question?", confidence_threshold=-0.1)

    def test_defaults_are_set(self):
        p = AnswerPolicyQuestionInput(question="Question?")
        assert p.max_results == 3
        assert p.audience == "student"
        assert p.confidence_threshold == 0.5


# Happy path


class TestHappyPath:
    def test_single_match_returned(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="cancellation", canonical="cancel?"), [[1.0, 0.0]]),
                (_entry(id="payment", canonical="pay?"), [[0.0, 1.0]]),
            ],
            query_embeddings={"How to cancel?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="How to cancel?"),
            ctx=ctx,
        )
        assert isinstance(result, AnswerPolicyQuestionOutput)
        assert result.found is True
        assert len(result.matches) == 1
        assert result.matches[0].id == "cancellation"
        assert result.matches[0].confidence == pytest.approx(1.0)
        assert result.fallback_message is None

    def test_multiple_matches_sorted_by_confidence(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="a"), [[1.0, 0.0]]),
                (_entry(id="b"), [[0.8, 0.6]]),  # cos ≈ 0.8 with [1,0]
                (_entry(id="c"), [[0.6, 0.8]]),  # cos ≈ 0.6 with [1,0]
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(
                question="test query?", max_results=5, confidence_threshold=0.5
            ),
            ctx=ctx,
        )
        ids = [m.id for m in result.matches]
        assert ids == ["a", "b", "c"]
        # Confidences are monotonically decreasing
        confs = [m.confidence for m in result.matches]
        assert confs == sorted(confs, reverse=True)

    def test_max_results_caps_output(self):
        ctx = _build_ctx(
            entries_with_embeddings=[(_entry(id=f"e{i}"), [[1.0, 0.0]]) for i in range(5)],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", max_results=2),
            ctx=ctx,
        )
        assert len(result.matches) == 2

    def test_sources_and_related_passed_through(self):
        e = _entry(
            id="x",
            sources=["FAQ", "presentation"],
            related=["y", "z"],
        )
        ctx = _build_ctx(
            entries_with_embeddings=[(e, [[1.0, 0.0]])],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(AnswerPolicyQuestionInput(question="test query?"), ctx=ctx)
        m = result.matches[0]
        assert m.sources == ["FAQ", "presentation"]
        assert m.related_ids == ["y", "z"]


# No match


class TestNoMatch:
    def test_below_threshold_returns_empty_with_fallback(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="x"), [[0.0, 1.0]])  # orthogonal to query
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", confidence_threshold=0.5),
            ctx=ctx,
        )
        assert result.found is False
        assert result.matches == []
        assert result.fallback_message is not None
        assert "hello@erasmuslifehousing.com" in result.fallback_message

    def test_empty_kb_returns_fallback(self):
        ctx = _build_ctx(
            entries_with_embeddings=[],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(AnswerPolicyQuestionInput(question="test query?"), ctx=ctx)
        assert result.found is False
        assert "+351" in result.fallback_message or "@" in result.fallback_message


# Audience filter pass-through


class TestAudienceFilter:
    def test_student_excludes_landlord_entries(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="s", audience="student"), [[1.0, 0.0]]),
                (_entry(id="l", audience="landlord"), [[1.0, 0.0]]),
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", audience="student"),
            ctx=ctx,
        )
        assert {m.id for m in result.matches} == {"s"}

    def test_landlord_excludes_student_entries(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="s", audience="student"), [[1.0, 0.0]]),
                (_entry(id="l", audience="landlord"), [[1.0, 0.0]]),
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", audience="landlord"),
            ctx=ctx,
        )
        assert {m.id for m in result.matches} == {"l"}

    def test_both_audiences_returns_all(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="s", audience="student"), [[1.0, 0.0]]),
                (_entry(id="l", audience="landlord"), [[1.0, 0.0]]),
                (_entry(id="x", audience="both"), [[1.0, 0.0]]),
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", audience="both", max_results=10),
            ctx=ctx,
        )
        assert {m.id for m in result.matches} == {"s", "l", "x"}


# Error handling


class TestErrorHandling:
    def test_no_ctx_raises(self):
        with pytest.raises(RuntimeError, match="KBContext"):
            answer_policy_question(
                AnswerPolicyQuestionInput(question="Test question?"),
                ctx=None,
            )


# Summary


class TestSummary:
    def test_summary_with_single_match_mentions_id(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="cancellation"), [[1.0, 0.0]]),
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(AnswerPolicyQuestionInput(question="test query?"), ctx=ctx)
        assert "cancellation" in result.summary
        assert "1.00" in result.summary or "1.0" in result.summary

    def test_summary_with_multiple_matches_shows_extras(self):
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="a"), [[1.0, 0.0]]),
                (_entry(id="b"), [[1.0, 0.0]]),
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(AnswerPolicyQuestionInput(question="test query?"), ctx=ctx)
        assert "+1 related" in result.summary

    def test_summary_on_no_match_says_no_match(self):
        ctx = _build_ctx(
            entries_with_embeddings=[],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(AnswerPolicyQuestionInput(question="test query?"), ctx=ctx)
        assert "No KB entry matched" in result.summary


# Confidence rounding


class TestConfidence:
    def test_confidence_rounded_to_four_decimals(self):
        # Vector with weird length so cosine isn't a round number
        ctx = _build_ctx(
            entries_with_embeddings=[
                (_entry(id="x"), [[3.0, 1.0]]),  # cos(0.95...something)
            ],
            query_embeddings={"test query?": [1.0, 0.0]},
        )
        result = answer_policy_question(
            AnswerPolicyQuestionInput(question="test query?", confidence_threshold=0.1),
            ctx=ctx,
        )
        # Whatever the value, it must be a float with ≤ 4 decimals
        c = result.matches[0].confidence
        assert isinstance(c, float)
        # round-trip check
        assert c == round(c, 4)
