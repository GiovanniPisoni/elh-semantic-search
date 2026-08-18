"""M6 groundedness — REPAIRED (truth-table) design, fresh-index arm.

The plain M6 batch shows the judge only {ground_truth, answer}. For the 26
list-returning queries (constraint_satisfaction x14 + factual_lookup x12) the
ground_truth states only a count + filters, so correctly-retrieved rooms look
fabricated to a judge with no DB access. This script gives the judge the
actual DATABASE TRUTH TABLE instead.

STEP A — read-only SQL truth tables (free).
STEP B — deterministic entity-extraction check against the truth tables (free).
STEP C — build the 52-request judge batch (build only, zero cost).

SECURITY: reads DB_URI from env only; never prints credentials.

Both Pinecone indexes were rebuilt from the current SQL catalogue (see
preregistration_eval.md addendum 2026-07-31); the old FIX 7/8 stale-corpus
reclassification (Residencia Nevogilde / Bonfim / Santos Student Flat ->
CORPUS_GROUNDED) is OBSOLETE and is NOT reimplemented here. No name is
hardcoded as an exception; every claim is scored against the live DB.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import yaml

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from elh_rag.tools._shared.metro_lines import (  # noqa: E402
    LISBON_NEIGHBORHOOD_TO_LINES,
    LISBON_ZONE_TO_LINES,
    PORTO_NEIGHBORHOOD_TO_LINES,
    PORTO_ZONE_TO_LINES,
    zones_on_line,
)
from elh_rag.tools._shared.room_id import encode_house_id, encode_room_id  # noqa: E402

DEFAULT_P3 = _ROOT / "benchmarks/runs/phase2_vs_phase3/v2/phase3_eval_v2_fresh.jsonl"
DEFAULT_P2 = _ROOT / "benchmarks/runs/phase2_vs_phase3/v2/phase2_eval_v2_fresh.jsonl"
DEFAULT_QS = _ROOT / "benchmarks/queries/phase2_vs_phase3/v2/golden_set_v2.yaml"
DEFAULT_OUT = _ROOT / "benchmarks/runs/phase2_vs_phase3/v2/judge_batches_fresh"

MODEL_HAIKU = "claude-haiku-4-5-20251001"
LIST_IN = {MODEL_HAIKU: 1.00}
LIST_OUT = {MODEL_HAIKU: 5.00}
BATCH_DISCOUNT = 0.50
MAX_OUT_TOKENS = 256
MAX_ROWS_IN_PROMPT = None  # v2: no cap -- truth table includes every matching room

BAR = "=" * 72
THIN = "-" * 72

# ---------------------------------------------------------------------------
# Env / DB
# ---------------------------------------------------------------------------


def load_env() -> None:
    p = _ROOT / ".env"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def get_conn():
    load_env()
    uri = os.environ.get("DB_URI")
    if not uri:
        raise RuntimeError("DB_URI not set")
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    return conn


def q(cur, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    if cur.description is None:
        return []
    return [dict(r) for r in cur.fetchall()]


# Columns pulled for every room-list truth table (cheap, single JOIN, small DB)
ROOM_LIST_COLUMNS = """
    r.idroom, r.loc_idhouse, r.dateupdate AS r_dateupdate,
    h.idhouse, h.dateupdate AS h_dateupdate,
    h.flatname, r.roomname, h.city, h.zone, h.neighboorhood AS neighborhood,
    r.autumnprice AS price_eur, r.springprice, r.summerprice, r.fixedprice,
    r.area, r.singlebed, r.doublebed, r.kingbed, r.queenbed, r.couchbed, r.secondbed,
    r.deposit, r.depositvalue,
    r.privatebathroom, r.balcony, r.desk, r.minreservemonths,
    r.extrapersonallowed, r.extrapersoncost,
    h.elevator, h.distancepublictransport, h.femalepreferred, h.malepreferred,
    h.internet, h.furnished, h.allowpets, h.washerdrier
"""

ROOM_LIST_FROM = """
    FROM room r
    JOIN house h ON h.idhouse = r.loc_idhouse AND h.dateupdate = r.loc_dateupdate
