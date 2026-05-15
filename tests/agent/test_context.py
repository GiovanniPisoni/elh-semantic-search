"""Tests for :class:`elh_rag.agent.context.AgentContext`."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

import pytest

from elh_rag.agent.context import AgentContext, _cached_embedder
from elh_rag.config import settings

# Fixtures


@pytest.fixture(autouse=True)
def clear_embedder_cache() -> Iterator[None]:
    """Reset lru_cache before each test so build() does fresh work."""
    _cached_embedder.cache_clear()
    yield
    _cached_embedder.cache_clear()


@pytest.fixture
def patched_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, MagicMock]:
    """Replace heavyweight dependencies with mocks for offline tests."""
    mock_embedder = MagicMock(name="Embedder")
    mock_pinecone_desc = MagicMock(name="PineconeDescriptions")
    mock_pinecone_rev = MagicMock(name="PineconeReviews")
    mock_db = MagicMock(name="Psycopg2Executor")
    mock_kb = MagicMock(name="KBContext")

    monkeypatch.setattr("elh_rag.agent.context.Embedder", lambda: mock_embedder)
    monkeypatch.setattr("elh_rag.agent.context.Psycopg2Executor", lambda **_: mock_db)
    
    # Two calls to PineconeVectorStore inside build(), keep them
    # distinguishable so we can verify the order and the correct index_name kwarg.
    def _pinecone_factory(**kw: object) -> MagicMock:
        if kw.get("index_name") == settings.pinecone_descriptions_index_name:
            return mock_pinecone_desc
        return mock_pinecone_rev

    monkeypatch.setattr("elh_rag.agent.context.PineconeVectorStore", _pinecone_factory)

    mock_kb_cls = MagicMock(from_default_yaml=lambda _embedder: mock_kb)
    monkeypatch.setattr("elh_rag.agent.context.KBContext", mock_kb_cls)

    return {
        "embedder": mock_embedder,
        "db": mock_db,
        "pinecone_desc": mock_pinecone_desc,
        "pinecone_rev": mock_pinecone_rev,
        "kb": mock_kb,
    }


# build() factory


class TestAgentContextBuild:
    def test_build_returns_agent_context_instance(
        self, patched_dependencies: dict[str, MagicMock]
    ) -> None:
        ctx = AgentContext.build()
        assert isinstance(ctx, AgentContext)

    def test_build_wires_all_five_fields(self, patched_dependencies: dict[str, MagicMock]) -> None:
        ctx = AgentContext.build()
        assert ctx.embedder is patched_dependencies["embedder"]
        assert ctx.db is patched_dependencies["db"]
        assert ctx.kb is patched_dependencies["kb"]
        assert ctx.descriptions_store is patched_dependencies["pinecone_desc"]
        assert ctx.reviews_store is patched_dependencies["pinecone_rev"]

    def test_build_caches_embedder_across_calls(
        self, patched_dependencies: dict[str, MagicMock]
    ) -> None:
        """Two consecutive build() calls share the same Embedder."""
        ctx1 = AgentContext.build()
        ctx2 = AgentContext.build()
        assert ctx1.embedder is ctx2.embedder


# Frozen dataclass


class TestAgentContextFrozen:
    def test_cannot_reassign_field(self, patched_dependencies: dict[str, MagicMock]) -> None:
        """A frozen+slots dataclass raises FrozenInstanceError on assignment."""
        ctx = AgentContext.build()
        with pytest.raises(FrozenInstanceError):
            ctx.db = None  # type: ignore[misc]

    def test_direct_construction_with_all_fields(self) -> None:
        """Tests can build AgentContext directly by passing all 5 fields."""
        ctx = AgentContext(
            db=MagicMock(name="db"),
            kb=MagicMock(name="kb"),
            embedder=MagicMock(name="embedder"),
            descriptions_store=MagicMock(name="descriptions_store"),
            reviews_store=MagicMock(name="reviews_store"),
        )
        assert isinstance(ctx, AgentContext)
