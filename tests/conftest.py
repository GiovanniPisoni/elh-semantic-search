"""
Shared pytest fixtures for the test suite.

Provides fake implementations of the external dependencies (vector store,
embedder, LLM client) so unit tests run offline and deterministic.
"""

from __future__ import annotations

from typing import Any

import pytest

from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import DocumentSource, ReviewMetadata

# Fake vector store


class FakeVectorStore:
    """In-memory VectorStore implementation for tests."""

    def __init__(self, canned_matches: list[dict[str, Any]] | None = None) -> None:
        self._vectors: list[dict[str, Any]] = []
        self._canned_matches = canned_matches or []
        self.upsert_calls: list[list[dict[str, Any]]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.delete_all_calls = 0

    def upsert(self, vectors: list[dict[str, Any]]) -> None:
        self.upsert_calls.append(vectors)
        self._vectors.extend(vectors)

    def query(
        self,
        embedding: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.query_calls.append({"embedding": embedding, "top_k": top_k, "filter": metadata_filter})
        return self._canned_matches[:top_k]

    def delete_all(self) -> None:
        self.delete_all_calls += 1
        self._vectors = []

    def count(self) -> int:
        return len(self._vectors)


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


# Fake LLM client


class FakeLLMClient(LLMClient):
    """LLM client that returns a canned response without calling Anthropic."""

    def __init__(self, canned_response: str = "Mock answer based on reviews.") -> None:
        self._canned_response = canned_response
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self._canned_response


# Fake query rewriter


class FakeQueryRewriter(QueryRewriter):
    """Query rewriter that returns a predictable transformation without LLM calls."""

    def __init__(
        self,
        canned_output: str | None = None,
        passthrough: bool = False,
    ) -> None:
        self._canned = canned_output
        self._passthrough = passthrough
        self.calls: list[str] = []

    def rewrite(self, question: str) -> str:
        self.calls.append(question)
        if self._passthrough or not question.strip():
            return question
        return self._canned if self._canned is not None else f"REWRITTEN: {question}"


# Fake reranker


class FakeReranker(Reranker):
    """Reranker that reverses the input order without loading any model.

    Reversing the order is a simple but effective signal that reranking
    actually ran: any test that expects the "reranked" order can assert
    on the reversed sequence.
    """

    def __init__(self, reverse: bool = True) -> None:
        self._reverse = reverse
        self.calls: list[tuple[str, int]] = []

    def rerank(
        self,
        query: str,
        candidates: list,
        top_k: int,
    ) -> list:
        from elh_rag.schemas import RetrievalResult

        self.calls.append((query, len(candidates)))
        ordered = list(reversed(candidates)) if self._reverse else list(candidates)
        return [
            RetrievalResult(
                text=c.text,
                metadata=c.metadata,
                vector_score=c.vector_score,
                rerank_score=float(len(ordered) - i),
            )
            for i, c in enumerate(ordered[:top_k])
        ]


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
def fake_store(fake_match: dict[str, Any]) -> VectorStore:
    """A fake vector store pre-loaded with one matching document."""
    return FakeVectorStore(canned_matches=[fake_match])


@pytest.fixture
def fake_embedder() -> Embedder:
    return FakeEmbedder()


@pytest.fixture
def fake_llm() -> LLMClient:
    return FakeLLMClient(canned_response="The bed is comfortable, per Review 1.")


@pytest.fixture
def fake_rewriter() -> QueryRewriter:
    """A rewriter that returns the input unchanged — no noise in other tests."""
    return FakeQueryRewriter(passthrough=True)


@pytest.fixture
def fake_reranker() -> Reranker:
    """A reranker that reverses the input order to make reordering visible."""
    return FakeReranker(reverse=True)


@pytest.fixture
def noop_reranker() -> Reranker:
    """A reranker that preserves input order (useful when testing other steps)."""
    return FakeReranker(reverse=False)
