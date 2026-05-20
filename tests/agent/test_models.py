"""Tests for :mod:`elh_rag.agent._models`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from elh_rag.agent._models import AgentResponse, ConversationTurn, ToolCall

# Fixtures


@pytest.fixture
def sample_tool_call() -> ToolCall:
    return ToolCall(
        hop_index=0,
        name="find_rooms",
        input_json='{"city": "Lisbon", "top_k": 5}',
        output_json='{"hits": []}',
        error=None,
        duration_ms=240,
        started_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_response(sample_tool_call: ToolCall) -> AgentResponse:
    return AgentResponse(
        query="Find me a room in Lisbon",
        final_message="I found 3 rooms in Lisbon.",
        stop_reason="end_turn",
        hop_count=2,
        tool_trace=[sample_tool_call],
        input_tokens=500,
        output_tokens=120,
        total_duration_ms=2400,
        started_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC),
    )


# ToolCall


class TestToolCall:
    def test_minimal_construction(self) -> None:
        tc = ToolCall(
            hop_index=0,
            name="x",
            input_json="{}",
            duration_ms=0,
            started_at=datetime.now(UTC),
        )
        assert tc.output_json is None
        assert tc.error is None

    def test_frozen(self, sample_tool_call: ToolCall) -> None:
        with pytest.raises(ValidationError):
            sample_tool_call.name = "other"  # type: ignore[misc]

    def test_hop_index_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolCall(
                hop_index=-1,
                name="x",
                input_json="{}",
                duration_ms=0,
                started_at=datetime.now(UTC),
            )

    def test_duration_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolCall(
                hop_index=0,
                name="x",
                input_json="{}",
                duration_ms=-1,
                started_at=datetime.now(UTC),
            )


# AgentResponse


class TestAgentResponse:
    def test_basic_construction(self, sample_response: AgentResponse) -> None:
        assert sample_response.query == "Find me a room in Lisbon"
        assert sample_response.stop_reason == "end_turn"
        assert len(sample_response.tool_trace) == 1

    def test_empty_tool_trace_allowed(self) -> None:
        r = AgentResponse(
            query="hi",
            final_message="Hello!",
            stop_reason="end_turn",
            hop_count=1,
            input_tokens=10,
            output_tokens=5,
            total_duration_ms=100,
            started_at=datetime.now(UTC),
        )
        assert r.tool_trace == []

    def test_frozen(self, sample_response: AgentResponse) -> None:
        with pytest.raises(ValidationError):
            sample_response.final_message = "other"  # type: ignore[misc]

    def test_invalid_stop_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentResponse(
                query="hi",
                final_message="",
                stop_reason="nonsense",  # type: ignore[arg-type]
                hop_count=1,
                input_tokens=0,
                output_tokens=0,
                total_duration_ms=0,
                started_at=datetime.now(UTC),
            )


# View methods


class TestViews:
    def test_to_user_dict_excludes_trace(self, sample_response: AgentResponse) -> None:
        d = sample_response.to_user_dict()
        assert "tool_trace" not in d
        assert d["answer"] == "I found 3 rooms in Lisbon."
        assert d["stop_reason"] == "end_turn"
        assert d["hop_count"] == 2
        assert d["tools_used"] == ["find_rooms"]
        assert d["duration_ms"] == 2400

    def test_to_full_dict_includes_trace(self, sample_response: AgentResponse) -> None:
        d = sample_response.to_full_dict()
        assert "tool_trace" in d
        assert len(d["tool_trace"]) == 1
        assert d["tool_trace"][0]["name"] == "find_rooms"
        assert d["query"] == "Find me a room in Lisbon"
        assert d["input_tokens"] == 500

    def test_to_full_dict_is_json_serialisable(self, sample_response: AgentResponse) -> None:
        """to_full_dict uses mode='json' so datetime is ISO-string, not datetime obj."""
        import json

        d = sample_response.to_full_dict()
        # Round-trip through json without errors.
        s = json.dumps(d)
        assert "2026-05-14" in s


# ConversationTurn


class TestConversationTurn:
    """Verify the conversation-turn input model."""

    def test_construction(self) -> None:
        t = ConversationTurn(role="user", content="hello")
        assert t.role == "user"
        assert t.content == "hello"

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConversationTurn(role="system", content="hi")  # type: ignore[arg-type]

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConversationTurn(role="user", content="")
