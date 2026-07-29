"""Phase 2 (pipelined RAG) eval-v2 runner.

Loads the same golden_set_v2.yaml used by run_eval_v2.py (Phase 3), sends
each query through the frozen Phase 2 RAGPipeline, and writes one JSONL
record per query in the SAME schema as the Phase 3 runner so downstream
comparison scripts can process both files uniformly.

Architecture recap (Phase 2 — fixed 3-LLM-call pipeline)
---------------------------------------------------------
  1. QueryRewriter  (Haiku)  → search-optimised rewrite of the user query
  2. IntentRouter   (Haiku)  → REVIEWS / DESCRIPTIONS / BOTH routing decision
  3. Generator      (Sonnet) → final answer from retrieved context

Token-tracking injection (no frozen-code change)
-------------------------------------------------
Phase 2's LLMClient.complete() discards response.usage and returns only the
text.  TrackingLLMClient is a thin subclass that overrides complete() to
capture response.usage BEFORE returning — no logic change, only observation.

Three separate TrackingLLMClient instances are created (one per role) and
injected via constructor arguments:
  • rewriter_tracker  → QueryRewriter(llm_client=rewriter_tracker)
  • router_tracker    → IntentRouter(llm_client=router_tracker)
  • generator_tracker → RAGPipeline(llm_client=generator_tracker, ...)

Before each query all three usage_log lists are cleared; after pipeline.query()
returns the logs contain exactly the tokens consumed by that query.

LRU-cache caveat: QueryRewriter wraps _rewrite_uncached in an lru_cache.
If two queries produce the same LLM rewrite, only the first call logs tokens;
subsequent hits are cache-served at zero cost.  With 96 distinct eval queries
this is unlikely, but the comment in hop_token_breakdown flags it.

Output schema
-------------
Matches Phase 3 JSONL schema (run_eval_v2.py) with three additions:
  • hop_token_breakdown  per-role breakdown (role=rewriter/router/generator)
  • phase2_pipeline_steps = 3  (informational; distinct from hop_count)
  • phase2_* observable fields: routing_intent, routing_confidence,
    routing_source, rewritten_query, retrieval_sources_n

hop_count in the record = the query's hop_count tag from the golden set
(for H2 hypothesis grouping); it does NOT reflect Phase 2's pipeline steps.

Output directory (default): ../../elh-semantic-search/benchmarks/runs/
Both Phase 2 and Phase 3 runs land in the same directory for easy comparison.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from elh_rag.generation.llm_client import LLMClient
from elh_rag.logging_setup import setup_logging
from elh_rag.pipeline import RAGPipeline
from elh_rag.retrieval.intent_router import IntentRouter
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.config import settings

logger = logging.getLogger(__name__)

# Phase 2 root and sibling Phase 3 root (resolved at import time)
_P2_ROOT = Path(__file__).resolve().parents[2]          # elh-rag-p2/
_P3_ROOT = _P2_ROOT.parent / "elh-semantic-search"      # elh-semantic-search/

DEFAULT_QUERIES_FILE = _P3_ROOT / "benchmarks" / "queries" / "golden_set_v2.yaml"
DEFAULT_OUTPUT_DIR   = _P3_ROOT / "benchmarks" / "runs"
MAX_RETRIES = 2

# The frozen Phase 2 config uses claude-sonnet-4-20250514 (EOL 2026-06-15).
# The runner injects a current equivalent so the API call succeeds.
# Haiku rewriter/router use settings.llm_rewriter_model / intent_router_model
# (both default to claude-haiku-4-5-20251001, which is current).
_GENERATOR_MODEL = "claude-sonnet-4-5"

# Approximate list prices (USD per 1 M tokens, 2026-06).
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001":  (0.80,  4.00),
    "claude-sonnet-4-20250514":   (3.00, 15.00),  # kept for legacy records
    "claude-sonnet-4-5":          (3.00, 15.00),
}
_DEFAULT_PRICE: tuple[float, float] = (3.00, 15.00)

# Single warm-up query to load the CrossEncoder model before timed runs.
_WARMUP_QUERY = "What are the best rooms in Lisbon?"


# ---------------------------------------------------------------------------
# TrackingLLMClient — per-call token capture without touching frozen code
# ---------------------------------------------------------------------------


class TrackingLLMClient(LLMClient):
    """LLMClient subclass that captures response.usage before returning text.

    Injection: pass an instance as llm_client= to QueryRewriter, IntentRouter,
    or RAGPipeline.  Clear usage_log before each pipeline.query() call and
    read it after to get that query's token counts for this role.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.usage_log: list[dict[str, int]] = []

    def complete(self, system: str, user: str) -> str:
        logger.debug("TrackingLLMClient.complete: model=%s", self._model)
        response = self.client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.usage_log.append(
                {
                    "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                }
            )
        return response.content[0].text


# ---------------------------------------------------------------------------
# QuerySpec (flat v2 golden-set format)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuerySpec:
    """One row from the golden_set_v2 YAML (flat list)."""

    id: str
    category: str
    language: str
    query: str
    expected_hop_count: int
    difficulty: str
    ground_truth: str
    expected_answer_type: str
    # optional category-specific tags
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
        )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_queries(path: Path) -> list[QuerySpec]:
    """Accept flat list (golden_set_v2) or legacy {queries:[...]} dict."""
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
    """Collect IDs already written to an existing JSONL (for resume)."""
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


