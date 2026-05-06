"""Tests for the Extractor protocol itself (no DB calls).

The protocol is the contract every data source adapter implements.
These tests verify that:
    1. Concrete extractors actually conform to the protocol at runtime
    2. The protocol is minimal enough that fake implementations work
"""

from __future__ import annotations

from collections.abc import Iterable

from elh_rag.data.extractor import Extractor
from elh_rag.data.review_extractor import ReviewExtractor
from elh_rag.schemas import Document, DocumentSource, ReviewMetadata

# Conformance of the real extractor


def test_review_extractor_conforms_to_protocol() -> None:
    """ReviewExtractor must be recognised as an Extractor at runtime.

    Uses @runtime_checkable on the protocol + isinstance check. If this
    fails, it means ReviewExtractor is missing a required attribute or
    method from the protocol.
    """
    extractor = ReviewExtractor(db_uri="fake", min_text_length=1)
    assert isinstance(extractor, Extractor)


def test_review_extractor_source_is_review() -> None:
    extractor = ReviewExtractor(db_uri="fake", min_text_length=1)
    assert extractor.source == DocumentSource.REVIEW


# A trivial fake implementation to prove the protocol is usable


class _FakeExtractor:
    """Minimal example showing what it takes to implement Extractor."""

    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    @property
    def source(self) -> DocumentSource:
        return DocumentSource.REVIEW

    def extract(self) -> Iterable[Document]:
        return iter(self._docs)


def test_fake_extractor_conforms_to_protocol() -> None:
    """A minimal class with just `source` and `extract()` should be accepted."""
    fake = _FakeExtractor([])
    assert isinstance(fake, Extractor)


def test_fake_extractor_yields_provided_documents() -> None:
    docs = [
        Document(text="doc 1", metadata=ReviewMetadata(id="1")),
        Document(text="doc 2", metadata=ReviewMetadata(id="2")),
    ]
    fake = _FakeExtractor(docs)

    result = list(fake.extract())

    assert result == docs
