"""
ConversationMemory — bounded FIFO buffer of past conversation turns.

Keeps the last N `(question, answer)` pairs in order. The `FollowUpRewriter`
reads this buffer to decide whether the next user question is a follow-up
that needs rewriting.
"""
from __future__ import annotations

from collections import deque
from typing import Iterable

from elh_rag.config import settings
from elh_rag.schemas import ConversationTurn


class ConversationMemory:
    """Bounded FIFO buffer of ConversationTurn objects."""

    def __init__(self, max_turns: int | None = None) -> None:
        self._max_turns = (
            max_turns
            if max_turns is not None
            else settings.conversational_memory_max_turns
        )
        self._turns: deque[ConversationTurn] = deque(maxlen=self._max_turns)

    # Mutation

    def append(self, question: str, answer: str) -> None:
        """Append a new turn. Oldest turns are discarded when at capacity."""
        self._turns.append(ConversationTurn(question=question, answer=answer))

    def clear(self) -> None:
        """Reset the memory, dropping all turns."""
        self._turns.clear()

    # Queries

    @property
    def max_turns(self) -> int:
        """Upper bound on stored turns."""
        return self._max_turns

    def is_empty(self) -> bool:
        """True if there are no stored turns."""
        return len(self._turns) == 0

    def turns(self) -> list[ConversationTurn]:
        """Return a snapshot of the stored turns as a list (oldest first)."""
        return list(self._turns)

    def __len__(self) -> int:
        return len(self._turns)

    def __iter__(self) -> Iterable[ConversationTurn]:
        return iter(self._turns)