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

    # System-prompt cache wrapping

    @staticmethod
    def _build_system_param(system: str) -> list[dict[str, Any]]:
        """Wrap the system prompt in a single cacheable content block.

        Anthropic prompt caching requires the ``system`` parameter to be
        a list of content blocks; attaching ``cache_control`` to that
        block tells the API to reuse the cached prefix on subsequent
        calls (90% input-token discount on cache reads). The TTL is the
        default ``ephemeral`` (~5 minutes), which is sufficient for both
        the benchmark workload and a typical interactive session.
        """
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    @staticmethod
    def _log_cache_usage(usage: Any) -> None:
        """Emit an INFO line with cache-creation / cache-read token counts."""
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        if cache_create or cache_read:
            logger.info(
                "agent.llm: cache_creation=%d, cache_read=%d, input=%d, output=%d",
                cache_create,
                cache_read,
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
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

        system_param = self._build_system_param(system)

        @self._retry_decorator()
        def _do_call() -> Any:
            return self.client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_param,
                messages=messages,
                tools=tools,
            )

        response = _do_call()
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._log_cache_usage(usage)
        return response

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

        system_param = self._build_system_param(system)

        @self._retry_decorator()
        def _open_stream() -> Any:
            return self.client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_param,
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
            usage = getattr(final, "usage", None)
            if usage is not None:
                self._log_cache_usage(usage)
            yield StreamChunk(final_message=final)
