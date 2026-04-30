"""Tests for the source-agnostic indexer.

The indexer accepts any `Extractor` and any `VectorStore`. These tests
verify the injection works end-to-end with fakes (no Pinecone, no
Supabase, no real model downloads).
"""
from __future__ import annotations

from typing import Any, Iterable
from unittest.mock import patch

import pytest

from elh_rag.data.extractor import Extractor
from elh_rag.indexing.indexer import (
    _sanitize_metadata,
    _summarise_by_city,
    _summarise_by_source,
    run_indexing,
)
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.schemas import (
    Document,
    DocumentSource,
    HouseMetadata,
    ReviewMetadata,
    RoomMetadata,
)


# Fake Extractor


class _FakeExtractor:
    """Minimal extractor that emits a fixed list of Documents."""

    def __init__(self, documents: list[Document]) -> None:
        self._documents = documents

    @property
    def source(self) -> DocumentSource:
        return DocumentSource.REVIEW if self._documents and isinstance(
            self._documents[0].metadata, ReviewMetadata
        ) else DocumentSource.HOUSE

    def extract(self) -> Iterable[Document]:
        return iter(self._documents)


# Fake VectorStore


class _FakeVectorStore:
    """Records upsert calls for assertions."""

    def __init__(self) -> None:
        self.upserted_batches: list[list[dict[str, Any]]] = []
        self.delete_all_called = False
        self._count = 0

    def upsert(self, vectors: list[dict[str, Any]]) -> None:
        self.upserted_batches.append(list(vectors))
        self._count += len(vectors)

    def query(
        self,
        embedding: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def delete_all(self) -> None:
        self.delete_all_called = True
        self._count = 0

    def count(self) -> int:
        return self._count


# Fake Embedder (deterministic)


class _FakeEmbedder:
    """Emits one-dim embeddings equal to the length of the text, for traceability."""

    def encode_batch(
        self, texts: list[str], batch_size: int = 16
    ) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

    def encode_query(self, text: str) -> list[float]:
        return [float(len(text))]


# Helpers


def _metadata_sanitize_tests() -> None:
    pass


def test_sanitize_metadata_passes_through_primitives() -> None:
    clean = _sanitize_metadata({"a": "x", "b": 1, "c": 1.5, "d": True})
    assert clean == {"a": "x", "b": 1, "c": 1.5, "d": True}


def test_sanitize_metadata_replaces_none_with_empty_string() -> None:
    clean = _sanitize_metadata({"x": None})
    assert clean == {"x": ""}


def test_sanitize_metadata_stringifies_lists_of_non_strings() -> None:
    clean = _sanitize_metadata({"tags": [1, 2, 3]})
    assert clean == {"tags": ["1", "2", "3"]}


# Summariser helpers


def test_summarise_by_city_counts_per_city() -> None:
    docs = [
        Document(text="a", metadata=ReviewMetadata(id="1", city="Lisbon")),
        Document(text="b", metadata=ReviewMetadata(id="2", city="Porto")),
        Document(text="c", metadata=ReviewMetadata(id="3", city="Lisbon")),
    ]
    assert _summarise_by_city(docs) == {"Lisbon": 2, "Porto": 1}


def test_summarise_by_city_labels_missing_city_as_unknown() -> None:
    docs = [
        Document(text="a", metadata=ReviewMetadata(id="1", city="")),
        Document(text="b", metadata=ReviewMetadata(id="2", city="Porto")),
    ]
    counts = _summarise_by_city(docs)
    assert counts["Unknown"] == 1
    assert counts["Porto"] == 1


def test_summarise_by_source_counts_per_source_kind() -> None:
    docs = [
        Document(text="a", metadata=ReviewMetadata(id="r1")),
        Document(text="b", metadata=HouseMetadata(id="h1")),
        Document(text="c", metadata=HouseMetadata(id="h2")),
        Document(text="d", metadata=RoomMetadata(id="rm1")),
    ]
    assert _summarise_by_source(docs) == {"house": 2, "review": 1, "room": 1}


# run_indexing end-to-end with fakes


def test_run_indexing_upserts_all_documents_from_extractor() -> None:
    docs = [
        Document(text="first doc", metadata=ReviewMetadata(id="1", city="Lisbon")),
        Document(text="second doc", metadata=ReviewMetadata(id="2", city="Porto")),
        Document(text="third doc", metadata=ReviewMetadata(id="3", city="Lisbon")),
    ]
    extractor = _FakeExtractor(docs)
    store = _FakeVectorStore()
    embedder = _FakeEmbedder()

    count = run_indexing(
        extractor=extractor,
        store=store,
        embedder=embedder,
    )

    assert count == 3
    # The single batch contains all 3 vectors
    all_vectors = [v for batch in store.upserted_batches for v in batch]
    assert len(all_vectors) == 3
    assert {v["id"] for v in all_vectors} == {"1", "2", "3"}


def test_run_indexing_returns_zero_when_extractor_is_empty() -> None:
    extractor = _FakeExtractor([])
    store = _FakeVectorStore()

    count = run_indexing(extractor=extractor, store=store, embedder=_FakeEmbedder())

    assert count == 0
    assert store.upserted_batches == []


def test_run_indexing_with_reset_calls_delete_all() -> None:
    docs = [Document(text="a", metadata=ReviewMetadata(id="1"))]
    store = _FakeVectorStore()
    # Pre-populate the store to trigger the delete_all branch
    store._count = 5

    run_indexing(
        extractor=_FakeExtractor(docs),
        store=store,
        embedder=_FakeEmbedder(),
        reset=True,
    )

    assert store.delete_all_called


def test_run_indexing_without_reset_does_not_delete_all() -> None:
    docs = [Document(text="a", metadata=ReviewMetadata(id="1"))]
    store = _FakeVectorStore()
    store._count = 5

    run_indexing(
        extractor=_FakeExtractor(docs),
        store=store,
        embedder=_FakeEmbedder(),
        reset=False,
    )

    assert not store.delete_all_called


def test_run_indexing_works_with_description_documents() -> None:
    """Proof that the indexer is truly source-agnostic: house + room docs flow through unchanged."""
    docs = [
        Document(text="house doc", metadata=HouseMetadata(id="house:H1", flatname="X")),
        Document(text="room doc", metadata=RoomMetadata(id="room:R1", roomname="Y")),
    ]
    extractor = _FakeExtractor(docs)
    store = _FakeVectorStore()

    count = run_indexing(
        extractor=extractor,
        store=store,
        embedder=_FakeEmbedder(),
    )

    assert count == 2
    all_vectors = [v for batch in store.upserted_batches for v in batch]
    ids = {v["id"] for v in all_vectors}
    assert ids == {"house:H1", "room:R1"}

    # Verify the metadata carries the source discriminator
    house_vec = next(v for v in all_vectors if v["id"] == "house:H1")
    room_vec = next(v for v in all_vectors if v["id"] == "room:R1")
    assert house_vec["metadata"]["source"] == "house"
    assert room_vec["metadata"]["source"] == "room"


# Conformance check on the fake extractor


def test_fake_extractor_conforms_to_protocol() -> None:
    """Keeps us honest: _FakeExtractor must satisfy the Extractor protocol."""
    fake = _FakeExtractor([])
    assert isinstance(fake, Extractor)