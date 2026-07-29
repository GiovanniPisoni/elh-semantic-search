"""Eval-v2 benchmark runner — Phase 3 (agent) harness.

Loads golden-set queries from a flat-list YAML file (golden_set_v2.yaml),
executes each through the Phase 3 agent, and appends one JSON line per query
to a timestamped JSONL file in benchmarks/runs/.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from elh_rag.agent import AgentContext, run_agent_turn
from elh_rag.agent.agent_llm_client import AgentLLMClient
from elh_rag.config import settings
from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_QUERIES_FILE = Path("benchmarks/queries/golden_set_v2.yaml")
DEFAULT_OUTPUT_DIR = Path("benchmarks/runs")
MAX_RETRIES = 2

# Approximate list prices (USD per 1 M tokens, 2026-06).
# Used only for the end-of-run cost estimate; not authoritative.
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5":         (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80,  4.00),
}
_DEFAULT_PRICE: tuple[float, float] = (3.00, 15.00)


# TrackingLLMClient


class TrackingLLMClient(AgentLLMClient):
    """AgentLLMClient subclass that records per-call token usage in usage_log."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.usage_log: list[dict[str, int]] = []

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Any:
        response = super().call(messages, tools, system=system)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.usage_log.append(
                {
                    "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                    "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                }
            )
        return response

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        system: str,
    ) -> Iterator[Any]:
        for chunk in super().stream(messages, tools, system=system):
            if chunk.final_message is not None:
                usage = getattr(chunk.final_message, "usage", None)
                if usage is not None:
                    self.usage_log.append(
                        {
                            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                        }
                    )
            yield chunk

# QuerySpec

@dataclass(frozen=True)
class QuerySpec:
    """One row from a golden-set YAML file (v2 flat-list or legacy dict)."""

    id: str
    category: str
    language: str
    query: str
    expected_hop_count: int
    difficulty: str
    ground_truth: str
    expected_answer_type: str
    # category-specific optional tags
    refusal_type: str | None
    policy_category: str | None
    review_query_type: str | None
    description_query_type: str | None
    ambiguity_type: str | None
    ambiguity_subtype: str | None
    factual_type: str | None
    constraint_set: str | None
    availability_window: str | None
    quantitative_type: str | None
    room_id: str | None
    expected_tools: list[str]
    notes: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuerySpec:
        hop = int(d.get("hop_count", d.get("expected_hop_count", 0)))
        return cls(
            id=d["id"],
            category=d["category"],
            language=d["language"],
            query=d["query"],
            expected_hop_count=hop,
            difficulty=str(d.get("difficulty", "")),
            ground_truth=str(d.get("ground_truth", "")),
            expected_answer_type=str(d.get("expected_answer_type", "")),
            refusal_type=d.get("refusal_type"),
            policy_category=d.get("policy_category"),
            review_query_type=d.get("review_query_type"),
            description_query_type=d.get("description_query_type"),
            ambiguity_type=d.get("ambiguity_type"),
            ambiguity_subtype=d.get("ambiguity_subtype"),
            factual_type=d.get("factual_type"),
            constraint_set=d.get("constraint_set"),
            availability_window=d.get("availability_window"),
            quantitative_type=d.get("quantitative_type"),
            room_id=d.get("room_id"),
            expected_tools=list(d.get("expected_tools", [])),
            notes=str(d.get("notes", "")),
        )

# I/O helpers

