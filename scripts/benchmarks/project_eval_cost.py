"""Cost projection for the full eval-v2 run (Phase B gate check).

Reads both smoke JSONLs, computes exact per-query costs, projects to 96 queries,
estimates judge costs, and prints a GATE PASS / GATE FAIL verdict.

Usage:
  python scripts/benchmarks/project_eval_cost.py \\
      --phase3-smoke benchmarks/runs/phase3_eval_v2_<ts>_smoke.jsonl \\
      --phase2-smoke benchmarks/runs/phase2_eval_v2_<ts>_smoke.jsonl

Or auto-detect the most recent smoke files:
  python scripts/benchmarks/project_eval_cost.py --auto
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ------------------------------------------------------------------------------
# PRICING -- stated explicitly so they can be verified.
# ------------------------------------------------------------------------------
# List prices (USD per 1 M tokens, 2026-07)
PRICE_IN_PER_M = {
    "claude-sonnet-4-5":         3.00,
    "claude-haiku-4-5-20251001": 1.00,
}
PRICE_OUT_PER_M = {
    "claude-sonnet-4-5":         15.00,
    "claude-haiku-4-5-20251001":  5.00,
}
# Cached input: 10% of the input rate for that model
CACHE_READ_DISCOUNT = 0.10
# Batch API: 50% off all costs
BATCH_DISCOUNT = 0.50

DEFAULT_IN_PER_M  = 3.00
DEFAULT_OUT_PER_M = 15.00

TOTAL_QUERIES = 96
GATE_THRESHOLD = 4.50
HARD_BUDGET    = 5.70


# ------------------------------------------------------------------------------
# Per-query cost (exact, with caching for Phase 3)
# ------------------------------------------------------------------------------

def query_cost_phase3(record: dict) -> float:
    """Exact cost for one Phase 3 record, accounting for cached input tokens."""
    total = 0.0
    for hop in record.get("hop_token_breakdown", []):
        model = hop.get("model", "")
        p_in  = PRICE_IN_PER_M.get(model, DEFAULT_IN_PER_M)
        p_out = PRICE_OUT_PER_M.get(model, DEFAULT_OUT_PER_M)

        uncached_in  = hop.get("input_tokens", 0)
        cached_read  = hop.get("cache_read_input_tokens", 0)
        out_tok      = hop.get("output_tokens", 0)

        # cached_read tokens are billed at CACHE_READ_DISCOUNT * p_in
        cost_in  = (uncached_in * p_in + cached_read * p_in * CACHE_READ_DISCOUNT) / 1_000_000
        cost_out = out_tok * p_out / 1_000_000
        total += cost_in + cost_out
    return total


def query_cost_phase2(record: dict) -> float:
    """Exact cost for one Phase 2 record (no caching)."""
    total = 0.0
    for hop in record.get("hop_token_breakdown", []):
        model = hop.get("model", "")
        p_in  = PRICE_IN_PER_M.get(model, DEFAULT_IN_PER_M)
        p_out = PRICE_OUT_PER_M.get(model, DEFAULT_OUT_PER_M)
        in_tok  = hop.get("input_tokens", 0)
        out_tok = hop.get("output_tokens", 0)
        total += (in_tok * p_in + out_tok * p_out) / 1_000_000
    return total


# ------------------------------------------------------------------------------
# I/O helpers
# ------------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def find_latest_smoke(output_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(
        output_dir.glob(f"{prefix}_eval_v2_*_smoke.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


# ------------------------------------------------------------------------------
# Judge cost estimation
# ------------------------------------------------------------------------------

def estimate_judge_tokens(p3_records: list[dict], p2_records: list[dict]) -> dict:
    """Estimate average judge input/output tokens from smoke data."""
    # Build lookup by id
    p3_by_id = {r["id"]: r for r in p3_records if r.get("status") == "success"}
    p2_by_id = {r["id"]: r for r in p2_records if r.get("status") == "success"}

    input_token_samples: list[int] = []
    output_token_estimate = 80  # short JSON verdict: ~80 output tokens

    for qid in set(p3_by_id) & set(p2_by_id):
        r3 = p3_by_id[qid]
        r2 = p2_by_id[qid]
        query_len      = len(r3.get("query", "").split())
        gt_len         = len(r3.get("ground_truth", "").split())
        ans3_len       = len(r3.get("final_message", "").split())
        ans2_len       = len(r2.get("final_message", "").split())
        # Rough token estimate: words * 1.3 (average English token/word ratio)
        total_words    = query_len + gt_len + ans3_len + ans2_len
        est_tokens     = int(total_words * 1.3) + 500  # +500 for judge system prompt
        input_token_samples.append(est_tokens)

    if not input_token_samples:
        # Fallback if no overlapping IDs
        avg_input = 2000
    else:
        avg_input = int(sum(input_token_samples) / len(input_token_samples))

    return {"avg_input": avg_input, "avg_output": output_token_estimate}


# ------------------------------------------------------------------------------
# Main projection logic
# ------------------------------------------------------------------------------

def project(p3_path: Path, p2_path: Path) -> None:
    bar = "=" * 70

    print(f"\n{bar}")
    print("  EVAL-V2 COST PROJECTION -- Phase B Smoke Gate")
    print(bar)

    # -- Pricing summary ------------------------------------------------------
    print("\n  PRICING USED (verify before trusting):")
    for m in ("claude-sonnet-4-5", "claude-haiku-4-5-20251001"):
        print(f"    {m:<36} in=${PRICE_IN_PER_M[m]:.2f}/MTok  out=${PRICE_OUT_PER_M[m]:.2f}/MTok")
    print(f"    Cached input read                     10% of input rate")
    print(f"    Batch API                              50% off all costs")

    # -- Load data ------------------------------------------------------------
    print(f"\n  Phase 3 smoke : {p3_path}")
    print(f"  Phase 2 smoke : {p2_path}")
    p3_records = [r for r in load_jsonl(p3_path) if r.get("status") == "success"]
    p2_records = [r for r in load_jsonl(p2_path) if r.get("status") == "success"]
    print(f"  Loaded: {len(p3_records)} Phase 3, {len(p2_records)} Phase 2 success records")

    # -- Per-query costs ------------------------------------------------------
    print(f"\n{'-'*70}")
    print("  SMOKE RESULTS -- Per-query breakdown")
    print(f"{'-'*70}")
    print(f"\n  Phase 3 (agent):")
    print(f"  {'ID':<30} {'models/tokens':>30}  {'cost_usd':>10}  {'cache_cr':>10}  {'cache_rd':>10}")

    p3_costs = []
    for r in p3_records:
        cost = query_cost_phase3(r)
        p3_costs.append(cost)
        breakdown = r.get("hop_token_breakdown", [])
        tok_summary = " + ".join(
            f"{h.get('model','?').split('-')[1][:6]}:{h.get('input_tokens',0)}in/{h.get('output_tokens',0)}out"
            for h in breakdown
        )
        cache_cr = sum(h.get("cache_creation_input_tokens", 0) for h in breakdown)
        cache_rd = sum(h.get("cache_read_input_tokens", 0) for h in breakdown)
        print(f"  {r['id']:<30} {tok_summary:>30}  ${cost:>9.5f}  {cache_cr:>10}  {cache_rd:>10}")

    print(f"\n  Phase 2 (pipeline):")
    print(f"  {'ID':<30} {'models/tokens':>30}  {'cost_usd':>10}")
    p2_costs = []
    for r in p2_records:
        cost = query_cost_phase2(r)
        p2_costs.append(cost)
        breakdown = r.get("hop_token_breakdown", [])
        tok_summary = " + ".join(
            f"{h.get('role','?')[:3]}:{h.get('input_tokens',0)}in/{h.get('output_tokens',0)}out"
            for h in breakdown
        )
        print(f"  {r['id']:<30} {tok_summary:>30}  ${cost:>9.5f}")

    # -- Cache evidence --------------------------------------------------------
    print(f"\n{'-'*70}")
    print("  CACHE EVIDENCE (Phase 3 only)")
    print(f"{'-'*70}")
    for i, r in enumerate(p3_records):
        breakdown = r.get("hop_token_breakdown", [])
        cache_cr = sum(h.get("cache_creation_input_tokens", 0) for h in breakdown)
        cache_rd = sum(h.get("cache_read_input_tokens", 0) for h in breakdown)
        marker = "← FIRST (expect cache_creation > 0)" if i == 0 else "← expect cache_read > 0"
        print(f"  [{i+1}] {r['id']:<30}  cache_creation={cache_cr:>6}  cache_read={cache_rd:>6}  {marker}")

    p3_first_cache_cr = sum(
        h.get("cache_creation_input_tokens", 0)
        for h in p3_records[0].get("hop_token_breakdown", [])
    ) if p3_records else 0
    cache_reads = [
        sum(h.get("cache_read_input_tokens", 0) for h in r.get("hop_token_breakdown", []))
        for r in p3_records[1:]
    ]
    cache_working = p3_first_cache_cr > 0 and any(cr > 0 for cr in cache_reads)
    if cache_working:
        print("\n  OK CACHE WORKING: first query created cache; subsequent queries hit it.")
    else:
        print("\n  !! WARNING: CACHE NOT WORKING -- cache_read_input_tokens=0 on queries 2+.")
        print("    This would SIGNIFICANTLY increase the Phase 3 cost projection.")

    # -- Run cost projection ---------------------------------------------------
    print(f"\n{'-'*70}")
    print("  RUN COST PROJECTION (96 queries)")
    print(f"{'-'*70}")

    # Phase 3: cost(q1, cache-miss) + 95 * mean(cost of q2-5, cache-hit)
    if len(p3_costs) >= 2:
        cost_q1   = p3_costs[0]   # first query (cache miss -- most expensive)
        cost_q2_5 = p3_costs[1:]  # remaining queries (cache hits)
        mean_q2_5 = sum(cost_q2_5) / len(cost_q2_5)
        p3_projected = cost_q1 + (TOTAL_QUERIES - 1) * mean_q2_5
        print(f"\n  Phase 3:")
        print(f"    Q1 cost (cache-miss)          : ${cost_q1:.5f}")
        print(f"    Mean cost Q2-Q{len(p3_records)} (cache-hit) : ${mean_q2_5:.5f}")
        print(f"    Projection: ${cost_q1:.5f} + {TOTAL_QUERIES-1} × ${mean_q2_5:.5f} = ${p3_projected:.4f}")
    else:
        mean_p3 = sum(p3_costs) / len(p3_costs) if p3_costs else 0
        p3_projected = mean_p3 * TOTAL_QUERIES
        print(f"\n  Phase 3 (flat mean, only {len(p3_costs)} sample): ${p3_projected:.4f}")

    # Phase 2: flat mean × 96
    if p2_costs:
        mean_p2 = sum(p2_costs) / len(p2_costs)
        p2_projected = mean_p2 * TOTAL_QUERIES
        print(f"\n  Phase 2:")
        print(f"    Mean cost                     : ${mean_p2:.5f}")
        print(f"    Projection: {len(p2_costs)} samples → {TOTAL_QUERIES} × ${mean_p2:.5f} = ${p2_projected:.4f}")
    else:
        p2_projected = 0.0
        print(f"\n  Phase 2: no data")

    # -- Judge cost projection -------------------------------------------------
    print(f"\n{'-'*70}")
    print("  JUDGE COST PROJECTION")
    print(f"{'-'*70}")

    judge_tokens = estimate_judge_tokens(p3_records, p2_records)
    avg_in  = judge_tokens["avg_input"]
    avg_out = judge_tokens["avg_output"]
    print(f"\n  Estimated judge token sizes from smoke data:")
    print(f"    Average input  : {avg_in} tokens  (query + ground_truth + both answers + system prompt)")
    print(f"    Average output : {avg_out} tokens  (short JSON verdict)")

    # Metric judges: M1, M3a, M3b, M6, M7 = 5 judges × 96 pairs
    # Model: Haiku, Batch API (-50%)
    metric_judge_calls = 5 * TOTAL_QUERIES
    p_haiku_in  = PRICE_IN_PER_M["claude-haiku-4-5-20251001"]
    p_haiku_out = PRICE_OUT_PER_M["claude-haiku-4-5-20251001"]
    cost_metric_judge_per_call = (avg_in * p_haiku_in + avg_out * p_haiku_out) / 1_000_000
    cost_metric_judges = cost_metric_judge_per_call * metric_judge_calls * BATCH_DISCOUNT
    print(f"\n  Metric judges (M1, M3a, M3b, M6, M7) -- Haiku, Batch API:")
    print(f"    5 judges × {TOTAL_QUERIES} pairs = {metric_judge_calls} calls")
    print(f"    Per call: ({avg_in} × ${p_haiku_in:.2f} + {avg_out} × ${p_haiku_out:.2f}) / 1M = ${cost_metric_judge_per_call:.5f}")
    print(f"    Batch discount (50%): × {BATCH_DISCOUNT}")
    print(f"    Total metric judges: {metric_judge_calls} × ${cost_metric_judge_per_call:.5f} × {BATCH_DISCOUNT} = ${cost_metric_judges:.4f}")

    # Strict judge (Phase D): 1 judge × 96 pairs
    # Model: Sonnet, Batch API (-50%)
    strict_judge_calls = TOTAL_QUERIES
    p_sonnet_in  = PRICE_IN_PER_M["claude-sonnet-4-5"]
    p_sonnet_out = PRICE_OUT_PER_M["claude-sonnet-4-5"]
    cost_strict_judge_per_call = (avg_in * p_sonnet_in + avg_out * p_sonnet_out) / 1_000_000
    cost_strict_judges = cost_strict_judge_per_call * strict_judge_calls * BATCH_DISCOUNT
    print(f"\n  Strict judge (Phase D) -- Sonnet, Batch API:")
    print(f"    1 judge × {TOTAL_QUERIES} pairs = {strict_judge_calls} calls")
    print(f"    Per call: ({avg_in} × ${p_sonnet_in:.2f} + {avg_out} × ${p_sonnet_out:.2f}) / 1M = ${cost_strict_judge_per_call:.5f}")
    print(f"    Batch discount (50%): × {BATCH_DISCOUNT}")
    print(f"    Total strict judge: {strict_judge_calls} × ${cost_strict_judge_per_call:.5f} × {BATCH_DISCOUNT} = ${cost_strict_judges:.4f}")

    total_judge_cost = cost_metric_judges + cost_strict_judges
    print(f"\n  Total judge cost: ${cost_metric_judges:.4f} + ${cost_strict_judges:.4f} = ${total_judge_cost:.4f}")

    # -- Grand total -----------------------------------------------------------
    print(f"\n{bar}")
    print("  TOTAL PROJECTED COST")
    print(bar)
    grand_total = p3_projected + p2_projected + total_judge_cost
    print(f"\n  Phase 3 run    : ${p3_projected:.4f}")
    print(f"  Phase 2 run    : ${p2_projected:.4f}")
    print(f"  All judges     : ${total_judge_cost:.4f}")
    print(f"  -----------------------------")
    print(f"  GRAND TOTAL    : ${grand_total:.4f}")
    print(f"  Gate threshold : ${GATE_THRESHOLD:.2f}")
    print(f"  Hard budget    : ${HARD_BUDGET:.2f}")
    print(f"  Smoke cost     : ~$0.00 (already spent -- this run)")
    print()

    margin = GATE_THRESHOLD - grand_total
    remaining_vs_budget = HARD_BUDGET - grand_total
    if grand_total <= GATE_THRESHOLD:
        print(f"  ████  GATE PASS  ████")
        print(f"  Projected ${grand_total:.4f} < gate ${GATE_THRESHOLD:.2f}")
        print(f"  Margin vs gate        : +${margin:.4f}")
        print(f"  Remaining vs $5.70 budget: +${remaining_vs_budget:.4f}")
    else:
        print(f"  ████  GATE FAIL  ████")
        print(f"  Projected ${grand_total:.4f} > gate ${GATE_THRESHOLD:.2f}")
        print(f"  Over gate by          : ${-margin:.4f}")
        print(f"  Over budget by        : ${-remaining_vs_budget:.4f}")
        print(f"  DO NOT start the full run. Investigate cost reduction options.")

    print(f"\n{bar}\n")


# ------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase3-smoke", type=Path, default=None, help="Phase 3 smoke JSONL path.")
    parser.add_argument("--phase2-smoke", type=Path, default=None, help="Phase 2 smoke JSONL path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks/runs"),
        help="Directory to search for smoke files when using --auto.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect the most recent *_smoke.jsonl files in --output-dir.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    output_dir = args.output_dir

    if args.auto:
        p3_path = find_latest_smoke(output_dir, "phase3")
        p2_path = find_latest_smoke(output_dir, "phase2")
        if not p3_path:
            print(f"ERROR: no phase3_eval_v2_*_smoke.jsonl found in {output_dir}")
            return 1
        if not p2_path:
            print(f"ERROR: no phase2_eval_v2_*_smoke.jsonl found in {output_dir}")
            return 1
    else:
        p3_path = args.phase3_smoke
        p2_path = args.phase2_smoke
        if not p3_path or not p2_path:
            print("ERROR: provide --phase3-smoke and --phase2-smoke, or use --auto")
            return 1

    if not p3_path.exists():
        print(f"ERROR: Phase 3 smoke file not found: {p3_path}")
        return 1
    if not p2_path.exists():
        print(f"ERROR: Phase 2 smoke file not found: {p2_path}")
        return 1

    project(p3_path, p2_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