"""


def _bed_type_label(row: dict[str, Any]) -> str:
    primary = None
    for col, label in (
        ("kingbed", "king"), ("queenbed", "queen"), ("doublebed", "double"),
        ("singlebed", "single"), ("couchbed", "couch"),
    ):
        if row.get(col) == "Y":
            primary = label
            break
    if primary is None:
        return "?"
    if row.get("secondbed") == "Y":
        return f"{primary}+second"
    return primary


def _room_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    room_id = encode_room_id(row["loc_idhouse"], row["idroom"], row["r_dateupdate"])
    house_id = encode_house_id(row["idhouse"], row["h_dateupdate"])
    return {
        "room_id": room_id,
        "house_id": house_id,
        "flatname": (row.get("flatname") or "").strip(),
        "roomname": (row.get("roomname") or "").strip(),
        "city": (row["city"] or "").strip(),
        "zone": (row["zone"] or "").strip(),
        "neighborhood": (row.get("neighborhood") or "").strip() or None,
        "price_eur": float(row["price_eur"]) if row["price_eur"] is not None else None,
        "spring_price": float(row["springprice"]) if row.get("springprice") is not None else None,
        "summer_price": float(row["summerprice"]) if row.get("summerprice") is not None else None,
        "fixed_price": row.get("fixedprice") == "Y",
        "area_m2": float(row["area"]) if row.get("area") is not None else None,
        "bed_type": _bed_type_label(row),
        "deposit": row.get("deposit") == "Y",
        "deposit_value": float(row["depositvalue"]) if row.get("depositvalue") is not None else None,
        "attrs": {
            "private_bathroom": row.get("privatebathroom") == "Y",
            "balcony": row.get("balcony") == "Y",
            "desk": row.get("desk") == "Y",
            "min_reserve_months": row.get("minreservemonths"),
            "extra_person_allowed": row.get("extrapersonallowed") == "Y",
            "extra_person_cost": (
                float(row["extrapersoncost"]) if row.get("extrapersoncost") is not None else None
            ),
            "elevator": row.get("elevator") == "Y",
            "distance_to_transport_m": row.get("distancepublictransport"),
            "female_preferred": row.get("femalepreferred") == "Y",
            "male_preferred": row.get("malepreferred") == "Y",
            "internet": row.get("internet") == "Y",
            "furnished": row.get("furnished") == "Y",
            "allow_pets": row.get("allowpets") == "Y",
            "washer_drier": row.get("washerdrier") == "Y",
        },
    }


# ---------------------------------------------------------------------------
# Query specs — one entry per list-returning query (14 CS + 12 FL = 26)
# Filters/SQL transcribed verbatim from the golden set's own "notes" field
# (each was itself SQL-verified against the DB when the golden set was frozen).
# ---------------------------------------------------------------------------

QuerySpec = dict[str, Any]

QUERY_SPECS: list[QuerySpec] = [
    dict(id="constraint_satisfaction_01", city="Lisbon",
         where="r.privatebathroom = 'Y' AND r.autumnprice <= %s", params=(1000,),
         relevant_attrs=["private_bathroom"], preregistered=35, tolerance=0),
    dict(id="constraint_satisfaction_02", city="Porto",
         where="r.balcony = 'Y' AND h.washerdrier = 'Y'", params=(),
         relevant_attrs=["balcony", "washer_drier"], preregistered=47, tolerance=0),
    dict(id="constraint_satisfaction_03", city="Lisbon", kind="ilike",
         where="(h.zone ILIKE %s OR h.neighboorhood ILIKE %s OR h.description ILIKE %s) AND r.autumnprice <= %s",
         params=("%Chiado%", "%Chiado%", "%Chiado%", 1100),
         exact_where="h.zone = 'Chiado' AND r.autumnprice <= %s", exact_params=(1100,),
         relevant_attrs=[], preregistered=59, tolerance=10),
    dict(id="constraint_satisfaction_04", city="Porto",
         where="(h.zone = %s OR h.neighboorhood = %s) AND h.elevator = 'Y'",
         params=("Paranhos", "Paranhos"),
         relevant_attrs=["elevator"], preregistered=29, tolerance=0),
    dict(id="constraint_satisfaction_05", city="Porto",
         where="r.autumnprice >= %s AND r.autumnprice <= %s", params=(500, 700),
         relevant_attrs=[], preregistered=78, tolerance=0),
    dict(id="constraint_satisfaction_06", city="Lisbon",
         where="h.distancepublictransport <= %s AND r.autumnprice <= %s", params=(300, 1200),
         relevant_attrs=["distance_to_transport_m"], preregistered=64, tolerance=0),
    dict(id="constraint_satisfaction_07", city="Porto",
         where="h.femalepreferred = 'Y' AND r.desk = 'Y'", params=(),
         relevant_attrs=["female_preferred", "desk"], preregistered=42, tolerance=0),
    dict(id="constraint_satisfaction_08", city="Lisbon",
         where="r.minreservemonths >= %s AND r.autumnprice <= %s", params=(6, 900),
         relevant_attrs=["min_reserve_months"], preregistered=0, tolerance=0,
         note="minreservemonths is NULL for every room; NULL >= 6 is NULL, so this "
              "filter combination structurally excludes all rows. 0 is the correct answer."),
    dict(id="constraint_satisfaction_09", city="Lisbon",
         where="r.autumnprice <= %s AND r.balcony = 'Y'", params=(1100,),
         relevant_attrs=["balcony"], preregistered=41, tolerance=0,
         note="2026 date window; reservation-exclusion is a no-op (calendar ends 2024-11-30)."),
    dict(id="constraint_satisfaction_10", city="Porto",
         where="r.autumnprice <= %s AND r.privatebathroom = 'Y'", params=(900,),
         relevant_attrs=["private_bathroom"], preregistered=27, tolerance=0,
         note="2026/2027 date window; reservation-exclusion is a no-op. Stay spans "
              "autumn+spring; fixed-price rooms show a flat rate, seasonal rooms a blended one."),
    # constraint_satisfaction_11 handled specially (availability_2024)
    dict(id="constraint_satisfaction_12", city="Lisbon",
         where="r.autumnprice <= %s AND r.privatebathroom = 'Y'", params=(1100,),
         relevant_attrs=["private_bathroom"], preregistered=63, tolerance=0,
         note="accepts_couples has no DB column and is silently ignored by find_rooms; "
              "the result set is NOT confirmed couple-friendly."),
    dict(id="constraint_satisfaction_13", city="Porto",
         where="h.internet = 'Y' AND r.privatebathroom = 'Y' AND r.autumnprice <= %s", params=(900,),
         relevant_attrs=["internet", "private_bathroom"], preregistered=27, tolerance=0),
    dict(id="constraint_satisfaction_14", city="Lisbon", kind="ilike",
         where="(h.zone ILIKE %s OR h.neighboorhood ILIKE %s OR h.description ILIKE %s) AND r.autumnprice <= %s",
         params=("%Arroios%", "%Arroios%", "%Arroios%", 1100),
         exact_where="h.zone = 'Arroios' AND r.autumnprice <= %s", exact_params=(1100,),
         relevant_attrs=[], preregistered=48, tolerance=10),
    dict(id="factual_lookup_01", city="Lisbon", where="", params=(),
         relevant_attrs=[], preregistered=556, tolerance=0, count_only=True),
    # factual_lookup_02 handled specially (zone_enum)
    dict(id="factual_lookup_03", city="Porto",
         where="r.autumnprice < %s", params=(450,),
         relevant_attrs=[], preregistered=20, tolerance=2),
    dict(id="factual_lookup_04", city="Lisbon",
         where="r.privatebathroom = 'Y'", params=(),
         relevant_attrs=["private_bathroom"], preregistered=188, tolerance=0),
    # factual_lookup_05 handled specially (metro_blue)
    # factual_lookup_06 handled specially (single_room)
    dict(id="factual_lookup_07", city="Lisbon",
         where="h.femalepreferred = 'Y'", params=(),
         relevant_attrs=["female_preferred"], preregistered=92, tolerance=0),
    dict(id="factual_lookup_08", city="Porto",
         where="h.allowpets = 'Y'", params=(),
         relevant_attrs=["allow_pets"], preregistered=0, tolerance=0,
         note="allowpets='Y' is not set on any Porto house row."),
    # factual_lookup_09 handled specially (non_filterable)
    dict(id="factual_lookup_10", city="Porto",
         where="h.distancepublictransport <= %s", params=(500,),
         relevant_attrs=["distance_to_transport_m"], preregistered=170, tolerance=1,
         note="True count is 169, not the pre-registered 170 -- this script always "
              "excludes the one autumnprice<=0 dirty-price row, which the original "
              "golden-set query (no price filter) did not. Tolerance +/-1 absorbs this."),
    dict(id="factual_lookup_11", city="Porto", where="", params=(),
         relevant_attrs=[], preregistered=376, tolerance=1, count_only=True,
         note="True count is 375, not the pre-registered 376 -- see factual_lookup_10 note "
              "(dirty-price-row exclusion). Tolerance +/-1 absorbs this."),
    dict(id="factual_lookup_12", city="Lisbon",
         where="h.furnished = 'Y'", params=(),
         relevant_attrs=["furnished"], preregistered=532, tolerance=0),
]

SPECIAL_IDS = {
    "constraint_satisfaction_11": "availability_2024",
    "factual_lookup_02": "zone_enum",
    "factual_lookup_05": "metro_blue",
    "factual_lookup_06": "single_room",
    "factual_lookup_09": "non_filterable",
}


def run_filter_query(cur, city: str, where_extra: str, params: tuple) -> tuple[list[dict], int]:
    """Run a standard filtered room-list query. Always excludes autumnprice<=0."""
    where = "r.status = 'Available' AND h.city = %s AND r.autumnprice > 0"
    p: list[Any] = [city]
    if where_extra:
        where += " AND " + where_extra
        p.extend(params)
    sql = f"SELECT {ROOM_LIST_COLUMNS} {ROOM_LIST_FROM} WHERE {where} ORDER BY r.idroom"
    rows = q(cur, sql, tuple(p))
    return [_room_row_to_dict(r) for r in rows], len(rows)


def build_truth_table(cur, spec: QuerySpec) -> dict[str, Any]:
    rooms, total = run_filter_query(cur, spec["city"], spec["where"], spec["params"])
    result: dict[str, Any] = {
        "id": spec["id"],
        "city": spec["city"],
        "total_matches": total,
        "preregistered_count": spec["preregistered"],
        "tolerance": spec.get("tolerance", 0),
        "relevant_attrs": spec.get("relevant_attrs", []),
        "rooms": rooms,
        "rooms_full": rooms,
        "n_more": 0,
        "note": spec.get("note"),
        "count_only": spec.get("count_only", False),
    }
    if spec.get("kind") == "ilike":
        exact_rows, exact_total = run_filter_query(
            cur, spec["city"], spec["exact_where"], spec["exact_params"]
        )
        result["exact_zone_total_matches"] = exact_total
        result["ilike_vs_exact_note"] = (
            f"ILIKE match (description text included) = {total}; "
            f"exact zone match only = {exact_total}. Both are acceptable answers "
            f"(tolerance +/-{spec.get('tolerance', 0)})."
        )
    return result


def build_metro_blue_truth_table(cur) -> dict[str, Any]:
    tool_zones = sorted(zones_on_line("Lisbon", "blue"))
    ph = ",".join(["%s"] * len(tool_zones))
    where_tool = f"(h.zone IN ({ph}) OR h.neighboorhood IN ({ph}))"
    params_tool = tuple(tool_zones) + tuple(tool_zones)
    rooms_tool, total_tool = run_filter_query(cur, "Lisbon", where_tool, params_tool)

    prereg_zones = ["Alfama", "Bairro Alto", "Chiado"]
    prereg_nbhd = ["Benfica"]
    ph_z = ",".join(["%s"] * len(prereg_zones))
    ph_n = ",".join(["%s"] * len(prereg_nbhd))
    where_prereg = f"(h.zone IN ({ph_z}) OR h.neighboorhood IN ({ph_n}))"
    params_prereg = tuple(prereg_zones) + tuple(prereg_nbhd)
    rooms_prereg, total_prereg = run_filter_query(cur, "Lisbon", where_prereg, params_prereg)

    discrepancy = total_tool != total_prereg
    return {
        "id": "factual_lookup_05",
        "city": "Lisbon",
        "total_matches": total_tool,
        "preregistered_count": 142,
        "tool_exact_count": total_tool,
        "tool_exact_zones_both_columns": tool_zones,
        "preregistered_count_asymmetric": total_prereg,
        "discrepancy_flagged": discrepancy,
        "note": (
            f"TOOL-EXACT reconstruction (metro_lines.zones_on_line applies all "
            f"{len(tool_zones)} blue-line names {tool_zones} to BOTH h.zone and "
            f"h.neighboorhood, matching find_rooms._sql_builder exactly): {total_tool} rows. "
            f"Pre-registered golden-set figure (asymmetric: zone IN "
            f"('Alfama','Bairro Alto','Chiado') OR neighboorhood IN ('Benfica')): "
            f"{total_prereg} rows. DISCREPANCY FLAGGED: {discrepancy} "
            f"(figures differ by {abs(total_tool - total_prereg)} rows) — both counts "
            f"are shown to the judge as acceptable; the truth table below lists the "
            f"tool-exact room set."
        ),
        "relevant_attrs": [],
        "rooms": rooms_tool,
        "rooms_full": rooms_tool,
        "n_more": 0,
        "count_only": False,
    }


def build_zone_enum_truth_table(cur) -> dict[str, Any]:
    sql = f"""
        SELECT h.zone, COUNT(*) AS n
        FROM room r JOIN house h ON h.idhouse = r.loc_idhouse AND h.dateupdate = r.loc_dateupdate
        WHERE r.status = 'Available' AND h.city = 'Porto' AND r.autumnprice > 0
        GROUP BY h.zone ORDER BY n DESC
    """
    rows = q(cur, sql)
    zones = [{"zone": r["zone"], "n_rooms": r["n"]} for r in rows]
    # Any genuine Porto property is a legitimate supporting example for a
    # zone-enumeration answer -- use the full Porto room set as the ground
    # truth for claim classification (not shown to the judge as a room list).
    porto_rooms_full, _ = run_filter_query(cur, "Porto", "", ())
    return {
        "id": "factual_lookup_02",
        "city": "Porto",
        "total_matches": len(zones),
        "preregistered_count": 9,
        "kind": "zone_enum",
        "zones": zones,
        "rooms": [],
        "rooms_full": porto_rooms_full,
        "n_more": 0,
        "relevant_attrs": [],
        "note": (
            "This query's ground truth is a ZONE NAME LIST, not a room list. "
            f"True zone set ({len(zones)} zones): "
            + ", ".join(f"{z['zone']} ({z['n_rooms']})" for z in zones)
        ),
        "count_only": False,
    }


def build_non_filterable_truth_table() -> dict[str, Any]:
    return {
        "id": "factual_lookup_09",
        "city": "Lisbon",
        "total_matches": None,
        "preregistered_count": None,
        "kind": "non_filterable",
        "rooms": [],
        "rooms_full": [],
        "n_more": 0,
        "relevant_attrs": [],
        "note": (
            "Room area (m^2) is NOT a filterable field in find_rooms / find_available_rooms. "
            "No SQL query is run for this item. The correct answer explains this limitation "
            "and does not return a fabricated filtered list of '>20 sqm' rooms."
        ),
        "count_only": False,
    }


def build_single_room_truth_table(cur) -> dict[str, Any]:
    # Exact primary-key match on the room the query's encoded id references
    # (autumn=980/extracost=95, confirmed DB 2026-06-22 per the golden set notes).
    sql = f"""
        SELECT {ROOM_LIST_COLUMNS} {ROOM_LIST_FROM}
        WHERE r.status = 'Available' AND h.idhouse = %s AND r.idroom = %s
    """
    rows = q(cur, sql, ("HSE_E6069573", "RM_HSE_E6069573_4"))
    room = _room_row_to_dict(rows[0]) if rows else None
    return {
        "id": "factual_lookup_06",
        "city": "Lisbon",
        "total_matches": 1 if room else 0,
        "preregistered_count": 1,
        "kind": "single_room",
        "rooms": [room] if room else [],
        "rooms_full": [room] if room else [],
        "n_more": 0,
        "relevant_attrs": ["extra_person_allowed", "extra_person_cost"],
        "note": (
            "Single anchor-room attribute lookup (not a filtered list). Ground truth: "
            "extra_person_allowed and extra_person_cost read directly from this room's row."
        ),
        "count_only": False,
    }


def build_availability_2024_truth_table(cur) -> dict[str, Any]:
    # Distinct-room baseline (Lisbon)
    sql_baseline = f"""
        SELECT DISTINCT ON (r.loc_idhouse, r.idroom) {ROOM_LIST_COLUMNS}
        {ROOM_LIST_FROM}
        WHERE r.status = 'Available' AND h.city = 'Lisbon' AND r.autumnprice > 0
        ORDER BY r.loc_idhouse, r.idroom
    """
    baseline_rows = q(cur, sql_baseline)
    baseline = {(r["loc_idhouse"], r["idroom"]): r for r in baseline_rows}

    occ_sql = """
        SELECT DISTINCT loc_idhouse, idroom FROM reservation
        WHERE blockeddatestart <= %s AND blockeddataend >= %s
    """
    occ_rows = q(cur, occ_sql, (date(2024, 9, 30), date(2024, 9, 1)))
    occupied = {(r["loc_idhouse"], r["idroom"]) for r in occ_rows}

    available_keys = [k for k in baseline if k not in occupied]
    available_rows = [baseline[k] for k in available_keys]
    rooms = [_room_row_to_dict(r) for r in available_rows]

    return {
        "id": "constraint_satisfaction_11",
        "city": "Lisbon",
        "total_matches": len(available_keys),
        "baseline_distinct_rooms": len(baseline),
        "excluded_by_reservation": len(baseline) - len(available_keys),
        "preregistered_count": 156,
        "preregistered_baseline": 435,
        "kind": "availability_2024",
        "relevant_attrs": [],
        "rooms": rooms,
        "rooms_full": rooms,
        "n_more": 0,
        "note": (
            f"Mechanism-check item (intentionally past date, Sep 2024). Distinct-room lens: "
            f"baseline={len(baseline)} Lisbon rooms, occupied-by-reservation={len(baseline) - len(available_keys)}, "
            f"available={len(available_keys)}. A correct answer returns materially fewer rooms "
            f"than the ~435/556 unfiltered baseline."
        ),
        "count_only": False,
    }


def build_all_truth_tables(cur) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}
    for spec in QUERY_SPECS:
        tables[spec["id"]] = build_truth_table(cur, spec)
    tables["factual_lookup_02"] = build_zone_enum_truth_table(cur)
    tables["factual_lookup_05"] = build_metro_blue_truth_table(cur)
    tables["factual_lookup_06"] = build_single_room_truth_table(cur)
    tables["factual_lookup_09"] = build_non_filterable_truth_table()
    tables["constraint_satisfaction_11"] = build_availability_2024_truth_table(cur)
    return tables


ALL_26_IDS = [
    f"constraint_satisfaction_{i:02d}" for i in range(1, 15)
] + [f"factual_lookup_{i:02d}" for i in range(1, 13)]


# ---------------------------------------------------------------------------
# STEP B — deterministic entity-extraction check
# ---------------------------------------------------------------------------

PROPERTY_TYPE_KEYWORDS = {
    "casa", "residencia", "apartment", "apartamento", "flat", "home",
    "studio", "house", "loft", "villa", "quarto",
}

IMPERATIVE_FIRST_WORDS = {
    "check", "get", "show", "calculate", "narrow", "relax", "increase",
    "view", "see", "compare", "book", "contact", "filter", "refine",
    "find", "search",
}

EXCLUDE_SUBSTRINGS = {
    "more rooms", "more options", "more details", "remaining",
    "rooms within", "most rooms", "all rooms", "most expensive", "cheapest",
    "flat rate", "flat price", "flat fee",
}

_ROOM_ID_ENCODED_RE = re.compile(
    r"\bHSE_[0-9A-Fa-f]+\|RM_HSE_[0-9A-Fa-f]+_\d+\|\d{4}-\d{2}-\d{2}(?:T[\d:.]+)?\b"
)
_HOUSE_ID_BARE_RE = re.compile(r"\bHSE_[0-9A-Fa-f]+\b")
_BOLD_SPAN_RE = re.compile(r"\*\*(.+?)\*\*")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]{3,}\|?\s*$")
_EUR_RE = re.compile(r"€\s?([\d.,]+)|([\d.,]+)\s?€")


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_geo_terms() -> set[str]:
    terms: set[str] = {"lisbon", "porto", "lisboa"}
    for d in (
        LISBON_ZONE_TO_LINES, LISBON_NEIGHBORHOOD_TO_LINES,
        PORTO_ZONE_TO_LINES, PORTO_NEIGHBORHOOD_TO_LINES,
    ):
        for name in d:
            terms.add(_normalize(name))
    return terms


GEO_TERMS_NORM = _build_geo_terms()


def _fetch_global_registries(cur) -> dict[str, Any]:
    flatnames = q(cur, "SELECT DISTINCT flatname FROM house WHERE flatname IS NOT NULL")
    houses = q(cur, "SELECT DISTINCT idhouse FROM house")
    norm_to_orig: dict[str, str] = {}
    for r in flatnames:
        name = (r["flatname"] or "").strip()
        if name:
            norm_to_orig.setdefault(_normalize(name), name)

    # Room-level registry (flatname -> every zone/price combination that
    # flatname genuinely has, anywhere in the DB) for attribute-tuple checks.
    room_rows = q(
        cur,
        """SELECT h.flatname, h.zone, r.autumnprice, r.springprice, r.summerprice
           FROM room r JOIN house h ON h.idhouse = r.loc_idhouse AND h.dateupdate = r.loc_dateupdate
           WHERE r.status = 'Available' AND h.flatname IS NOT NULL""",
    )
    room_registry: dict[str, list[dict[str, Any]]] = {}
    for r in room_rows:
        fn = (r["flatname"] or "").strip()
        if not fn:
            continue
        room_registry.setdefault(_normalize(fn), []).append({
            "zone_norm": _normalize((r["zone"] or "").strip()),
            "zone_orig": (r["zone"] or "").strip(),
            "prices": [
                float(p) for p in (r["autumnprice"], r["springprice"], r["summerprice"]) if p is not None
            ],
        })

    return {
        "flatnames_norm_to_orig": norm_to_orig,
        "house_ids": {h["idhouse"] for h in houses},
        "room_registry": room_registry,
    }


def _extract_nearby_zone_and_price(answer: str, start: int, end: int) -> tuple[str | None, float | None]:
    """Look in a window right after a flatname mention for a stated zone and/or price."""
    window = answer[max(0, start - 40): min(len(answer), end + 300)]
    window_norm = f" {_normalize(window)} "
    zone: str | None = None
    zone_terms = sorted(
        (t for t in GEO_TERMS_NORM if t not in {"lisbon", "porto", "lisboa"} and len(t) >= 4),
        key=len, reverse=True,
    )
    for term in zone_terms:
        if f" {term} " in window_norm:
            zone = term
            break
    price: float | None = None
    pm = _EUR_RE.search(window)
    if pm:
        raw = pm.group(1) or pm.group(2)
        try:
            price = float(raw.replace(",", ""))
        except ValueError:
            price = None
    return zone, price


def _attribute_match(
    flatname_norm: str, zone: str | None, price: float | None,
    room_registry: dict[str, list[dict[str, Any]]], price_tol: float = 3.0,
) -> bool:
    """True if nothing to check, or a real row for this flatname matches the
    stated zone AND/OR price (whichever were extractable from the text)."""
    if zone is None and price is None:
        return True
    candidates = room_registry.get(flatname_norm, [])
    if not candidates:
        return True  # global flatname existence already checked elsewhere
    for c in candidates:
        zone_ok = zone is None or c["zone_norm"] == zone
        price_ok = price is None or any(abs(p - price) <= price_tol for p in c["prices"])
        if zone_ok and price_ok:
            return True
    return False


def _room_exists_in_db(cur, house_id: str, room_id: str, dateupdate) -> bool:
    rows = q(
        cur,
        "SELECT 1 FROM room WHERE loc_idhouse = %s AND idroom = %s AND loc_dateupdate = %s LIMIT 1",
        (house_id, room_id, dateupdate),
    )
    return bool(rows)


def _detect_header_span_texts(answer: str) -> set[str]:
    """Bold spans on a markdown table header row (line above a '|---|---|' separator)."""
    lines = answer.splitlines()
    headers: set[str] = set()
    for i, line in enumerate(lines):
        if _TABLE_SEP_RE.match(line) and i > 0:
            for m in _BOLD_SPAN_RE.finditer(lines[i - 1]):
                headers.add(m.group(1).strip())
    return headers


def _is_excluded_span(span: str) -> bool:
    stripped = span.strip()
    low = stripped.lower()
    if low.startswith("to "):
        return True
    first_word = re.split(r"\s+", stripped)[0].strip(":,.-").lower() if stripped else ""
    if first_word in IMPERATIVE_FIRST_WORDS:
        return True
    for phrase in EXCLUDE_SUBSTRINGS:
        if phrase in low:
            return True
    return False


def _has_property_keyword_and_2_words(span: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", span)
    if len(words) < 2:
        return False
    low_words = {w.lower() for w in words}
    if not (low_words & PROPERTY_TYPE_KEYWORDS):
        return False
    # Reject "<bare geo term> <keyword>" (e.g. "Campanha flat"): once the
    # trailing property/room-type word(s) are dropped, what's left must NOT
    # itself be just a known zone/neighborhood/city name.
    trimmed = list(words)
    while trimmed and trimmed[-1].lower() in PROPERTY_TYPE_KEYWORDS | _ROOM_TYPE_WORDS:
        trimmed = trimmed[:-1]
    if trimmed and _normalize(" ".join(trimmed)) in GEO_TERMS_NORM:
        return False
    return True


_ROOM_TYPE_WORDS = {
    "room", "suite", "studio", "economy", "deluxe", "master", "single", "double",
    "en", "im", "chambre",
}


def _strip_once(s: str) -> list[str]:
    """One round of qualifier-stripping transforms; returns candidate outputs."""
    out: list[str] = []
    # leading list numbering: "1. Room in X" -> "Room in X"
    s2 = re.sub(r"^\s*\d+[.)]\s*", "", s)
    if s2 != s:
        out.append(s2)
    # "<Name>, <Zone>" -> "<Name>"
    if "," in s:
        out.append(s.split(",", 1)[0].strip())
    # "<RoomType> in/en/im <Name>" -> "<Name>"
    m = re.match(r"^.+?\b(?:in|en|im)\s+(.+)$", s, re.IGNORECASE)
    if m:
        out.append(m.group(1).strip())
    # "<Name> in/en/im <Zone>" -> "<Name>" (opposite order, equally common)
    m2 = re.match(r"^(.+?)\s+\b(?:in|en|im)\b\s+.+$", s, re.IGNORECASE)
    if m2:
        out.append(m2.group(1).strip())
    # em-dash / en-dash / colon separated qualifiers: "<Name> — <Descriptor>"
    for sep in ("—", "–", " - ", ":"):
        if sep in s:
            out.append(s.split(sep, 1)[0].strip())
    # trailing parenthetical: "<Name> (28m2)" -> "<Name>"
    s3 = re.sub(r"\s*\(.*?\)\s*$", "", s).strip()
    if s3 != s:
        out.append(s3)
    # "<Name> <RoomType>" -> "<Name>" (drop trailing property-type word(s))
    words = s.split()
    trimmed = list(words)
    while trimmed and trimmed[-1].lower().strip(",.():") in PROPERTY_TYPE_KEYWORDS | _ROOM_TYPE_WORDS:
        trimmed = trimmed[:-1]
    if trimmed and len(trimmed) != len(words):
        out.append(" ".join(trimmed))
    return out


def _qualifier_strip_variants(span: str) -> list[str]:
    """Iteratively strip qualifiers (combining transforms) until a fixed point."""
    frontier = [span.strip()]
    seen: list[str] = []
    seen_set: set[str] = set()
    depth = 0
    while frontier and depth < 4:
        depth += 1
        next_frontier: list[str] = []
        for s in frontier:
            for v in _strip_once(s):
                if v and v not in seen_set:
                    seen_set.add(v)
                    seen.append(v)
                    next_frontier.append(v)
        frontier = next_frontier
    return seen


@dataclass
class Claim:
    kind: str  # "room_id" | "flatname" | "total_matches"
    raw: str
    resolved_name: str | None
    classification: str  # VERIFIED | FILTER_VIOLATION | FABRICATED | ATTRIBUTE_MISMATCH
    classification_loose: str = ""  # pre-tightening classification (v1 rule), for diffing

    def __post_init__(self) -> None:
        if not self.classification_loose:
            self.classification_loose = self.classification


def extract_claims(
    query_id: str,
    truth: dict[str, Any],
    answer: str,
    registries: dict[str, Any],
    cur,
) -> list[Claim]:
    claims: list[Claim] = []
    seen_raw: set[str] = set()

    truth_rooms = truth.get("rooms_full", truth.get("rooms", []))
    truth_flatnames_norm = {
        _normalize(r["flatname"]) for r in truth_rooms if r.get("flatname")
    }
    truth_norm_to_orig: dict[str, str] = {}
    for r in truth_rooms:
        if r.get("flatname"):
            truth_norm_to_orig.setdefault(_normalize(r["flatname"]), r["flatname"])
    truth_room_ids = {r["room_id"] for r in truth_rooms}
    truth_house_ids = {r["house_id"].split("|")[0] for r in truth_rooms}

    # -- Room IDs (encoded) --
    for m in _ROOM_ID_ENCODED_RE.finditer(answer):
        raw = m.group(0)
        if raw in seen_raw:
            continue
        seen_raw.add(raw)
        if raw in truth_room_ids:
            claims.append(Claim("room_id", raw, raw, "VERIFIED"))
            continue
        try:
            from elh_rag.tools._shared.room_id import decode_room_id
            parts = decode_room_id(raw)
            exists = _room_exists_in_db(cur, parts.house_id, parts.room_id, parts.dateupdate.date())
        except Exception:
            exists = False
        claims.append(Claim("room_id", raw, raw, "FILTER_VIOLATION" if exists else "FABRICATED"))

    # -- Bare HSE_ ids not already covered by an encoded match --
    encoded_house_parts = {c.raw.split("|")[0] for c in claims if c.kind == "room_id"}
    for m in _HOUSE_ID_BARE_RE.finditer(answer):
        raw = m.group(0)
        if raw in seen_raw or raw in encoded_house_parts:
            continue
        seen_raw.add(raw)
        if raw in truth_house_ids:
            claims.append(Claim("room_id", raw, raw, "VERIFIED"))
        elif raw in registries["house_ids"]:
            claims.append(Claim("room_id", raw, raw, "FILTER_VIOLATION"))
        else:
            claims.append(Claim("room_id", raw, raw, "FABRICATED"))

    # -- Bold-span flatname candidates --
    header_spans = _detect_header_span_texts(answer)
    all_flat_norm = set(registries["flatnames_norm_to_orig"].keys())

    for m in _BOLD_SPAN_RE.finditer(answer):
        span = m.group(1).strip()
        if not span or span in header_spans:
            continue
        if _normalize(span) in GEO_TERMS_NORM:
            continue
        if _is_excluded_span(span):
            continue
        if span in seen_raw:
            continue
        if _HOUSE_ID_BARE_RE.search(span):
            # Already covered by the room-id extractor above.
            continue

        # Try direct + qualifier-stripped variants against truth-table / global flatnames
        candidates = [span] + _qualifier_strip_variants(span)
        resolved: tuple[str, str] | None = None  # (classification, matched_variant)
        for cand in candidates:
            n = _normalize(cand)
            if not n:
                continue
            if n in truth_flatnames_norm:
                resolved = ("VERIFIED", cand)
                break
            if n in all_flat_norm:
                resolved = ("FILTER_VIOLATION", cand)
                break

        if resolved is not None:
            seen_raw.add(span)
            cls, matched_variant = resolved
            if cls == "VERIFIED":
                zone, price = _extract_nearby_zone_and_price(answer, m.start(1), m.end(1))
                if not _attribute_match(
                    _normalize(matched_variant), zone, price, registries["room_registry"]
                ):
                    claims.append(Claim("flatname", span, matched_variant, "ATTRIBUTE_MISMATCH", "VERIFIED"))
                    continue
            claims.append(Claim("flatname", span, matched_variant, cls))
            continue

        # Rule (b): structurally looks like a property name -> candidate, unresolved = FABRICATED
        if _has_property_keyword_and_2_words(span):
            seen_raw.add(span)
            claims.append(Claim("flatname", span, None, "FABRICATED"))
        # else: not accepted as a candidate at all (rule a and b both failed) -> ignored

    # -- Plain-text flatname scan: truth-table flatnames mentioned anywhere in
    #    the answer (not just inside **bold** spans), e.g. footnote citations --
    already_matched = {
        _normalize(c.resolved_name) for c in claims if c.kind == "flatname" and c.resolved_name
    }
    answer_norm = _normalize(answer)
    for fn_norm, fn_orig in truth_norm_to_orig.items():
        if len(fn_norm) < 6 or fn_norm in already_matched:
            continue
        if f" {fn_norm} " in f" {answer_norm} ":
            pm = re.search(re.escape(fn_orig), answer, re.IGNORECASE)
            zone, price = (None, None)
            if pm:
                zone, price = _extract_nearby_zone_and_price(answer, pm.start(), pm.end())
            if not _attribute_match(fn_norm, zone, price, registries["room_registry"]):
                claims.append(Claim("flatname", fn_orig, fn_orig, "ATTRIBUTE_MISMATCH", "VERIFIED"))
            else:
                claims.append(Claim("flatname", fn_orig, fn_orig, "VERIFIED"))
            already_matched.add(fn_norm)

    # -- total_matches claim (skip for zone-enumeration / non-filterable /
    #    single-room items, where "N rooms" isn't the ground-truth quantity) --
    if truth.get("kind") not in {"zone_enum", "non_filterable", "single_room"} and truth.get("total_matches") is not None:
        stated = _extract_stated_total(answer)
        if stated is not None:
            true_n = truth["total_matches"]
            tol = truth.get("tolerance", 0)
            cls = "VERIFIED" if abs(stated - true_n) <= tol else "FABRICATED"
            claims.append(Claim("total_matches", str(stated), str(true_n), cls))

    return claims


_TOTAL_NEAR_ROOMS_RE = re.compile(
    r"\b(\d{1,4}(?:,\d{3})*)\b\s*(?:\*\*)?\s*(?:available\s+)?rooms?\b", re.IGNORECASE
)
_NO_ROOMS_RE = re.compile(r"\b(no|zero|0|none)\b\s*(?:available\s+)?rooms?\b", re.IGNORECASE)


def _extract_stated_total(answer: str) -> int | None:
    if _NO_ROOMS_RE.search(answer[:400]):
        return 0
    m = _TOTAL_NEAR_ROOMS_RE.search(answer)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def score_answer(claims: list[Claim]) -> float | None:
    if not claims:
        return None
    n_verified = sum(1 for c in claims if c.classification == "VERIFIED")
    return n_verified / len(claims)


def classify_no_claims(query_id: str, truth: dict[str, Any], answer: str) -> str:
    """VAGUE / EXTRACTION_GAP / NO_RESULTS for an answer with n_claims == 0."""
    if truth.get("total_matches") == 0:
        return "NO_RESULTS"
    # crude "did it name specifics" check: any digit-bearing bold span or price mention
    if _BOLD_SPAN_RE.search(answer) or _EUR_RE.search(answer):
        return "EXTRACTION_GAP"
    return "VAGUE"


UNVERIFIABLE_FIELDS_NOTE = (
    "Fields NOT captured in this table (heating/AC, closet, window, cable TV, "
    "specific views, exact floor/building number, photos, review sentiment, "
    "and any amenity not listed in the columns below) are UNVERIFIABLE -- their "
    "presence in the answer is neither confirmed nor denied by this table. "
    "Do not treat a mention of them as fabrication."
)


def _price_str(r: dict[str, Any]) -> str:
    a, s, u = r.get("price_eur"), r.get("spring_price"), r.get("summer_price")
    if r.get("fixed_price") or (a == s == u):
        return f"EUR{a:.0f}(fixed)" if a is not None else "EUR?"
    parts = []
    if a is not None:
        parts.append(f"aut={a:.0f}")
    if s is not None:
        parts.append(f"spr={s:.0f}")
    if u is not None:
        parts.append(f"sum={u:.0f}")
    return "EUR[" + ",".join(parts) + "]" if parts else "EUR?"


def _deposit_str(r: dict[str, Any]) -> str:
    if not r.get("deposit"):
        return "deposit=N"
    v = r.get("deposit_value")
    return f"deposit=Y(EUR{v:.0f})" if v is not None else "deposit=Y"


def format_truth_table(truth: dict[str, Any]) -> str:
    lines: list[str] = [f"City: {truth.get('city')}"]
    if truth.get("total_matches") is not None:
        tol = truth.get("tolerance", 0)
        lines.append(
            f"True total_matches: {truth['total_matches']}"
            + (f" (tolerance +/-{tol})" if tol else "")
        )
    if truth.get("note"):
        lines.append(f"Note: {truth['note']}")
    if truth.get("ilike_vs_exact_note"):
        lines.append(f"Note: {truth['ilike_vs_exact_note']}")
    if truth.get("zones"):
        lines.append(
            "Zones: " + ", ".join(f"{z['zone']} ({z['n_rooms']} rooms)" for z in truth["zones"])
        )
    rooms = truth.get("rooms", [])
    if rooms:
        lines.append(
            f"Matching rooms -- COMPLETE list, all {len(rooms)} rooms satisfying the filters "
            f"(no rows omitted). Absence of a room/property from this list IS evidence it does "
            f"not exist in the catalogue matching these filters."
        )
        lines.append(
            "Columns: room_id | flatname (roomname) | zone [neighbourhood] | price | "
            "area_m2 | bed | bathroom | deposit | filter-relevant attrs"
        )
        rel = truth.get("relevant_attrs", [])
        for r in rooms:
            attrs_str = ""
            if rel:
                attrs_str = " [" + ", ".join(f"{k}={r['attrs'].get(k)}" for k in rel) + "]"
            nbhd = f" [{r['neighborhood']}]" if r.get("neighborhood") else ""
            bath = "private" if r["attrs"].get("private_bathroom") else "shared"
            area = f"{r['area_m2']:.0f}m2" if r.get("area_m2") is not None else "?m2"
            lines.append(
                f"  - {r['room_id']} | {r['flatname']} ({r['roomname']}) | "
                f"{r['zone']}{nbhd} | {_price_str(r)} | {area} | bed={r.get('bed_type')} | "
                f"bath={bath} | {_deposit_str(r)}{attrs_str}"
            )
    lines.append(UNVERIFIABLE_FIELDS_NOTE)
    return "\n".join(lines)


def format_det_summary(claims: list[Claim]) -> str:
    if not claims:
        return "No factual claims could be automatically extracted from this answer."
    lines = [f"Automated fact-check found {len(claims)} checkable claim(s):"]
    for c in claims:
        lines.append(f"  - [{c.kind}] {c.raw!r} -> {c.classification}")
    n_v = sum(1 for c in claims if c.classification == "VERIFIED")
    lines.append(f"Deterministic score: {n_v}/{len(claims)} verified.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# STEP C — build the judge batch
# ---------------------------------------------------------------------------

_BLIND_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bphase\s*2\b", re.IGNORECASE), "System A"),
    (re.compile(r"\bphase\s*3\b", re.IGNORECASE), "System B"),
    (re.compile(r"\bpipeline\b", re.IGNORECASE), "workflow"),
    (re.compile(r"\bbaseline\b", re.IGNORECASE), "reference"),
    (re.compile(r"\bthe agent\b", re.IGNORECASE), "the assistant"),
    (re.compile(r"\ban agent\b", re.IGNORECASE), "a housing assistant"),
    (re.compile(r"\bagent\b", re.IGNORECASE), "assistant"),
]


def _blind(text: str) -> str:
    for pattern, replacement in _BLIND_SUBS:
        text = pattern.sub(replacement, text)
    return text


SYS_M6_REPAIR = """\
You are an evaluation judge for a student housing assistant.
Score the (query, answer) pair for GROUNDEDNESS using the DATABASE TRUTH TABLE
provided below the query, plus an automated fact-check summary of the answer's
claims against that truth table.

