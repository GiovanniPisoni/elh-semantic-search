"""Build blinded Anthropic Batch API JSONL files for all judge types.

Creates one JSONL batch file per judge type plus a mapping file.
ZERO cost: does NOT submit any batch or make any LLM call.

Blinding rule: prompts contain no system-identifying strings
  ('phase2', 'phase3', 'agent', 'pipeline', 'baseline').
  The separate id_mapping.jsonl maps custom_id -> {system, query_id, metric}.

Judges (model, count):
  M1_strict          Sonnet 4.6   192  (all 96 x 2 systems)
  M1_lenient         Haiku 4.5    192  (all 96 x 2 systems)
  M3a_refusal        Haiku 4.5     20  (out_of_scope 10 x 2)
  M3b_clarification  Haiku 4.5     24  (underspecified_ambiguous 12 x 2)
  M6_groundedness    Haiku 4.5    172  (all answerable 86 x 2)
  M7_multilingual    Haiku 4.5     28  (non-EN 14 x 2)
  M1_strict_agree    Haiku 4.5     30  (seeded random subset of M1_strict)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Blinding sanitizer
_BLIND_SUBS: list[tuple[re.Pattern, str]] = [
    # Explicit system names
    (re.compile(r'\bphase\s*2\b', re.IGNORECASE),    "System A"),
    (re.compile(r'\bphase\s*3\b', re.IGNORECASE),    "System B"),
    # Architecture labels
    (re.compile(r'\bpipeline\b', re.IGNORECASE),      "workflow"),
    (re.compile(r'\bbaseline\b', re.IGNORECASE),      "reference"),
    (re.compile(r'\bthe agent\b', re.IGNORECASE),     "the assistant"),
    (re.compile(r'\ban agent\b',  re.IGNORECASE),     "a housing assistant"),
    (re.compile(r'\bagent\b',     re.IGNORECASE),     "assistant"),
]


def _blind(text: str) -> str:
    """Strip system-identifying terms from text destined for a judge prompt."""
    for pattern, replacement in _BLIND_SUBS:
        text = pattern.sub(replacement, text)
    return text

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_P3  = _ROOT / "benchmarks/runs/phase2_vs_phase3/phase3_eval_v2.jsonl"
DEFAULT_P2  = _ROOT / "benchmarks/runs/phase2_vs_phase3/phase2_eval_v2.jsonl"
DEFAULT_QS  = _ROOT / "benchmarks/queries/phase2_vs_phase3/v2/golden_set_v2.yaml"
DEFAULT_OUT = _ROOT / "benchmarks/runs/phase2_vs_phase3/v2/judge_batches"

# Models
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"

# Pricing
LIST_IN:  dict[str, float] = {MODEL_SONNET: 3.00, MODEL_HAIKU: 1.00}
LIST_OUT: dict[str, float] = {MODEL_SONNET: 15.00, MODEL_HAIKU: 5.00}
BATCH_DISCOUNT = 0.50
MAX_OUT_TOKENS = 256   # all judges output short JSON

# Agreement subset config
AGREEMENT_N    = 30
AGREEMENT_SEED = 42

# System prompts (blinded)

SYS_M1_STRICT = """\
You are an evaluation judge for a student housing assistant.
Score the (query, answer) pair on a 3-point scale using the STRICT rubric below.

1.0 — fully solved:
  - Directly addresses the user's intent.
  - Cost queries include the COMPUTED TOTAL (not just components like monthly rent).
  - List queries return relevant, specific items.
  - Multi-step queries complete ALL required steps.
  - Ambiguous queries: either asks a clarifying question OR explicitly states an assumption.
  - Impossible / out-of-scope queries: refuses with a clear explanation.
  - Response is in the SAME LANGUAGE as the query.

0.5 — partial (borderline only):
  - Addresses the topic but misses one required component.
  - Correct content but in the wrong language.
  - One non-core hallucinated fact (core facts are correct).

0.0 — not solved:
  - Fabricates the core answer.
  - Gives an empty or unhelpful "I don't know" when a valid answer exists.
  - Confabulates instead of refusing / clarifying.

Be strict. Reserve 0.5 for genuinely borderline cases.
Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text before or after the JSON.\
"""

SYS_M1_LENIENT = """\
You are an evaluation judge for a student housing assistant.
Score the (question, answer) pair on a 3-point scale:

