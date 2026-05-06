"""
Entry point to (re)build Pinecone indices from Supabase data.

The indexer supports two corpora:
    - reviews       (elh-reviews index)
    - descriptions  (elh-descriptions index)
"""

from __future__ import annotations

import argparse
import logging

from elh_rag.config import settings
from elh_rag.data.description_extractor import DescriptionExtractor
from elh_rag.data.review_extractor import ReviewExtractor
from elh_rag.indexing.indexer import run_indexing
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


SOURCE_CHOICES = ("reviews", "descriptions", "all")


def index_reviews(reset: bool) -> int:
    """Index student reviews into the reviews Pinecone index."""
    logger.info("=" * 60)
    logger.info("Indexing REVIEWS  →  %s", settings.pinecone_index_name)
    logger.info("=" * 60)
    return run_indexing(
        extractor=ReviewExtractor(),
        store=PineconeVectorStore(index_name=settings.pinecone_index_name),
        reset=reset,
    )


def index_descriptions(reset: bool) -> int:
    """Index house + room descriptions into the descriptions Pinecone index."""
    logger.info("=" * 60)
    logger.info(
        "Indexing DESCRIPTIONS  →  %s",
        settings.pinecone_descriptions_index_name,
    )
    logger.info("=" * 60)
    return run_indexing(
        extractor=DescriptionExtractor(),
        store=PineconeVectorStore(
            index_name=settings.pinecone_descriptions_index_name,
        ),
        reset=reset,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Index ELH data into Pinecone.")
    parser.add_argument(
        "--source",
        choices=SOURCE_CHOICES,
        default="reviews",
        help=("Which corpus to index: reviews (default), descriptions, or all."),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing vectors in the target index before indexing.",
    )
    args = parser.parse_args()

    setup_logging()

    if args.source == "reviews":
        index_reviews(reset=args.reset)
    elif args.source == "descriptions":
        index_descriptions(reset=args.reset)
    elif args.source == "all":
        index_reviews(reset=args.reset)
        index_descriptions(reset=args.reset)


if __name__ == "__main__":
    main()
