"""Tests for the ConversationMemory bounded FIFO buffer."""
from __future__ import annotations

from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.schemas import ConversationTurn


# Empty / lifecycle


def test_new_memory_is_empty() -> None:
    mem = ConversationMemory(max_turns=5)
    assert mem.is_empty()
    assert len(mem) == 0
    assert mem.turns() == []


def test_append_increases_length() -> None:
    mem = ConversationMemory(max_turns=5)
    mem.append("q1", "a1")
    assert len(mem) == 1
    assert not mem.is_empty()


def test_clear_resets_buffer() -> None:
    mem = ConversationMemory(max_turns=5)
    mem.append("q1", "a1")
    mem.append("q2", "a2")
    mem.clear()
    assert len(mem) == 0
    assert mem.is_empty()


# FIFO bounding


def test_buffer_drops_oldest_when_at_capacity() -> None:
    mem = ConversationMemory(max_turns=3)
    mem.append("q1", "a1")
    mem.append("q2", "a2")
    mem.append("q3", "a3")
    mem.append("q4", "a4")  # should evict q1

    turns = mem.turns()
    assert [t.question for t in turns] == ["q2", "q3", "q4"]
    assert len(mem) == 3


def test_max_turns_property_exposes_bound() -> None:
    mem = ConversationMemory(max_turns=7)
    assert mem.max_turns == 7


# Snapshot semantics


def test_turns_returns_a_list_copy_not_internal_buffer() -> None:
    """Mutating the returned list must not affect future calls."""
    mem = ConversationMemory(max_turns=5)
    mem.append("q1", "a1")
    snapshot = mem.turns()
    snapshot.append(ConversationTurn(question="injected", answer="bad"))

    fresh = mem.turns()
    assert len(fresh) == 1
    assert fresh[0].question == "q1"


def test_iteration_yields_turn_objects_in_insertion_order() -> None:
    mem = ConversationMemory(max_turns=5)
    mem.append("q1", "a1")
    mem.append("q2", "a2")
    questions = [t.question for t in mem]
    assert questions == ["q1", "q2"]


# Integration with Pydantic settings default


def test_default_max_turns_comes_from_settings(monkeypatch) -> None:
    """When max_turns is None, ConversationMemory reads settings."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "conversational_memory_max_turns", 4)
    mem = ConversationMemory()
    assert mem.max_turns == 4