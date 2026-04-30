"""Tests for the custom evaluation framework."""
from __future__ import annotations

import pytest

from elh_rag.evaluation.judge import _try_parse_json, EvaluationJudge, JudgeError
from elh_rag.evaluation.metrics import (
    answer_relevancy,
    context_recall,
    faithfulness,
    MetricResult,
)


# JSON parser robustness


def test_parse_simple_json() -> None:
    assert _try_parse_json('{"score": 0.5}') == {"score": 0.5}


def test_parse_json_with_whitespace() -> None:
    assert _try_parse_json('   {"score": 0.5}   ') == {"score": 0.5}


def test_parse_json_with_markdown_fences() -> None:
    raw = '```json\n{"score": 0.5}\n```'
    assert _try_parse_json(raw) == {"score": 0.5}


def test_parse_json_with_plain_fences() -> None:
    raw = '```\n{"score": 0.5}\n```'
    assert _try_parse_json(raw) == {"score": 0.5}


def test_parse_json_with_preamble_and_trailing_text() -> None:
    raw = 'Sure, here is the JSON: {"score": 0.7} (hope this helps)'
    assert _try_parse_json(raw) == {"score": 0.7}


def test_parse_returns_none_on_empty() -> None:
    assert _try_parse_json("") is None


def test_parse_returns_none_on_no_json() -> None:
    assert _try_parse_json("no json here") is None


def test_parse_returns_none_on_malformed_json() -> None:
    assert _try_parse_json('{"score": 0.5,}') is None  # trailing comma


def test_parse_nested_json() -> None:
    raw = '{"claims": [{"text": "x", "supported": true}]}'
    parsed = _try_parse_json(raw)
    assert parsed["claims"][0]["supported"] is True


# Fake judge


class _FakeJudge(EvaluationJudge):
    """Test double — returns canned responses without API calls."""

    def __init__(self, response: dict | Exception) -> None:
        # Bypass real __init__ to avoid needing an API key.
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def ask_json(self, system: str, user: str, retry_on_parse_error: bool = True):
        self.calls.append((system, user))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# Faithfulness


def test_faithfulness_all_supported() -> None:
    judge = _FakeJudge({
        "claims": [
            {"text": "claim A", "supported": True, "reason": "ok"},
            {"text": "claim B", "supported": True, "reason": "ok"},
        ]
    })
    result = faithfulness(judge=judge, answer="some answer", contexts=["ctx 1"])
    assert result.score == 1.0
    assert result.details["total_claims"] == 2


def test_faithfulness_partial_support() -> None:
    judge = _FakeJudge({
        "claims": [
            {"text": "claim A", "supported": True},
            {"text": "claim B", "supported": False},
            {"text": "claim C", "supported": True},
        ]
    })
    result = faithfulness(judge=judge, answer="some answer", contexts=["ctx"])
    assert result.score == round(2 / 3, 3)


def test_faithfulness_returns_none_when_no_claims() -> None:
    """Empty claims list = 'I don't know' answer = correct behaviour for unanswerable."""
    judge = _FakeJudge({"claims": []})
    result = faithfulness(judge=judge, answer="I don't know", contexts=["ctx"])
    assert result.score is None


def test_faithfulness_returns_none_on_judge_error() -> None:
    judge = _FakeJudge(JudgeError("api crashed"))
    result = faithfulness(judge=judge, answer="ans", contexts=["ctx"])
    assert result.score is None
    assert "error" in result.details


def test_faithfulness_returns_none_on_empty_inputs() -> None:
    judge = _FakeJudge({"claims": []})
    assert faithfulness(judge=judge, answer="", contexts=["ctx"]).score is None
    assert faithfulness(judge=judge, answer="ans", contexts=[]).score is None


# Context recall


def test_context_recall_all_covered() -> None:
    judge = _FakeJudge({
        "concepts": [
            {"concept": "safety", "covered": True, "evidence": "felt safe"},
            {"concept": "Lisbon", "covered": True, "evidence": "in Lisboa"},
        ]
    })
    result = context_recall(
        judge=judge, must_mention=["safety", "Lisbon"], contexts=["ctx"]
    )
    assert result.score == 1.0


def test_context_recall_partial_coverage() -> None:
    judge = _FakeJudge({
        "concepts": [
            {"concept": "safety", "covered": True},
            {"concept": "balcony", "covered": False},
        ]
    })
    result = context_recall(
        judge=judge, must_mention=["safety", "balcony"], contexts=["ctx"]
    )
    assert result.score == 0.5


def test_context_recall_skips_when_no_must_mention() -> None:
    judge = _FakeJudge({"concepts": []})
    result = context_recall(judge=judge, must_mention=[], contexts=["ctx"])
    assert result.score is None
    # Judge should not have been called
    assert judge.calls == []


def test_context_recall_zero_when_no_contexts_but_concepts_expected() -> None:
    judge = _FakeJudge({"concepts": []})
    result = context_recall(judge=judge, must_mention=["safety"], contexts=[])
    assert result.score == 0.0


def test_context_recall_returns_none_on_judge_error() -> None:
    judge = _FakeJudge(JudgeError("api crashed"))
    result = context_recall(judge=judge, must_mention=["safety"], contexts=["ctx"])
    assert result.score is None


# Answer relevancy


def test_answer_relevancy_returns_score() -> None:
    judge = _FakeJudge({
        "score": 0.8,
        "reasoning": "On-topic, concise",
        "is_unanswerable_query": False,
    })
    result = answer_relevancy(judge=judge, question="q?", answer="ans")
    assert result.score == 0.8
    assert result.details["reasoning"] == "On-topic, concise"


def test_answer_relevancy_handles_unanswerable() -> None:
    judge = _FakeJudge({
        "score": 1.0,
        "reasoning": "Correctly said 'I don't know'",
        "is_unanswerable_query": True,
    })
    result = answer_relevancy(
        judge=judge, question="asdfgh", answer="I don't have information"
    )
    assert result.score == 1.0
    assert result.details["is_unanswerable_query"] is True


def test_answer_relevancy_zero_for_empty_answer() -> None:
    judge = _FakeJudge({"score": 0.0})  # not even called
    result = answer_relevancy(judge=judge, question="q?", answer="   ")
    assert result.score == 0.0


def test_answer_relevancy_returns_none_on_invalid_score() -> None:
    judge = _FakeJudge({"score": "not a number"})
    result = answer_relevancy(judge=judge, question="q?", answer="ans")
    assert result.score is None


def test_answer_relevancy_returns_none_on_out_of_range_score() -> None:
    judge = _FakeJudge({"score": 1.5})
    result = answer_relevancy(judge=judge, question="q?", answer="ans")
    assert result.score is None


def test_answer_relevancy_returns_none_on_judge_error() -> None:
    judge = _FakeJudge(JudgeError("api crashed"))
    result = answer_relevancy(judge=judge, question="q?", answer="ans")
    assert result.score is None