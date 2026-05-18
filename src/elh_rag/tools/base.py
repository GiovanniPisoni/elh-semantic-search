"""Tool registry, decorator factory and dispatcher.

This module is the backbone of the tool-augmented RAG architecture.
It exposes three things:

    * ``@register_tool(name, description, input_model, *, ctx_attr=None)``
      — decorator factory that registers a function as a callable
      tool, with an input schema (Pydantic), a human-readable
      description used by the orchestrator's prompt, and an optional
      ``ctx_attr`` declaring which sub-context the tool expects when
      dispatched by the Phase 3 agent (e.g. ``"db"`` for the
      ``DBExecutor``, ``"kb"`` for the ``KBContext``).

    * ``TOOLS_REGISTRY`` — module-level dict, single source of truth
      mapping tool names to their callable + metadata.

    * ``execute_tool(name, payload, ctx=None)`` — dispatcher. Looks up
      the tool, validates the payload against the registered Pydantic
      model, runs the function (passing ``ctx`` if the tool accepts
      it), and returns its raw output. Errors are normalised to
      ``ToolValidationError`` / ``ToolExecutionError`` /
      ``ToolNotFoundError``.

``ctx_attr`` is an agent-layer-only concept: it is metadata stored
in :class:`ToolSpec` for the Phase 3 agent loop to consult before
dispatching a tool. The dispatcher itself (:func:`execute_tool`)
ignores ``ctx_attr`` and forwards whatever ``ctx`` it receives,
keeping the Phase 2 test harness and Phase 3 unit-test patterns
working unchanged.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .errors import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)

# Registry data model


@dataclass(frozen=True)
class ToolSpec:
    """Frozen metadata about a registered tool."""

    name: str
    description: str
    input_model: type[BaseModel]
    func: Callable[..., Any]
    accepts_ctx: bool
    ctx_attr: str | None = None
    """If set, the Phase 3 agent passes ``getattr(agent_context, ctx_attr)``
    as the tool's ``ctx`` argument instead of the full AgentContext.

    Conventions used in this project:
        "db"   - tool expects a DBExecutor   (Tools 1-5)
        "kb"   - tool expects a KBContext    (Tool 6)
        None   - tool expects the full AgentContext (RAG corpora)

    Backwards-compatible default: ``None`` means the dispatcher
    forwards ``ctx`` unchanged (Phase 2/3 unit-test pattern).
    """


# Single source of truth. Populated at import time by ``@register_tool``.
TOOLS_REGISTRY: dict[str, ToolSpec] = {}

# Decorator factory


def register_tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
    *,
    ctx_attr: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a callable as a tool, attaching schema and metadata.

    Parameters
    ----------
    name
        Unique tool name used in the registry and exposed to the LLM.
    description
        Human-readable description shown to the LLM in the tool
        schema.
    input_model
        Pydantic model that validates the tool's input payload.
    ctx_attr, optional
        Name of an attribute on the Phase 3 ``AgentContext`` from
        which the loop should extract the sub-context to pass as
        ``ctx`` when dispatching this tool. Use ``"db"`` for tools
        that take a ``DBExecutor``, ``"kb"`` for tools that take a
        ``KBContext``. Leave as ``None`` (default) to receive the
        full ``AgentContext`` (or whatever ``ctx`` the direct
        dispatcher caller supplies, in test scenarios).
    """
    if not name or not name.strip():
        raise ValueError("Tool name must be a non-empty string.")
    if not isinstance(input_model, type) or not issubclass(input_model, BaseModel):
        raise ValueError(f"input_model must be a pydantic.BaseModel subclass, got {input_model!r}.")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in TOOLS_REGISTRY:
            raise ValueError(
                f"Tool {name!r} is already registered "
                f"(by {TOOLS_REGISTRY[name].func.__qualname__})."
            )
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        accepts_ctx = len(params) >= 2 and any(
            p.name == "ctx"
            or (
                idx == 1
                and p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            )
            for idx, p in enumerate(params)
        )
        TOOLS_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            func=func,
            accepts_ctx=accepts_ctx,
            ctx_attr=ctx_attr,
        )
        return func

    return decorator


# Dispatcher


def execute_tool(
    name: str,
    payload: Mapping[str, Any],
    ctx: Any | None = None,
) -> Any:
    """Validate a raw payload and run the registered tool.

    Note: this dispatcher ignores ``ctx_attr`` — it forwards whatever
    ``ctx`` was supplied. The Phase 3 agent loop is responsible for
    resolving ``ctx_attr`` against the AgentContext before calling
    this function. Unit tests that exercise tools directly continue
    to pass any ``ctx`` shape they want.
    """
    spec = TOOLS_REGISTRY.get(name)
    if spec is None:
        raise ToolNotFoundError(name, available=list(TOOLS_REGISTRY))

    try:
        validated = spec.input_model(**payload)
    except ValidationError as e:
        raise ToolValidationError(spec.name, e) from e

    try:
        if spec.accepts_ctx:
            # Pass ctx as keyword to handle both positional and keyword-only signatures
            return spec.func(validated, ctx=ctx)
        return spec.func(validated)
    except (ToolValidationError, ToolNotFoundError):
        # These are programming errors from inside a tool — bubble up
        # without wrapping (would lose information).
        raise
    except Exception as e:
        raise ToolExecutionError(
            spec.name,
            message=str(e) or type(e).__name__,
            cause=e,
        ) from e


# Introspection helpers


def list_tools() -> list[str]:
    """Return registered tool names (sorted, for stable test output)."""
    return sorted(TOOLS_REGISTRY)


def get_tool(name: str) -> ToolSpec:
    """Return the ToolSpec for a registered tool."""
    spec = TOOLS_REGISTRY.get(name)
    if spec is None:
        raise ToolNotFoundError(name, available=list(TOOLS_REGISTRY))
    return spec


def _clear_registry_for_tests() -> None:
    """Test-only helper. Resets the global registry."""
    TOOLS_REGISTRY.clear()
