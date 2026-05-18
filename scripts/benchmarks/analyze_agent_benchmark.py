"""Analyse a Phase 3 agent benchmark run.

Reads a JSONL file produced by :mod:`scripts.benchmarks.run_agent_benchmark`,
computes per-category aggregate metrics, and writes a Markdown report.

Metrics:
- tool_coverage = fraction of queries in which ``set(expected_tools) <= set(tools_used)``.
    Subset match: the agent may invoke extra tools (e.g. semantic
    fallback) without penalty.

- latency_* = wall-clock per-query duration in seconds, summarised as mean,
    p50 (median) and p95.

- tokens_* = average input and output tokens per query.

- cost_usd = sum of (input * 3.0 + output * 15.0) / 1_000_000 USD using Claude
    Sonnet 4.5 pricing.

Failure rate is also reported when applicable.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elh_rag.logging_setup import setup_logging

logger = logging.getLogger(__name__)


INPUT_PRICE_PER_MTOK = 3.0
OUTPUT_PRICE_PER_MTOK = 15.0


DEFAULT_RUNS_DIR = Path("benchmarks/runs")
DEFAULT_REPORTS_DIR = Path("benchmarks/reports")


def latest_run_file(runs_dir: Path) -> Path:
    """Return the most recently modified JSONL file in runs_dir."""
    if not runs_dir.exists():
        raise FileNotFoundError(f"Runs directory does not exist: {runs_dir}")
    candidates = sorted(runs_dir.glob("agent_benchmark_*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No agent_benchmark_*.jsonl files in {runs_dir}")
    return candidates[-1]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load all records from a JSONL file."""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """USD cost of a single query at Sonnet 4.5 pricing."""
    return (input_tokens * INPUT_PRICE_PER_MTOK + output_tokens * OUTPUT_PRICE_PER_MTOK) / 1_000_000


def percentile(values: list[float], p: float) -> float:
    """Return the p-th percentile (p in [0, 100]) using linear interpolation."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate metrics over a set of query records."""
    if not records:
        return {
            "n": 0,
            "n_success": 0,
            "n_failed": 0,
        }
    successes = [r for r in records if r.get("status") == "success"]
    failures = [r for r in records if r.get("status") == "failed"]

    if not successes:
        return {
            "n": len(records),
            "n_success": 0,
            "n_failed": len(failures),
            "failure_rate": 1.0,
        }

    tool_cov_hits = sum(
        1
        for r in successes
        if set(r.get("expected_tools", [])).issubset(set(r.get("tools_used", [])))
    )
    latencies_s = [r["total_duration_ms"] / 1000.0 for r in successes]
    input_tokens = [r["input_tokens"] for r in successes]
    output_tokens = [r["output_tokens"] for r in successes]
    hops = [r["hop_count"] for r in successes]
    total_input = sum(input_tokens)
    total_output = sum(output_tokens)

    return {
        "n": len(records),
        "n_success": len(successes),
        "n_failed": len(failures),
        "failure_rate": len(failures) / len(records),
        "tool_coverage": tool_cov_hits / len(successes),
        "tool_coverage_hits": tool_cov_hits,
        "latency_avg_s": statistics.mean(latencies_s),
        "latency_p50_s": percentile(latencies_s, 50),
        "latency_p95_s": percentile(latencies_s, 95),
        "latency_max_s": max(latencies_s),
        "tokens_in_avg": statistics.mean(input_tokens),
        "tokens_out_avg": statistics.mean(output_tokens),
        "tokens_in_total": total_input,
        "tokens_out_total": total_output,
        "hops_avg": statistics.mean(hops),
        "hops_max": max(hops),
        "cost_total_usd": compute_cost_usd(total_input, total_output),
    }