def build_output_path(output_dir: Path, dry: bool, smoke: bool = False) -> Path:
    ts = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    suffix = "_dry" if dry else ("_smoke" if smoke else "")
    return output_dir / f"phase2_eval_v2_{ts}{suffix}.jsonl"


def _category_tags(qs: QuerySpec) -> dict[str, Any]:
    candidates = {
        "refusal_type":           qs.refusal_type,
        "policy_category":        qs.policy_category,
        "review_query_type":      qs.review_query_type,
        "description_query_type": qs.description_query_type,
        "ambiguity_type":         qs.ambiguity_type,
        "ambiguity_subtype":      qs.ambiguity_subtype,
        "factual_type":           qs.factual_type,
        "constraint_set":         qs.constraint_set,
        "availability_window":    qs.availability_window,
        "quantitative_type":      qs.quantitative_type,
        "room_id":                qs.room_id,
    }
    return {k: v for k, v in candidates.items() if v is not None}


# ---------------------------------------------------------------------------
# Pipeline factory — built ONCE, shared across all queries
# ---------------------------------------------------------------------------


def build_pipeline() -> tuple[RAGPipeline, TrackingLLMClient, TrackingLLMClient, TrackingLLMClient]:
    """Construct RAGPipeline with injected tracking clients.

    Returns (pipeline, rewriter_tracker, router_tracker, generator_tracker).
    Clear all three trackers' usage_log before each pipeline.query() call.

    Injection map (no frozen-code modified):
      rewriter_tracker  → QueryRewriter(llm_client=rewriter_tracker)
      router_tracker    → IntentRouter(llm_client=router_tracker)
      generator_tracker → RAGPipeline(llm_client=generator_tracker,
                                      query_rewriter=rewriter_obj,
                                      intent_router=router_obj)
    """
    rewriter_tracker = TrackingLLMClient(
        model=settings.llm_rewriter_model,
        max_tokens=settings.llm_rewriter_max_tokens,
        temperature=0.0,
    )
    router_tracker = TrackingLLMClient(
        model=settings.intent_router_model,
        max_tokens=settings.intent_router_max_tokens,
        temperature=0.0,
    )
    generator_tracker = TrackingLLMClient(
        model=_GENERATOR_MODEL,       # frozen config has deprecated claude-sonnet-4-20250514
        max_tokens=settings.llm_max_tokens,
        temperature=0.0,
    )

    rewriter_obj = QueryRewriter(llm_client=rewriter_tracker)
    router_obj   = IntentRouter(llm_client=router_tracker)

    pipeline = RAGPipeline(
        llm_client=generator_tracker,
        query_rewriter=rewriter_obj,
        intent_router=router_obj,
    )
    return pipeline, rewriter_tracker, router_tracker, generator_tracker


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


