"""Custom exceptions for the tools layer.

Three levels of error, with clear semantics so the orchestrator can
decide the user-facing reaction:

    * ToolNotFoundError: orchestrator picked a non-existent tool name
                          (programming bug or LLM hallucination on tool
                          names — should bubble up).
    * ToolValidationError: input dict failed Pydantic validation
                           (malformed args from the LLM — orchestrator
                           may retry with a corrective prompt).
    * ToolExecutionError: tool ran but failed at runtime (DB down,
                          empty result, downstream API error).
                          Orchestrator should surface a graceful message
                          to the user and log the cause.
"""

from __future__ import annotations


class ToolError(Exception):
    """Base class for all tool-layer errors."""


class ToolNotFoundError(ToolError):
    """Raised when execute_tool is called with an unregistered tool name."""

    def __init__(self, name: str, available: list[str] | None = None) -> None:
        self.name = name
        self.available = available or []
        msg = f"Tool {name!r} is not registered."
        if available:
            msg += f" Available tools: {sorted(available)}"
        super().__init__(msg)


class ToolValidationError(ToolError):
    """Raised when the input payload fails the tool's Pydantic schema.

    Wraps the original ``pydantic.ValidationError`` to keep details
    accessible while presenting a stable interface to callers.
    """

    def __init__(self, tool_name: str, original: Exception) -> None:
        self.tool_name = tool_name
        self.original = original
        super().__init__(f"Invalid input for tool {tool_name!r}: {original}")


class ToolExecutionError(ToolError):
    """Raised when a tool's underlying logic fails at runtime.

    Use this to wrap DB errors, network errors, etc., so the orchestrator
    sees a single error type regardless of the tool that produced it.
    """

    def __init__(self, tool_name: str, message: str, cause: Exception | None = None) -> None:
        self.tool_name = tool_name
        self.cause = cause
        full = f"Tool {tool_name!r} failed: {message}"
        if cause is not None:
            full += f" (caused by: {type(cause).__name__}: {cause})"
        super().__init__(full)
