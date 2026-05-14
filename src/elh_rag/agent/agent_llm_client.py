"""
Anthropic SDK wrapper for the agent layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)


# AgentLLMClient


class AgentLLMClient:
    """Anthropic-backed LLM client for the agent loop."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        raise NotImplementedError("Implemented in next step")

    @property
    def client(self) -> Any:
        """Lazily-initialised Anthropic client."""
        raise NotImplementedError("Implemented in next step")

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Any:
        """One ``messages.create`` call with tenacity retry on transient errors."""
        raise NotImplementedError("Implemented in next step")

    # Streaming call (final hop)

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Iterator[Any]:
        """Stream ``messages.create`` deltas with tenacity retry."""
        raise NotImplementedError("Implemented in next step")
