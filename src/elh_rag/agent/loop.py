"""
Agent loop: LLM call -> tool dispatch -> LLM call -> ... -> final answer.

Top-level controller for a single agent turn, mirroring the
:class:`elh_rag.orchestration.orchestrator.Orchestrator` pattern but
LLM-driven (the model picks tools) rather than rule-driven.

Algorithm
---------
1. Validate query length (D6.4: hard cap at ``settings.agent_max_query_chars``).
2. Build the initial messages list: ``[{"role": "user", "content": query}]``.
3. Loop up to ``settings.agent_max_hops`` iterations:
       a. Call the LLM (streaming if any callback is provided,
          non-streaming otherwise).
       b. If ``stop_reason == "end_turn"`` (no tool use):
          assemble AgentResponse with stop_reason="end_turn" and exit.
       c. If ``stop_reason == "tool_use"``:
          - For each tool_use block, dispatch via
            :func:`elh_rag.tools.base.execute_tool`, after resolving
            the tool's preferred sub-context from AgentContext (see
            :func:`_resolve_tool_ctx`).
          - Catch ToolError subclasses; build a tool_result block
            with ``is_error=True`` and pass through to the model
            (D4.8 pass-through).
          - Append assistant message + tool_result blocks to messages.
          - Continue.
4. If MAX_HOPS exhausted without end_turn, assemble AgentResponse
   with stop_reason="max_hops_reached".

Tool ctx resolution
-------------------
Different tools expect different ``ctx`` shapes:
    Tools 1-5 (find_rooms, ...)     - DBExecutor
    Tool 6 (answer_policy_question) - KBContext
    RAG corpora wrappers            - full AgentContext

Each tool declares its preferred ctx via ``ctx_attr`` on its
:func:`register_tool` decorator. The loop reads this attribute and
passes the corresponding sub-context (via ``getattr(agent_ctx,
ctx_attr)``) to :func:`execute_tool`. When ``ctx_attr`` is ``None``
the full AgentContext is forwarded.

Streaming (D4.9)
----------------
Streaming is engaged on EVERY hop when ``on_text`` is provided.

Input length check (D6.4)
-------------------------
Queries longer than ``settings.agent_max_query_chars`` are rejected
with :class:`InputValidationError` BEFORE the first LLM call.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from elh_rag.agent._models import AgentResponse, ToolCall
from elh_rag.agent.agent_llm_client import AgentLLMClient
from elh_rag.agent.agent_prompt import SYSTEM_PROMPT
from elh_rag.agent.context import AgentContext
from elh_rag.agent.tool_registry import build_tool_schemas
from elh_rag.config import settings
from elh_rag.tools.base import TOOLS_REGISTRY, execute_tool
from elh_rag.tools.errors import ToolError

logger = logging.getLogger(__name__)


# Exceptions


class InputValidationError(ValueError):
    """Raised when the user query violates length or shape constraints."""


# Callback type aliases

OnTextCallback = Callable[[str], None]
"""Receives every text delta chunk as the model generates it."""

OnToolCallCallback = Callable[[ToolCall], None]
"""Receives each completed :class:`ToolCall` after dispatch."""


# Public API


def run_agent_turn(
    query: str,
    ctx: AgentContext,
    *,
    on_text: OnTextCallback | None = None,
    on_tool_call: OnToolCallCallback | None = None,
    llm: AgentLLMClient | None = None,
) -> AgentResponse:
    """Execute one agent turn end-to-end.

    Parameters
    ----------
    query
        Natural-language question from the user. Must be non-empty
        and <= ``settings.agent_max_query_chars`` characters.
    ctx
        Shared per-turn state: DB, KB, embedder, vector stores.
    on_text, optional
        Callback invoked with each text delta the model streams. When
        provided, the loop engages streaming on every LLM call.
    on_tool_call, optional
        Callback invoked once per dispatched tool with the completed
        ToolCall record (including output or error).
    llm, optional
        Override the default :class:`AgentLLMClient`. Used by tests.

    Returns
    -------
    AgentResponse
        Final answer + full tool trace + aggregate metrics.

    Raises
    ------
    InputValidationError
        If the query is empty or exceeds the configured length limit.
    """
    # 1. Input validation (D6.4)
    _validate_query(query)

    # 2. Setup
    started_at = datetime.now(UTC)
    start_perf = time.perf_counter()
    llm = llm or AgentLLMClient()
    tools = build_tool_schemas()
    streaming = on_text is not None

    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]
    tool_trace: list[ToolCall] = []
    input_tokens_total = 0
    output_tokens_total = 0
    final_message = ""
    stop_reason: str = "error"
    hop_index = 0

    # 3. Loop
    for hop_index in range(settings.agent_max_hops):
        logger.debug("agent.loop hop=%d, streaming=%s", hop_index, streaming)

        response = _call_llm(
            llm=llm,
            messages=messages,
            tools=tools,
            streaming=streaming,
            on_text=on_text,
        )

        # Accumulate token usage
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens_total += getattr(usage, "input_tokens", 0) or 0
            output_tokens_total += getattr(usage, "output_tokens", 0) or 0

        # End-turn: model has produced a final answer
        if response.stop_reason == "end_turn":
            final_message = _extract_text(response.content)
            stop_reason = "end_turn"
            break

        # Tool-use: dispatch each tool_use block
        if response.stop_reason == "tool_use":
            messages.append(
                {
                    "role": "assistant",
                    "content": _content_blocks_to_dicts(response.content),
                }
            )

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for block in tool_use_blocks:
                call_record, result_block = _dispatch_tool(
                    block=block, ctx=ctx, hop_index=hop_index
                )
                tool_trace.append(call_record)
                tool_results.append(result_block)
                if on_tool_call is not None:
                    on_tool_call(call_record)

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop_reason (e.g. "max_tokens")
        logger.warning(
            "agent.loop: unexpected stop_reason=%r at hop=%d", response.stop_reason, hop_index
        )
        final_message = _extract_text(response.content)
        stop_reason = "error"
        break
    else:
        # for-else: loop completed without break (max_hops reached)
        stop_reason = "max_hops_reached"
        final_message = _extract_text(response.content) if "response" in locals() else ""
        logger.warning("agent.loop: max_hops_reached (%d)", settings.agent_max_hops)

    total_duration_ms = int((time.perf_counter() - start_perf) * 1000)

    return AgentResponse(
        query=query,
        final_message=final_message,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        hop_count=hop_index + 1,
        tool_trace=tool_trace,
        input_tokens=input_tokens_total,
        output_tokens=output_tokens_total,
        total_duration_ms=total_duration_ms,
        started_at=started_at,
    )


# Helpers


def _validate_query(query: str) -> None:
    """D6.4 input validation: non-empty + length cap."""
    if not query or not query.strip():
        raise InputValidationError("Query must be a non-empty string.")
    if len(query) > settings.agent_max_query_chars:
        raise InputValidationError(
            f"Query length {len(query)} exceeds limit of "
            f"{settings.agent_max_query_chars} characters."
        )


def _call_llm(
    *,
    llm: AgentLLMClient,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    streaming: bool,
    on_text: OnTextCallback | None,
) -> Any:
    """One LLM step: either streaming (with text callback) or plain call.

    Returns the assembled Anthropic ``Message`` either way.
    """
    if streaming:
        final = None
        for chunk in llm.stream(messages=messages, tools=tools, system=SYSTEM_PROMPT):
            if chunk.text_delta is not None and on_text is not None:
                on_text(chunk.text_delta)
            if chunk.final_message is not None:
                final = chunk.final_message
        if final is None:
            raise RuntimeError("Streaming completed without a final_message chunk.")
        return final
    return llm.call(messages=messages, tools=tools, system=SYSTEM_PROMPT)


def _resolve_tool_ctx(tool_name: str, agent_ctx: AgentContext) -> Any:
    """Pull the sub-context that the named tool expects from AgentContext.

    Reads the tool's ``ctx_attr`` declaration from the registry:

        ctx_attr="db"   -> agent_ctx.db   (DBExecutor for Tools 1-5)
        ctx_attr="kb"   -> agent_ctx.kb   (KBContext for Tool 6)
        ctx_attr=None   -> agent_ctx      (RAG corpora; full context)

    If the tool is not registered the full AgentContext is returned;
    :func:`execute_tool` will then raise ``ToolNotFoundError`` which
    the loop handles as a pass-through error.
    """
    spec = TOOLS_REGISTRY.get(tool_name)
    if spec is None or spec.ctx_attr is None:
        return agent_ctx
    return getattr(agent_ctx, spec.ctx_attr)


def _dispatch_tool(
    *,
    block: Any,
    ctx: AgentContext,
    hop_index: int,
) -> tuple[ToolCall, dict[str, Any]]:
    """Dispatch one tool_use block; return (trace entry, tool_result for the model)."""
    started = time.perf_counter()
    started_ts = datetime.now(UTC)
    name = block.name
    tool_input = block.input

    tool_ctx = _resolve_tool_ctx(name, ctx)

    try:
        output = execute_tool(name, tool_input, ctx=tool_ctx)
        output_json: str | None = _serialise_tool_output(output)
        error: str | None = None
    except ToolError as exc:
        output_json = None
        error = str(exc) or type(exc).__name__
        logger.info("agent.loop: tool %r raised ToolError: %s", name, error)
    except Exception as exc:  # defensive: should never happen, but pass-through
        output_json = None
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("agent.loop: tool %r raised unexpected exception", name)

    duration_ms = int((time.perf_counter() - started) * 1000)

    result_content = output_json if output_json is not None else (error or "Unknown error")
    result_block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": result_content,
        "is_error": error is not None,
    }

    call = ToolCall(
        hop_index=hop_index,
        name=name,
        input_json=json.dumps(tool_input, default=str),
        output_json=output_json,
        error=error,
        duration_ms=duration_ms,
        started_at=started_ts,
    )
    return call, result_block


def _serialise_tool_output(output: Any) -> str:
    """JSON-serialise a tool output (Pydantic model or plain object)."""
    if hasattr(output, "model_dump_json"):
        return output.model_dump_json()
    return json.dumps(output, default=str)


def _extract_text(content_blocks: list[Any]) -> str:
    """Concatenate the text from all ``text`` blocks in a response content list."""
    return "".join(b.text for b in content_blocks if b.type == "text")


def _content_blocks_to_dicts(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert SDK content blocks back into dicts for the next API call."""
    out: list[dict[str, Any]] = []
    for b in blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out
