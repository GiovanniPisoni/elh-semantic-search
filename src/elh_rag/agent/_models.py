"""
Structured output  dataclasses for a single agent turn.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# ToolCall


class ToolCall(BaseModel):
    """One tool invocation inside an agent turn."""

    model_config = ConfigDict(frozen=True)


# AgentResponse


_StopReason = Literal["end_turn", "max_hops_reached", "error", "input_invalid"]


class AgentResponse(BaseModel):
    """Result of a single agent turn."""

    model_config = ConfigDict(frozen=True)

    def to_user_dict(self) -> dict[str, Any]:
        """UI-facing view: final answer + light summary, no trace."""
        raise NotImplementedError("Implemented in next step")

    def to_full_dict(self) -> dict[str, Any]:
        """Audit-facing view: full trace + all metrics + original query."""
        raise NotImplementedError("Implemented in next step")
