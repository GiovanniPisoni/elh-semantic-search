"""
Indexer: build the embeddings of the extracted documents and upsert them
into the vector store.

Source-agnostic: the indexer accepts any `Extractor` implementation and
any `VectorStore` implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from elh_rag.config import settings
from elh_rag.data.extractor import Extractor
from elh_rag.data.review_extractor import ReviewExtractor
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.schemas import Document

logger = logging.getLogger(__name__)
 
# Helpers

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
    vectors: list[dict[str, Any]] = []
    for doc, emb in zip(documents, embeddings):
        metadata = _sanitize_metadata(doc.metadata.to_pinecone_dict())
        metadata["text"] = doc.text
        vectors.append(
            {
                "id": doc.metadata.id,
                "values": emb,
                "metadata": metadata,
            }
        )
    return vectors
 
def _summarise_by_city(documents: list[Document]) -> dict[str, int]:
    """Per-city document count for logging."""
    counts: dict[str, int] = {}
    for doc in documents:
        city = getattr(doc.metadata, "city", None) or "Unknown"
        counts[city] = counts.get(city, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))

def _summarise_by_source(documents: list[Document]) -> dict[str, int]:
    """Per-source document count for logging (useful when mixing HOUSE+ROOM)."""
    counts: dict[str, int] = {}
    for doc in documents:
        source = doc.metadata.source.value
        counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))

# Core indexing routine
 
def run_indexing(
    extractor: Extractor | None = None,
    store: VectorStore | None = None,
    embedder: Embedder | None = None,
    reset: bool = False,
) -> int:
    """Index all documents produced by `extractor` into `store`.
 
    Returns the number of vectors upserted.
    """
    extractor = extractor or ReviewExtractor()
    store = store or PineconeVectorStore()
    embedder = embedder or Embedder()
 
    logger.info("Extracting documents from source=%s", extractor.source.value)
    documents = list(extractor.extract())
    if not documents:
        logger.error("No documents returned by extractor — aborting indexing")
        return 0
 
    for source, n in _summarise_by_source(documents).items():
        logger.info("  source=%-10s %d documents", source, n)
    for city, n in _summarise_by_city(documents).items():
        logger.info("  city=%-15s %d documents", city, n)
 
    existing = store.count()
    logger.info("Vectors already in target index: %d", existing)
    if reset and existing > 0:
        logger.warning("reset=True: deleting all %d existing vectors", existing)
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
