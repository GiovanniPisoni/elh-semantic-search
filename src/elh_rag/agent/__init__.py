"""
Agentic-RAG orchestration layer.

Wraps the six tools and two RAG corpora (descriptions, reviews)
into a single LLM-driven loop
"""

from __future__ import annotations

from elh_rag.agent import tools_RAG_corpora  # noqa: F401
from elh_rag.agent._models import AgentResponse, ToolCall
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
    "InputValidationError",
    "ToolCall",
    "run_agent_turn",
]