1.0 — Fully solves the task with specific, actionable content
      (concrete numbers, names, dates, or recommendations).

0.5 — Partially helpful. Relevant to the task but missing key information
      or too generic to act on.

0.0 — Off-topic, evasive, or provides no actionable content.

SPECIAL CASE: if the question is genuinely unanswerable for a student housing
assistant (legal, medical, out-of-scope), a clear refusal explaining why scores 1.0.

This metric judges only the (question, answer) pair. Ignore how the answer was
reached; judge only whether it is helpful.
Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "reason": "<one sentence>"}
No other text.\
"""

SYS_M3A = """\
You are an evaluation judge. The query below falls outside the scope of a student
housing assistant (which handles only room search, pricing, availability, policies,
and descriptions for student accommodation in Lisbon and Porto). The query asks about
something the assistant should refuse or redirect.

Score the answer:
1.0 — Clearly refuses to address the out-of-scope request AND explains why
      (or explains what it CAN help with instead).
0.5 — Hedges or gives a vague refusal without a clear explanation; or redirects
      without explaining that the request is out of scope.
0.0 — Attempts to answer the out-of-scope request as if it were in scope.

Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text.\
"""

SYS_M3B = """\
You are an evaluation judge. The query below is intentionally underspecified or
ambiguous: it has more than one valid reading, and a thoughtful assistant should
either ask a clarifying question or explicitly state an assumption before answering.

Score the answer:
1.0 — Ideal: explicitly asks for clarification OR states an assumption up front
      ("I'm assuming you mean X") and answers accordingly.
0.5 — Partial: hints at the ambiguity but does not address it clearly; or asks
      a partially helpful question without covering the key ambiguity.
0.0 — Does not acknowledge the ambiguity at all; answers one reading as if it
      were the only valid interpretation without flagging this.

Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text.\
"""

SYS_M6 = """\
You are an evaluation judge assessing factual groundedness of a housing-assistant
answer. Compare the answer to the ground-truth reference to detect fabrication.

Score the answer:
1.0 — Fully grounded: all specific claims (prices, room IDs, dates, availability)
      are consistent with or follow from the ground truth; no invented facts.
0.5 — Mostly grounded: one minor unsupported or vague claim; the core answer is sound.
0.0 — Significant fabrication: invents core facts (prices, room IDs, dates, totals)
      that are absent from or contradict the ground truth.

Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text.\
"""

SYS_M7 = """\
You are an evaluation judge. The query was written in a non-English language.
Assess TWO things:

(a) Language match: did the assistant respond in the SAME language as the query?
    (true = yes, false = responded in a different language)

(b) Content quality (same scale used for task success):
    1.0 — Fully addresses the query with specific, accurate information.
    0.5 — Partially addresses the query but misses key information.
    0.0 — Off-topic, evasive, or provides no useful information.

Output ONLY valid JSON:
{"language_ok": <true|false>, "content_score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text.\
"""

# User-message templates

def _user_msg_standard(query: str, category: str, difficulty: str,
                        ground_truth: str, answer: str) -> str:
    return (
        f"**Query**: {query}\n"
        f"**Category**: {category}\n"
        f"**Difficulty**: {difficulty}\n\n"
        f"**Ground truth reference**:\n{_blind(ground_truth)}\n\n"
        f"---\n"
        f"**Answer to evaluate**:\n{_blind(answer)}"
    )


def _user_msg_m7(query: str, language: str, category: str, difficulty: str,
                  ground_truth: str, answer: str) -> str:
    return (
        f"**Query language**: {language}\n"
        f"**Query**: {query}\n"
        f"**Category**: {category}\n"
        f"**Difficulty**: {difficulty}\n\n"
        f"**Ground truth reference**:\n{_blind(ground_truth)}\n\n"
        f"---\n"
        f"**Answer to evaluate**:\n{_blind(answer)}"
    )

# Token & cost estimation

def _approx_tokens(text: str) -> int:
    """Conservative token estimate: 1 token per 3.5 characters."""
    return max(1, int(len(text) / 3.5))


def _batch_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in  = LIST_IN.get(model, 3.00)  * (1 - BATCH_DISCOUNT)
    p_out = LIST_OUT.get(model, 15.00) * (1 - BATCH_DISCOUNT)
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000

# Batch record builder

def make_batch_record(custom_id: str, model: str,
                      system_prompt: str, user_message: str) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "params": {
            "model":      model,
            "max_tokens": MAX_OUT_TOKENS,
            "temperature": 0,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": user_message}],
        },
    }

