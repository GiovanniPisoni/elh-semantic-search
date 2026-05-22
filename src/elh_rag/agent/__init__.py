"""
Agentic-RAG orchestration layer.

Wraps the six Phase 3 tools and two RAG corpora (descriptions,
reviews) into a single LLM-driven loop.
"""

from __future__ import annotations

import elh_rag.tools.answer_policy_question.tool
import elh_rag.tools.compute_total_cost.tool
import elh_rag.tools.find_available_rooms.tool
import elh_rag.tools.find_rooms.tool
import elh_rag.tools.get_booking_stats.tool
import elh_rag.tools.get_property_details.tool  # noqa: F401

# Side-effect imports.
#
# Each of the eight tools registers itself into TOOLS_REGISTRY via
# the ``@register_tool`` decorator at module import. By importing
# them here, every consumer of :mod:`elh_rag.agent` gets the full
# tool set automatically — no need for application code or smoke
# scripts to enumerate the tool modules by hand.
#
# Two RAG-corpora wrappers (search_descriptions, search_reviews)
# live inside the agent package itself; the other six are
# re-exported here from :mod:`elh_rag.tools`.
from elh_rag.agent import tools_RAG_corpora  # noqa: F401

# Public API symbols
from elh_rag.agent._models import AgentResponse, ConversationTurn, ToolCall
from elh_rag.agent.agent_llm_client import AgentLLMClient
from elh_rag.agent.context import AgentContext
from elh_rag.agent.loop import (
    InputValidationError,
    run_agent_turn,
)

__all__ = [
    "AgentContext",
    "AgentLLMClient",
    "AgentResponse",
    "ConversationTurn",
    "InputValidationError",
    "ToolCall",
    "run_agent_turn",
]
