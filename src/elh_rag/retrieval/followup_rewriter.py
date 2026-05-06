"""
Follow-up rewriter.

Turns a conversational follow-up like "and in Porto?" into a standalone
search query by consulting the past turns stored in `ConversationMemory`.
The rewriter runs before routing and retrieve, so the downstream pipeline
always sees a self-contained question.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from elh_rag.config import settings
from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import (
    FOLLOWUP_REWRITER_SYSTEM_PROMPT,
    build_followup_rewriter_prompt,
)
from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.schemas import ConversationTurn

logger = logging.getLogger(__name__)


_ANSWER_SNIPPET_CHARS = 240


class FollowUpRewriter:
    """Rewrites follow-up questions into standalone queries using history."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient(
            model=settings.followup_rewriter_model,
            max_tokens=settings.followup_rewriter_max_tokens,
        )

    def rewrite(self, question: str, memory: ConversationMemory | None) -> str:
        """Return the standalone form of `question` given the conversation memory."""
        if memory is None or memory.is_empty():
            return question

        stripped = question.strip()
        if not stripped:
            return question

        history_lines = _format_history(memory.turns())
        if not history_lines:
            return question

        signature = _memory_signature(memory.turns())
        try:
            return _rewrite_cached(
                llm=self._llm,
                history_signature=signature,
                history_lines_tuple=tuple(history_lines),
                question=stripped,
            )
        except Exception as exc:
            logger.warning(
                "Follow-up rewriter failed (%s) — falling back to original question",
                exc,
            )
            return question


# Helpers


def _format_history(turns: list[ConversationTurn]) -> list[str]:
    """Render stored turns as `Turn N user/assistant:` lines for the prompt."""
    lines: list[str] = []
    for i, turn in enumerate(turns, start=1):
        question = turn.question.strip()
        answer = turn.answer.strip()

        if len(answer) > _ANSWER_SNIPPET_CHARS:
            answer = answer[:_ANSWER_SNIPPET_CHARS].rstrip() + "…"
        if question:
            lines.append(f"Turn {i} user: {question}")
        if answer:
            lines.append(f"Turn {i} assistant: {answer}")
    return lines


def _memory_signature(turns: list[ConversationTurn]) -> str:
    """Stable signature of the history for cache key purposes."""
    return "||".join(t.question.strip() for t in turns)


@lru_cache(maxsize=128)
def _rewrite_cached(
    llm: LLMClient,
    history_signature: str,
    history_lines_tuple: tuple[str, ...],
    question: str,
) -> str:
    """LLM-backed rewriting, memoised on (history, question)."""
    user_prompt = build_followup_rewriter_prompt(
        history_lines=list(history_lines_tuple),
        question=question,
    )
    raw = llm.complete(
        system=FOLLOWUP_REWRITER_SYSTEM_PROMPT,
        user=user_prompt,
    )
    cleaned = _clean_output(raw)
    if not cleaned:
        # Empty response → fall back to the original question.
        return question
    return cleaned


def _clean_output(raw: str) -> str:
    """Strip common wrappers from the LLM output."""
    if not raw:
        return ""
    cleaned = raw.strip()
    # Remove surrounding quotes if the model returned them despite the
    # prompt instructions.
    if len(cleaned) >= 2 and cleaned[0] in ('"', "'") and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    return cleaned
