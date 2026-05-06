"""
Logging setup for the ELH RAG system.
"""

from __future__ import annotations

import logging
import sys

from elh_rag.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger for the entire application."""
    log_level = (level or settings.log_level).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Tame noisy third-party loggers
    for noisy in ("httpx", "urllib3", "sentence_transformers", "pinecone"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
