"""
Agent loop: LLM call -> tool dispatch -> LLM call -> ... -> final answer.

Algorithm:
1. Validate query length.
2. Build the initial messages list: ``[{"role": "user", "content": query}]``.
3. Call ``AgentLLMClient.call(messages, tools, system=SYSTEM_PROMPT)``.
4. Loop up to MAX_HOPS iterations:
       a. If the model returns ``stop_reason == "end_turn"`` (no tool use):
          assemble AgentResponse with stop_reason="end_turn" and exit.
       b. If the model returns ``stop_reason == "tool_use"``:
          - For each tool_use block, dispatch via
            :func:`elh_rag.tools.base.execute_tool`.
          - Catch ``ToolError`` subclasses; pass the error string to
            the model as a ``tool_result`` block with
            ``is_error=True``.
          - Append assistant message + tool_result blocks to messages.
          - Call the model again.
5. If MAX_HOPS exhausted without an end_turn, assemble AgentResponse
   with stop_reason="max_hops_reached".
"""

from __future__ import annotations

import logging

from elh_rag.agent._models import AgentResponse

logger = logging.getLogger(__name__)


# Limits


MAX_HOPS: int = 5

MAX_QUERY_CHARS: int = 4000


# Exceptions


class InputValidationError(ValueError):
    """Raised when the user query violates length or shape constraints."""


# Public API


def run_agent_turn(query: str, ctx) -> AgentResponse:
    """Execute one agent turn end-to-end."""
    raise NotImplementedError("Implemented in next steps")
