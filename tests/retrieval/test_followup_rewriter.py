"""Tests for the FollowUpRewriter."""

from __future__ import annotations

from elh_rag.generation.llm_client import LLMClient
from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.retrieval.followup_rewriter import (
    FollowUpRewriter,
    _clean_output,
    _format_history,
    _rewrite_cached,
)
from elh_rag.schemas import ConversationTurn

# Fake LLM


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


def _memory_with(turns: list[tuple[str, str]]) -> ConversationMemory:
    mem = ConversationMemory(max_turns=10)
    for q, a in turns:
        mem.append(q, a)
    return mem


# Empty / no-op paths


def test_no_memory_returns_question_unchanged() -> None:
    rewriter = FollowUpRewriter(llm_client=_FakeLLM(canned_output="should-not-be-used"))

    result = rewriter.rewrite(question="cheap house in Lisbon", memory=None)

    assert result == "cheap house in Lisbon"


def test_empty_memory_returns_question_unchanged() -> None:
    fake = _FakeLLM(canned_output="should-not-be-used")
    rewriter = FollowUpRewriter(llm_client=fake)

    result = rewriter.rewrite(
        question="cheap house in Lisbon",
        memory=ConversationMemory(),
    )

    assert result == "cheap house in Lisbon"
    assert fake.calls == []


def test_blank_question_returns_unchanged() -> None:
    fake = _FakeLLM(canned_output="something")
    rewriter = FollowUpRewriter(llm_client=fake)

    assert rewriter.rewrite(question="   ", memory=_memory_with([("q", "a")])) == "   "
    assert fake.calls == []


# Five canonical follow-up sequences


def test_sequence_1_city_swap_en() -> None:
    fake = _FakeLLM(canned_output="cheap house in Porto")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with(
        [("cheap house in Lisbon", "Residencia Campo de Ourique offers €350/month.")]
    )

    result = rewriter.rewrite("and in Porto?", memory=memory)

    assert result == "cheap house in Porto"
    assert len(fake.calls) == 1
    # The prompt must include the previous turn so the LLM can resolve "Porto"
    assert "Lisbon" in fake.calls[0]["user"]


def test_sequence_2_property_swap_en() -> None:
    fake = _FakeLLM(canned_output="Review of Bright Apartment")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("Review of Casa Verde", "Casa Verde is rated 4.5/5...")])

    result = rewriter.rewrite("And for Bright Apartment?", memory=memory)

    assert result == "Review of Bright Apartment"


def test_sequence_3_constraint_addition() -> None:
    fake = _FakeLLM(canned_output="rooms with balcony under 400 euros")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with(
        [("rooms with balcony", "Found 12 rooms with balconies in Lisbon and Porto.")]
    )

    result = rewriter.rewrite("only the ones under 400 euros?", memory=memory)

    assert result == "rooms with balcony under 400 euros"


def test_sequence_4_city_filter_it() -> None:
    """Italian follow-up adding city constraint."""
    fake = _FakeLLM(canned_output="studenti che si sono lamentati del proprietario a Lisbona")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with(
        [
            (
                "studenti che si sono lamentati del proprietario",
                "Diversi studenti hanno menzionato problemi con la comunicazione...",
            )
        ]
    )

    result = rewriter.rewrite("solo a Lisbona?", memory=memory)

    assert "Lisbona" in result
    assert "proprietario" in result


def test_sequence_5_attribute_filter() -> None:
    fake = _FakeLLM(canned_output="houses near university with 2 bedrooms")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with(
        [("houses near university", "Top picks: Bright Apartment Ramalde, Cosy Home Porto...")]
    )

    result = rewriter.rewrite("Show me 2-bedroom ones", memory=memory)

    assert "2" in result
    assert "university" in result.lower() or "near" in result.lower()


# Edge cases


def test_standalone_question_returned_unchanged_by_llm() -> None:
    """If the LLM (correctly) returns the question unchanged, we propagate it."""
    fake = _FakeLLM(canned_output="cheapest apartment in Porto")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("hello", "Hi! How can I help?")])

    result = rewriter.rewrite("cheapest apartment in Porto", memory=memory)

    assert result == "cheapest apartment in Porto"


def test_llm_exception_falls_back_to_original_question() -> None:
    fake = _FakeLLM(raise_exc=RuntimeError("api unavailable"))
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("cheap house Lisbon", "Found 3 options...")])

    result = rewriter.rewrite("and in Porto?", memory=memory)

    assert result == "and in Porto?"


def test_empty_llm_output_falls_back_to_original_question() -> None:
    fake = _FakeLLM(canned_output="   ")  # whitespace only
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("q", "a")])

    result = rewriter.rewrite("follow up?", memory=memory)

    assert result == "follow up?"


def test_quoted_llm_output_is_unquoted() -> None:
    fake = _FakeLLM(canned_output='"cheap house in Porto"')
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("cheap house Lisbon", "Found 3 options...")])

    result = rewriter.rewrite("and in Porto?", memory=memory)

    assert result == "cheap house in Porto"


# Helpers


def test_clean_output_strips_double_quotes() -> None:
    assert _clean_output('"hello"') == "hello"


def test_clean_output_strips_single_quotes() -> None:
    assert _clean_output("'hello'") == "hello"


def test_clean_output_returns_empty_on_empty() -> None:
    assert _clean_output("") == ""
    assert _clean_output("   ") == ""


def test_format_history_truncates_long_answers() -> None:
    long_answer = "x" * 1000
    turns = [ConversationTurn(question="q", answer=long_answer)]
    lines = _format_history(turns)

    answer_line = next(line for line in lines if line.startswith("Turn 1 assistant"))
    assert len(answer_line) < 400  # well under the 1000-char raw answer
    assert answer_line.endswith("…")


def test_format_history_skips_blank_fields() -> None:
    turns = [
        ConversationTurn(question="q1", answer=""),
        ConversationTurn(question="", answer="a2"),
    ]
    lines = _format_history(turns)
    # Only the non-empty fields render
    assert any("q1" in line for line in lines)
    assert any("a2" in line for line in lines)
    assert len(lines) == 2  # not 4


# Cache behaviour


def test_repeated_identical_calls_use_cache() -> None:
    """Same memory + same question should call the LLM only once."""
    fake = _FakeLLM(canned_output="cheap house in Porto")
    rewriter = FollowUpRewriter(llm_client=fake)
    memory = _memory_with([("cheap house Lisbon", "...")])

    # Clear lru_cache from any prior test pollution
    _rewrite_cached.cache_clear()

    rewriter.rewrite("and in Porto?", memory=memory)
    rewriter.rewrite("and in Porto?", memory=memory)

    assert len(fake.calls) == 1
