"""``KBContext``: the ctx bundle injected into Tool 6.

Tools 1-5 take a :class:`elh_rag.tools._shared.db.DBExecutor` as
``ctx``. Tool 6 takes a :class:`KBContext` instead — a different ctx
type because the tool's dependency profile is different (loaded KB
+ embedder rather than a SQL connection).
"""

from __future__ import annotations

from pathlib import Path

from elh_rag.indexing.embeddings import Embedder

from ._loader import build_indexed_entries
from ._models import Audience, KBEntry
from ._store import KBStore


class KBContext:
    """Bundle of (KBStore + embedder) injected as ``ctx`` for Tool 6.

    Holds the loaded KB and the embedder used to encode incoming
    questions. Provides a single :meth:`search` entry point that
    delegates to :meth:`KBStore.search` after embedding the query.
    """

    def __init__(self, kb_store: KBStore, embedder: Embedder) -> None:
        self.kb_store = kb_store
        self.embedder = embedder

    def search(
        self,
        question: str,
        *,
        audience: Audience = "student",
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> list[tuple[KBEntry, float]]:
        """Embed the question and delegate to :meth:`KBStore.search`."""
        query_embedding = self.embedder.encode_query(question)
        return self.kb_store.search(
            query_embedding,
            audience=audience,
            top_k=top_k,
            threshold=threshold,
        )

    @classmethod
    def from_yaml(
        cls,
        embedder: Embedder,
        path: Path | None = None,
    ) -> KBContext:
        """Load YAML, embed every (canonical + variants), return ready ctx."""
        indexed = build_indexed_entries(embedder, path)
        return cls(KBStore(indexed), embedder)

    @classmethod
    def from_default_yaml(cls, embedder: Embedder) -> KBContext:
        """Convenience factory: load the bundled ``kb/policies.yaml``."""
        return cls.from_yaml(embedder)
