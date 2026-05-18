"""
Structured output dataclasses for a single agent turn.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ToolCall


class ToolCall(BaseModel):
    """One tool invocation inside an agent turn."""

    model_config = ConfigDict(frozen=True)

    hop_index: int = Field(
        ..., ge=0, description="Zero-based index of the agent hop in which this call occurred."
    )
    name: str = Field(..., description="Registered tool name (e.g. 'find_rooms').")
    input_json: str = Field(
        ...,
        description=(
            "JSON-serialised tool input, as the model produced it. "
            "Verbatim from the tool_use block input field."
        ),
    )
    output_json: str | None = Field(
        default=None,
        description=(
            "JSON-serialised tool output on success, or None if the "
            "tool raised an error (in which case ``error`` is populated)."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error message if the tool raised, otherwise None. Mutually "
            "exclusive with ``output_json``."
        ),
    )
    duration_ms: int = Field(..., ge=0, description="Wall-clock duration of this tool call.")
    started_at: datetime = Field(..., description="Timestamp when the tool dispatch began (UTC).")


# AgentResponse


_StopReason = Literal["end_turn", "max_hops_reached", "error", "input_invalid"]


class AgentResponse(BaseModel):
    """Result of a single agent turn."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="The user's original query string.")
    final_message: str = Field(
        ...,
        description=(
            "The assistant's final text answer. Empty string only if "
            "stop_reason indicates an abnormal termination."
        ),
    )
    stop_reason: _StopReason = Field(
        ...,
        description=(
            "Why the loop terminated: 'end_turn' (model produced a "
            "final answer), 'max_hops_reached' (loop hit MAX_HOPS), "
            "'error' (unrecoverable error), 'input_invalid' (D6.4 "
            "input check failed before the first LLM call)."
        ),
    )
    hop_count: int = Field(
        ..., ge=0, description="Number of LLM-call iterations executed (1-based count)."
    )
    tool_trace: list[ToolCall] = Field(
        default_factory=list,
        description="Ordered list of every tool invocation in this turn.",
    )
    input_tokens: int = Field(
        ..., ge=0, description="Sum of input_tokens across all LLM calls in this turn."
    )
    output_tokens: int = Field(
        ..., ge=0, description="Sum of output_tokens across all LLM calls in this turn."
    )
    total_duration_ms: int = Field(
        ..., ge=0, description="Wall-clock duration of the full turn, end to end."
    )
    started_at: datetime = Field(..., description="Timestamp when the turn began (UTC).")

    # Views

    def to_user_dict(self) -> dict[str, Any]:
        """UI-facing view: final answer + light summary, no trace."""
        return {
            "answer": self.final_message,
            "stop_reason": self.stop_reason,
            "hop_count": self.hop_count,
            "tools_used": [t.name for t in self.tool_trace],
            "duration_ms": self.total_duration_ms,
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Audit-facing view: full trace + all metrics + original query."""
        return self.model_dump(mode="json")