THE TRUTH TABLE IS COMPLETE (v2): it lists EVERY room in the database that
satisfies this query's filters -- no rows are omitted or sampled. This was not
true in an earlier version of this evaluation (which capped the list at 15
rows and caused real rooms to look fabricated); it is fixed now. Because the
list is complete, a room or property genuinely absent from it IS evidence of
fabrication -- but only for the columns the table actually carries.

For every specific factual claim the answer makes (room/property name, id,
zone, price, area, bed type, bathroom type, deposit, count), classify it one
of three ways:
  - CONTRADICTED: the truth table shows something DIFFERENT from what the
    answer states for that same room/property (wrong price for a listed room,
    a room/property not present anywhere in the table, a total_matches count
    that contradicts the true total). This is fabrication -- penalise it.
  - SUPPORTED: the claim matches a row in the truth table exactly (or within
    normal rounding). Correct -- do NOT penalise specificity for this.
  - UNVERIFIABLE: the claim is about an attribute the truth table does not
    carry at all (see the table's own "Fields NOT captured" note -- e.g.
    heating/AC, closet, exact floor, photos, review sentiment). Do NOT treat
    this as fabrication. Note it in your rationale as unverifiable and score
    based only on the claims you CAN verify.

Rubric (0.0 / 0.5 / 1.0), based only on CONTRADICTED vs SUPPORTED claims
(ignore UNVERIFIABLE claims when scoring):
1.0 - every verifiable claim is SUPPORTED. No CONTRADICTED claims.
0.5 - mostly grounded: exactly one CONTRADICTED claim among otherwise
      SUPPORTED ones.
