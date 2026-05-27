"""Extract top-K candidates for the Precision@K micro-benchmark.

Loads ``benchmarks/queries/precision_at_k_queries.yaml`` and, for each
query, calls the appropriate semantic RAG tool (``search_descriptions``
or ``search_reviews``) with ``top_k=10`` against live Pinecone.

Outputs two files in ``benchmarks/runs/``:

    * ``precision_at_k_candidates.jsonl`` — machine-readable JSONL,
      one record per query with the full ten candidate hits.

    * ``precision_at_k_candidates_human.txt`` — human-readable companion
      so Giovanni can scan candidates and mark which IDs are truly
      relevant by editing ``precision_at_k_queries.yaml``.

Usage::

    python -m scripts.eval.precision_at_k_extract

Cost: ~$0.01 (only the 10 query strings are embedded; no LLM calls).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from elh_rag.agent import AgentContext
from elh_rag.agent.tools_RAG_corpora import (
    RAGSearchOutput,
    SearchDescriptionsInput,
    SearchReviewsInput,
    search_descriptions,
    search_reviews,
)
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


DEFAULT_QUERIES_FILE = Path("benchmarks/queries/precision_at_k_queries.yaml")
DEFAULT_OUTPUT_DIR = Path("benchmarks/runs")
DEFAULT_JSONL_NAME = "precision_at_k_candidates.jsonl"
DEFAULT_HUMAN_NAME = "precision_at_k_candidates_human.txt"

# Extract more than top_k_evaluate so Giovanni sees the full neighborhood
# of candidates when annotating ground truth.
EXTRACT_TOP_K = 10

# How many characters of the chunk text to show in the human file.
HUMAN_TEXT_PREVIEW = 200

# Which metadata fields to surface in the human-readable file, per corpus.
HUMAN_METADATA_FIELDS = {
    "search_descriptions": ("source", "city", "zone", "neighbourhood", "flatname", "roomname"),
    "search_reviews": (
        "city",
        "neighbourhood",
        "flatname",
        "overall_rating",
        "cleaning_rating",
        "communication_rating",
        "location_rating",
        "review_title",
    ),
}


@dataclass(frozen=True)
class QuerySpec:
    """One row from the precision_at_k_queries.yaml file."""

    id: str
    query: str
    tool: str
    top_k_evaluate: int
    relevant_source_ids: list[str]
    notes: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuerySpec:
        return cls(
            id=d["id"],
            query=d["query"],
            tool=d["tool"],
            top_k_evaluate=int(d.get("top_k_evaluate", 5)),
            relevant_source_ids=list(d.get("relevant_source_ids") or []),
            notes=str(d.get("notes", "")),
        )


def load_queries(path: Path) -> list[QuerySpec]:
    """Load and parse the YAML query set."""
    if not path.exists():
        raise FileNotFoundError(f"Queries file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "queries" not in raw:
        raise ValueError(f"Invalid YAML schema: top-level key 'queries' required in {path}")
    return [QuerySpec.from_dict(q) for q in raw["queries"]]


def run_one_query(qspec: QuerySpec, ctx: AgentContext) -> RAGSearchOutput:
    """Dispatch to the right tool and return the raw RAGSearchOutput."""
    if qspec.tool == "search_descriptions":
        payload = SearchDescriptionsInput(query=qspec.query, top_k=EXTRACT_TOP_K)
        return search_descriptions(payload, ctx=ctx)
    if qspec.tool == "search_reviews":
        payload = SearchReviewsInput(query=qspec.query, top_k=EXTRACT_TOP_K)
        return search_reviews(payload, ctx=ctx)
    raise ValueError(
        f"query {qspec.id!r}: unknown tool {qspec.tool!r} "
        "(expected 'search_descriptions' or 'search_reviews')"
    )


def _record_for_jsonl(qspec: QuerySpec, output: RAGSearchOutput) -> dict[str, Any]:
    """Build the JSONL record for one query."""
    return {
        "id": qspec.id,
        "query": qspec.query,
        "tool": qspec.tool,
        "top_k_evaluate": qspec.top_k_evaluate,
        "corpus": output.corpus,
        "candidates": [
            {
                "rank": i + 1,
                "source_id": h.source_id,
                "score": h.score,
                "text": h.text,
                "metadata": h.metadata,
            }
            for i, h in enumerate(output.hits)
        ],
    }


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    """Atomically write the JSONL output."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
    tmp.replace(output_path)


