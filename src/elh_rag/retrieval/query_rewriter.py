"""
Query rewriter.

Rewrites natural-language questions into search-optimized queries using a small LLM.
- Injectable: uses Anthropic Haiku in prod, fake in tests.
- Memoized: caches results to save API costs.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from elh_rag.config import settings
from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import (
    REWRITER_SYSTEM_PROMPT,
    build_rewriter_prompt,
)

logger = logging.getLogger(__name__)


class QueryRewriter:
    """LLM-based query rewriter for improved semantic retrieval."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient(
            model=settings.llm_rewriter_model,
            max_tokens=settings.llm_rewriter_max_tokens,
        )
        self._rewrite_cached = lru_cache(maxsize=128)(self._rewrite_uncached)

    def rewrite(self, question: str) -> str:
        """Return a search-optimised version of the given question.

        Falls back to the original question on empty input or LLM failure,
        so retrieval never breaks because of a rewriting issue.
        """
        question = question.strip()
        if not question:
            return question

        try:
            rewritten = self._rewrite_cached(question)
        except Exception as exc:
            logger.warning("Query rewriting failed (%s) — falling back to original", exc)
            return question

        logger.debug("Rewrote %r -> %r", question, rewritten)
        return rewritten

    def _rewrite_uncached(self, question: str) -> str:
        """Call the LLM and clean up its output."""
        raw = self._llm.complete(
            system=REWRITER_SYSTEM_PROMPT,
            user=build_rewriter_prompt(question),
        )
        return self._clean_output(raw) or question

    @staticmethod
    def _clean_output(raw: str) -> str:
        """Strip whitespace, surrounding quotes, and common LLM preambles."""
        text = raw.strip()
        for prefix in ("Rewritten search query:", "Rewritten query:", "Query:"):
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix) :].strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1].strip()
        return text
