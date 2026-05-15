"""Tests for :mod:`elh_rag.agent.agent_prompt`."""

from __future__ import annotations

from elh_rag.agent.agent_prompt import SYSTEM_PROMPT

# Tool names that should appear (at least once) in SYSTEM_PROMPT
# so the LLM is told they exist.
_EXPECTED_TOOL_MENTIONS = {
    "find_rooms",
    "find_available_rooms",
    "compute_total_cost",
    "get_property_details",
    "get_booking_stats",
    "answer_policy_question",
    "search_descriptions",
    "search_reviews",
}


# Languages that the few-shot examples should cover.
_EXPECTED_LANGUAGE_HINTS = {
    "English",
    "Italian",
    "Portuguese",
    "Spanish",
    "German",
    "French",
}


class TestSystemPromptShape:
    def test_is_non_empty_string(self) -> None:
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 1000  # non-trivial content

    def test_mentions_every_tool(self) -> None:
        """All 8 tools must be named in the prompt so the model knows them."""
        missing = {tool for tool in _EXPECTED_TOOL_MENTIONS if tool not in SYSTEM_PROMPT}
        assert not missing, f"prompt does not mention: {missing}"

    def test_covers_six_languages_in_examples(self) -> None:
        """Few-shot examples must touch all six target languages."""
        missing = {lang for lang in _EXPECTED_LANGUAGE_HINTS if lang not in SYSTEM_PROMPT}
        assert not missing, f"prompt does not cover: {missing}"

    def test_contains_routing_rules_section(self) -> None:
        assert "ROUTING RULES" in SYSTEM_PROMPT

    def test_contains_examples_section(self) -> None:
        assert "EXAMPLES" in SYSTEM_PROMPT

    def test_contains_error_handling_section(self) -> None:
        assert "ERROR HANDLING" in SYSTEM_PROMPT
