"""
Shared pytest fixtures for the test suite.

Provides fake implementations of the external dependencies (vector store,
embedder, LLM client) so unit tests run offline and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from elh_rag.indexing.embeddings import Embedder
from elh_rag.schemas import DocumentSource, ReviewMetadata

# Fake embedder


class FakeEmbedder(Embedder):
    """Embedder that returns deterministic fake vectors without loading any model."""

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim
        self._model_name = "fake"
        self._model = None

    @property
    def dimension(self) -> int:
        return self._dim

    def encode_query(self, text: str) -> list[float]:
        return [float(len(text) % 10) / 10.0] * self._dim

    def encode_batch(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        return [[float(len(t) % 10) / 10.0] * self._dim for t in texts]


# Fake db executor


class FakeDbExecutor:
    """Minimal in-memory DBExecutor implementation for tests.

    Stores a list of (sql_pattern, response) mappings and returns the
    response of the first pattern that appears as a substring in the
    executed SQL. Matching is loose by design — tests assert on the
    high-level behaviour of the tool, not on exact SQL strings.

    Records every call into `calls` so tests can assert on the SQL
    and parameters that were issued.
    """

    def __init__(self) -> None:
        self._responses: list[tuple[str, list[dict[str, Any]]]] = []
        self.calls: list[dict[str, Any]] = []

    def add_response(self, sql_substring: str, response: list[dict[str, Any]]) -> None:
        """Register a canned response for any SQL containing sql_substring."""
        self._responses.append((sql_substring, response))

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"sql": sql, "params": params})
        for pattern, response in self._responses:
            if pattern in sql:
                return response
        return []

    def reset(self) -> None:
        self._responses.clear()
        self.calls.clear()


# Pytest fixtures


@pytest.fixture
def fake_metadata() -> ReviewMetadata:
    """A single ReviewMetadata instance for tests."""
    return ReviewMetadata(
        id="rev-001",
        source=DocumentSource.REVIEW,
        city="Lisbon",
        zone="Alfama",
        flatname="Casa do Sol",
        roomname="Blue Room",
        overall_rating=5,
        review_title="Amazing stay",
        review_text_original="The bed was very comfortable and the host was kind.",
    )


@pytest.fixture
def fake_match(fake_metadata: ReviewMetadata) -> dict[str, Any]:
    """A single Pinecone-shaped match dict for tests."""
    return {
        "id": fake_metadata.id,
        "score": 0.87,
        "metadata": fake_metadata.to_pinecone_dict(),
    }


@pytest.fixture
def fake_embedder() -> Embedder:
    return FakeEmbedder()


@pytest.fixture
def fake_db() -> FakeDbExecutor:
    """Empty in-memory DB executor — call add_response() to seed it."""
    return FakeDbExecutor()
