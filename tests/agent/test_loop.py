"""Tests for :func:`elh_rag.agent.loop.run_agent_turn`."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from elh_rag.agent._models import ToolCall
from elh_rag.agent.agent_llm_client import StreamChunk
from elh_rag.agent.loop import InputValidationError, run_agent_turn
from elh_rag.tools.errors import ToolExecutionError, ToolValidationError

# Helpers for building fake LLM responses


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(block_id: str, name: str, tool_input: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def _usage(input_tokens: int, output_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _end_turn_message(text: str, in_tok: int = 100, out_tok: int = 20) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[_text_block(text)],
        usage=_usage(in_tok, out_tok),
    )


def _tool_use_message(
    tool_calls: list[tuple[str, str, dict[str, Any]]],
    leading_text: str = "",
    in_tok: int = 100,
    out_tok: int = 30,
) -> SimpleNamespace:
    """Build a tool_use response with N tool_use blocks.

    Args:
        tool_calls: list of (block_id, tool_name, tool_input) tuples.
        leading_text: optional text block before the tool_use blocks.
    """
    content: list[SimpleNamespace] = []
    if leading_text:
        content.append(_text_block(leading_text))
    for block_id, name, tool_input in tool_calls:
        content.append(_tool_use_block(block_id, name, tool_input))
    return SimpleNamespace(
        stop_reason="tool_use",
        content=content,
        usage=_usage(in_tok, out_tok),
    )


# Fixtures


@pytest.fixture
def mock_ctx() -> Any:
    """Stand-in AgentContext; the real shape doesn't matter since execute_tool is patched."""
    return MagicMock(name="AgentContext")


@pytest.fixture
def mock_llm() -> MagicMock:
    return MagicMock(name="AgentLLMClient")


# Input validation


class TestInputValidation:
    def test_empty_query_rejected(self, mock_ctx: Any, mock_llm: MagicMock) -> None:
        with pytest.raises(InputValidationError):
            run_agent_turn("", mock_ctx, llm=mock_llm)

    def test_whitespace_only_query_rejected(self, mock_ctx: Any, mock_llm: MagicMock) -> None:
        with pytest.raises(InputValidationError):
            run_agent_turn("   \n  ", mock_ctx, llm=mock_llm)

    def test_too_long_query_rejected(
        self, mock_ctx: Any, mock_llm: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("elh_rag.agent.loop.settings.agent_max_query_chars", 10)
        with pytest.raises(InputValidationError):
            run_agent_turn("x" * 11, mock_ctx, llm=mock_llm)


# Happy path


class TestHappyPath:
    def test_simple_end_turn_no_tools(self, mock_ctx: Any, mock_llm: MagicMock) -> None:
        """LLM responds with end_turn on first call, no tool dispatch."""
        mock_llm.call.return_value = _end_turn_message("Hello world!")

        response = run_agent_turn("Hi", mock_ctx, llm=mock_llm)

        assert response.stop_reason == "end_turn"
        assert response.hop_count == 1
        assert response.final_message == "Hello world!"
        assert response.tool_trace == []
        assert response.input_tokens == 100
        assert response.output_tokens == 20
        assert mock_llm.call.call_count == 1

    def test_single_tool_call(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LLM calls 1 tool, then returns end_turn."""
        mock_output = MagicMock()
        mock_output.model_dump_json.return_value = '{"hits": [{"text": "room"}]}'
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_output)

        mock_llm.call.side_effect = [
            _tool_use_message([("tool_1", "find_rooms", {"city": "Lisbon"})]),
            _end_turn_message("Found 1 room."),
        ]

        response = run_agent_turn("Find rooms in Lisbon", mock_ctx, llm=mock_llm)

        assert response.stop_reason == "end_turn"
        assert response.hop_count == 2
        assert response.final_message == "Found 1 room."
        assert len(response.tool_trace) == 1
        call = response.tool_trace[0]
        assert call.name == "find_rooms"
        assert call.hop_index == 0
        assert call.output_json == '{"hits": [{"text": "room"}]}'
        assert call.error is None
        assert mock_llm.call.call_count == 2

    def test_multi_hop_with_two_tools(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LLM calls 2 tools across 2 hops, then end_turn."""
        outputs = [
            MagicMock(model_dump_json=lambda: '{"room_id": 42}'),
            MagicMock(model_dump_json=lambda: '{"total": 4200}'),
        ]
        outputs_iter = iter(outputs)
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: next(outputs_iter))

        mock_llm.call.side_effect = [
            _tool_use_message([("tool_1", "find_rooms", {"city": "Lisbon"})]),
            _tool_use_message([("tool_2", "compute_total_cost", {"room_id": 42})]),
            _end_turn_message("Total cost: 4200 EUR."),
        ]

        response = run_agent_turn(
            "Find cheapest in Lisbon and compute cost", mock_ctx, llm=mock_llm
        )

        assert response.hop_count == 3
        assert response.stop_reason == "end_turn"
        assert [t.name for t in response.tool_trace] == ["find_rooms", "compute_total_cost"]
        assert [t.hop_index for t in response.tool_trace] == [0, 1]

    def test_token_counts_aggregated_across_hops(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_out = MagicMock(model_dump_json=lambda: "{}")
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_out)

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {})], in_tok=200, out_tok=50),
            _end_turn_message("done", in_tok=300, out_tok=80),
        ]

        response = run_agent_turn("q", mock_ctx, llm=mock_llm)

        assert response.input_tokens == 500
        assert response.output_tokens == 130


