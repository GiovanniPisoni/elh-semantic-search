"""Tool registry, decorator factory and dispatcher.

This module is the backbone of the tool-augmented RAG architecture.
It exposes three things:

    * ``@register_tool(name, description, input_model)`` — decorator
      factory that registers a function as a callable tool, with an
      input schema (Pydantic) and a human-readable description used
      by the orchestrator's prompt.

    * ``TOOLS_REGISTRY`` — module-level dict, single source of truth
      mapping tool names to their callable + metadata.

    * ``execute_tool(name, payload, ctx=None)`` — dispatcher. Looks up
      the tool, validates the payload against the registered Pydantic
      model, runs the function (passing ``ctx`` if the tool accepts
      it), and returns its raw output. Errors are normalised to
      ``ToolValidationError`` / ``ToolExecutionError`` /
      ``ToolNotFoundError``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Mapping

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


# Single source of truth. Populated at import time by ``@register_tool``.
TOOLS_REGISTRY: dict[str, ToolSpec] = {}

# Decorator factory


def register_tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a callable as a tool, attaching schema and metadata."""
    if not name or not name.strip():
        raise ValueError("Tool name must be a non-empty string.")
    if not isinstance(input_model, type) or not issubclass(input_model, BaseModel):
        raise ValueError(
            f"input_model must be a pydantic.BaseModel subclass, "
            f"got {input_model!r}."
        )

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in TOOLS_REGISTRY:
            raise ValueError(
                f"Tool {name!r} is already registered "
                f"(by {TOOLS_REGISTRY[name].func.__qualname__})."
            )
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        accepts_ctx = (
            len(params) >= 2
            and any(
                p.name == "ctx"
                or (idx == 1 and p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                ))
                for idx, p in enumerate(params)
            )
        )
        TOOLS_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            func=func,
            accepts_ctx=accepts_ctx,
        )
        return func

    return decorator


# Dispatcher


def execute_tool(
    name: str,
    payload: Mapping[str, Any],
    ctx: Any | None = None,
) -> Any:
    """Validate a raw payload and run the registered tool."""
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