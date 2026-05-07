"""Tool-augmented RAG: tools layer.

Public re-exports. Individual tool modules import directly from
``base`` and ``errors`` to avoid circular imports during registration.
"""

from .base import (
    TOOLS_REGISTRY,
    ToolSpec,
    execute_tool,
    get_tool,
    list_tools,
    register_tool,
)
from .errors import (
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)

__all__ = [
    "TOOLS_REGISTRY",
    "ToolError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolSpec",
    "ToolValidationError",
    "execute_tool",
    "get_tool",
    "list_tools",
    "register_tool",
]