# I/O helpers

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        qs = yaml.safe_load(f)
    return {q["id"]: q for q in qs}


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# Core builder

def build(p3_path: Path, p2_path: Path, qs_path: Path, out_dir: Path) -> None:
    bar  = "=" * 72
    thin = "-" * 72

    p3_recs = {r["id"]: r for r in load_jsonl(p3_path) if r.get("status") == "success"}
    p2_recs = {r["id"]: r for r in load_jsonl(p2_path) if r.get("status") == "success"}
    golden  = load_golden(qs_path)

    print(f"\n{bar}")
    print("  EVAL-V2 JUDGE BATCH BUILDER (Phase C/D)")
    print(f"{bar}")
    print(f"  Phase 3: {len(p3_recs)} records  Phase 2: {len(p2_recs)} records")
    print(f"  Output : {out_dir}\n")

    # Ordered list of all queries
    all_ids = list(golden.keys())

    # Filter sets
    qr_out_of_scope = [qid for qid in all_ids
                        if golden[qid]["category"] == "out_of_scope"]
    qr_ambiguous    = [qid for qid in all_ids
                        if golden[qid]["category"] == "underspecified_ambiguous"]
    qr_answerable   = [qid for qid in all_ids
                        if golden[qid]["category"] != "out_of_scope"]
    qr_non_en       = [qid for qid in all_ids
                        if golden[qid].get("language", "en") != "en"]

    print(f"  Query subsets:")
    print(f"    all             : {len(all_ids)}")
    print(f"    out_of_scope    : {len(qr_out_of_scope)}")
    print(f"    ambiguous       : {len(qr_ambiguous)}")
    print(f"    answerable      : {len(qr_answerable)}")
    print(f"    non-EN          : {len(qr_non_en)}\n")

    systems = [("phase3", p3_recs), ("phase2", p2_recs)]

    # All batch specs: (key, model, sys_prompt, query_ids, label)
    batch_specs = [
        ("M1_strict",         MODEL_SONNET, SYS_M1_STRICT,  all_ids,         "all"),
        ("M1_lenient",        MODEL_HAIKU,  SYS_M1_LENIENT, all_ids,         "all"),
        ("M3a_refusal",       MODEL_HAIKU,  SYS_M3A,        qr_out_of_scope, "out_of_scope"),
        ("M3b_clarification", MODEL_HAIKU,  SYS_M3B,        qr_ambiguous,    "underspecified_ambiguous"),
        ("M6_groundedness",   MODEL_HAIKU,  SYS_M6,         qr_answerable,   "answerable"),
        ("M7_multilingual",   MODEL_HAIKU,  SYS_M7,         qr_non_en,       "non-EN"),
    ]

    # Global mapping list (id_mapping.jsonl)
    all_mappings: list[dict] = []

    # Track M1_strict custom_ids for the agreement subset
    m1_strict_ids: list[str] = []

    batch_stats: list[dict] = []
    example_prompts: dict[str, dict] = {}

    for metric, model, sys_prompt, query_ids, scope_label in batch_specs:
        batch_records: list[dict] = []

        for qid in query_ids:
            q       = golden[qid]
            gt      = q["ground_truth"]
            query   = q["query"]
            cat     = q["category"]
            diff    = q.get("difficulty", "medium")
            lang    = q.get("language", "en")
            ambig_t = q.get("ambiguity_type")

            for system_name, recs in systems:
                rec = recs.get(qid)
                if rec is None:
                    continue
                answer = rec.get("final_message", "")

                cid = f"{metric}_{system_name}_{qid}"

                if metric == "M7_multilingual":
                    user_msg = _user_msg_m7(query, lang, cat, diff, gt, answer)
                else:
                    user_msg = _user_msg_standard(query, cat, diff, gt, answer)

                batch_records.append(make_batch_record(cid, model, sys_prompt, user_msg))

                mapping_entry: dict[str, Any] = {
                    "custom_id": cid,
                    "system":    system_name,
                    "query_id":  qid,
                    "metric":    metric,
                    "category":  cat,
                    "language":  lang,
                }
                if ambig_t:
                    mapping_entry["ambiguity_type"] = ambig_t
                    mapping_entry["ambiguity_subtype"] = q.get("ambiguity_subtype")
                all_mappings.append(mapping_entry)

                if metric == "M1_strict":
                    m1_strict_ids.append(cid)

                if metric == "M1_strict" and "M1_strict" not in example_prompts:
                    example_prompts["M1_strict"] = {
                        "system": sys_prompt, "user": user_msg,
                        "custom_id": cid, "model": model,
                    }
                if metric == "M3b_clarification" and "M3b_clarification" not in example_prompts:
                    example_prompts["M3b_clarification"] = {
                        "system": sys_prompt, "user": user_msg,
                        "custom_id": cid, "model": model,
                    }

        # Cost estimation
        sys_tokens  = _approx_tokens(sys_prompt)
        # Mean user message tokens (sample from first record)
        sample_user = batch_records[0]["params"]["messages"][0]["content"] if batch_records else ""
        user_tokens = _approx_tokens(sample_user)
        mean_in = sys_tokens + user_tokens
        n = len(batch_records)
        total_in  = mean_in * n
        total_out = MAX_OUT_TOKENS * n
        cost = _batch_cost(model, total_in, total_out)

        batch_stats.append({
            "metric":     metric,
            "model":      model,
            "n":          n,
            "sys_tok":    sys_tokens,
            "user_tok":   user_tokens,
            "mean_in":    mean_in,
            "total_in":   total_in,
            "total_out":  total_out,
            "cost_usd":   cost,
        })

        fname = out_dir / f"batch_{metric}.jsonl"
        write_jsonl(fname, batch_records)
        print(f"  Wrote {fname.name}  ({n} records)")

    # M1_strict_agreement subset
    rng = random.Random(AGREEMENT_SEED)
    agree_ids = rng.sample(m1_strict_ids, min(AGREEMENT_N, len(m1_strict_ids)))

    # Look up full batch records from M1_strict file
    m1_strict_path = out_dir / "batch_M1_strict.jsonl"
    m1_strict_lookup = {r["custom_id"]: r for r in load_jsonl(m1_strict_path)}

    agree_records: list[dict] = []
    for cid in agree_ids:
        orig = m1_strict_lookup[cid]
        # Same prompt, different model, different custom_id prefix
        new_cid = "M1_strict_agree_" + cid[len("M1_strict_"):]
        agree_records.append(make_batch_record(
            new_cid, MODEL_HAIKU,
            orig["params"]["system"],
            orig["params"]["messages"][0]["content"],
        ))
        # Get original mapping
        orig_map = next(m for m in all_mappings if m["custom_id"] == cid)
        entry: dict[str, Any] = {
            "custom_id":    new_cid,
            "system":       orig_map["system"],
            "query_id":     orig_map["query_id"],
            "metric":       "M1_strict_agree",
            "category":     orig_map["category"],
            "language":     orig_map["language"],
            "source_cid":   cid,
        }
        all_mappings.append(entry)

    agree_path = out_dir / "batch_M1_strict_agree.jsonl"
    write_jsonl(agree_path, agree_records)
    print(f"  Wrote {agree_path.name}  ({len(agree_records)} records, seed={AGREEMENT_SEED})")

    # Cost for agreement batch
    n_a = len(agree_records)
    s = batch_stats[0]
    cost_a = _batch_cost(MODEL_HAIKU, s["mean_in"] * n_a, MAX_OUT_TOKENS * n_a)
    batch_stats.append({
        "metric": "M1_strict_agree", "model": MODEL_HAIKU,
        "n": n_a, "sys_tok": s["sys_tok"], "user_tok": s["user_tok"],
        "mean_in": s["mean_in"], "total_in": s["mean_in"] * n_a,
        "total_out": MAX_OUT_TOKENS * n_a, "cost_usd": cost_a,
    })

    # Write id_mapping.jsonl
    mapping_path = out_dir / "id_mapping.jsonl"
    write_jsonl(mapping_path, all_mappings)
    print(f"  Wrote {mapping_path.name}  ({len(all_mappings)} entries)\n")

    # Agreement subset IDs record
    agree_meta_path = out_dir / "agreement_subset_ids.json"
    agree_meta_path.write_text(
        json.dumps({
            "seed": AGREEMENT_SEED,
            "n": len(agree_ids),
            "sampled_from": "batch_M1_strict.jsonl",
            "haiku_batch": "batch_M1_strict_agree.jsonl",
            "source_custom_ids": agree_ids,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Wrote {agree_meta_path.name}\n")

    # Cost summary table
    print(f"{bar}")
    print("  ESTIMATED BATCH COSTS  (50% batch discount applied)")
    print(f"{thin}")
    print(f"  {'Metric':<24} {'Model':<30} {'N':>5} {'~in/call':>9} {'~tot_in':>9} "
          f"{'~tot_out':>9} {'$USD':>8}")
    total_cost = 0.0
    for s in batch_stats:
        print(f"  {s['metric']:<24} {s['model']:<30} {s['n']:>5} "
              f"{s['mean_in']:>9,} {s['total_in']:>9,} {s['total_out']:>9,} "
              f"${s['cost_usd']:>7.4f}")
        total_cost += s["cost_usd"]
    print(f"{thin}")
    print(f"  {'TOTAL JUDGE COST':<24} {'':30} {'':5} {'':9} {'':9} {'':9} "
          f"${total_cost:>7.4f}")

    spent_runs = 2.274
    remaining = 5.70 - spent_runs
    after_judges = remaining - total_cost
    print(f"\n  Budget:           $5.7000")
    print(f"  Spent (runs):    -${spent_runs:.4f}  (Phase B projection, both systems)")
    print(f"  Remaining:        ${remaining:.4f}")
    print(f"  Judge cost:      -${total_cost:.4f}  (estimate, batch 50% off)")
    print(f"  After judges:     ${after_judges:.4f}  margin for re-runs / Phase E\n")

    # Example prompts
    print(f"{bar}")
    print("  EXAMPLE PROMPT 1: M1_strict")
    print(f"{thin}")
    ep = example_prompts.get("M1_strict", {})
    print(f"  custom_id : {ep.get('custom_id')}")
    print(f"  model     : {ep.get('model')}")
    print(f"\n  --- SYSTEM PROMPT ---\n")
    for line in ep.get("system", "").splitlines():
        print(f"  {line}")
    print(f"\n  --- USER MESSAGE ---\n")
    for line in ep.get("user", "").splitlines():
        print(f"  {line}")
    print()

    print(f"{bar}")
    print("  EXAMPLE PROMPT 2: M3b_clarification")
    print(f"{thin}")
    ep2 = example_prompts.get("M3b_clarification", {})
    print(f"  custom_id : {ep2.get('custom_id')}")
    print(f"  model     : {ep2.get('model')}")
    print(f"\n  --- SYSTEM PROMPT ---\n")
    for line in ep2.get("system", "").splitlines():
        print(f"  {line}")
    print(f"\n  --- USER MESSAGE ---\n")
    for line in ep2.get("user", "").splitlines():
        print(f"  {line}")
    print()

    # Verification counts
    print(f"{bar}")
    print("  VERIFICATION: expected vs actual counts")
    print(f"{thin}")
    expected = {
        "M1_strict":         2 * len(all_ids),
        "M1_lenient":        2 * len(all_ids),
        "M3a_refusal":       2 * len(qr_out_of_scope),
        "M3b_clarification": 2 * len(qr_ambiguous),
        "M6_groundedness":   2 * len(qr_answerable),
        "M7_multilingual":   2 * len(qr_non_en),
        "M1_strict_agree":   len(agree_records),
    }
    for s in batch_stats:
        exp = expected.get(s["metric"], "?")
        ok = "OK" if s["n"] == exp else "MISMATCH"
        print(f"  {s['metric']:<24} expected={exp:>4}  actual={s['n']:>4}  {ok}")

    print(f"\n  Agreement subset IDs (seed={AGREEMENT_SEED}):")
    for cid in agree_ids:
        print(f"    {cid}")
    print(f"\n{bar}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase3",   type=Path, default=DEFAULT_P3)
    p.add_argument("--phase2",   type=Path, default=DEFAULT_P2)
    p.add_argument("--queries",  type=Path, default=DEFAULT_QS)
    p.add_argument("--out-dir",  type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    for path in [args.phase3, args.phase2, args.queries]:
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
    build(args.phase3, args.phase2, args.queries, args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
