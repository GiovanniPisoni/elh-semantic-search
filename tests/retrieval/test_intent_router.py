"""Tests for the IntentRouter."""

from __future__ import annotations

from typing import Any

import pytest

from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import INTENT_ROUTER_SYSTEM_PROMPT
from elh_rag.retrieval.intent_router import (
    _DESCRIPTIONS_KEYWORDS,
    _REVIEWS_KEYWORDS,
    IntentRouter,
    _extract_json,
    _keyword_fallback,
    _parse_confidence,
    _parse_intent,
)
from elh_rag.schemas import Intent, RoutingDecision

# Fake LLMClient


class _FakeLLM(LLMClient):
    """LLMClient that returns canned output or raises, without network calls."""

    def __init__(
        self,
        canned_output: str | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._canned = canned_output
        self._raise = raise_exc
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if self._raise is not None:
            raise self._raise
        return self._canned or ""


def _make_router(
    llm_output: str | None = None,
    raise_exc: Exception | None = None,
    threshold: float = 0.8,
) -> IntentRouter:
    fake = _FakeLLM(canned_output=llm_output, raise_exc=raise_exc)
    return IntentRouter(llm_client=fake, confidence_threshold=threshold)


# _extract_json helper


def test_extract_json_on_clean_output() -> None:
    raw = '{"intent": "reviews", "confidence": 0.9, "reasoning": "ok"}'
    assert _extract_json(raw) == {
        "intent": "reviews",
        "confidence": 0.9,
        "reasoning": "ok",
    }


def test_extract_json_strips_markdown_fences() -> None:
    raw = '```json\n{"intent": "both", "confidence": 0.5}\n```'
    assert _extract_json(raw) == {"intent": "both", "confidence": 0.5}


def test_extract_json_finds_object_inside_preamble() -> None:
    raw = 'Here is the classification:\n{"intent": "descriptions", "confidence": 0.8}'
    assert _extract_json(raw) == {"intent": "descriptions", "confidence": 0.8}


def test_extract_json_returns_none_on_invalid_input() -> None:
    assert _extract_json("") is None
    assert _extract_json("not json at all") is None
    assert _extract_json("{invalid json}") is None


# _parse_intent helper


@pytest.mark.parametrize(
    "value,expected",
    [
        ("reviews", Intent.REVIEWS),
        ("REVIEWS", Intent.REVIEWS),
        ("  Descriptions  ", Intent.DESCRIPTIONS),
        ("both", Intent.BOTH),
    ],
)
def test_parse_intent_accepts_valid_strings(value: str, expected: Intent) -> None:
    assert _parse_intent(value) == expected


@pytest.mark.parametrize("value", ["invalid", "", None, 123])
def test_parse_intent_rejects_invalid_values(value: Any) -> None:
    assert _parse_intent(value) is None


# _parse_confidence helper


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, 0.5),
        (1.0, 1.0),
        (0.0, 0.0),
        ("0.7", 0.7),
        (1.5, 1.0),
        (-0.3, 0.0),
        (None, 0.0),
        ("not a number", 0.0),
    ],
)
def test_parse_confidence_clamps_to_unit_range(value: Any, expected: float) -> None:
    assert _parse_confidence(value) == expected


# Keyword fallback


def test_keyword_fallback_routes_to_reviews_on_review_keywords() -> None:
    decision = _keyword_fallback("how did students feel about the landlord?")
    assert decision.intent == Intent.REVIEWS
    assert decision.source == "keyword"
    assert 0.0 <= decision.confidence <= 1.0


def test_keyword_fallback_routes_to_descriptions_on_description_keywords() -> None:
    decision = _keyword_fallback("what is the WiFi speed in Mbps?")
    assert decision.intent == Intent.DESCRIPTIONS
    assert decision.source == "keyword"


def test_keyword_fallback_routes_to_both_on_ambiguous_query() -> None:
    decision = _keyword_fallback("tell me about Porto")
    assert decision.intent == Intent.BOTH
    assert decision.source == "keyword"


def test_keyword_fallback_prefers_both_when_both_kinds_of_keywords_are_present() -> None:
    """If a query mixes review-style + description-style keywords, play it safe."""
    decision = _keyword_fallback("what is the price and how did students feel about the landlord")
    assert decision.intent == Intent.BOTH


# Happy path: LLM returns well-formed JSON


