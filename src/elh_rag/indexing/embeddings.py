"""
Embedding model wrapper.

Encapsulates the SentenceTransformer model behind a small interface,
making it injectable into the pipeline and easy to mock in tests.
"""
from __future__ import annotations

import logging
from typing import Any

from elh_rag.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """SentenceTransformer-based embedder for queries and documents."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.embedding_model
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        """Lazily-initialised SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info(
                "Embedding dim: %d", self._model.get_sentence_embedding_dimension()
            )
        return self._model

    @property
    def dimension(self) -> int:
        """Output dimensionality of the embedding model."""
        return int(self.model.get_sentence_embedding_dimension())

    def encode_query(self, text: str) -> list[float]:
        """Encode a single query string into a normalised vector."""
        vec = self.model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def encode_batch(
        self, texts: list[str], batch_size: int | None = None
    ) -> list[list[float]]:
        """Encode a batch of texts into normalised vectors."""
        bs = batch_size or settings.indexing_batch_size
        vecs = self.model.encode(
            texts,
            batch_size=bs,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return vecs.tolist()