def render_markdown(
    *,
    input_path: Path,
    records: list[dict[str, Any]],
    overall: dict[str, Any],
    per_category: dict[str, dict[str, Any]],
    per_language: dict[str, dict[str, Any]],
) -> str:
    """Build the Markdown report string."""
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append("# Phase 3 Agent Benchmark Report")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- Run file: `{input_path.name}`")
    lines.append(f"- Total queries: {overall['n']}")
    lines.append(f"- Success: {overall['n_success']}  |  Failed: {overall['n_failed']}")
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.extend(_metric_table(overall))
    lines.append("")

    lines.append("## Per category")
    lines.append("")
    lines.append(
        "| Category | n | Coverage | Lat. avg | Lat. p95 | Tok in (avg) | Tok out (avg) | Cost USD |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for cat, agg in sorted(per_category.items()):
        if agg["n_success"] == 0:
            lines.append(f"| {cat} | {agg['n']} | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {cat} | {agg['n']} | "
            f"{agg['tool_coverage'] * 100:.0f}% "
            f"({agg['tool_coverage_hits']}/{agg['n_success']}) | "
            f"{agg['latency_avg_s']:.1f}s | "
            f"{agg['latency_p95_s']:.1f}s | "
            f"{agg['tokens_in_avg']:.0f} | "
            f"{agg['tokens_out_avg']:.0f} | "
            f"${agg['cost_total_usd']:.2f} |"
        )
    lines.append("")

    lines.append("## Per language")
    lines.append("")
    lines.append("| Language | n | Coverage | Lat. avg | Tok in (avg) | Tok out (avg) |")
    lines.append("|---|---|---|---|---|---|")
    for lang, agg in sorted(per_language.items()):
        if agg["n_success"] == 0:
            lines.append(f"| {lang} | {agg['n']} | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {lang} | {agg['n']} | "
            f"{agg['tool_coverage'] * 100:.0f}% | "
            f"{agg['latency_avg_s']:.1f}s | "
            f"{agg['tokens_in_avg']:.0f} | "
            f"{agg['tokens_out_avg']:.0f} |"
        )
    lines.append("")

    lines.append("## Per query")
    lines.append("")
    lines.append(
        "| ID | Cat | Lang | Status | Tools used | Hops | Tok (in/out) | Lat. (s) | Coverage |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in records:
        if r.get("status") == "success":
            coverage_ok = set(r.get("expected_tools", [])).issubset(set(r.get("tools_used", [])))
            cov_str = "OK" if coverage_ok else "MISS"
            tools_str = ", ".join(r.get("tools_used", []))
            tok_in = r.get("input_tokens", 0)
            tok_out = r.get("output_tokens", 0)
            lat = r.get("total_duration_ms", 0) / 1000.0
            hops = r.get("hop_count", 0)
            lines.append(
                f"| {r['id']} | {r['category']} | {r['language']} | OK | "
                f"{tools_str} | {hops} | {tok_in}/{tok_out} | {lat:.1f} | {cov_str} |"
            )
        else:
            err = r.get("error", "unknown")
            lines.append(
                f"| {r['id']} | {r['category']} | {r['language']} | FAILED | - | - | - | - | {err} |"
            )
    lines.append("")

    return "\n".join(lines)


def _metric_table(agg: dict[str, Any]) -> list[str]:
    """Render an aggregate dict as a 2-column Markdown table (key/value)."""
    if agg.get("n_success", 0) == 0:
        return ["No successful queries to analyse."]
    rows: list[str] = []
    rows.append("| Metric | Value |")
    rows.append("|---|---|")
    rows.append(
        f"| Tool routing coverage | {agg['tool_coverage'] * 100:.0f}% ({agg['tool_coverage_hits']}/{agg['n_success']}) |"
    )
    rows.append(
        f"| Failure rate | {agg['failure_rate'] * 100:.0f}% ({agg['n_failed']}/{agg['n']}) |"
    )
    rows.append(f"| Latency avg | {agg['latency_avg_s']:.1f} s |")
    rows.append(f"| Latency p50 | {agg['latency_p50_s']:.1f} s |")
    rows.append(f"| Latency p95 | {agg['latency_p95_s']:.1f} s |")
    rows.append(f"| Latency max | {agg['latency_max_s']:.1f} s |")
    rows.append(f"| Hops avg | {agg['hops_avg']:.1f} |")
    rows.append(f"| Hops max | {agg['hops_max']} |")
    rows.append(
        f"| Tokens in (avg / total) | {agg['tokens_in_avg']:.0f} / {agg['tokens_in_total']} |"
    )
    rows.append(
        f"| Tokens out (avg / total) | {agg['tokens_out_avg']:.0f} / {agg['tokens_out_total']} |"
    )
    rows.append(f"| Cost total | ${agg['cost_total_usd']:.2f} USD |")
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="JSONL run file. If omitted, the most recent file in benchmarks/runs/ is used.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help=f"Directory for the Markdown report (default: {DEFAULT_REPORTS_DIR}).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the rendered Markdown report to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    input_path = args.input or latest_run_file(DEFAULT_RUNS_DIR)
    print(f"Analyzing: {input_path}")
    records = load_jsonl(input_path)

    overall = aggregate(records)

    per_category: dict[str, dict[str, Any]] = {}
    grouped_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped_by_cat[r.get("category", "unknown")].append(r)
    for cat, group in grouped_by_cat.items():
        per_category[cat] = aggregate(group)

    per_language: dict[str, dict[str, Any]] = {}
    grouped_by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped_by_lang[r.get("language", "unknown")].append(r)
    for lang, group in grouped_by_lang.items():
        per_language[lang] = aggregate(group)

    markdown = render_markdown(
        input_path=input_path,
        records=records,
        overall=overall,
        per_category=per_category,
        per_language=per_language,
    )

    # Write report
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_name = input_path.stem.replace("agent_benchmark_", "agent_benchmark_report_") + ".md"
    report_path = args.output_dir / report_name
    report_path.write_text(markdown, encoding="utf-8")
    print(f"Report written to: {report_path}")

    if args.stdout:
        print()
        print(markdown)

    if overall.get("n_success", 0) > 0:
        print(
            f"\nSUMMARY  coverage={overall['tool_coverage'] * 100:.0f}%  "
            f"lat_avg={overall['latency_avg_s']:.1f}s  "
            f"cost=${overall['cost_total_usd']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