def test_router_routes_to_reviews_with_high_confidence() -> None:
    raw = '{"intent": "reviews", "confidence": 0.92, "reasoning": "about experience"}'
    router = _make_router(llm_output=raw)

    decision = router.route("did students feel safe at night?")

    assert decision.intent == Intent.REVIEWS
    assert decision.confidence == 0.92
    assert decision.source == "llm"
    assert "experience" in decision.reasoning.lower()


def test_router_routes_to_descriptions_with_high_confidence() -> None:
    raw = '{"intent": "descriptions", "confidence": 0.9, "reasoning": "factual query"}'
    router = _make_router(llm_output=raw)

    decision = router.route("how many bathrooms does the apartment have?")

    assert decision.intent == Intent.DESCRIPTIONS
    assert decision.confidence == 0.9
    assert decision.source == "llm"


def test_router_routes_to_both_directly_when_llm_says_so() -> None:
    raw = '{"intent": "both", "confidence": 0.7, "reasoning": "mixed query"}'
    router = _make_router(llm_output=raw, threshold=0.8)

    decision = router.route("tell me about the apartment and how students liked it")

    assert decision.intent == Intent.BOTH
    assert decision.source == "llm"


# Low-confidence escalation to both


def test_low_confidence_single_corpus_escalates_to_both() -> None:
    raw = '{"intent": "reviews", "confidence": 0.4, "reasoning": "unclear"}'
    router = _make_router(llm_output=raw, threshold=0.8)

    decision = router.route("some unclear query")

    assert decision.intent == Intent.BOTH
    assert decision.source == "llm"
    assert "escalated" in decision.reasoning.lower()


def test_high_confidence_single_corpus_is_not_escalated() -> None:
    raw = '{"intent": "descriptions", "confidence": 0.95, "reasoning": "clearly factual"}'
    router = _make_router(llm_output=raw, threshold=0.8)

    decision = router.route("what is the monthly price?")

    assert decision.intent == Intent.DESCRIPTIONS


def test_exact_threshold_confidence_is_accepted() -> None:
    raw = '{"intent": "reviews", "confidence": 0.8, "reasoning": "ok"}'
    router = _make_router(llm_output=raw, threshold=0.8)

    decision = router.route("any query")

    # At threshold, accept (>=)
    assert decision.intent == Intent.REVIEWS


# Error paths: LLM failure or malformed output


def test_router_uses_keyword_fallback_on_llm_exception() -> None:
    router = _make_router(raise_exc=RuntimeError("api down"))

    decision = router.route("landlord experience was great")

    assert decision.source == "keyword"
    assert decision.intent == Intent.REVIEWS


def test_router_uses_keyword_fallback_on_unparseable_json() -> None:
    router = _make_router(llm_output="this is not json")

    decision = router.route("price of a room")

    assert decision.source == "keyword"
    assert decision.intent == Intent.DESCRIPTIONS


def test_router_uses_keyword_fallback_on_unknown_intent_value() -> None:
    raw = '{"intent": "gibberish", "confidence": 0.9}'
    router = _make_router(llm_output=raw)

    decision = router.route("WiFi speed kitchen appliances")

    assert decision.source == "keyword"
    assert decision.intent == Intent.DESCRIPTIONS


# Edge cases


def test_empty_query_returns_default_both() -> None:
    router = _make_router(llm_output='{"intent": "reviews", "confidence": 1.0}')

    for empty in ["", "   ", "\n\t"]:
        decision = router.route(empty)
        assert decision.intent == Intent.BOTH
        assert decision.source == "default"
        assert decision.confidence == 0.0


def test_router_passes_system_and_user_prompts_to_llm() -> None:
    fake = _FakeLLM(canned_output='{"intent": "reviews", "confidence": 0.9}')
    router = IntentRouter(llm_client=fake, confidence_threshold=0.8)

    router.route("any query")

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "corpora" in call["system"].lower() or "corpus" in call["system"].lower()
    assert "any query" in call["user"]


# Cache behaviour


def test_repeated_queries_hit_the_cache() -> None:
    fake = _FakeLLM(canned_output='{"intent": "reviews", "confidence": 0.9}')
    router = IntentRouter(llm_client=fake, confidence_threshold=0.8)

    router.route("same query")
    router.route("same query")
    router.route("same query")

    assert len(fake.calls) == 1