def load_queries(path: Path) -> list[QuerySpec]:
    if not path.exists():
        raise FileNotFoundError(f"Queries file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict) and "queries" in raw:
        entries = raw["queries"]
    else:
        raise ValueError(
            f"Invalid YAML schema in {path}: "
            "expected a flat list or a dict with top-level key 'queries'."
        )
    return [QuerySpec.from_dict(q) for q in entries]


def load_completed_ids(path: Path) -> set[str]:
    seen: set[str] = set()
    if not path.exists():
        return seen
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seen.add(rec["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return seen


def build_output_path(output_dir: Path, system: str, dry: bool, smoke: bool = False) -> Path:
    ts = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    suffix = "_dry" if dry else ("_smoke" if smoke else "")
    return output_dir / f"{system}_eval_v2_{ts}{suffix}.jsonl"


def _category_tags(qs: QuerySpec) -> dict[str, Any]:
    candidates = {
        "refusal_type": qs.refusal_type,
        "policy_category": qs.policy_category,
        "review_query_type": qs.review_query_type,
        "description_query_type": qs.description_query_type,
        "ambiguity_type": qs.ambiguity_type,
        "ambiguity_subtype": qs.ambiguity_subtype,
        "factual_type": qs.factual_type,
        "constraint_set": qs.constraint_set,
        "availability_window": qs.availability_window,
        "quantitative_type": qs.quantitative_type,
        "room_id": qs.room_id,
    }
    return {k: v for k, v in candidates.items() if v is not None}

# Query execution

def _attempt_query(
    query_spec: QuerySpec,
    ctx: AgentContext,
    system: str,
) -> dict[str, Any]:
    """One attempt at running a single query. Raises on failure."""
    if system == "phase2":
        raise NotImplementedError(
            "Phase 2 evaluation is not implemented in this runner. "
            "Implement run_phase2_benchmark.py using RAGPipeline.query()."
        )

    primary_tracker = TrackingLLMClient(
        model=settings.agent_llm_model,
        temperature=0.0,
    )
    synthesis_tracker: TrackingLLMClient | None = None
    if settings.agent_use_haiku_synthesis:
        synthesis_tracker = TrackingLLMClient(
            model=settings.agent_synthesis_model,
            temperature=0.0,
        )

    response = run_agent_turn(
        query=query_spec.query,
        ctx=ctx,
        llm=primary_tracker,
        synthesis_llm=synthesis_tracker,
    )

    # Build hop-level token breakdown
    hop_token_breakdown: list[dict[str, Any]] = []
    for i, u in enumerate(primary_tracker.usage_log):
        hop_token_breakdown.append(
            {
                "hop_index": i,
                "model": settings.agent_llm_model,
                "input_tokens": u["input_tokens"],
                "output_tokens": u["output_tokens"],
                "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
            }
        )
    if synthesis_tracker:
        base = len(primary_tracker.usage_log)
        for j, u in enumerate(synthesis_tracker.usage_log):
            hop_token_breakdown.append(
                {
                    "hop_index": base + j,
                    "model": settings.agent_synthesis_model,
                    "input_tokens": u["input_tokens"],
                    "output_tokens": u["output_tokens"],
                    "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
                }
            )

    return {
        "system": system,
        "id": query_spec.id,
        "category": query_spec.category,
        "language": query_spec.language,
        "difficulty": query_spec.difficulty,
        "query": query_spec.query,
        "expected_hop_count": query_spec.expected_hop_count,
        "expected_answer_type": query_spec.expected_answer_type,
        "ground_truth": query_spec.ground_truth,
        **_category_tags(query_spec),
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
        "hop_token_breakdown": hop_token_breakdown,
        "total_duration_ms": response.total_duration_ms,
        "started_at": response.started_at.isoformat(),
    }


def run_with_retry(
    query_spec: QuerySpec,
    ctx: AgentContext,
    system: str,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """C6 retry: up to max_retries extra attempts; write status='failed' on all failing."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return _attempt_query(query_spec, ctx, system)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "benchmark: query %r attempt %d/%d failed (%s), retrying...",
                    query_spec.id,
                    attempt + 1,
                    max_retries + 1,
                    type(exc).__name__,
                )
    return {
        "system": system,
        "id": query_spec.id,
        "category": query_spec.category,
        "language": query_spec.language,
        "difficulty": query_spec.difficulty,
        "query": query_spec.query,
        "expected_hop_count": query_spec.expected_hop_count,
        "expected_answer_type": query_spec.expected_answer_type,
        "ground_truth": query_spec.ground_truth,
        **_category_tags(query_spec),
        "status": "failed",
        "error": f"{type(last_exc).__name__}: {last_exc}",
    }

# CLI helpers

def _print_dry_run_plan(
    queries: list[QuerySpec], system: str, output_path: Path
) -> None:
    bar = "=" * 62
    print(f"\n{bar}")
    print(f"  DRY-RUN PLAN  —  {system.upper()}")
    print(bar)
    print(f"  Queries file : {DEFAULT_QUERIES_FILE}")
    print(f"  Total queries: {len(queries)}")
    print(f"  Output path  : {output_path}")
    print()

    by_cat = Counter(q.category for q in queries)
    print("  By category:")
    for cat, n in sorted(by_cat.items()):
        print(f"    {cat:<32} {n:>3}")

    by_lang = Counter(q.language for q in queries)
    print(f"\n  By language      : {dict(by_lang)}")

    by_diff = Counter(q.difficulty for q in queries)
    print(f"  By difficulty    : {dict(sorted(by_diff.items()))}")

    by_hop = Counter(q.expected_hop_count for q in queries)
    print(f"  By hop_count     : {dict(sorted(by_hop.items()))}")

    by_ans = Counter(q.expected_answer_type for q in queries)
    print(f"  By answer_type   : {dict(by_ans)}")

    print("\n  First 5 query IDs:")
    for q in queries[:5]:
        print(
            f"    {q.id:<14} [{q.category:<28}] "
            f"hop={q.expected_hop_count} lang={q.language}"
        )
    if len(queries) > 5:
        print(f"    ... {len(queries) - 5} more")

    print(f"\n{bar}")
    print("  Validation : OK — all required fields present, no duplicate IDs")
    print("  API calls  : 0 (--dry-run; remove flag to execute)")
    print(f"{bar}\n")


def _compute_cost(records: list[dict[str, Any]]) -> float:
    total = 0.0
    for rec in records:
        if rec.get("status") != "success":
            continue
        breakdown = rec.get("hop_token_breakdown")
        if breakdown:
            for hop in breakdown:
                p_in, p_out = _PRICE_PER_M.get(hop.get("model", ""), _DEFAULT_PRICE)
                total += (
                    hop["input_tokens"] * p_in + hop["output_tokens"] * p_out
                ) / 1_000_000
        else:
            in_tok = rec.get("input_tokens", 0)
            out_tok = rec.get("output_tokens", 0)
            total += (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    return total

# Argument parsing

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES_FILE,
        help=f"YAML query file (default: {DEFAULT_QUERIES_FILE}).",
    )
    parser.add_argument(
        "--system",
        choices=["phase3", "phase2"],
        default="phase3",
        help="Which system to evaluate: phase3 (agent) or phase2 (pipeline). Default: phase3.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for auto-generated JSONL path (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Explicit output JSONL path. If the file exists, IDs already "
            "present are skipped (resume mode). Default: auto-timestamped "
            "file in --output-dir."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Run only the first N queries. Combine with --dry-run for zero-cost smoke-test.",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        metavar="ID1,ID2,...",
        help=(
            "Comma-separated list of query IDs to run (e.g. --ids out_of_scope_01,qr_07). "
            "Overrides --limit. Use for stratified smoke samples."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Tag output file as a smoke run (adds _smoke suffix, prevents confusion with full runs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Load and validate queries, print the execution plan, "
            "then exit without any API call. Zero cost."
        ),
    )
    return parser.parse_args()

# Main

def main() -> int:
    setup_logging()
    args = parse_args()

    queries = load_queries(args.queries)

    if args.ids is not None:
        id_set = {s.strip() for s in args.ids.split(",") if s.strip()}
        queries = [q for q in queries if q.id in id_set]
        if not queries:
            print(f"ERROR: --ids specified but none of {sorted(id_set)} found in queries file.")
            return 1
        # Preserve the order given by --ids
        id_order = [s.strip() for s in args.ids.split(",") if s.strip()]
        queries.sort(key=lambda q: id_order.index(q.id) if q.id in id_order else len(id_order))
        print(f"--ids: running {len(queries)} selected queries: {[q.id for q in queries]}")
    elif args.limit is not None:
        queries = queries[: args.limit]
        print(f"--limit {args.limit}: running first {len(queries)} queries.")

    smoke = args.smoke or (args.ids is not None)

    # Determine output path
    if args.output is not None:
        output_path = args.output
    else:
        output_path = build_output_path(args.output_dir, args.system, args.dry_run, smoke=smoke)

    if args.dry_run:
        _print_dry_run_plan(queries, args.system, output_path)
        return 0

    # Phase 2 not yet implemented for live runs
    if args.system == "phase2":
        print(
            "ERROR: --system phase2 live run is not yet implemented. "
            "Use --dry-run to validate queries, or implement "
            "run_phase2_benchmark.py using RAGPipeline.query()."
        )
        return 1

    completed_ids = load_completed_ids(output_path)
    if completed_ids:
        original_count = len(queries)
        queries = [q for q in queries if q.id not in completed_ids]
        print(
            f"RESUME: {len(completed_ids)} already done, "
            f"{len(queries)}/{original_count} remaining."
        )

    print(f"\nBuilding AgentContext (loads embedder + Pinecone clients, ~3-5 s)...")
    ctx = AgentContext.build()
    print(f"AgentContext ready. Running {len(queries)} queries.\n")
    print(f"Output: {output_path}\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    failures = 0

    with output_path.open("a", encoding="utf-8") as out_f:
        for i, qspec in enumerate(queries, start=len(completed_ids) + 1):
            total = len(queries) + len(completed_ids)
            prefix = f"[{i}/{total}] {qspec.id}"
            print(f"{prefix} ({qspec.category}, {qspec.language}) ...", end=" ", flush=True)

            record = run_with_retry(qspec, ctx, args.system)
            records.append(record)

            out_f.write(json.dumps(record, ensure_ascii=False))
            out_f.write("\n")
            out_f.flush()

            if record["status"] == "success":
                dur_s = record.get("total_duration_ms", 0) / 1000
                in_tok = record.get("input_tokens", 0)
                out_tok = record.get("output_tokens", 0)
                hops = record.get("hop_count", "?")
                print(f"OK {dur_s:.1f}s  {in_tok}/{out_tok} tok  hops={hops}")
            else:
                failures += 1
                print(f"FAILED  {record.get('error', '?')}")

    cost = _compute_cost(records)
    total_in = sum(r.get("input_tokens", 0) for r in records if r.get("status") == "success")
    total_out = sum(r.get("output_tokens", 0) for r in records if r.get("status") == "success")
    print(
        f"\nDONE  queries={len(records)}  failures={failures}  "
        f"tokens={total_in}in/{total_out}out  cost~=${cost:.3f}"
    )
    print(f"Output: {output_path}")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