def _attempt_query(
    qs: QuerySpec,
    pipeline: RAGPipeline,
    rewriter_tracker: TrackingLLMClient,
    router_tracker: TrackingLLMClient,
    generator_tracker: TrackingLLMClient,
) -> dict[str, Any]:
    """One attempt. Raises on failure."""
    # Clear logs so this query's tokens are isolated
    rewriter_tracker.usage_log.clear()
    router_tracker.usage_log.clear()
    generator_tracker.usage_log.clear()

    start = time.perf_counter()
    response = pipeline.query(qs.query)
    total_duration_ms = int((time.perf_counter() - start) * 1000)

    # Build per-role token breakdown (matches Phase 3's hop_token_breakdown field)
    hop_token_breakdown: list[dict[str, Any]] = []

    # Rewriter: may have 0 entries if lru_cache hit or rewriting disabled
    for u in rewriter_tracker.usage_log:
        hop_token_breakdown.append(
            {
                "role": "rewriter",
                "model": rewriter_tracker._model,
                "input_tokens": u["input_tokens"],
                "output_tokens": u["output_tokens"],
            }
        )

    # Router: should have exactly 1 entry when intent routing is enabled
    for u in router_tracker.usage_log:
        hop_token_breakdown.append(
            {
                "role": "router",
                "model": router_tracker._model,
                "input_tokens": u["input_tokens"],
                "output_tokens": u["output_tokens"],
            }
        )

    # Generator: 0 entries if no sources were retrieved, 1 otherwise
    for u in generator_tracker.usage_log:
        hop_token_breakdown.append(
            {
                "role": "generator",
                "model": generator_tracker._model,
                "input_tokens": u["input_tokens"],
                "output_tokens": u["output_tokens"],
            }
        )

    total_in  = sum(u["input_tokens"]  for u in rewriter_tracker.usage_log
                                                + router_tracker.usage_log
                                                + generator_tracker.usage_log)
    total_out = sum(u["output_tokens"] for u in rewriter_tracker.usage_log
                                                + router_tracker.usage_log
                                                + generator_tracker.usage_log)

    routing = response.routing
    record: dict[str, Any] = {
        "system": "phase2",
        "id": qs.id,
        "category": qs.category,
        "language": qs.language,
        "difficulty": qs.difficulty,
        "query": qs.query,
        "expected_hop_count": qs.expected_hop_count,  # from golden set (H2 grouping)
        "expected_answer_type": qs.expected_answer_type,
        "ground_truth": qs.ground_truth,
        **_category_tags(qs),
        # Execution result (same field names as Phase 3)
        "status": "success",
        "final_message": response.answer,
        "stop_reason": "end_turn",         # Phase 2 always terminates normally
        "hop_count": qs.expected_hop_count,  # golden-set hop_count for grouping
        "phase2_pipeline_steps": 3,          # informational; not a hop count
        "input_tokens": total_in,
        "output_tokens": total_out,
        "hop_token_breakdown": hop_token_breakdown,
        "total_duration_ms": total_duration_ms,
        "started_at": datetime.now(UTC).isoformat(),
        # Phase 2 observables
        "routing_intent":     routing.intent.value if routing else None,
        "routing_confidence": routing.confidence   if routing else None,
        "routing_source":     routing.source       if routing else None,
        "rewritten_query":    response.rewritten_query,
        "retrieval_sources_n": len(response.sources),
    }
    return record


