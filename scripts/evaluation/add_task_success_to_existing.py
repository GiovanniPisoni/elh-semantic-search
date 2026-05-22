"""Retrofit task_success scores onto an existing evaluation JSONL.

Reads a JSONL produced by run_custom_eval.py before task_success
existed, computes task_success on each record's (question, answer)
pair, and writes a new JSONL with the task_success_score and
task_success_details fields added.

Records that already have task_success_score are skipped (idempotent).
Records missing 'question' or 'answer' fields are passed through
unchanged with a logged warning.

Usage:
    python -m scripts.evaluation.add_task_success_to_existing \
        --input evaluation/reports/light_eval/INPUT.jsonl \
        --output evaluation/reports/light_eval/OUTPUT.jsonl

Cost: ~$0.001 per query, so ~$0.02 for a 20-query JSONL.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from elh_rag.evaluation.judge import EvaluationJudge
from elh_rag.evaluation.metrics import task_success


def retrofit(input_path: Path, output_path: Path) -> dict[str, int]:
    """Read input JSONL, compute task_success per record, write new JSONL.

    Returns counts: {total, scored, skipped_existing, skipped_invalid}.
    """
    judge = EvaluationJudge()
    counts = {"total": 0, "scored": 0, "skipped_existing": 0, "skipped_invalid": 0}

    with (
        input_path.open("r", encoding="utf-8") as infile,
        output_path.open("w", encoding="utf-8") as outfile,
    ):
        for line_num, raw in enumerate(infile, 1):
            line = raw.strip()
            if not line:
                continue
            counts["total"] += 1

            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  line {line_num}: invalid JSON, skipping: {exc}")
                counts["skipped_invalid"] += 1
                continue

            if "task_success_score" in rec:
                outfile.write(line + "\n")
                counts["skipped_existing"] += 1
                continue

            question = rec.get("question") or rec.get("query")
            answer = rec.get("answer", "")

            if not question or not answer:
                outfile.write(line + "\n")
                counts["skipped_invalid"] += 1
                print(f"  line {line_num} ({rec.get('id', '?')}): missing question/answer")
                continue

            result = task_success(judge=judge, question=question, answer=answer)
            rec["task_success_score"] = result.score
            rec["task_success_details"] = result.details
            outfile.write(json.dumps(rec, ensure_ascii=False) + "\n")
            counts["scored"] += 1

            score_repr = f"{result.score:.2f}" if result.score is not None else "ERR"
            print(f"  line {line_num} ({rec.get('id', '?')}): {score_repr}")

            time.sleep(0.1)  # gentle rate limiting

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrofit task_success on an existing JSONL.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Retrofitting task_success: {args.input} -> {args.output}")
    counts = retrofit(args.input, args.output)
    print()
    print(
        f"Done. Total: {counts['total']}, Scored: {counts['scored']}, "
        f"Skipped (existing): {counts['skipped_existing']}, "
        f"Skipped (invalid): {counts['skipped_invalid']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