0.0 - two or more CONTRADICTED claims, or a CONTRADICTED claim about the core
      entity/count of the answer (a fabricated room, a wrong price for a real
      room, or a count that contradicts the true total).

IMPORTANT: Listing a room that genuinely exists in the truth table, with
correct attributes, is CORRECT behaviour -- do NOT penalise specificity.
An answer that lists many real, correctly-filtered rooms should score 1.0
even if it also mentions UNVERIFIABLE attributes (e.g. "has A/C") that the
table cannot confirm or deny.
The automated fact-check summary is a helper signal, not a verdict -- use
your own judgement of the truth table if you believe it is mistaken.

Output ONLY valid JSON: {"score": <0.0|0.5|1.0>, "rationale": "<one sentence>"}
No other text before or after the JSON.
"""


def _user_msg_m6_repair(
    query: str, category: str, difficulty: str, language: str,
    truth_text: str, det_text: str, answer: str,
) -> str:
    return (
        f"**Query**: {_blind(query)}\n"
        f"**Category**: {category}\n"
        f"**Difficulty**: {difficulty}\n"
        f"**Language**: {language}\n\n"
        f"**Database truth table**:\n{_blind(truth_text)}\n\n"
        f"**Automated fact-check summary**:\n{_blind(det_text)}\n\n"
        "---\n"
        f"**Answer to evaluate**:\n{_blind(answer)}\n"
    )


def make_batch_record(custom_id: str, model: str, system_prompt: str, user_message: str) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "params": {
            "model": model,
            "max_tokens": MAX_OUT_TOKENS,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        },
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def check_blinding_violations(records: list[dict]) -> list[tuple[str, str, str]]:
    pat = re.compile(r"phase\s*2|phase\s*3|\bagent\b|\bpipeline\b|\bbaseline\b", re.IGNORECASE)
    violations: list[tuple[str, str, str]] = []
    for r in records:
        sys_p = r["params"]["system"]
        user_p = r["params"]["messages"][0]["content"]
        for label, text in [("system", sys_p), ("user", user_p)]:
            for m in pat.finditer(text):
                violations.append((r["custom_id"], label, m.group()))
    return violations


def measure_tokens_sample(records: list[dict], model: str, sample_n: int = 15) -> tuple[float, int]:
    """Real (not heuristic) input-token count via the Anthropic count_tokens API,
    averaged over a sample. Returns (mean_input_tokens, n_sampled)."""
    mean, _max, n = measure_tokens_all(records, sample_n=sample_n)
    return mean, n


def measure_tokens_all(records: list[dict], sample_n: int | None = None) -> tuple[float, int, int]:
    """Real (not heuristic) input-token count via the Anthropic count_tokens API.
    sample_n=None measures every record. Returns (mean, max, n_measured)."""
    load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return (float("nan"), 0, 0)
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    sample = records if sample_n is None else records[: min(sample_n, len(records))]
    totals: list[int] = []
    for r in sample:
        p = r["params"]
        result = client.messages.count_tokens(
            model=p["model"], system=p["system"], messages=p["messages"]
        )
        totals.append(result.input_tokens)
    if not totals:
        return (float("nan"), 0, 0)
    return (sum(totals) / len(totals), max(totals), len(totals))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        qs = yaml.safe_load(f)
    return {q["id"]: q for q in qs}


def run(p3_path: Path, p2_path: Path, qs_path: Path, out_dir: Path) -> None:
    p3_recs = {r["id"]: r for r in load_jsonl(p3_path) if r.get("status") == "success"}
    p2_recs = {r["id"]: r for r in load_jsonl(p2_path) if r.get("status") == "success"}
    golden = load_golden(qs_path)

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ---- STEP A ----
    print(f"\n{BAR}\n  STEP A -- DATABASE TRUTH TABLES (26 list-returning queries)\n{BAR}")
    tables = build_all_truth_tables(cur)
    print(f"  {'ID':<30}{'true_n':>8}{'prereg':>8}{'tol':>6}{'match':>8}")
    for qid in ALL_26_IDS:
        t = tables[qid]
        true_n, prereg, tol = t.get("total_matches"), t.get("preregistered_count"), t.get("tolerance", 0)
        ok = "n/a" if true_n is None or prereg is None else str(abs(true_n - prereg) <= tol)
        print(f"  {qid:<30}{str(true_n):>8}{str(prereg):>8}{str(tol):>6}{ok:>8}")
    if tables["factual_lookup_05"]["discrepancy_flagged"]:
        t5 = tables["factual_lookup_05"]
        print(f"\n  DISCREPANCY FLAGGED (factual_lookup_05, blue metro line):")
        print(f"    tool-exact (symmetric, matches find_rooms._sql_builder) = {t5['tool_exact_count']}")
        print(f"    pre-registered (asymmetric)                              = {t5['preregistered_count_asymmetric']}")

    # ---- STEP B ----
    print(f"\n{BAR}\n  STEP B -- DETERMINISTIC ENTITY-EXTRACTION CHECK\n{BAR}")
    registries = _fetch_global_registries(cur)

    all_claims: dict[tuple[str, str], list[Claim]] = {}
    no_claim_reasons: dict[tuple[str, str], str] = {}
    residual_fabricated: list[tuple[str, str, str, str]] = []

    for qid in ALL_26_IDS:
        for sysname, recs in [("phase3", p3_recs), ("phase2", p2_recs)]:
            rec = recs.get(qid)
            if rec is None:
                continue
            answer = rec.get("final_message", "")
            claims = extract_claims(qid, tables[qid], answer, registries, cur)
            all_claims[(qid, sysname)] = claims
            if not claims:
                no_claim_reasons[(qid, sysname)] = classify_no_claims(qid, tables[qid], answer)
            for c in claims:
                if c.classification == "FABRICATED":
                    residual_fabricated.append((qid, sysname, c.kind, c.raw))

    coverage = {k: len(v) > 0 for k, v in all_claims.items()}
    n_covered = sum(coverage.values())
    print(f"  Coverage: {n_covered}/{len(all_claims)} (query, system) pairs have >=1 checkable claim")

    print(f"\n  {'ID':<30}{'system':<8}{'n_claims':>9}{'verified':>9}{'m6_det':>8}")
    per_system_scores: dict[str, list[float]] = {"phase3": [], "phase2": []}
    for qid in ALL_26_IDS:
        for sysname in ("phase3", "phase2"):
            claims = all_claims.get((qid, sysname))
            if claims is None:
                continue
            if not claims:
                reason = no_claim_reasons[(qid, sysname)]
                print(f"  {qid:<30}{sysname:<8}{'0':>9}{'-':>9}{'  ('+reason+')':>8}")
            else:
                n_v = sum(1 for c in claims if c.classification == "VERIFIED")
                score = score_answer(claims)
                per_system_scores[sysname].append(score)
                print(f"  {qid:<30}{sysname:<8}{len(claims):>9}{n_v:>9}{score:>8.2f}")

    print(f"\n  Mean m6_det (all answers with n_claims>0, NOT paired):")
    for sysname in ("phase3", "phase2"):
        scores = per_system_scores[sysname]
        mean = sum(scores) / len(scores) if scores else float("nan")
        print(f"    {sysname}: mean={mean:.3f}  n={len(scores)}")

    paired_ids = [
        qid for qid in ALL_26_IDS
        if coverage.get((qid, "phase3")) and coverage.get((qid, "phase2"))
    ]
    excluded_ids = [qid for qid in ALL_26_IDS if qid not in paired_ids]
    print(f"\n  PAIRED subset (both systems have claims): {len(paired_ids)}/26 queries")
    print(f"  Excluded from paired comparison: {excluded_ids}")
    for sysname in ("phase3", "phase2"):
        paired_scores = [score_answer(all_claims[(qid, sysname)]) for qid in paired_ids]
        mean = sum(paired_scores) / len(paired_scores) if paired_scores else float("nan")
        print(f"    {sysname} (paired, n={len(paired_scores)}): mean={mean:.3f}")

    print(f"\n  Verifiability rate (n_claims==0 breakdown):")
    for sysname in ("phase3", "phase2"):
        reasons = [no_claim_reasons[k] for k in no_claim_reasons if k[1] == sysname]
        from collections import Counter
        cnt = Counter(reasons)
        print(f"    {sysname}: {dict(cnt)}  (n_covered={sum(1 for k in coverage if k[1]==sysname and coverage[k])}/{sum(1 for k in coverage if k[1]==sysname)})")

    print(f"\n  RESIDUAL FABRICATED LIST ({len(residual_fabricated)} items) -- manual inspection:")
    for qid, sysname, kind, raw in residual_fabricated:
        print(f"    {qid:<30}{sysname:<8}[{kind}] {raw!r}")

    # ---- STEP B.5 -- stricter flatname rule (attribute-tuple check) ----
    print(f"\n{BAR}\n  STEP B.5 -- STRICTER FLATNAME RULE (price+zone must match a real row)\n{BAR}")
    flips: list[tuple[str, str, str, str]] = []
    for (qid, sysname), claims in all_claims.items():
        for c in claims:
            if c.classification != c.classification_loose:
                flips.append((qid, sysname, c.raw, f"{c.classification_loose} -> {c.classification}"))
    print(f"  Claims that changed classification under the stricter rule: {len(flips)}")
    for qid, sysname, raw, change in flips:
        print(f"    {qid:<30}{sysname:<8}{raw!r:<55}{change}")
    target = ("constraint_satisfaction_06", "phase2")
    target_flipped = any(f[0] == target[0] and f[1] == target[1] for f in flips)
    print(f"\n  cs_06/phase2 'Cosy Home Lisbon in Graca EUR525' flips: {target_flipped}")

    print(f"\n  Mean m6_det -- LOOSE rule (v1, as before) vs STRICT rule (v2, this run):")
    for sysname in ("phase3", "phase2"):
        loose_scores, strict_scores = [], []
        for qid in ALL_26_IDS:
            claims = all_claims.get((qid, sysname))
            if not claims:
                continue
            n = len(claims)
            n_v_strict = sum(1 for c in claims if c.classification == "VERIFIED")
            n_v_loose = sum(1 for c in claims if c.classification_loose == "VERIFIED")
            strict_scores.append(n_v_strict / n)
            loose_scores.append(n_v_loose / n)
        lm = sum(loose_scores) / len(loose_scores) if loose_scores else float("nan")
        sm = sum(strict_scores) / len(strict_scores) if strict_scores else float("nan")
        print(f"    {sysname}: loose={lm:.3f}  strict={sm:.3f}  n={len(strict_scores)}")

    n_attr_mismatch = sum(
        1 for claims in all_claims.values() for c in claims if c.classification == "ATTRIBUTE_MISMATCH"
    )
    print(f"\n  Total ATTRIBUTE_MISMATCH claims: {n_attr_mismatch}")

    # ---- STEP C ----
    print(f"\n{BAR}\n  STEP C -- BUILD JUDGE BATCH v2 (M6_repaired_v2, 52 requests, build only)\n{BAR}")
    records: list[dict] = []
    mapping: list[dict] = []
    for qid in ALL_26_IDS:
        q_golden = golden[qid]
        for sysname, recs in [("phase3", p3_recs), ("phase2", p2_recs)]:
            rec = recs.get(qid)
            if rec is None:
                continue
            answer = rec.get("final_message", "")
            claims = all_claims[(qid, sysname)]
            truth_text = format_truth_table(tables[qid])
            det_text = format_det_summary(claims)
            user_msg = _user_msg_m6_repair(
                q_golden["query"], q_golden["category"], q_golden.get("difficulty", "medium"),
                q_golden.get("language", "en"), truth_text, det_text, answer,
            )
            cid = f"M6_repaired_{sysname}_{qid}"
            records.append(make_batch_record(cid, MODEL_HAIKU, SYS_M6_REPAIR, user_msg))
            mapping.append({
                "custom_id": cid, "system": sysname, "query_id": qid, "metric": "M6_repaired",
                "category": q_golden["category"], "language": q_golden.get("language", "en"),
                "m6_det": score_answer(claims), "n_claims": len(claims),
            })

    print(f"  Built {len(records)} records (expected 52)")

    violations = check_blinding_violations(records)
    print(f"  Blinding violations: {len(violations)} (expected 0)")
    for v in violations[:10]:
        print(f"    {v}")

    out_dir.mkdir(parents=True, exist_ok=True)
    # v1 files (batch_M6_repaired.jsonl, id_mapping_M6_repaired.jsonl,
    # m6_repair_truth_tables.json) are NOT touched -- kept as capping-defect evidence.
    batch_path = out_dir / "batch_M6_repaired_v2.jsonl"
    write_jsonl(batch_path, records)
    print(f"  Wrote {batch_path.name}")
    mapping_path = out_dir / "id_mapping_M6_repaired_v2.jsonl"
    write_jsonl(mapping_path, mapping)
    print(f"  Wrote {mapping_path.name}")

    truth_tables_path = out_dir / "m6_repair_truth_tables_v2.json"
    truth_tables_path.write_text(json.dumps(tables, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  Wrote {truth_tables_path.name}")

    # ---- Cost (this batch only; combined gate is a separate step) ----
    print(f"\n{THIN}\n  M6_repaired_v2 COST ESTIMATE (MEASURED tokens, every one of 52 records, 50% batch discount)\n{THIN}")
    mean_tok, max_tok, n_measured = measure_tokens_all(records, sample_n=None)
    if n_measured:
        total_in = mean_tok * len(records)
        total_out = MAX_OUT_TOKENS * len(records)
        cost = (total_in * LIST_IN[MODEL_HAIKU] * (1 - BATCH_DISCOUNT)
                + total_out * LIST_OUT[MODEL_HAIKU] * (1 - BATCH_DISCOUNT)) / 1_000_000
        print(f"  MEASURED input tokens (n={n_measured}/52): mean={mean_tok:.0f}  max={max_tok}")
        print(f"  requests={len(records)}  total_in~{total_in:,.0f}  total_out~{total_out:,}  cost=${cost:.4f}")
    else:
        print("  ANTHROPIC_API_KEY not set -- could not measure real token counts.")

    cur.close()
    conn.close()

    print(f"\n{BAR}\n  DONE. v2 batch written to: {out_dir}\n  v1 files untouched. No batch was submitted.\n{BAR}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase3", type=Path, default=DEFAULT_P3)
    p.add_argument("--phase2", type=Path, default=DEFAULT_P2)
    p.add_argument("--queries", type=Path, default=DEFAULT_QS)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    for path in [args.phase3, args.phase2, args.queries]:
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
    run(args.phase3, args.phase2, args.queries, args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
