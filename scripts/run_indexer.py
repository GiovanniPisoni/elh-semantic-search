"""
Entry point to (re)build the Pinecone index from Supabase data.
"""
from __future__ import annotations

import argparse

from elh_rag.indexing.indexer import run_indexing
from elh_rag.logging_setup import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index ELH reviews into Pinecone."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing vectors before indexing.",
    )
    args = parser.parse_args()

    setup_logging()
    run_indexing(reset=args.reset)


if __name__ == "__main__":
    main()
