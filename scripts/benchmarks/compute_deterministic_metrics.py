"""Deterministic metrics (M2, M4, cost) for eval-v2.

Reads both JSONL files and the golden set, then computes:
  M2  computational_correctness  (quantitative_reasoning, 16 queries)
  M4  latency                    (mean/median/p95, by system / category / hop)
  Cost per system from hop_token_breakdown (Sonnet vs Haiku rates,
        cached vs uncached -- reported BOTH as-deployed and uncached)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_P3 = _ROOT / "benchmarks/runs/phase2_vs_phase3/phase3_eval_v2.jsonl"
DEFAULT_P2 = _ROOT / "benchmarks/runs/phase2_vs_phase3/phase2_eval_v2.jsonl"
DEFAULT_QS = _ROOT / "benchmarks/queries/phase2_vs_phase3/v2/golden_set_v2.yaml"

PRICE_IN: dict[str, float] = {
    "claude-sonnet-4-5":         3.00,
    "claude-haiku-4-5-20251001": 1.00,
}
PRICE_OUT: dict[str, float] = {
    "claude-sonnet-4-5":         15.00,
    "claude-haiku-4-5-20251001":  5.00,
}
CACHE_READ_FRACTION = 0.10
DEFAULT_PRICE_IN  = 3.00
DEFAULT_PRICE_OUT = 15.00

# I/O helpers

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        qs = yaml.safe_load(f)
    return {q["id"]: q for q in qs}

# Latency helpers

def _percentile(data: list[float], pct: float) -> float:
    """Return the p-th percentile of data (0-100)."""
    if not data:
        return float("nan")
    s = sorted(data)
    k = (pct / 100) * (len(s) - 1)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def latency_stats(durations_ms: list[float]) -> dict[str, float]:
    if not durations_ms:
        return {"mean": float("nan"), "median": float("nan"), "p95": float("nan"), "n": 0}
    return {
        "mean":   statistics.mean(durations_ms),
        "median": statistics.median(durations_ms),
        "p95":    _percentile(durations_ms, 95),
        "n":      len(durations_ms),
    }

# Cost computation

def record_cost_deployed(rec: dict[str, Any]) -> float:
    """Exact cost as-deployed: Phase 3 uses cached input, Phase 2 doesn't."""
    total = 0.0
    for hop in rec.get("hop_token_breakdown", []):
        model  = hop.get("model", "")
        p_in   = PRICE_IN.get(model, DEFAULT_PRICE_IN)
        p_out  = PRICE_OUT.get(model, DEFAULT_PRICE_OUT)
        in_tok  = hop.get("input_tokens", 0)
        out_tok = hop.get("output_tokens", 0)
        cr_tok  = hop.get("cache_read_input_tokens", 0)
        # cache_read tokens are billed at CACHE_READ_FRACTION * p_in
        # input_tokens is the uncached portion; cache_read is extra
        total += (in_tok * p_in + cr_tok * p_in * CACHE_READ_FRACTION + out_tok * p_out) / 1_000_000
    return total


def record_cost_uncached(rec: dict[str, Any]) -> float:
    """Hypothetical cost if NO caching applied (all input at full rate)."""
    total = 0.0
    for hop in rec.get("hop_token_breakdown", []):
        model   = hop.get("model", "")
        p_in    = PRICE_IN.get(model, DEFAULT_PRICE_IN)
        p_out   = PRICE_OUT.get(model, DEFAULT_PRICE_OUT)
        in_tok  = hop.get("input_tokens", 0)
        cr_tok  = hop.get("cache_read_input_tokens", 0)
        cc_tok  = hop.get("cache_creation_input_tokens", 0)
        out_tok = hop.get("output_tokens", 0)
        # All input tokens (including cache_read and cache_creation) at full rate
        total_in = in_tok + cr_tok + cc_tok
        total += (total_in * p_in + out_tok * p_out) / 1_000_000
    return total

# Computational correctness

def _extract_amounts(text: str) -> list[float]:
    """Extract all euro amounts from text, handling EN and EU number formats.

    EN: 1,370.75  (comma=thousands, dot=decimal)
    EU: 1.134,75  (dot=thousands, comma=decimal)
    Plain: 663.60 or 663,60

    Returns a deduplicated list of candidate floats.
    """
    clean = re.sub(r"\*+", "", text)  # strip markdown bold
    clean = clean.replace("€", " ")  # remove € sign

    seen: set[float] = set()
    result: list[float] = []

    def add(v: float) -> None:
        rv = round(v, 2)
        if rv > 0 and rv not in seen:
            seen.add(rv)
            result.append(rv)

    for m in re.finditer(r"\b\d{1,3}(?:\.\d{3})+,\d{2}\b", clean):
        add(float(m.group().replace(".", "").replace(",", ".")))

    for m in re.finditer(r"\b\d{1,3}(?:,\d{3})+\.\d{2}\b", clean):
        add(float(m.group().replace(",", "")))

    for m in re.finditer(r"\b(\d{1,6})\.(\d{2})\b", clean):
        add(float(m.group()))

    for m in re.finditer(r"(?<!\d)(\d{1,6}),(\d{2})(?!\d)", clean):
        candidate = float(m.group(1) + "." + m.group(2))
        if not any(abs(candidate - x) < 0.01 for x in seen):
            add(candidate)

    return result