def run_with_retry(
    qs: QuerySpec,
    pipeline: RAGPipeline,
    rewriter_tracker: TrackingLLMClient,
    router_tracker: TrackingLLMClient,
    generator_tracker: TrackingLLMClient,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """Up to max_retries extra attempts; write status='failed' on all failing."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return _attempt_query(qs, pipeline, rewriter_tracker, router_tracker, generator_tracker)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "phase2 benchmark: query %r attempt %d/%d failed (%s), retrying...",
                    qs.id,
                    attempt + 1,
                    max_retries + 1,
                    type(exc).__name__,
                )
    return {
        "system": "phase2",
        "id": qs.id,
        "category": qs.category,
        "language": qs.language,
        "difficulty": qs.difficulty,
        "query": qs.query,
        "expected_hop_count": qs.expected_hop_count,
        "expected_answer_type": qs.expected_answer_type,
        "ground_truth": qs.ground_truth,
        **_category_tags(qs),
        "status": "failed",
        "error": f"{type(last_exc).__name__}: {last_exc}",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="Explicit output JSONL path. If exists, IDs already present are skipped (resume).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Run only the first N queries.",
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
        help="Load + validate queries, print plan, exit without any API call.",
    )
    return parser.parse_args()


def _print_dry_run_plan(queries: list[QuerySpec], output_path: Path) -> None:
    bar = "=" * 62
    print(f"\n{bar}")
    print("  DRY-RUN PLAN  --  PHASE2")
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
    by_hop  = Counter(q.expected_hop_count for q in queries)
    print(f"  By hop_count     : {dict(sorted(by_hop.items()))}")
    by_ans  = Counter(q.expected_answer_type for q in queries)
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
    print("  Validation : OK -- all required fields present, no duplicate IDs")
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
                total += (hop["input_tokens"] * p_in + hop["output_tokens"] * p_out) / 1_000_000
        else:
            in_tok  = rec.get("input_tokens", 0)
            out_tok = rec.get("output_tokens", 0)
            total  += (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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
        id_order = [s.strip() for s in args.ids.split(",") if s.strip()]
        queries.sort(key=lambda q: id_order.index(q.id) if q.id in id_order else len(id_order))
        print(f"--ids: running {len(queries)} selected queries: {[q.id for q in queries]}")
    elif args.limit is not None:
        queries = queries[: args.limit]
        print(f"--limit {args.limit}: running first {len(queries)} queries.")

    smoke = args.smoke or (args.ids is not None)
    output_path = args.output if args.output else build_output_path(args.output_dir, args.dry_run, smoke=smoke)

    if args.dry_run:
        _print_dry_run_plan(queries, output_path)
        return 0

    # Resume
    completed_ids = load_completed_ids(output_path)
    if completed_ids:
        original_count = len(queries)
        queries = [q for q in queries if q.id not in completed_ids]
        print(f"RESUME: {len(completed_ids)} already done, {len(queries)}/{original_count} remaining.")

    print("\nBuilding Phase 2 pipeline (loads embedder + CrossEncoder reranker, ~20-60 s)...")
    pipeline, rewriter_tracker, router_tracker, generator_tracker = build_pipeline()

    # Warm-up: one throwaway query to load the CrossEncoder model into memory
    # so the first timed benchmark query isn't penalised by cold-start.
    print(f"Warm-up query: {_WARMUP_QUERY!r} ...")
    try:
        rewriter_tracker.usage_log.clear()
        router_tracker.usage_log.clear()
        generator_tracker.usage_log.clear()
        pipeline.query(_WARMUP_QUERY)
        print("Warm-up done.")
    except Exception as exc:
        print(f"Warm-up failed ({type(exc).__name__}) — continuing anyway.")

    print(f"Running {len(queries)} queries -> {output_path}\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    failures = 0

    with output_path.open("a", encoding="utf-8") as out_f:
        for i, qs in enumerate(queries, start=len(completed_ids) + 1):
            total_n = len(queries) + len(completed_ids)
            print(f"[{i}/{total_n}] {qs.id} ({qs.category}, {qs.language}) ...", end=" ", flush=True)

            record = run_with_retry(qs, pipeline, rewriter_tracker, router_tracker, generator_tracker)
            records.append(record)

            # Append + flush immediately so crash keeps prior results
            out_f.write(json.dumps(record, ensure_ascii=False))
            out_f.write("\n")
            out_f.flush()

            if record["status"] == "success":
                dur_s   = record.get("total_duration_ms", 0) / 1000
                in_tok  = record.get("input_tokens", 0)
                out_tok = record.get("output_tokens", 0)
                intent  = record.get("routing_intent", "?")
                print(f"OK {dur_s:.1f}s  {in_tok}/{out_tok} tok  route={intent}")
            else:
                failures += 1
                print(f"FAILED  {record.get('error', '?')}")

    cost = _compute_cost(records)
    total_in  = sum(r.get("input_tokens", 0)  for r in records if r.get("status") == "success")
    total_out = sum(r.get("output_tokens", 0) for r in records if r.get("status") == "success")
    print(
        f"\nDONE  queries={len(records)}  failures={failures}  "
        f"tokens={total_in}in/{total_out}out  cost~=${cost:.3f}"
    )
    print(f"Output: {output_path}")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