def _format_metadata(tool: str, metadata: dict[str, Any]) -> str:
    """Pick the most relevant metadata fields for the human file."""
    fields = HUMAN_METADATA_FIELDS.get(tool, ())
    parts = []
    for key in fields:
        val = metadata.get(key)
        if val in (None, "", 0):
            continue
        parts.append(f"{key}={val}")
    return ", ".join(parts) if parts else "(no metadata)"


def _format_text_preview(text: str, limit: int = HUMAN_TEXT_PREVIEW) -> str:
    """Truncate and single-line the chunk text for the human file."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "..."


def write_human_file(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write the human-readable companion file for manual annotation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("Precision@K candidates — manual annotation worksheet")
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        "For each query below, decide which source_ids in the top-10 truly answer "
        "the query."
    )
    lines.append(
        "Then open precision_at_k_queries.yaml and fill relevant_source_ids with "
        "those IDs."
    )
    lines.append("")

    for rec in records:
        lines.append("=" * 78)
        lines.append(f"QUERY {rec['id']}  ({rec['tool']}, corpus={rec['corpus']})")
        lines.append(f'  text: "{rec["query"]}"')
        lines.append(f"  top_k_evaluate (P@K cutoff): {rec['top_k_evaluate']}")
        lines.append("-" * 78)

        candidates = rec["candidates"]
        if not candidates:
            lines.append("  (no candidates returned)")
            lines.append("")
            continue

        for cand in candidates:
            rank = cand["rank"]
            sid = cand["source_id"]
            score = cand["score"]
            meta_str = _format_metadata(rec["tool"], cand.get("metadata") or {})
            text_str = _format_text_preview(cand.get("text", ""))
            lines.append(f"  [{rank:2d}] **{sid}**   score={score:.3f}")
            lines.append(f"       meta: {meta_str}")
            lines.append(f"       text: {text_str}")
        lines.append("")

    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    tmp.replace(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES_FILE,
        help=f"YAML query file (default: {DEFAULT_QUERIES_FILE}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    queries = load_queries(args.queries)
    print(f"Loaded {len(queries)} queries from {args.queries}")

    print("Building AgentContext (loads embedder + Pinecone clients)...")
    ctx = AgentContext.build()
    print("AgentContext ready.\n")

    records: list[dict[str, Any]] = []
    failures = 0

    for i, qspec in enumerate(queries, start=1):
        prefix = f"[{i}/{len(queries)}] {qspec.id} ({qspec.tool})"
        print(f"{prefix} ...", end=" ", flush=True)
        try:
            output = run_one_query(qspec, ctx)
            record = _record_for_jsonl(qspec, output)
            records.append(record)
            print(f"OK ({len(output.hits)} candidates)")
        except Exception as exc:
            failures += 1
            logger.exception("extract: query %r failed", qspec.id)
            print(f"FAILED: {type(exc).__name__}: {exc}")

    jsonl_path = args.output_dir / DEFAULT_JSONL_NAME
    human_path = args.output_dir / DEFAULT_HUMAN_NAME
    write_jsonl(records, jsonl_path)
    write_human_file(records, human_path)

    print()
    print(f"DONE  queries={len(queries)}  failures={failures}")
    print(f"JSONL : {jsonl_path}")
    print(f"Human : {human_path}")
    print()
    print("Next step: open precision_at_k_queries.yaml and fill in")
    print("relevant_source_ids for each query based on the human file above,")
    print("then run scripts/eval/precision_at_k_compute.py.")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
