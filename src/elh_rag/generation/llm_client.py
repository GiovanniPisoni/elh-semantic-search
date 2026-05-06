"""
LLM client wrapper.

Encapsulates the Anthropic SDK behind a small, swappable interface,
making the pipeline independent from any specific provider.
"""

from __future__ import annotations

import logging
from typing import Any

from elh_rag.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Anthropic-backed LLM client."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._model = model or settings.llm_model
        self._temperature = temperature if temperature is not None else settings.llm_temperature
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        """Lazily-initialised Anthropic client."""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    def complete(self, system: str, user: str) -> str:
        """Generate a single completion given system and user prompts."""
        logger.debug("LLM call: model=%s, temp=%.2f", self._model, self._temperature)
        response = self.client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