def test_different_queries_each_call_the_llm() -> None:
    fake = _FakeLLM(canned_output='{"intent": "both", "confidence": 0.7}')
    router = IntentRouter(llm_client=fake, confidence_threshold=0.8)

    router.route("first query")
    router.route("second query")

    assert len(fake.calls) == 2


# RoutingDecision is immutable


def test_routing_decision_is_frozen() -> None:
    import dataclasses

    decision = RoutingDecision(intent=Intent.REVIEWS, confidence=0.9)
    try:
        decision.confidence = 0.5  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RoutingDecision should be frozen")


# Phase 2.5 light

# Structural sentinels


def test_router_prompt_contains_qualitative_modifiers_rule() -> None:
    """The QUALITATIVE MODIFIERS rule must stay in the system prompt."""
    assert "QUALITATIVE MODIFIERS rule" in INTENT_ROUTER_SYSTEM_PROMPT
    # Spot-check at least one sample modifier from each category so that
    # editing only some of them gets caught.
    for sample in ("fast", "quiet", "clean", "responsive", "warm"):
        assert sample in INTENT_ROUTER_SYSTEM_PROMPT, (
            f"modifier '{sample}' missing from QUALITATIVE MODIFIERS rule"
        )


def test_router_prompt_contains_non_leak_few_shot_examples() -> None:
    """The two few-shot Q/A examples must stay in the prompt."""
    assert "Reliable heating in a private room" in INTENT_ROUTER_SYSTEM_PROMPT
    assert "Clean kitchen with dishwasher" in INTENT_ROUTER_SYSTEM_PROMPT


# Behavioral documentation: keyword fallback diverges from LLM by design


def test_keyword_fallback_diverges_from_llm_for_q16_pattern() -> None:
    """q16-style query: 'flat in a quiet neighbourhood with a lift'.

    With the patched LLM router, this query routes to BOTH (the
    QUALITATIVE MODIFIERS rule recognises 'quiet' as subjective).

    With the keyword fallback (used when Anthropic API is down or
    returns malformed output), this query routes to REVIEWS instead,
    because the substring 'neighbour' inside 'neighbourhood' matches
    the reviews keyword list, and 'lift' is not in either list.

    This divergence is documented in docs/phase4_light_outcomes.md.
    If the fallback behavior changes — either through new keywords or
    through a richer fallback heuristic — this test will fail and the
    documentation must be updated.
    """
    decision = _keyword_fallback("flat in a quiet neighbourhood with a lift")
    assert decision.intent == Intent.REVIEWS
    assert decision.source == "keyword"


def test_keyword_fallback_diverges_from_llm_for_q17_pattern() -> None:
    """q17-style query: 'double room with fast wifi and washing machine'.

    With the patched LLM router, this query routes to BOTH (the
    QUALITATIVE MODIFIERS rule recognises 'fast' as subjective).

    With the keyword fallback, the query routes to DESCRIPTIONS,
    because 'wifi' and 'washing machine' are both description keywords
    and no review keyword matches.

    Same caveat as the q16 test: divergence is by design and documented.
    """
    decision = _keyword_fallback("double room with fast wifi and washing machine")
    assert decision.intent == Intent.DESCRIPTIONS
    assert decision.source == "keyword"


def test_qualitative_modifiers_are_not_in_keyword_lists() -> None:
    """The modifiers from the LLM rule must NOT leak into the keyword lists.

    The keyword fallback and the LLM router are two independent code
    paths. The LLM router uses the QUALITATIVE MODIFIERS rule from the
    prompt. The fallback uses a static keyword match. Mixing modifiers
    into the keyword lists would conflate the two abstractions and
    introduce confusing routing behavior.

    If in the future you want the fallback to also be modifier-aware,
    that is a deliberate design change — extend `_keyword_fallback`
    with its own modifier check, do NOT inject modifiers into the
    plain keyword tuples.
    """
    modifiers = ("fast", "quiet", "clean", "responsive", "reliable")
    for modifier in modifiers:
        assert modifier not in _REVIEWS_KEYWORDS, (
            f"'{modifier}' is a qualitative modifier, not a review keyword"
        )
        assert modifier not in _DESCRIPTIONS_KEYWORDS, (
            f"'{modifier}' is a qualitative modifier, not a description keyword"
        )
