"""ELH RAG package — public API.

Phase 3 (Agentic RAG) is the deployed system. The Phase 2 pipeline
(pipelined-RAG) has been archived to branch ``v2-pipelined-RAG-archive``
and is no longer part of the package public surface.
"""

from __future__ import annotations

from elh_rag.agent import (
    AgentContext,
    AgentResponse,
    ConversationTurn,
    InputValidationError,
    ToolCall,
    run_agent_turn,
)
from elh_rag.config import settings

__all__ = [
    "AgentContext",
    "AgentResponse",
    "ConversationTurn",
    "InputValidationError",
    "ToolCall",
    "run_agent_turn",
    "settings",
]

__version__ = "3.0.0"
