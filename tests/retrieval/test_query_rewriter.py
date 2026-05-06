"""Tests for the QueryRewriter component"""

from __future__ import annotations

import pytest
from tests.conftest import FakeLLMClient

from elh_rag.retrieval.query_rewriter import QueryRewriter

# Output cleaning


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("quiet room for studying", "quiet room for studying"),
        ("  quiet room  ", "quiet room"),
        ('"quiet room"', "quiet room"),
        ("'quiet room'", "quiet room"),
        ("Rewritten search query: quiet room", "quiet room"),
        ("Rewritten query: quiet room", "quiet room"),
        ("Query: quiet room", "quiet room"),
        ("REWRITTEN QUERY: quiet room", "quiet room"),
    ],
)
def test_clean_output_strips_noise(raw: str, expected: str) -> None:
    assert QueryRewriter._clean_output(raw) == expected


# Core rewriting behaviour


def test_rewrite_returns_llm_output_for_non_empty_input() -> None:
    fake = FakeLLMClient(canned_response="quiet room for studying, peaceful")
    rewriter = QueryRewriter(llm_client=fake)

    result = rewriter.rewrite("I need a quiet place where I can study")

    assert result == "quiet room for studying, peaceful"
    assert len(fake.calls) == 1


def test_rewrite_returns_original_on_empty_input() -> None:
    fake = FakeLLMClient(canned_response="should not be called")
    rewriter = QueryRewriter(llm_client=fake)

    assert rewriter.rewrite("") == ""
    assert rewriter.rewrite("   ") == ""
    assert fake.calls == []


def test_rewrite_falls_back_to_original_on_llm_exception() -> None:
    class BrokenLLM(FakeLLMClient):
        def complete(self, system: str, user: str) -> str:
            raise RuntimeError("API down")

    rewriter = QueryRewriter(llm_client=BrokenLLM())

    assert rewriter.rewrite("quiet room") == "quiet room"


def test_rewrite_falls_back_when_llm_returns_empty() -> None:
    fake = FakeLLMClient(canned_response="   ")
    rewriter = QueryRewriter(llm_client=fake)

    assert rewriter.rewrite("quiet room") == "quiet room"


# Cache behaviour


def test_repeated_queries_hit_the_cache() -> None:
    fake = FakeLLMClient(canned_response="rewritten version")
    rewriter = QueryRewriter(llm_client=fake)

    rewriter.rewrite("same question")
    rewriter.rewrite("same question")
    rewriter.rewrite("same question")

    assert len(fake.calls) == 1


def test_different_queries_each_call_the_llm() -> None:
    fake = FakeLLMClient(canned_response="rewritten")
    rewriter = QueryRewriter(llm_client=fake)

    rewriter.rewrite("first question")
    rewriter.rewrite("second question")

    assert len(fake.calls) == 2


# Prompt contract


def test_rewriter_sends_system_and_user_prompts() -> None:
    fake = FakeLLMClient(canned_response="output")
    rewriter = QueryRewriter(llm_client=fake)

    rewriter.rewrite("comfortable bed in Lisbon")

    call = fake.calls[0]
    assert "query rewriter" in call["system"].lower()
    assert "comfortable bed in Lisbon" in call["user"]
