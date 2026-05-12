"""YAML loader and cross-ref validation for the policy KB.

Two functions surface from here:

    * :func:`load_entries` — read and validate ``policies.yaml``,
      returning a list of :class:`._models.KBEntry`. Pure I/O.
    * :func:`build_indexed_entries` — convenience that loads the YAML,
      embeds every (canonical + variants) text with a caller-supplied
      embedder, and wraps each in an :class:`._models.IndexedEntry`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import yaml

from ._models import IndexedEntry, KBEntry

logger = logging.getLogger(__name__)


_DEFAULT_KB_PATH = Path(__file__).parent / "kb" / "policies.yaml"


# Embedder protocol


class _Embedder(Protocol):
    """Minimal subset of :class:`elh_rag.indexing.embeddings.Embedder`.

    Declared locally to keep this module independent of the embedder
    implementation — useful for tests that pass a stub.
    """

    def encode_batch(
        self, texts: list[str], batch_size: int | None = None
    ) -> list[list[float]]: ...


# Public API


def load_entries(path: Path | None = None) -> list[KBEntry]:
    """Read the YAML file and validate every entry.

    Raises:
        FileNotFoundError: the YAML file is missing.
        ValueError: top-level shape is wrong (not a mapping with an
            ``entries`` key, or ``entries`` is not a list).
        pydantic.ValidationError: an entry violates the
            :class:`._models.KBEntry` schema (missing field, invalid
            audience, etc.).
    """
    p = path or _DEFAULT_KB_PATH
    if not p.is_file():
        raise FileNotFoundError(f"KB YAML not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "entries" not in data:
        raise ValueError(f"KB YAML at {p} must be a mapping with an 'entries' key")
    raw_entries = data["entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("KB YAML 'entries' must be a list")
    entries = [KBEntry.model_validate(item) for item in raw_entries]
    _validate_cross_refs(entries)
    return entries


def build_indexed_entries(
    embedder: _Embedder,
    path: Path | None = None,
) -> list[IndexedEntry]:
    """Load + embed in one pass. Used by :meth:`._context.KBContext` factories."""
    entries = load_entries(path)
    indexed: list[IndexedEntry] = []
    for entry in entries:
        texts = [entry.canonical_question, *entry.question_variants]
        embeddings = embedder.encode_batch(texts)
        indexed.append(IndexedEntry(entry=entry, variant_embeddings=embeddings))
    logger.info(
        "KB loaded: %d entries, %d total variant embeddings",
        len(indexed),
        sum(len(ie.variant_embeddings) for ie in indexed),
    )
    return indexed


# Internal: cross-ref validation


def _validate_cross_refs(entries: list[KBEntry]) -> None:
    """Warn (don't fail) on dangling ``related`` IDs.

    A dangling ref is a sign the YAML went stale (entry id renamed
    without updating cross-refs) but it doesn't break behaviour: the
    LLM just won't get that follow-up suggestion. So we log and move
    on rather than blocking startup.
    """
    known_ids = {e.id for e in entries}
    for e in entries:
        for ref in e.related:
            if ref not in known_ids:
                logger.warning(
                    "KB entry %r references unknown related id %r",
                    e.id,
                    ref,
                )
