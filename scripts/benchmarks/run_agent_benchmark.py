"""Run the agent benchmark.

Loads queries from a YAML file (default
``benchmarks/queries/agent_queries.yaml``), executes each query
through :func:`elh_rag.agent.run_agent_turn` against live services,
and writes one JSON line per query to a timestamped file in
``benchmarks/runs/``.

The script is resilient: a single-query failure logs the error and
continues with the remaining queries; the failure record is still
written to the JSONL output for analysis.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from elh_rag.agent import AgentContext, run_agent_turn
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


DEFAULT_QUERIES_FILE = Path("benchmarks/queries/agent_queries.yaml")
DEFAULT_OUTPUT_DIR = Path("benchmarks/runs")


@dataclass(frozen=True)
class QuerySpec:
    """One row from the YAML query set."""

    id: str
    category: str
    language: str
    query: str
    expected_tools: list[str]
    expected_hop_count: int
    notes: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuerySpec:
        return cls(
            id=d["id"],
            category=d["category"],
            language=d["language"],
            query=d["query"],
            expected_tools=list(d.get("expected_tools", [])),
            expected_hop_count=int(d.get("expected_hop_count", 0)),
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


def run_one_query(query_spec: QuerySpec, ctx: AgentContext) -> dict[str, Any]:
    """Execute one query. Return a JSON-serialisable result dict.

    Captures either the AgentResponse fields (on success) or an
    error record (on failure). Always returns a dict so the JSONL
    is uniform.
    """
    record: dict[str, Any] = {
        "id": query_spec.id,
        "category": query_spec.category,
        "language": query_spec.language,
        "query": query_spec.query,
        "expected_tools": query_spec.expected_tools,
        "expected_hop_count": query_spec.expected_hop_count,
        "notes": query_spec.notes,
    }
    started = time.perf_counter()
    try:
        response = run_agent_turn(query=query_spec.query, ctx=ctx)
        record.update(
            {
                "status": "success",
                "final_message": response.final_message,
                "stop_reason": response.stop_reason,
                "hop_count": response.hop_count,
                "tools_used": [t.name for t in response.tool_trace],
                "tool_trace": [
                    {
                        "hop_index": t.hop_index,
                        "name": t.name,
                        "duration_ms": t.duration_ms,
                        "error": t.error,
                    }
                    for t in response.tool_trace
                ],
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_duration_ms": response.total_duration_ms,
                "started_at": response.started_at.isoformat(),
            }
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        record.update(
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": elapsed_ms,
            }
        )
        logger.exception("benchmark: query %r failed", query_spec.id)
    return record


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    """Atomically write a list of records as JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
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
        help=f"Output directory for the JSONL run file (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only the first 3 queries (smoke-test mode, ~0.30 USD).",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    queries = load_queries(args.queries)
    if args.dry_run:
        queries = queries[:3]
        print(f"DRY-RUN: limiting to first {len(queries)} queries.")

    print("\nBuilding AgentContext (this loads the embedder, ~2-4 s)...")
    ctx = AgentContext.build()
    print(f"AgentContext ready. Running {len(queries)} queries.\n")

    records: list[dict[str, Any]] = []
    total_input_tokens = 0
    total_output_tokens = 0
    failures = 0

    for i, qspec in enumerate(queries, start=1):
        prefix = f"[{i}/{len(queries)}] {qspec.id}"
        print(f"{prefix} ({qspec.category}, {qspec.language}) ...", end=" ", flush=True)

        record = run_one_query(qspec, ctx)
        records.append(record)

        if record["status"] == "success":
            dur_s = record["total_duration_ms"] / 1000
            in_tok = record["input_tokens"]
            out_tok = record["output_tokens"]
            tools = record["tools_used"]
            total_input_tokens += in_tok
            total_output_tokens += out_tok
            print(f"OK {dur_s:.1f}s, {in_tok}/{out_tok} tok, tools={tools}")
        else:
            failures += 1
            print(f"FAILED: {record['error']}")

    # Write JSONL with timestamp
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    suffix = "-dry" if args.dry_run else ""
    output_path = args.output_dir / f"agent_benchmark_{timestamp}{suffix}.jsonl"
    write_jsonl(records, output_path)

    # Summary
    cost = (total_input_tokens * 3.0 + total_output_tokens * 15.0) / 1_000_000
    print(
        f"\nDONE  queries={len(queries)}  failures={failures}  "
        f"tokens={total_input_tokens}in/{total_output_tokens}out  "
        f"cost=${cost:.2f}"
    )
    print(f"Output written to: {output_path}")
    return 1 if failures > 0 and not args.dry_run else 0


if __name__ == "__main__":
    sys.exit(main())
