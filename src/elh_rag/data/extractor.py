"""
Extractor protocol — the contract every data source adapter implements.

An extractor is responsible for reading a specific slice of the ELH
database and emitting a stream of `Document` objects ready for indexing.

The protocol is intentionally minimal:
    - `source` identifies the domain
    - `extract()` yields Documents
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from elh_rag.schemas import Document, DocumentSource


@runtime_checkable
class Extractor(Protocol):
    """Contract for any ELH data source extractor.

    Implementations connect to Supabase, execute a query tailored to their
    slice of the schema, and yield `Document` objects. The pipeline stays
    agnostic about the specifics of each source.
    """

    @property
    def source(self) -> DocumentSource:
        """Which document source this extractor produces."""
        ...

    def extract(self) -> Iterable[Document]:
        """Yield Documents ready to be embedded and indexed."""
        ...
