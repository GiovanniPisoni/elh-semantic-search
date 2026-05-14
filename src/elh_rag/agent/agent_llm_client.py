"""
Anthropic SDK wrapper for the agent layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from elh_rag.config import settings

logger = logging.getLogger(__name__)


# Transient exceptions that warrant a retry.
_RETRY_ON: tuple[type[Exception], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)


# StreamChunk


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """One incremental chunk emitted during streaming."""

    text_delta: str | None = None
    tool_use: Any | None = None
    final_message: Any | None = None


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
        self._model = model or settings.agent_llm_model
        self._max_tokens = max_tokens or settings.agent_llm_max_tokens
        self._temperature = (
            temperature if temperature is not None else settings.agent_llm_temperature
        )
        self._max_retries = max_retries or settings.agent_llm_max_retries
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        """Lazily-initialised Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    # Retry decorator factory

    def _retry_decorator(self) -> Any:
        """Build a tenacity retry decorator with this instance's config."""
        return retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRY_ON),
            reraise=True,
        )

    # Non-streaming call

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Any:
        """One ``messages.create`` call with tenacity retry on transient errors."""
        logger.debug(
            "agent_llm.call: model=%s, temp=%.2f, n_messages=%d, n_tools=%d",
            self._model,
            self._temperature,
            len(messages),
            len(tools),
        )

        @self._retry_decorator()
        def _do_call() -> Any:
            return self.client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system,
                messages=messages,
                tools=tools,
            )

        return _do_call()

    # Streaming call

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Iterator[StreamChunk]:
        """Stream ``messages.create`` deltas, retry-wrapped on open only.
        Used on the final hop where streaming hides total latency.
        """
        logger.debug(
            "agent_llm.stream: model=%s, temp=%.2f, n_messages=%d, n_tools=%d",
            self._model,
            self._temperature,
            len(messages),
            len(tools),
        )

        @self._retry_decorator()
        def _open_stream() -> Any:
            return self.client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system,
                messages=messages,
                tools=tools,
            )

        stream_ctx = _open_stream()

        with stream_ctx as anthropic_stream:
            # 1. yield text deltas as they arrive
            for text_delta in anthropic_stream.text_stream:
                yield StreamChunk(text_delta=text_delta)

            # 2. emit the final assembled message
            final = anthropic_stream.get_final_message()
            yield StreamChunk(final_message=final)