def _parse_gt_total(ground_truth: str) -> float | None:
    """Extract the primary total from a ground_truth string.

    Looks for patterns like:
      total_stay_cost_eur = €949.40
      total_stay_cost=€949.40
      total_stay_cost_eur = 949.40
    Returns the first match as a float, or None.
    """
    m = re.search(r"total_stay_cost[_\w]*\s*=\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth)
    if m:
        return float(m.group(1))
    return None


def _parse_gt_comparison(ground_truth: str, qid: str) -> dict[str, Any]:
    """Parse expected values for comparison queries (qr_13-16).

    Returns a dict with keys: totals (list of expected floats), winner (str|None),
    delta (float|None).
    """
    totals: list[float] = []
    winner: str | None = None
    delta:  float | None = None

    for m in re.finditer(r"total_stay_cost\w*=\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth):
        totals.append(float(m.group(1)))

    if qid == "qr_13":
        winner = "porto"
        dm = re.search(r"Porto saves\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth)
        if dm:
            delta = float(dm.group(1))

    elif qid == "qr_14":
        pm = re.search(r"Premium:\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth)
        if pm:
            delta = float(pm.group(1))

    elif qid == "qr_15":
        dm = re.search(r"Autumn costs\s*[€\s]*([0-9]+\.[0-9]{2})\s*more", ground_truth,
                       re.IGNORECASE)
        if not dm:
            dm = re.search(r"difference as\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth,
                           re.IGNORECASE)
        if dm:
            delta = float(dm.group(1))

    elif qid == "qr_16":
        pm = re.search(r"Extra-person premium\s*=\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth,
                       re.IGNORECASE)
        if not pm:
            pm = re.search(r"extra cost as\s*[€\s]*([0-9]+\.[0-9]{2})", ground_truth,
                           re.IGNORECASE)
        if pm:
            delta = float(pm.group(1))

    return {"totals": totals, "winner": winner, "delta": delta}


def _near(a: float, b: float, tol: float = 1.0) -> bool:
    return abs(a - b) <= tol


def score_m2_simple(answer: str, gt_total: float) -> float:
    """M2 for simple single-total queries: 1.0 if any extracted amount is within ±1 EUR."""
    amounts = _extract_amounts(answer)
    return 1.0 if any(_near(x, gt_total) for x in amounts) else 0.0


def score_m2_comparison(answer: str, expected: dict[str, Any]) -> tuple[float, str]:
    """M2 for comparison queries (qr_13-16).

    Scoring rule (pre-registered):
      1.0  BOTH totals within ±1 EUR AND direction/delta correct.
      0.5  Exactly one of: (a) only one total correct, (b) totals correct but
           direction/delta wrong.
      0.0  No totals correct.

    Returns (score, explanation).
    """
    amounts = _extract_amounts(answer)
    totals = expected["totals"]
    winner = expected["winner"]
    delta  = expected["delta"]

    matched = [any(_near(x, t) for x in amounts) for t in totals]
    n_matched = sum(matched)
    all_matched = n_matched == len(totals) and len(totals) > 0

    direction_ok = True
    if winner:
        direction_ok = winner.lower() in answer.lower()
    if delta and direction_ok:
        direction_ok = any(_near(x, delta) for x in amounts)

    if all_matched and direction_ok:
        return 1.0, f"all {len(totals)} totals found, direction/delta correct"
    elif all_matched and not direction_ok:
        return 0.5, f"all {len(totals)} totals found but direction/delta wrong or missing"
    elif n_matched > 0 and direction_ok:
        return 0.5, f"{n_matched}/{len(totals)} totals correct, direction ok"
    elif n_matched > 0:
        return 0.5, f"{n_matched}/{len(totals)} totals correct, direction missing"
    else:
        return 0.0, "no expected totals found in answer"


COMPARISON_IDS = {"qr_13", "qr_14", "qr_15", "qr_16"}


def compute_m2(
    p3_recs: list[dict],
    p2_recs: list[dict],
    golden: dict[str, dict],
) -> dict[str, Any]:
    """Compute M2 for all 16 quantitative_reasoning queries."""
    results: dict[str, dict] = {}

    all_recs = [("phase3", p3_recs), ("phase2", p2_recs)]
    for system, recs in all_recs:
        qr = [r for r in recs if r["category"] == "quantitative_reasoning"]
        for rec in qr:
            qid = rec["id"]
            gt  = golden[qid]["ground_truth"]
            ans = rec.get("final_message", "")
            key = f"{system}:{qid}"

            if qid in COMPARISON_IDS:
                expected = _parse_gt_comparison(gt, qid)
                score, explanation = score_m2_comparison(ans, expected)
                results[key] = {
                    "system": system, "id": qid, "score": score,
                    "type": "comparison", "rule": explanation,
                    "expected_totals": expected["totals"],
                    "expected_delta": expected["delta"],
                    "extracted": _extract_amounts(ans)[:10],
                }
            else:
                gt_total = _parse_gt_total(gt)
                if gt_total is None:
                    results[key] = {"system": system, "id": qid, "score": None,
                                    "type": "simple", "rule": "GT parse failed"}
                    continue
                score = score_m2_simple(ans, gt_total)
                results[key] = {
                    "system": system, "id": qid, "score": score,
                    "type": "simple", "rule": f"gt={gt_total:.2f}, ±1 EUR tolerance",
                    "extracted": _extract_amounts(ans)[:10],
                }

    return results

# Main report

def _fmt(x: float) -> str:
    return f"{x:.1f}"


def run(p3_path: Path, p2_path: Path, qs_path: Path) -> None:
    bar = "=" * 72
    thin = "-" * 72

    print(f"\n{bar}")
    print("  EVAL-V2 DETERMINISTIC METRICS REPORT (Phase C)")
    print(f"{bar}")
    print(f"\n  Phase 3 JSONL : {p3_path}")
    print(f"  Phase 2 JSONL : {p2_path}")
    print(f"  Golden set    : {qs_path}\n")

    p3_recs = [r for r in load_jsonl(p3_path) if r.get("status") == "success"]
    p2_recs = [r for r in load_jsonl(p2_path) if r.get("status") == "success"]
    golden  = load_golden(qs_path)

    print(f"  Loaded: {len(p3_recs)} Phase-3, {len(p2_recs)} Phase-2 records (all status=success)\n")

    # Latency
    print(f"{bar}")
    print("  M4 LATENCY")
    print(f"{thin}")
    print("  NOTE: Phase 2 latency includes CPU-bound CrossEncoder reranker")
    print("  (BAAI/bge-reranker-v2-m3 loaded once; first query has cold-start).")
    print("  This is hardware-dependent; results on other machines will differ.\n")

    for label, recs in [("Phase 3 (agent)", p3_recs), ("Phase 2 (pipeline)", p2_recs)]:
        durs = [r["total_duration_ms"] for r in recs]
        s = latency_stats(durs)
        print(f"  {label}  (n={s['n']})")
        print(f"    mean={_fmt(s['mean'])}ms  median={_fmt(s['median'])}ms  p95={_fmt(s['p95'])}ms\n")

    # By category
    print("  By category (mean ms):")
    cats = sorted({r["category"] for r in p3_recs + p2_recs})
    print(f"  {'Category':<32} {'Phase3_mean':>12} {'Phase2_mean':>12}  {'n3':>4}  {'n2':>4}")
    for cat in cats:
        d3 = [r["total_duration_ms"] for r in p3_recs if r["category"] == cat]
        d2 = [r["total_duration_ms"] for r in p2_recs if r["category"] == cat]
        m3 = statistics.mean(d3) if d3 else float("nan")
        m2 = statistics.mean(d2) if d2 else float("nan")
        print(f"  {cat:<32} {m3:>12.0f} {m2:>12.0f}  {len(d3):>4}  {len(d2):>4}")

    # By hop_count
    print("\n  By hop_count (mean ms):")
    hops = sorted({r.get("expected_hop_count", r.get("hop_count", 0)) for r in p3_recs})
    print(f"  {'hop':>4} {'Phase3_mean':>12} {'Phase2_mean':>12}  {'n3':>4}  {'n2':>4}")
    for hop in hops:
        d3 = [r["total_duration_ms"] for r in p3_recs
              if r.get("expected_hop_count", r.get("hop_count", -1)) == hop]
        d2 = [r["total_duration_ms"] for r in p2_recs
              if r.get("expected_hop_count", r.get("hop_count", -1)) == hop]
        m3 = statistics.mean(d3) if d3 else float("nan")
        m2 = statistics.mean(d2) if d2 else float("nan")
        print(f"  {hop:>4} {m3:>12.0f} {m2:>12.0f}  {len(d3):>4}  {len(d2):>4}")

    # Cost
    print(f"\n{bar}")
    print("  EXACT COST FROM hop_token_breakdown")
    print(f"{thin}")
    print("  Pricing: Sonnet-4-5 $3.00/$15.00 per MTok in/out")
    print("           Haiku-4-5  $1.00/$5.00  per MTok in/out")
    print("           Cached read = 10% of input rate (Phase 3 only)\n")

    for label, recs in [("Phase 3", p3_recs), ("Phase 2", p2_recs)]:
        dep = sum(record_cost_deployed(r) for r in recs)
        unc = sum(record_cost_uncached(r) for r in recs)
        in3  = sum(sum(h.get("input_tokens", 0)               for h in r.get("hop_token_breakdown", [])) for r in recs)
        cr3  = sum(sum(h.get("cache_read_input_tokens", 0)    for h in r.get("hop_token_breakdown", [])) for r in recs)
        cc3  = sum(sum(h.get("cache_creation_input_tokens", 0) for h in r.get("hop_token_breakdown", [])) for r in recs)
        out3 = sum(sum(h.get("output_tokens", 0)              for h in r.get("hop_token_breakdown", [])) for r in recs)
        print(f"  {label}:")
        print(f"    input_tokens           = {in3:>8,}")
        print(f"    cache_creation_tokens  = {cc3:>8,}  (billed as regular input)")
        print(f"    cache_read_tokens      = {cr3:>8,}  (billed at 10% of input rate)")
        print(f"    output_tokens          = {out3:>8,}")
        print(f"    Cost as-deployed       = ${dep:.4f}")
        print(f"    Cost uncached (no cache) = ${unc:.4f}  <-- pre-reg requires dual reporting\n")

    # Computational correctness
    print(f"{bar}")
    print("  M2 COMPUTATIONAL CORRECTNESS (quantitative_reasoning, n=16)")
    print(f"{thin}")
    print("  Rules:")
    print("    Simple queries (qr_01-12, 2-hop): 1.0 if any extracted number")
    print("      within +/-1 EUR of ground-truth total; 0.0 otherwise.")
    print("    Comparison queries (qr_13-16, 3-hop): require BOTH totals")
    print("      within +/-1 EUR AND direction/delta correct.")
    print("      Partial credit (0.5) if one total correct or totals ok but")
    print("      direction missing. (Rule scored separately per pre-reg.)\n")

    m2_results = compute_m2(p3_recs, p2_recs, golden)

    qr_ids = [q["id"] for q in golden.values() if q["category"] == "quantitative_reasoning"]
    qr_ids.sort()
    print(f"  {'ID':<32} {'hop':>4} {'P3_score':>9} {'P2_score':>9}  {'type'}")
    for qid in qr_ids:
        r3 = m2_results.get(f"phase3:{qid}", {})
        r2 = m2_results.get(f"phase2:{qid}", {})
        hop = golden[qid].get("hop_count", "?")
        s3 = r3.get("score")
        s2 = r2.get("score")
        s3_str = f"{s3:.1f}" if s3 is not None else "N/A"
        s2_str = f"{s2:.1f}" if s2 is not None else "N/A"
        qtype = "COMPARISON" if qid in COMPARISON_IDS else "simple"
        print(f"  {qid:<32} {hop:>4} {s3_str:>9} {s2_str:>9}  {qtype}")

    print()
    for label, system in [("Phase 3", "phase3"), ("Phase 2", "phase2")]:
        scores = [v["score"] for k, v in m2_results.items()
                  if k.startswith(system + ":") and v["score"] is not None]
        if scores:
            mean_all = statistics.mean(scores)
            simple_scores = [v["score"] for k, v in m2_results.items()
                             if k.startswith(system + ":") and v["score"] is not None
                             and v.get("type") == "simple"]
            comp_scores = [v["score"] for k, v in m2_results.items()
                           if k.startswith(system + ":") and v["score"] is not None
                           and v.get("type") == "comparison"]
            print(f"  {label}  M2 mean (all 16): {mean_all:.3f}")
            if simple_scores:
                print(f"    Simple (qr_01-12, n={len(simple_scores)}): {statistics.mean(simple_scores):.3f}")
            if comp_scores:
                print(f"    Comparison (qr_13-16, n={len(comp_scores)}): {statistics.mean(comp_scores):.3f}")

    print(f"\n  Comparison query detail:")
    for qid in COMPARISON_IDS:
        for system, label in [("phase3", "P3"), ("phase2", "P2")]:
            key = f"{system}:{qid}"
            r = m2_results.get(key, {})
            score = r.get("score", "?")
            rule  = r.get("rule", "?")
            print(f"  [{label}] {qid}: score={score}  rule={rule!r}")

    print(f"\n{bar}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase3",   type=Path, default=DEFAULT_P3)
    p.add_argument("--phase2",   type=Path, default=DEFAULT_P2)
    p.add_argument("--queries",  type=Path, default=DEFAULT_QS)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    for path in [args.phase3, args.phase2, args.queries]:
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
    run(args.phase3, args.phase2, args.queries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
