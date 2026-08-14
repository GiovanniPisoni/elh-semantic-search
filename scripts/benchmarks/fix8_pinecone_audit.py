"""FIX 8 — Pinecone index audit vs SQL house table.

Settles the H-stale / H-fab debate for the 16 P2 'fabricated' names by querying
the CURRENT state of both Pinecone indexes.

SECURITY: reads credentials from env only; never prints them.

Usage:
    python scripts/benchmarks/fix8_pinecone_audit.py
"""
from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg2

_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Env / credentials
# ---------------------------------------------------------------------------

def load_env() -> None:
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def get_pc():
    from pinecone import Pinecone
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY not set")
    return Pinecone(api_key=api_key)


def get_db_conn():
    uri = os.environ.get("DB_URI")
    if not uri:
        raise RuntimeError("DB_URI not set")
    return psycopg2.connect(uri)


# ---------------------------------------------------------------------------
# Name normalisation (same as build_m6_repair.py)
# ---------------------------------------------------------------------------

def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[-_–—]", " ", s)
    s = re.sub(r"['\"]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Fabricated names from FIX 6/7 residual list (base property names, deduplicated)
_FAB_BASE_NAMES = [
    "Residencia Nevogilde",
    "Residencia Bonfim",
    "Santos Student Flat",
    "Studio Loft",
]

# ---------------------------------------------------------------------------
# Pinecone sampling — collect all distinct flatname+idhouse metadata
# ---------------------------------------------------------------------------

def _collect_metadata_via_list(index, index_name: str) -> list[dict]:
    """Use index.list() (Pinecone Serverless) to enumerate all IDs, then fetch."""
    print(f"  [{index_name}] Listing all vector IDs …")
    all_ids: list[str] = []
    try:
        for batch in index.list(limit=100):
            # batch may be a list of strings or an object with .vectors
            if isinstance(batch, list):
                all_ids.extend(batch)
            else:
                # newer SDK: batch might be a ListResponse
                ids_batch = getattr(batch, "vectors", None) or getattr(batch, "ids", None) or batch
                all_ids.extend(ids_batch if isinstance(ids_batch, list) else [str(ids_batch)])
            if len(all_ids) % 1000 == 0 and len(all_ids) > 0:
                print(f"  [{index_name}]   … {len(all_ids)} IDs so far")
    except Exception as e:
        print(f"  [{index_name}] list() failed: {e!r} — falling back to query sampling")
        return []

    print(f"  [{index_name}] Total IDs listed: {len(all_ids)}")
    if not all_ids:
        return []

    # Fetch in batches of 100 (Pinecone fetch limit)
    records: list[dict] = []
    for start in range(0, len(all_ids), 100):
        batch = all_ids[start: start + 100]
        try:
            resp = index.fetch(ids=batch)
            vecs = getattr(resp, "vectors", resp) if not isinstance(resp, dict) else resp
            if isinstance(vecs, dict):
                for vid, vec in vecs.items():
                    meta = getattr(vec, "metadata", {}) or {}
                    if not isinstance(meta, dict):
                        meta = dict(meta)
                    records.append({"id": vid, **meta})
        except Exception as e:
            print(f"  [{index_name}] fetch batch {start}–{start+100} failed: {e!r}")
        if (start // 100) % 20 == 0 and start > 0:
            print(f"  [{index_name}]   fetched metadata for {len(records)} vectors")
            time.sleep(0.1)

    return records


def _collect_metadata_via_query(index, index_name: str, dim: int, n_samples: int = 300) -> list[dict]:
    """Fallback: random-vector queries to sample metadata."""
    import random
    print(f"  [{index_name}] Sampling via random-vector queries (n={n_samples}) …")
    records: list[dict] = []
    seen_ids: set[str] = set()

    for _ in range(n_samples // 10):
        vec = [random.gauss(0, 1) for _ in range(dim)]
        try:
            resp = index.query(vector=vec, top_k=10, include_metadata=True)
            matches = getattr(resp, "matches", []) or []
            for m in matches:
                vid = getattr(m, "id", str(m))
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    meta = getattr(m, "metadata", {}) or {}
                    if not isinstance(meta, dict):
                        meta = dict(meta)
                    records.append({"id": vid, **meta})
        except Exception as e:
            print(f"  [{index_name}] query sample failed: {e!r}")

    return records


def _targeted_lookup(index, index_name: str, flatname: str, dim: int) -> list[dict]:
    """Query with metadata filter on flatname (exact match)."""
    results: list[dict] = []
    dummy = [0.0] * dim
    try:
        resp = index.query(
            vector=dummy,
            top_k=50,
            include_metadata=True,
            filter={"flatname": {"$eq": flatname}},
        )
        matches = getattr(resp, "matches", []) or []
        for m in matches:
            meta = getattr(m, "metadata", {}) or {}
            if not isinstance(meta, dict):
                meta = dict(meta)
            results.append({"id": getattr(m, "id", ""), "score": float(getattr(m, "score", 0)), **meta})
    except Exception as e:
        print(f"  [{index_name}] metadata filter on flatname={flatname!r} failed: {e!r}")
    return results


def audit_index(pc, index_name: str) -> dict:
    """Collect stats + metadata from one Pinecone index."""
    print(f"\n  Connecting to index '{index_name}' …")
    try:
        index = pc.Index(index_name)
    except Exception as e:
        return {"error": str(e), "index_name": index_name}

    # Stats
    stats = {}
    try:
        raw_stats = index.describe_index_stats()
        stats["total_vector_count"] = int(raw_stats.total_vector_count)
        namespaces = getattr(raw_stats, "namespaces", {}) or {}
        stats["namespaces"] = {k: getattr(v, "vector_count", v) for k, v in namespaces.items()}
        dim = int(getattr(raw_stats, "dimension", 768))
        stats["dimension"] = dim
    except Exception as e:
        print(f"  describe_index_stats failed: {e!r}")
        dim = 768
        stats["total_vector_count"] = -1

    print(f"  Vector count : {stats.get('total_vector_count', '?')}")
    print(f"  Dimension    : {stats.get('dimension', '?')}")
    if stats.get("namespaces"):
        print(f"  Namespaces   : {stats['namespaces']}")

    # Collect metadata
    records = _collect_metadata_via_list(index, index_name)
    if not records:
        records = _collect_metadata_via_query(index, index_name, dim)

    # Aggregate distinct values
    distinct_idhouse: dict[str, int] = defaultdict(int)   # idhouse → count
    distinct_flatname: dict[str, int] = defaultdict(int)  # flatname → count
    for r in records:
        ih = (r.get("idhouse") or "").strip()
        fn = (r.get("flatname") or "").strip()
        if ih:
            distinct_idhouse[ih] += 1
        if fn:
            distinct_flatname[fn] += 1

    # Targeted flatname lookup for each fabricated name
    fab_results: dict[str, list[dict]] = {}
    for base in _FAB_BASE_NAMES:
        hits = _targeted_lookup(index, index_name, base, dim)
        fab_results[base] = hits
        # Also try normalised forms
        norm = _norm_name(base)
        # Common accent variants
        for variant in [base, base.replace("Residencia", "Residência"),
                        base.replace("Flat", "Flat ")]:
            if variant != base:
                h2 = _targeted_lookup(index, index_name, variant, dim)
                if h2:
                    fab_results[f"{base} (variant: {variant!r})"] = h2

    return {
        "index_name":       index_name,
        "stats":            stats,
        "n_sampled":        len(records),
        "distinct_idhouse": dict(distinct_idhouse),
        "distinct_flatname": dict(distinct_flatname),
        "fab_results":      fab_results,
    }


# ---------------------------------------------------------------------------
# SQL reference sets
# ---------------------------------------------------------------------------

def sql_reference(conn) -> dict:
    cur = conn.cursor()
    cur.execute("""
SELECT TRIM(idhouse) AS idhouse, TRIM(flatname) AS flatname, TRIM(status) AS status
FROM house
WHERE flatname IS NOT NULL AND TRIM(flatname) != ''
""")
    rows = cur.fetchall()
    sql_idhouses  = {r[0] for r in rows}
    sql_flatnames = {r[1] for r in rows}
    # Review corpus idhouses
    cur.execute("SELECT DISTINCT TRIM(loc_idhouse) FROM review WHERE status='approved'")
    review_idhouses = {r[0] for r in cur.fetchall()}
    cur.close()
    return {
        "sql_idhouses":     sql_idhouses,
        "sql_flatnames":    sql_flatnames,
        "review_idhouses":  review_idhouses,
        "n_house":          len(sql_idhouses),
        "n_flatname":       len(sql_flatnames),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_env()

    bar  = "=" * 72
    thin = "-" * 72

    print(f"\n{bar}")
    print("  FIX 8 — PINECONE INDEX AUDIT  (runs evaluated 2026-07-28)")
    print(f"  CAVEAT: this measures index state TODAY (2026-07-31).")
    print(f"  If indexes were modified after 2026-07-28 the test may not")
    print(f"  reflect the state the system queried during the runs.")
    print(f"{bar}\n")

    # SQL baseline
    print(f"{thin}")
    print("  SQL BASELINE")
    print(f"{thin}")
    conn = get_db_conn()
    sql = sql_reference(conn)
    conn.close()
    print(f"  House table: {sql['n_house']} distinct idhouses, {sql['n_flatname']} distinct flatnames")
    print(f"  Review corpus: {len(sql['review_idhouses'])} distinct idhouses with approved reviews")

    # Pinecone audit
    pc = get_pc()

    reviews_audit     = audit_index(pc, "elh-reviews")
    descriptions_audit = audit_index(pc, "elh-descriptions")

    for audit in [reviews_audit, descriptions_audit]:
        if "error" in audit:
            print(f"\n  !! Index '{audit['index_name']}' error: {audit['error']}")
            continue

        idx     = audit["index_name"]
        pin_ihs = set(audit["distinct_idhouse"].keys())
        pin_fns = set(audit["distinct_flatname"].keys())

        print(f"\n{thin}")
        print(f"  INDEX: {idx}")
        print(f"{thin}")
        print(f"  Vector count (Pinecone): {audit['stats'].get('total_vector_count', '?')}")
        print(f"  Vectors sampled for metadata: {audit['n_sampled']}")
        print(f"  Distinct idhouse in sample : {len(pin_ihs)}")
        print(f"  Distinct flatname in sample: {len(pin_fns)}")

        # Drift analysis
        if pin_ihs:
            in_pin_not_sql = pin_ihs - sql["sql_idhouses"]
            in_sql_not_pin = sql["sql_idhouses"] - pin_ihs
            print(f"\n  DRIFT vs SQL house table:")
            print(f"    idhouse in Pinecone NOT in SQL : {len(in_pin_not_sql)}", end="")
            if in_pin_not_sql:
                print(f"  →  {sorted(in_pin_not_sql)[:5]}")
            else:
                print()
            print(f"    idhouse in SQL NOT in Pinecone : {len(in_sql_not_pin)}", end="")
            if in_sql_not_pin:
                print(f"  →  {sorted(in_sql_not_pin)[:5]}")
            else:
                print()

        if pin_fns:
            in_pin_not_sql = pin_fns - sql["sql_flatnames"]
            in_sql_not_pin = sql["sql_flatnames"] - pin_fns
            print(f"\n  DRIFT vs SQL flatnames:")
            print(f"    flatname in Pinecone NOT in SQL: {len(in_pin_not_sql)}", end="")
            if in_pin_not_sql:
                print(f"  →  {sorted(in_pin_not_sql)[:5]}")
            else:
                print()
            print(f"    flatname in SQL NOT in Pinecone: {len(in_sql_not_pin)}", end="")
            if in_sql_not_pin:
                print(f"  →  {sorted(in_sql_not_pin)[:5]}")
            else:
                print()

        # Targeted lookup for fabricated names
        print(f"\n  TARGETED LOOKUP — fabricated names in '{idx}':")
        print(f"  {'Name':<35} {'hits':>5}  idhouse(s) found")
        print(f"  {'-'*35} {'-'*5}  {'-'*30}")
        any_found = False
        for name, hits in audit["fab_results"].items():
            n = len(hits)
            idhse = sorted({h.get("idhouse", "") for h in hits if h.get("idhouse")})
            found_str = ", ".join(idhse[:3]) if idhse else ("(metadata match, no idhouse)" if n else "—")
            print(f"  {name:<35} {n:>5}  {found_str}")
            if n > 0:
                any_found = True
        if not any_found:
            print(f"  → None of the fabricated names found in '{idx}' via metadata filter.")

    # Summary verdict
    print(f"\n{bar}")
    print("  FIX 8 VERDICT SUMMARY")
    print(f"{bar}")

    all_fab_hits_reviews     = {
        n for n, h in reviews_audit.get("fab_results", {}).items() if h
    }
    all_fab_hits_desc        = {
        n for n, h in descriptions_audit.get("fab_results", {}).items() if h
    }
    any_found_total = all_fab_hits_reviews | all_fab_hits_desc

    rev_drift = len(set(reviews_audit.get("distinct_idhouse", {}).keys()) - sql["sql_idhouses"])
    des_drift = len(set(descriptions_audit.get("distinct_idhouse", {}).keys()) - sql["sql_idhouses"])

    if rev_drift > 0 or des_drift > 0:
        print(f"  H-STALE signal: {rev_drift} stale idhouses in reviews index, "
              f"{des_drift} in descriptions index.")
    else:
        print(f"  No stale idhouses detected in either index "
              f"(index appears re-synced with current SQL).")

    if any_found_total:
        print(f"  Fabricated names found in Pinecone → H-STALE supported:")
        for n in sorted(any_found_total):
            print(f"    {n}")
        print(f"\n  -> These names are CORPUS_GROUNDED (Pinecone had them during the run).")
        print(f"     FIX 8 update: reclassify from TRUE_FABRICATION → CORPUS_GROUNDED.")
    else:
        print(f"  None of the fabricated names found in current Pinecone indexes.")
        print(f"  -> H-fab supported: names absent from both SQL and Pinecone today.")
        print(f"     If indexes were NOT modified after 2026-07-28:")
        print(f"       TRUE_FABRICATION classification is confirmed.")
        print(f"     If indexes were re-indexed after that date:")
        print(f"       This test cannot rule out H-stale (stale entries may have been removed).")

    print(f"\n  CAVEAT (per FIX 8 spec): this audit ran on 2026-07-31.")
    print(f"  Benchmark runs executed on 2026-07-28. If the Pinecone indexes")
    print(f"  were modified between those dates, this test is NOT conclusive.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
