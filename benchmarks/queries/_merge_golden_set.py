"""Merge the 8 eval-v2 cassettes into a single frozen golden_set_v2.yaml and
print its sha256. Deterministic order → reproducible hash. Run from repo root."""
import hashlib
import sys
from collections import Counter
from pathlib import Path

import yaml

QDIR = Path("benchmarks/queries")

# Fixed concatenation order → the hash is reproducible.
CASSETTES = [
    ("out_of_scope",            "golden_set_v2_out_of_scope.yaml",            10),
    ("policy_rules",            "golden_set_v2_policy_rules.yaml",            12),
    ("subjective_reviews",      "golden_set_v2_subjective_reviews.yaml",      10),
    ("subjective_descriptions", "golden_set_v2_subjective_descriptions.yaml", 10),
    ("underspecified_ambiguous","golden_set_v2_underspecified_ambiguous.yaml",12),
    ("factual_lookup",          "golden_set_v2_factual_lookup.yaml",          12),
    ("constraint_satisfaction", "golden_set_v2_constraint_satisfaction.yaml", 14),
    ("quantitative_reasoning",  "golden_set_v2_quantitative_reasoning.yaml",  16),
]
REQUIRED = {"id", "category", "language", "hop_count", "query",
            "expected_answer_type", "ground_truth"}

merged, errors, seen_ids = [], [], set()

for expected_cat, fname, expected_n in CASSETTES:
    path = QDIR / fname
    if not path.exists():
        errors.append(f"MISSING FILE: {fname}")
        continue
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    if len(entries) != expected_n:
        errors.append(f"{fname}: expected {expected_n} entries, found {len(entries)}")
    for e in entries:
        missing = REQUIRED - set(e)
        if missing:
            errors.append(f"{e.get('id','?')}: missing fields {missing}")
        if e.get("category") != expected_cat:
            errors.append(f"{e.get('id','?')}: category '{e.get('category')}' != '{expected_cat}'")
        if e["id"] in seen_ids:
            errors.append(f"DUPLICATE id: {e['id']}")
        seen_ids.add(e["id"])
        merged.append(e)

if errors:
    print("VALIDATION FAILED:")
    for err in errors:
        print("  -", err)
    sys.exit(1)

if len(merged) != 96:
    print(f"TOTAL MISMATCH: {len(merged)} entries (expected 96)")
    sys.exit(1)

# Canonical serialization → stable bytes → stable hash.
text = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True,
                      default_flow_style=False, width=100)
out = QDIR / "golden_set_v2.yaml"
out.write_text(text, encoding="utf-8")
digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

print(f"MERGED: {len(merged)} entries -> {out}")
print("\nBy category:")
for cat, _, n in CASSETTES:
    print(f"  {cat:26} {n}")
print("\nBy language:", dict(Counter(e["language"] for e in merged)))
print("By hop_count:", dict(sorted(Counter(e["hop_count"] for e in merged).items())))
print("By expected_answer_type:", dict(Counter(e["expected_answer_type"] for e in merged)))
print(f"\nsha256: {digest}")
print("^ paste this into PREREGISTRATION_EVAL_V2.md")