# Error pass-through


class TestErrorPassThrough:
    def test_tool_execution_error_pass_through(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A ToolExecutionError becomes a tool_result with is_error=True."""

        def _raising(*a, **kw):
            raise ToolExecutionError("find_rooms", message="DB connection lost")

        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", _raising)

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {"city": "Lisbon"})]),
            _end_turn_message("I cannot search rooms right now."),
        ]

        response = run_agent_turn("Find rooms", mock_ctx, llm=mock_llm)

        assert response.stop_reason == "end_turn"
        assert len(response.tool_trace) == 1
        call = response.tool_trace[0]
        assert call.error is not None
        assert "DB connection lost" in call.error
        assert call.output_json is None

    def test_tool_validation_error_pass_through(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ToolValidationError handled the same as ToolExecutionError."""

        def _raising(*a, **kw):
            raise ToolValidationError("find_rooms", ValueError("bad input"))

        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", _raising)

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {"bad": "input"})]),
            _end_turn_message("Input was invalid; please rephrase."),
        ]

        response = run_agent_turn("Find rooms", mock_ctx, llm=mock_llm)

        assert response.tool_trace[0].error is not None


# max_hops_reached


class TestMaxHopsReached:
    def test_max_hops_exhausted(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If the LLM keeps asking for tools, the loop stops at max_hops."""
        monkeypatch.setattr("elh_rag.agent.loop.settings.agent_max_hops", 3)

        mock_out = MagicMock(model_dump_json=lambda: "{}")
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_out)

        mock_llm.call.return_value = _tool_use_message(
            [("t", "find_rooms", {})], leading_text="thinking..."
        )

        response = run_agent_turn("q", mock_ctx, llm=mock_llm)

        assert response.stop_reason == "max_hops_reached"
        assert response.hop_count == 3
        assert len(response.tool_trace) == 3


# Streaming callbacks


class TestStreaming:
    def test_on_text_callback_invoked(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
    ) -> None:
        """When on_text is given, the loop uses .stream() and forwards text deltas."""
        final_msg = _end_turn_message("Hello world!")

        def _fake_stream(**_: Any) -> Iterator[StreamChunk]:
            yield StreamChunk(text_delta="Hello")
            yield StreamChunk(text_delta=" world!")
            yield StreamChunk(final_message=final_msg)

        mock_llm.stream.side_effect = lambda **kw: _fake_stream(**kw)

        captured: list[str] = []
        response = run_agent_turn(
            "Hi", mock_ctx, llm=mock_llm, on_text=lambda t: captured.append(t)
        )

        assert captured == ["Hello", " world!"]
        assert response.final_message == "Hello world!"
        mock_llm.stream.assert_called_once()
        mock_llm.call.assert_not_called()

    def test_on_tool_call_callback_invoked(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """on_tool_call fires once per dispatched tool."""
        mock_out = MagicMock(model_dump_json=lambda: "{}")
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_out)

        mock_llm.call.side_effect = [
            _tool_use_message([("t", "find_rooms", {"city": "Lisbon"})]),
            _end_turn_message("done"),
        ]

        captured: list[ToolCall] = []
        run_agent_turn("q", mock_ctx, llm=mock_llm, on_tool_call=lambda tc: captured.append(tc))

        assert len(captured) == 1
        assert captured[0].name == "find_rooms"
        mock_llm.call.assert_called()
        mock_llm.stream.assert_not_called()


# Ctx resolution (Step 3.5 fix)


class TestCtxResolution:
    """Verify that the loop reads spec.ctx_attr and passes the right sub-context."""

    def test_db_tool_receives_db_subctx(
        self,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A tool registered with ctx_attr='db' receives ctx.db, not the full AgentContext."""
        # AgentContext is already populated with the 8 real tools via side-effect
        # imports in elh_rag.agent.__init__; find_rooms has ctx_attr="db".
        captured_ctx: dict[str, Any] = {}

        def _spy_execute_tool(name: str, payload: Any, ctx: Any = None) -> Any:
            captured_ctx["ctx"] = ctx
            return MagicMock(model_dump_json=lambda: "{}")

        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", _spy_execute_tool)

        agent_ctx = SimpleNamespace(
            db="DB_SENTINEL",
            kb="KB_SENTINEL",
            embedder=None,
            descriptions_store=None,
            reviews_store=None,
        )

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {"city": "Lisbon"})]),
            _end_turn_message("done"),
        ]

        run_agent_turn("q", agent_ctx, llm=mock_llm)  # type: ignore[arg-type]

        assert captured_ctx["ctx"] == "DB_SENTINEL"

    def test_kb_tool_receives_kb_subctx(
        self,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """answer_policy_question (ctx_attr='kb') receives ctx.kb."""
        captured_ctx: dict[str, Any] = {}

        def _spy_execute_tool(name: str, payload: Any, ctx: Any = None) -> Any:
            captured_ctx["ctx"] = ctx
            return MagicMock(model_dump_json=lambda: "{}")

        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", _spy_execute_tool)

        agent_ctx = SimpleNamespace(
            db="DB_SENTINEL",
            kb="KB_SENTINEL",
            embedder=None,
            descriptions_store=None,
            reviews_store=None,
        )

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "answer_policy_question", {"question": "How?"})]),
            _end_turn_message("done"),
        ]

        run_agent_turn("q", agent_ctx, llm=mock_llm)  # type: ignore[arg-type]

        assert captured_ctx["ctx"] == "KB_SENTINEL"

    def test_rag_tool_receives_full_agent_ctx(
        self,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RAG corpora tools (ctx_attr=None) receive the full AgentContext."""
        captured_ctx: dict[str, Any] = {}

        def _spy_execute_tool(name: str, payload: Any, ctx: Any = None) -> Any:
            captured_ctx["ctx"] = ctx
            return MagicMock(model_dump_json=lambda: "{}")

        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", _spy_execute_tool)

        agent_ctx = SimpleNamespace(
            db="DB_SENTINEL",
            kb="KB_SENTINEL",
            embedder=None,
            descriptions_store=None,
            reviews_store=None,
        )

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "search_descriptions", {"query": "test"})]),
            _end_turn_message("done"),
        ]

        run_agent_turn("q", agent_ctx, llm=mock_llm)  # type: ignore[arg-type]

        assert captured_ctx["ctx"] is agent_ctx


# Model split (Sonnet hop 0, Haiku hop 1+)


class TestModelSplit:
    """Verify hop 0 uses primary, hop >= 1 uses synthesis (when enabled)."""

    def test_hop_0_uses_primary_client(self, mock_ctx: Any) -> None:
        """Hop 0 dispatches to the primary client even when synthesis is provided."""
        primary = MagicMock(name="primary")
        synthesis = MagicMock(name="synthesis")
        primary._model = "sonnet-test"
        synthesis._model = "haiku-test"
        # Primary returns end_turn at hop 0; synthesis should never be called.
        primary.call.return_value = _end_turn_message("Hello!")

        response = run_agent_turn("Hi", mock_ctx, llm=primary, synthesis_llm=synthesis)

        primary.call.assert_called_once()
        synthesis.call.assert_not_called()
        assert response.hop_count == 1
        assert response.final_message == "Hello!"

    def test_hop_1_uses_synthesis_client(
        self,
        mock_ctx: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Hop 0 routes a tool, hop 1 uses synthesis client to write the final text."""
        primary = MagicMock(name="primary")
        synthesis = MagicMock(name="synthesis")
        primary._model = "sonnet-test"
        synthesis._model = "haiku-test"

        primary.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {"city": "Lisbon"})]),
        ]
        synthesis.call.side_effect = [
            _end_turn_message("Here are 3 rooms in Lisbon."),
        ]

        mock_output = MagicMock(model_dump_json=lambda: "{}")
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_output)

        response = run_agent_turn(
            "Find rooms in Lisbon", mock_ctx, llm=primary, synthesis_llm=synthesis
        )

        primary.call.assert_called_once()  # hop 0 only
        synthesis.call.assert_called_once()  # hop 1 only
        assert response.hop_count == 2
        assert response.final_message == "Here are 3 rooms in Lisbon."

    def test_synthesis_none_falls_back_to_primary(
        self,
        mock_ctx: Any,
        mock_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When synthesis_llm is None and llm is explicitly given, primary handles all hops."""
        mock_output = MagicMock(model_dump_json=lambda: "{}")
        monkeypatch.setattr("elh_rag.agent.loop.execute_tool", lambda *a, **kw: mock_output)

        mock_llm.call.side_effect = [
            _tool_use_message([("t1", "find_rooms", {})]),
            _end_turn_message("done"),
        ]

        # synthesis_llm not provided -> primary used for all hops
        response = run_agent_turn("q", mock_ctx, llm=mock_llm)

        assert mock_llm.call.call_count == 2  # both hops used the same mock
        assert response.hop_count == 2
