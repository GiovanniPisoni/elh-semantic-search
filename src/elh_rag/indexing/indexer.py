"""
Indexer: build the embeddings of the extracted documents and upsert them
into the vector store.
"""
from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from elh_rag.config import settings
from elh_rag.data.extractor import fetch_documents, summarise_corpus
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.schemas import Document

logger = logging.getLogger(__name__)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Coerce metadata values to Pinecone-compatible types (str/int/float/bool/list[str])."""
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            clean[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = [str(v) for v in value]
        else:
            clean[key] = str(value)
    return clean


def _build_vectors(
    documents: list[Document], embeddings: list[list[float]]
) -> list[dict[str, Any]]:
    """Pair documents with their embeddings into Pinecone vector dicts."""
    return [
        {
            "id": doc.metadata.id,
            "values": emb,
            "metadata": _sanitize_metadata(doc.metadata.to_pinecone_dict()),
        }
        for doc, emb in zip(documents, embeddings)
    ]


def run_indexing(
    reset: bool = False,
    store: VectorStore | None = None,
    embedder: Embedder | None = None,
) -> int:
    """Index all reviews from Supabase into the vector store.

    Returns the number of vectors upserted.
    """
    store = store or PineconeVectorStore()
    embedder = embedder or Embedder()

    logger.info("Fetching documents from Supabase")
    documents = fetch_documents()
    if not documents:
        logger.error("No documents found — aborting indexing")
        return 0

    for city, n in summarise_corpus(documents).items():
        logger.info("  %-15s %d reviews", city, n)

    existing = store.count()
    logger.info("Vectors already in index: %d", existing)
    if reset and existing > 0:
        logger.warning("--reset requested: deleting all %d existing vectors", existing)
        store.delete_all()

    logger.info("Indexing %d documents", len(documents))

    indexed = 0
    upsert_buffer: list[dict[str, Any]] = []
    batch_size = settings.indexing_batch_size
    upsert_batch = settings.indexing_upsert_batch

    with tqdm(total=len(documents), desc="Indexing", unit="doc") as pbar:
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            texts = [d.text for d in batch]
            embeddings = embedder.encode_batch(texts, batch_size=batch_size)
            upsert_buffer.extend(_build_vectors(batch, embeddings))

            if len(upsert_buffer) >= upsert_batch:
                store.upsert(upsert_buffer)
                indexed += len(upsert_buffer)
                upsert_buffer = []

            pbar.update(len(batch))

    if upsert_buffer:
        store.upsert(upsert_buffer)
        indexed += len(upsert_buffer)

    final = store.count()
    logger.info("Indexed %d documents (store now contains %d vectors)", indexed, final)
    return indexed
