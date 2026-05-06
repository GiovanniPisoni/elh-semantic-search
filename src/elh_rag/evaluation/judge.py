"""
EvaluationJudge - thin wrapper around the Anthropic client for metric scoring
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import Anthropic

from elh_rag.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5"
_DEFAULT_MAX_TOKENS = 1500
_DEFAULT_TEMPERATURE = 0.0


class JudgeError(Exception):
    """
    Raised when the judge LLM call cannot produce a usable JSON response.

    Caller code (the metrics) catches this and returns None, signalling
    that the metric should be skipped for this query rather than being
    forced to a misleading 0.0.
    """


class EvaluationJudge:
    """
    LLM-as-judge for evaluation metrics.

    Stateless: each call is independent. Constructed once per evaluation
    run and passed to each metric function.
    """

    def __init__(
        self,
        model: str = _DEFAULT_JUDGE_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> None:
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    def ask_json(
        self,
        system: str,
        user: str,
        retry_on_parse_error: bool = True,
    ) -> dict[str, Any]:
        """
        Ask the judge a question and return its JSON response.
        """
        try:
            raw = self._call(system=system, user=user)
        except Exception as e:
            raise JudgeError(f"API call failed: {e}") from e

        parsed = _try_parse_json(raw)
        if parsed is not None:
            return parsed

        if not retry_on_parse_error:
            raise JudgeError(f"Unparsable JSON output: {raw[:200]}")

        retry_user = (
            f"{user}\n\n"
            "Your previous response was not valid JSON. Output ONLY the "
            "JSON object, with no preamble, no markdown fences, no "
            "trailing commentary."
        )
        try:
            raw_retry = self._call(system=system, user=retry_user)
        except Exception as e:
            raise JudgeError(f"Retry API call failed: {e}") from e

        parsed = _try_parse_json(raw_retry)
        if parsed is not None:
            return parsed

        raise JudgeError(
            f"Unparsable JSON after retry. First: {raw[:120]} | Retry: {raw_retry[:120]}"
        )

    def _call(self, system: str, user: str) -> str:
        """Single API call, returning the raw text output."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if not response.content:
            return ""
        return response.content[0].text


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from LLM text output."""
    if not raw:
        return None

    text = raw.strip()

    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) == 2:
            text = lines[1]

        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
