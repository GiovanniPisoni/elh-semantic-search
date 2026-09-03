"""M6 step 4 -- LLM extraction + SQL verification (build only; STOPS before submit).

Splits the M6-repaired judge into two jobs so the LLM is exposed to neither
the truth table nor a rubric:
  - the LLM ONLY converts prose (query + answer) into structured claims
  - CODE verifies those claims against the database and computes the score

SCOPE: the same 52 records (26 list-returning queries x 2 systems) already
covered by M6-repaired and the human evaluation (id_mapping_M6_repaired.jsonl),
so all measures are comparable.

Usage:
  python scripts/benchmarks/build_m6_step4.py build     # Step A + C (build batch, print cost gate, STOP)
  python scripts/benchmarks/build_m6_step4.py verify     # Step B (run only after the batch has been submitted
                                                           # and results/results_M6_extraction.jsonl exists)

SECURITY: reads DB_URI (verify mode only) from env; never prints credentials.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import psycopg2.extras

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import build_m6_repair as m6r  # noqa: E402  (sibling script -- reuses DB/truth-table/token/blinding helpers)

from elh_rag.tools._shared.room_id import decode_room_id  # noqa: E402  (src/ already on sys.path via m6r import)
from elh_rag.tools._shared.room_id import InvalidRoomIdError  # noqa: E402

_ROOT = m6r._ROOT
V2_DIR = _ROOT / "benchmarks/runs/phase2_vs_phase3/v2"
JB_DIR = V2_DIR / "judge_batches_fresh"
ID_MAP_PATH = JB_DIR / "id_mapping_M6_repaired.jsonl"
ANSWER_FILES = ("phase2_eval_v2_fresh.jsonl", "phase3_eval_v2_fresh.jsonl")

BATCH_OUT = JB_DIR / "batch_M6_extraction.jsonl"
MAPPING_OUT = JB_DIR / "id_mapping_M6_extraction.jsonl"
RESULTS_IN = JB_DIR / "results" / "results_M6_extraction.jsonl"
SCORES_OUT = JB_DIR / "results" / "m6_step4_scores.jsonl"

MODEL = m6r.MODEL_HAIKU
LIST_IN = m6r.LIST_IN
LIST_OUT = m6r.LIST_OUT
BATCH_DISCOUNT = m6r.BATCH_DISCOUNT
MAX_OUT_TOKENS = 2000  # extraction output is longer than a verdict; the M6_repaired
                       # batch truncated 10/52 responses at 256 -- do not repeat that
REMAINING_BUDGET_HINT = 8.4  # supervisor-reported figure at task time; informational only

BAR = m6r.BAR
THIN = m6r.THIN

# ---------------------------------------------------------------------------
# STEP A -- extraction batch (LLM sees ONLY query + answer; no truth table, no rubric)
# ---------------------------------------------------------------------------

SYS_EXTRACTION = """\
You extract structured claims from a housing-search assistant's answer to a
user query. You are NOT scoring or judging the answer, and you have no
database or ground truth to consult -- none is given to you. Report ONLY what
the answer text itself asserts. Do not infer, do not correct, do not fill in
facts the answer does not state.

Output ONLY valid JSON matching this exact schema, no other text before or
after it:
{
  "stated_total": <int|null>,
  "rooms": [ {
      "property_name": <str|null>,
      "room_name": <str|null>,
      "zone": <str|null>,
      "neighborhood": <str|null>,
      "room_id": <str|null>,
      "price_eur": <number|null>,
      "price_season": <"autumn"|"spring"|"summer"|"fixed"|null>
  } ],
  "attribute_claims": [ {
      "subject": <str>,
      "attribute": <str>,
      "value": <str>
  } ],
  "denials": [ <str> ]
}

Rules:
- "stated_total": the count the answer explicitly gives (e.g. "I found 12
  rooms"). null if no count is stated.
- "rooms": one entry per distinct room/property the answer names. Fill only
  the fields the answer actually states for that room; use null for anything
  not mentioned. If the answer names no rooms, return an empty list.
- "attribute_claims": any claim about a field not already covered by the room
  fields above -- e.g. metro line, number of bathrooms, air conditioning,
  heating, bed linen, kitchen access, area in m2, desk, elevator, pets
  allowed, deposit, minimum stay. "subject" names which room/property the
  claim is about (as it appears in the answer), or "all" if the claim applies
  to every room in the answer collectively.
  "value" is the claimed value as a short string (e.g. "yes", "no", "2",
  "blue line", "25 m2").
- "denials": any explicit statement that no rooms match, that a filter
  cannot be applied, or that some requested information is unknown or
  unavailable. One string per denial, verbatim or lightly paraphrased.
- If a list has nothing to report, return it as an empty list [], never omit
  the key.
"""


def _user_msg_extraction(query: str, answer: str) -> str:
    return f"**User query**:\n{m6r._blind(query)}\n\n**Assistant answer**:\n{m6r._blind(answer)}\n"


def make_batch_record(custom_id: str, model: str, system_prompt: str, user_message: str) -> dict[str, Any]:
    """Local copy of m6r.make_batch_record -- that one hardcodes m6r's own
    module-level MAX_OUT_TOKENS (256), which would silently re-truncate
    extraction responses at the exact cap this step was told to avoid."""
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


def load_answer_index() -> dict[tuple[str, str], dict[str, Any]]:
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for fname in ANSWER_FILES:
        for rec in m6r.load_jsonl(V2_DIR / fname):
            idx[(rec["system"], rec["id"])] = rec
    return idx


def build_extraction_batch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    id_map = m6r.load_jsonl(ID_MAP_PATH)
    answers = load_answer_index()

    records: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    for m in id_map:
        system, query_id = m["system"], m["query_id"]
        ans_rec = answers.get((system, query_id))
        if ans_rec is None:
            raise RuntimeError(f"No phase answer found for {system}/{query_id}")
        cid = f"M6_extraction_{system}_{query_id}"
        user_msg = _user_msg_extraction(ans_rec.get("query", ""), ans_rec.get("final_message", ""))
        records.append(make_batch_record(cid, MODEL, SYS_EXTRACTION, user_msg))
        mapping.append({
            "custom_id": cid, "system": system, "query_id": query_id,
            "metric": "M6_extraction", "category": m["category"], "language": m["language"],
        })
    return records, mapping


def run_build() -> None:
    print(f"\n{BAR}\n  STEP A -- BUILD EXTRACTION BATCH (LLM sees ONLY query + answer)\n{BAR}")
    records, mapping = build_extraction_batch()
    print(f"  Built {len(records)} records (expected 52)")

    violations = m6r.check_blinding_violations(records)
    print(f"  Blinding violations: {len(violations)} (expected 0)")
    for v in violations[:10]:
        print(f"    {v}")

    m6r.write_jsonl(BATCH_OUT, records)
    print(f"  Wrote {BATCH_OUT.relative_to(_ROOT)}")
    m6r.write_jsonl(MAPPING_OUT, mapping)
    print(f"  Wrote {MAPPING_OUT.relative_to(_ROOT)}")

    print(f"\n{BAR}\n  STEP C -- COST GATE\n{BAR}")
    mean_tok, max_tok, n_measured = m6r.measure_tokens_all(records, sample_n=None)
    if n_measured:
        total_in = mean_tok * len(records)
        total_out = MAX_OUT_TOKENS * len(records)  # worst case: max_tokens, no completions exist yet
        cost = (
            total_in * LIST_IN[MODEL] * (1 - BATCH_DISCOUNT)
            + total_out * LIST_OUT[MODEL] * (1 - BATCH_DISCOUNT)
        ) / 1_000_000
        print(f"  requests                 : {len(records)}")
        print(f"  MEASURED input tokens    : mean={mean_tok:.0f}  max={max_tok}  (n={n_measured}/{len(records)})")
        print(f"  max_tokens (output cap)  : {MAX_OUT_TOKENS}")
        print(f"  total_in (est)           : {total_in:,.0f}")
        print(f"  total_out (worst case)   : {total_out:,}")
        print(f"  model                    : {MODEL}  (${LIST_IN[MODEL]}/${LIST_OUT[MODEL]} per MTok, "
              f"{int(BATCH_DISCOUNT * 100)}% batch discount)")
        print(f"  ESTIMATED COST           : ${cost:.4f}")
        print(f"  remaining budget (hint)  : ~${REMAINING_BUDGET_HINT:.2f}  ->  after this batch: "
              f"~${REMAINING_BUDGET_HINT - cost:.4f}")
    else:
        print("  ANTHROPIC_API_KEY not set -- could not measure real token counts.")

    print(f"\n{THIN}\n  ONE FULL EXAMPLE PROMPT (verbatim, record 0)\n{THIN}")
    example = records[0]
    print(json.dumps(example, indent=2, ensure_ascii=False))

    print(f"\n{BAR}\n  STOP -- batch built, NOT submitted. Awaiting approval to submit.\n{BAR}\n")


# ---------------------------------------------------------------------------
# STEP B -- SQL verifier (code written now; run this only after Step A's
# batch has been submitted, polled to completion, and results saved to
# RESULTS_IN by scripts/benchmarks/submit_judge_batch.py)
# ---------------------------------------------------------------------------

SUPPORTED, CONTRADICTED, UNVERIFIABLE = "SUPPORTED", "CONTRADICTED", "UNVERIFIABLE"
PRICE_TOL = 1.0  # EUR


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned


def repair_truncated_json(text: str) -> dict[str, Any] | None:
    """Salvage a partial object from a response cut off at max_tokens.

    Schema field order is stated_total, rooms, attribute_claims, denials, so a
    mid-stream truncation (always observed inside attribute_claims -- rooms
    come first and are short) still leaves stated_total and the full rooms
    list intact; only the tail of attribute_claims and the denials list (which
    comes last and is never reached) are lost for a repaired record. Walks the
    bracket/string state to find the last position at which the JSON so far is
    a valid *prefix* of a well-formed document (just after a top-level comma
    or a closed object/array), snapshots the open-bracket stack at that point,
    and closes it there -- NOT at the final (over-extended) stack, which would
    include the brackets opened by the still-incomplete trailing element.
    """
    s = _strip_fences(text)
    start = s.find("{")
    if start == -1:
        return None
    s = s[start:]
    stack: list[str] = []
    in_string = False
    escape = False
    last_safe = 0
    last_safe_stack: list[str] = []
    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            last_safe, last_safe_stack = i + 1, list(stack)
        elif ch == ",":
            last_safe, last_safe_stack = i, list(stack)
    if not stack:
        return None  # already balanced -- not actually truncated, let the plain parser handle it
    truncated = s[:last_safe].rstrip()
    if truncated.endswith(","):
        truncated = truncated[:-1]
    closers = "".join("}" if c == "{" else "]" for c in reversed(last_safe_stack))
    try:
        obj = json.loads(truncated + closers)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def parse_extraction_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Parse an extraction response. Returns (obj_or_None, status), status in
    {"ok", "repaired", "failed"}. "repaired" means the response was truncated
    at max_tokens and a partial object (rooms/stated_total intact, tail of
    attribute_claims and all denials potentially lost) was salvaged."""
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned), "ok"
    except Exception:
        pass
    repaired = repair_truncated_json(text)
    if repaired is not None:
        return repaired, "repaired"
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0)), "ok"
        except Exception:
            pass
    return None, "failed"


@dataclass
class VerifiedClaim:
    kind: str  # "room" | "stated_total" | "attribute" | "denial"
    outcome: str  # SUPPORTED | CONTRADICTED | UNVERIFIABLE
    detail: str
    raw: dict[str, Any] = field(default_factory=dict)


def _normalize(s: str) -> str:
    return m6r._normalize(s)


_LOCALE_SUFFIX_RE = re.compile(r"\b(area|zone|district|neighbou?rhood)\b")


def _normalize_locale(s: str) -> str:
    """Normalize a zone/neighborhood string for comparison, additionally
    stripping generic descriptor words the extraction routinely appends
    (e.g. answer says "Santos Area", DB zone is "Santos" -- the room is
    real and in the right zone, "Area" is not part of the name)."""
    n = _normalize(s)
    n = _LOCALE_SUFFIX_RE.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _fetch_room_id_pairs_global(cur) -> set[tuple[str, str]]:
    """(house_id, room_id) pairs for every room row in the DB, whitespace-stripped.

    loc_idhouse/idroom are fixed-width CHAR(n) columns, blank-padded to their
    declared length -- comparing them raw against a clean extracted id (or
    against m6r's own un-stripped registries["house_ids"]) always fails.
    """
    rows = m6r.q(cur, "SELECT loc_idhouse, idroom FROM room")
    return {(r["loc_idhouse"].strip(), r["idroom"].strip()) for r in rows}


def _room_id_pair(raw_id: str) -> tuple[str, str] | None:
    """First two pipe-delimited segments (house_id, room_id) of a room_id
    string, tolerating a missing/garbled dateupdate suffix."""
    parts = raw_id.split("|")
    if len(parts) >= 2 and parts[0].startswith("HSE_") and parts[1].startswith("RM_"):
        return parts[0], parts[1]
    return None


def _resolve_room_id(
    raw_id: str, truth_rooms: list[dict[str, Any]], registries: dict[str, Any],
) -> tuple[str, str, dict[str, Any] | None]:
    """Returns (outcome, detail, matched_truth_room_or_None) for a claimed room_id string.

    The extraction pass was observed to silently drop the dateupdate suffix
    from room_ids the answer actually cites in full (answer gives
    'HSE_X|RM_HSE_X_4|2022-03-02T00:00:00', extraction keeps only
    'HSE_X|RM_HSE_X_4') -- match on the (house_id, room_id) pair, ignoring the
    date segment, rather than requiring an exact string match against the
    fully-encoded truth-table id (which would always miss).
    """
    raw_id = raw_id.strip().strip("*")
    by_id = {r["room_id"]: r for r in truth_rooms}
    if raw_id in by_id:
        return SUPPORTED, f"room_id {raw_id!r} matches a row satisfying the query's filters", by_id[raw_id]

    by_pair = {(r["room_id"].split("|")[0], r["room_id"].split("|")[1]): r for r in truth_rooms}
    pair = _room_id_pair(raw_id)
    if pair is not None:
        if pair in by_pair:
            return SUPPORTED, (
                f"room_id {raw_id!r} matches a row satisfying the query's filters "
                f"(matched on house_id+room_id; dateupdate suffix was dropped by extraction)"
            ), by_pair[pair]
        if pair in registries["room_pairs_global"]:
            return CONTRADICTED, f"room_id {raw_id!r} exists in the DB but does not satisfy this query's filters", None
        return CONTRADICTED, f"room_id {raw_id!r} does not exist in the database", None

    # bare house-id-only claim (no room segment given)
    m = re.match(r"^(HSE_[0-9A-Fa-f]+)", raw_id)
    house_bare = m.group(1) if m else None
    if house_bare is None:
        return CONTRADICTED, f"room_id {raw_id!r} is not a recognisable house/room id", None
    house_matches = [r for (h, _rid), r in by_pair.items() if h == house_bare]
    if house_matches:
        return SUPPORTED, (
            f"house {house_bare!r} has at least one room satisfying the query's filters "
            f"(house-level match only -- no specific room_id given)"
        ), house_matches[0]
    global_houses = {h for h, _ in registries["room_pairs_global"]}
    if house_bare in global_houses:
        return CONTRADICTED, f"house {house_bare!r} exists in the DB but has no room satisfying this query's filters", None
    return CONTRADICTED, f"house {house_bare!r} does not exist in the database", None


def _price_ok_generic(
    r: dict[str, Any], price_eur: float | None, price_season: str | None,
) -> bool:
    if price_eur is None:
        return True
    season_map = {
        "autumn": r.get("price_eur"), "spring": r.get("spring_price"),
        "summer": r.get("summer_price"), "fixed": r.get("price_eur"),
    }
    target = season_map.get(price_season) if price_season else None
    candidates_prices = (
        [target] if target is not None
        else [r.get("price_eur"), r.get("spring_price"), r.get("summer_price")]
    )
    return any(p is not None and abs(p - price_eur) <= PRICE_TOL for p in candidates_prices)


def _resolve_unnamed_room_by_zone_price(
    zone: str | None, price_eur: float | None, price_season: str | None,
    truth_rooms: list[dict[str, Any]],
) -> tuple[str, str]:
    """Fallback for the (observed, common) case where the answer never names a
    real property -- e.g. phase3 tables that label rows by ZONE only (the
    header reads "House & Zone" but every value is actually just a zone name).
    A property_name of "Anjos" is then not a fabricated property, it is a
    misread zone label; treating it as CONTRADICTED "property does not exist"
    would blame the system for a labelling quirk this verifier introduced
    downstream of extraction, not something the system asserted. Zone+price
    is weaker evidence than a real id/name (several rooms can share both), so
    a match is UNVERIFIABLE (identity not confirmable), not SUPPORTED --  but
    it still catches a genuinely fabricated zone+price combination as
    CONTRADICTED.
    """
    if price_eur is None or not zone:
        return CONTRADICTED, "no property_name/room_id, and not enough zone+price signal to check against the DB"
    zone_norm = _normalize_locale(zone)
    for r in truth_rooms:
        if zone_norm not in {_normalize_locale(r.get("zone") or ""), _normalize_locale(r.get("neighborhood") or "")}:
            continue
        if _price_ok_generic(r, price_eur, price_season):
            return UNVERIFIABLE, (
                f"no property name or room_id given -- zone {zone!r} + price EUR{price_eur:g} matches a row "
                f"satisfying the query's filters, but identity cannot be confirmed to one specific room"
            )
    return CONTRADICTED, (
        f"no room in this query's filtered result set has zone {zone!r} at price EUR{price_eur:g} "
        f"(and no property name or room_id was given to check instead)"
    )


def _resolve_room_by_name(
    property_name: str, room_name: str | None, zone: str | None,
    price_eur: float | None, price_season: str | None,
    truth_rooms: list[dict[str, Any]], registries: dict[str, Any],
) -> tuple[str, str, dict[str, Any] | None]:
    """Returns (outcome, detail, matched_truth_room_or_None)."""
    pname_norm = _normalize(property_name)
    if not pname_norm:
        return UNVERIFIABLE, "no property_name given -- cannot resolve identity", None

    candidates = [r for r in truth_rooms if _normalize(r["flatname"]) == pname_norm]
    if room_name and candidates:
        rname_norm = _normalize(room_name)
        narrowed = [r for r in candidates if _normalize(r["roomname"]) == rname_norm]
        if narrowed:
            candidates = narrowed

    if not candidates:
        if pname_norm in registries["flatnames_norm_to_orig"]:
            return (
                CONTRADICTED,
                f"property {property_name!r} exists in the DB but has no room satisfying "
                f"this query's filters" + (f" matching room {room_name!r}" if room_name else ""),
                None,
            )
        outcome, detail = _resolve_unnamed_room_by_zone_price(zone, price_eur, price_season, truth_rooms)
        return outcome, f"property_name {property_name!r} is not a real property in the DB -- {detail}", None

    def _price_ok(r: dict[str, Any]) -> bool:
        if price_eur is None:
            return True
        season_map = {
            "autumn": r.get("price_eur"), "spring": r.get("spring_price"),
            "summer": r.get("summer_price"), "fixed": r.get("price_eur"),
        }
        target = season_map.get(price_season) if price_season else None
        candidates_prices = (
            [target] if target is not None
            else [r.get("price_eur"), r.get("spring_price"), r.get("summer_price")]
        )
        return any(p is not None and abs(p - price_eur) <= PRICE_TOL for p in candidates_prices)

    def _zone_ok(r: dict[str, Any]) -> bool:
        if not zone:
            return True
        zn = _normalize_locale(zone)
        return zn == _normalize_locale(r.get("zone") or "") or zn == _normalize_locale(r.get("neighborhood") or "")

    for r in candidates:
        if _price_ok(r) and _zone_ok(r):
            return SUPPORTED, f"property {property_name!r} matches a row satisfying the query's filters", r

    bad_fields = []
    if zone and not any(_zone_ok(r) for r in candidates):
        bad_fields.append(f"zone (claimed {zone!r})")
    if price_eur is not None and not any(_price_ok(r) for r in candidates):
        bad_fields.append(f"price (claimed EUR{price_eur:g} {price_season or ''})")
    detail = f"property {property_name!r} found, but stated " + " and ".join(bad_fields) + " does not match"
    return CONTRADICTED, detail, None


def verify_room_claim(
    room: dict[str, Any], truth: dict[str, Any], registries: dict[str, Any],
) -> tuple[VerifiedClaim, dict[str, Any] | None]:
    """Returns (claim, matched_truth_room_or_None). The matched row -- not a
    re-derived flatname-only lookup -- is what attribute_claims about this
    same room should be checked against; a second, cruder re-match here would
    routinely pick a DIFFERENT real row than the one actually verified
    whenever the same property_name appears more than once in an answer
    (common: one flatname, several room types/zones)."""
    truth_rooms = truth.get("rooms_full", truth.get("rooms", []))

    room_id = (room.get("room_id") or "").strip()
    if room_id:
        outcome, detail, matched = _resolve_room_id(room_id, truth_rooms, registries)
        return VerifiedClaim("room", outcome, detail, room), matched

    pname = (room.get("property_name") or "").strip()
    if pname:
        outcome, detail, matched = _resolve_room_by_name(
            pname, room.get("room_name"), room.get("zone") or room.get("neighborhood"),
            room.get("price_eur"), room.get("price_season"), truth_rooms, registries,
        )
        return VerifiedClaim("room", outcome, detail, room), matched

    return VerifiedClaim("room", UNVERIFIABLE, "no room_id or property_name -- cannot resolve identity", room), None


# attribute-name -> (kind, getter). Checked in order; first substring match wins.
# Anything NOT matched here has no column in the schema and is UNVERIFIABLE by
# design (e.g. metro line, bathroom count, air conditioning, heating, bed
# linen, kitchen access, view, floor number, photos, review sentiment).
ATTRIBUTE_RESOLVERS: list[tuple[list[str], str, Callable[[dict[str, Any]], Any]]] = [
    (["shared bathroom"], "bool_inverse", lambda r: r["attrs"]["private_bathroom"]),
    (["private bathroom", "ensuite", "en-suite", "own bathroom"], "bool", lambda r: r["attrs"]["private_bathroom"]),
    (["balcony"], "bool", lambda r: r["attrs"]["balcony"]),
    (["desk"], "bool", lambda r: r["attrs"]["desk"]),
    (["elevator", "lift"], "bool", lambda r: r["attrs"]["elevator"]),
    (["internet", "wifi", "wi-fi"], "bool", lambda r: r["attrs"]["internet"]),
    (["furnished"], "bool", lambda r: r["attrs"]["furnished"]),
    (["pet"], "bool", lambda r: r["attrs"]["allow_pets"]),
    (["washer", "dryer", "laundry machine"], "bool", lambda r: r["attrs"]["washer_drier"]),
    (["female"], "bool", lambda r: r["attrs"]["female_preferred"]),
    (["male"], "bool", lambda r: r["attrs"]["male_preferred"]),
    (["deposit value", "deposit amount"], "numeric", lambda r: r["deposit_value"]),
    (["deposit"], "bool", lambda r: r["deposit"]),
    (["area", "m2", "sqm", "square met"], "numeric", lambda r: r["area_m2"]),
    (["distance to", "transport distance", "meters to", "metres to"], "numeric",
     lambda r: r["attrs"]["distance_to_transport_m"]),
    (["minimum stay", "min reserve", "min. reserve", "minimum reservation"], "numeric",
     lambda r: r["attrs"]["min_reserve_months"]),
    (["extra person cost", "extra guest cost", "additional person cost"], "numeric",
     lambda r: r["attrs"]["extra_person_cost"]),
    (["extra person", "extra guest", "additional person"], "bool", lambda r: r["attrs"]["extra_person_allowed"]),
    (["bed type", "bed size"], "string", lambda r: r["bed_type"]),
    (["zone", "neighborhood", "neighbourhood", "district"], "string", lambda r: r["zone"]),
]

_TRUE_WORDS = {"yes", "y", "true", "1", "available", "present", "has", "provided", "allowed"}
_FALSE_WORDS = {"no", "n", "false", "0", "not available", "absent", "none", "not allowed", "not provided"}


def _resolve_attribute(attribute_text: str) -> tuple[str, Callable[[dict[str, Any]], Any]] | None:
    norm = _normalize(attribute_text)
    for keywords, kind, getter in ATTRIBUTE_RESOLVERS:
        if any(kw in norm or _normalize(kw) in norm for kw in keywords):
            return kind, getter
    return None


def _find_subject_room(
    subject: str, extracted_rooms: list[dict[str, Any]], resolved_rooms: dict[int, dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Best-effort match of an attribute_claim's free-text subject to one of
    this record's already-resolved room dicts (from verify_room_claim).

    Scores each extracted room by whether its property_name AND/OR room_name
    appear in the subject text and picks the highest-scoring one, instead of
    returning the first property_name substring hit. Two extracted rooms
    routinely share a property_name (the same flatname cited for two
    different room types in one answer); a first-match rule silently
    attributes claim N's subject to room 0's DB row whenever room 0 happens
    to share a property_name with the room the claim is actually about,
    fabricating a value mismatch that isn't real.
    """
    subj_norm = _normalize(subject)
    if subj_norm and subj_norm != "all":
        best_i, best_score = None, 0
        for i, room in enumerate(extracted_rooms):
            pname_norm = _normalize(room.get("property_name") or "")
            rname_norm = _normalize(room.get("room_name") or "")
            score = 0
            if rname_norm and (rname_norm in subj_norm or subj_norm in rname_norm):
                score += 2
            if pname_norm and (pname_norm in subj_norm or subj_norm in pname_norm):
                score += 1
            if score > best_score:
                best_i, best_score = i, score
        if best_i is not None:
            return resolved_rooms.get(best_i)
    if len(extracted_rooms) == 1:
        return resolved_rooms.get(0)
    return None


def _check_value_against_room(
    kind: str, getter: Callable[[dict[str, Any]], Any], attribute: str, value: str, room: dict[str, Any],
) -> tuple[str, str]:
    """Returns (outcome, detail) comparing one claimed value to one resolved room's actual value."""
    actual = getter(room)
    if kind in ("bool", "bool_inverse"):
        claimed_bool = None
        v = value.strip().lower()
        if v in _TRUE_WORDS:
            claimed_bool = True
        elif v in _FALSE_WORDS:
            claimed_bool = False
        if claimed_bool is None:
            return UNVERIFIABLE, f"could not parse boolean value {value!r}"
        actual_bool = (not actual) if kind == "bool_inverse" else bool(actual)
        outcome = SUPPORTED if actual_bool == claimed_bool else CONTRADICTED
        return outcome, f"{attribute}: claimed={value!r} actual={actual!r}"
    if kind == "numeric":
        try:
            claimed_num = float(re.sub(r"[^\d.\-]", "", value))
        except ValueError:
            return UNVERIFIABLE, f"could not parse numeric value {value!r}"
        if actual is None:
            return CONTRADICTED, f"{attribute}: claimed={value!r} but DB value is null"
        outcome = SUPPORTED if abs(float(actual) - claimed_num) <= max(1.0, 0.05 * abs(claimed_num)) else CONTRADICTED
        return outcome, f"{attribute}: claimed={value!r} actual={actual!r}"
    # string
    outcome = SUPPORTED if _normalize(str(value)) == _normalize(str(actual or "")) else CONTRADICTED
    return outcome, f"{attribute}: claimed={value!r} actual={actual!r}"


def verify_attribute_claim(
    claim: dict[str, Any], extracted_rooms: list[dict[str, Any]], resolved_rooms: dict[int, dict[str, Any] | None],
) -> VerifiedClaim:
    attribute, value, subject = claim.get("attribute", ""), claim.get("value", ""), claim.get("subject", "")
    resolved = _resolve_attribute(attribute)
    if resolved is None:
        return VerifiedClaim(
            "attribute", UNVERIFIABLE,
            f"attribute {attribute!r} has no column in the schema", claim,
        )
    kind, getter = resolved

    if (subject or "").strip().lower() == "all":
        # A blanket "all rooms have X" claim is falsified by ANY resolved room
        # that contradicts it -- check every verified room in this record,
        # not just one. Previously routed straight to UNVERIFIABLE (no single
        # room to check against), which let real contradictions slip through
        # a system's blanket claims undetected.
        rooms = [r for r in resolved_rooms.values() if r is not None]
        if not rooms:
            return VerifiedClaim(
                "attribute", UNVERIFIABLE,
                f"attribute {attribute!r} is mappable, but no room in this answer resolved to a "
                f"verified DB row to check the blanket claim against", claim,
            )
        outcomes = [_check_value_against_room(kind, getter, attribute, value, r) for r in rooms]
        contradicting = [(o, d) for o, d in outcomes if o == CONTRADICTED]
        if contradicting:
            _, d = contradicting[0]
            return VerifiedClaim(
                "attribute", CONTRADICTED,
                f"blanket claim '{attribute}={value}' for all rooms is false for at least "
                f"{len(contradicting)}/{len(rooms)} verified room(s), e.g. {d}", claim,
            )
        if all(o == SUPPORTED for o, _ in outcomes):
            return VerifiedClaim(
                "attribute", SUPPORTED,
                f"blanket claim '{attribute}={value}' holds for all {len(rooms)} verified room(s)", claim,
            )
        return VerifiedClaim(
            "attribute", UNVERIFIABLE,
            f"blanket claim '{attribute}={value}' -- value could not be parsed/checked for any verified room", claim,
        )

    subject_room = _find_subject_room(subject, extracted_rooms, resolved_rooms)
    if subject_room is None:
        return VerifiedClaim(
            "attribute", UNVERIFIABLE,
            f"attribute {attribute!r} is mappable, but subject {subject!r} could not be "
            f"resolved to a verified room in this answer", claim,
        )
    outcome, detail = _check_value_against_room(kind, getter, attribute, value, subject_room)
    return VerifiedClaim("attribute", outcome, detail, claim)


_NO_MATCH_RE = re.compile(r"\b(no|zero|none|not (?:find|found)|can'?t find)\b.{0,20}\b(room|match|result|listing)", re.IGNORECASE)


def verify_denial(denial: str, truth: dict[str, Any]) -> VerifiedClaim:
    if _NO_MATCH_RE.search(denial) and truth.get("total_matches") is not None:
        if truth["total_matches"] == 0:
            return VerifiedClaim("denial", SUPPORTED, f"denial {denial!r}: true total_matches is 0", {"text": denial})
        return VerifiedClaim(
            "denial", CONTRADICTED,
            f"denial {denial!r} is false: {truth['total_matches']} rows actually satisfy this query", {"text": denial},
        )
    return VerifiedClaim(
        "denial", UNVERIFIABLE,
        f"denial {denial!r} is not a checkable 'no rows match' claim against this schema", {"text": denial},
    )


def verify_stated_total(stated_total: int, truth: dict[str, Any]) -> VerifiedClaim | None:
    if truth.get("kind") in {"zone_enum", "non_filterable", "single_room"} or truth.get("total_matches") is None:
        return None
    true_n, tol = truth["total_matches"], truth.get("tolerance", 0)
    outcome = SUPPORTED if abs(stated_total - true_n) <= tol else CONTRADICTED
    return VerifiedClaim(
        "stated_total", outcome,
        f"stated_total={stated_total} true_total_matches={true_n} (tolerance +/-{tol})",
        {"stated_total": stated_total},
    )


def verify_record(
    extraction: dict[str, Any], truth: dict[str, Any], registries: dict[str, Any],
) -> list[VerifiedClaim]:
    claims: list[VerifiedClaim] = []

    extracted_rooms = extraction.get("rooms") or []
    resolved_rooms: dict[int, dict[str, Any] | None] = {}
    for i, room in enumerate(extracted_rooms):
        vc, matched = verify_room_claim(room, truth, registries)
        claims.append(vc)
        resolved_rooms[i] = matched if vc.outcome == SUPPORTED else None

    stated_total = extraction.get("stated_total")
    if stated_total is not None:
        vc = verify_stated_total(int(stated_total), truth)
        if vc is not None:
            claims.append(vc)

    for ac in extraction.get("attribute_claims") or []:
        claims.append(verify_attribute_claim(ac, extracted_rooms, resolved_rooms))

    for denial in extraction.get("denials") or []:
        claims.append(verify_denial(denial, truth))

    return claims


def score_claims(claims: list[VerifiedClaim]) -> float | None:
    n_sup = sum(1 for c in claims if c.outcome == SUPPORTED)
    n_con = sum(1 for c in claims if c.outcome == CONTRADICTED)
    if n_sup + n_con == 0:
        return None
    return n_sup / (n_sup + n_con)


def run_verify() -> None:
    if not RESULTS_IN.exists():
        print(f"ERROR: {RESULTS_IN.relative_to(_ROOT)} not found -- submit and poll the batch first.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{BAR}\n  STEP B -- SQL VERIFICATION OF EXTRACTED CLAIMS\n{BAR}")
    mapping = {r["custom_id"]: r for r in m6r.load_jsonl(MAPPING_OUT)}
    results = {r["custom_id"]: r for r in m6r.load_jsonl(RESULTS_IN)}

    conn = m6r.get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    truth_tables = m6r.build_all_truth_tables(cur)
    registries = m6r._fetch_global_registries(cur)
    registries["house_ids"] = {h.strip() for h in registries["house_ids"]}  # m6r leaves these padded
    registries["room_pairs_global"] = _fetch_room_id_pairs_global(cur)

    scored: list[dict[str, Any]] = []
    n_ok = n_repaired = n_failed = 0
    for cid, m in mapping.items():
        res = results.get(cid)
        if res is None or res.get("type") != "succeeded":
            scored.append({**m, "error": "no succeeded batch result"})
            continue
        extraction, status = parse_extraction_json(res["text"])
        if status == "ok":
            n_ok += 1
        elif status == "repaired":
            n_repaired += 1
        else:
            n_failed += 1
        if extraction is None:
            scored.append({**m, "error": "could not parse extraction JSON", "raw_text": res["text"]})
            continue

        truth = truth_tables[m["query_id"]]
        claims = verify_record(extraction, truth, registries)
        n_sup = sum(1 for c in claims if c.outcome == SUPPORTED)
        n_con = sum(1 for c in claims if c.outcome == CONTRADICTED)
        n_unv = sum(1 for c in claims if c.outcome == UNVERIFIABLE)
        scored.append({
            **m,
            "M6_step4": score_claims(claims),
            "n_supported": n_sup,
            "n_contradicted": n_con,
            "n_unverifiable": n_unv,
            "contradicted_items": [
                {"kind": c.kind, "detail": c.detail, "raw": c.raw} for c in claims if c.outcome == CONTRADICTED
            ],
            "extraction_status": status,
        })

    cur.close()
    conn.close()

    m6r.write_jsonl(SCORES_OUT, scored)
    print(f"  Wrote {SCORES_OUT.relative_to(_ROOT)}")
    print(f"  Extraction JSON: ok={n_ok}  repaired(truncated-but-salvaged)={n_repaired}  failed={n_failed}  (of {len(mapping)})")

    print(f"\n  {'query_id':<30}{'system':<8}{'sup':>5}{'con':>5}{'unv':>5}{'M6_step4':>10}")
    per_system: dict[str, list[float]] = {"phase2": [], "phase3": []}
    unv_totals: dict[str, int] = {"phase2": 0, "phase3": 0}
    for r in scored:
        if "error" in r:
            print(f"  {r['query_id']:<30}{r['system']:<8}  {r['error']}")
            continue
        score_str = f"{r['M6_step4']:.3f}" if r["M6_step4"] is not None else "None"
        print(
            f"  {r['query_id']:<30}{r['system']:<8}{r['n_supported']:>5}{r['n_contradicted']:>5}"
            f"{r['n_unverifiable']:>5}{score_str:>10}"
        )
        if r["M6_step4"] is not None:
            per_system[r["system"]].append(r["M6_step4"])
        unv_totals[r["system"]] += r["n_unverifiable"]

    print(f"\n  Mean M6_step4 (records with >=1 verifiable claim):")
    for sysname in ("phase2", "phase3"):
        scores = per_system[sysname]
        mean = sum(scores) / len(scores) if scores else float("nan")
        print(f"    {sysname}: mean={mean:.3f}  n={len(scores)}/26")

    print(f"\n  Total UNVERIFIABLE claims (attribute has no column in the schema):")
    for sysname in ("phase2", "phase3"):
        print(f"    {sysname}: {unv_totals[sysname]}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["build", "verify"], nargs="?", default="build")
    args = p.parse_args()
    if args.mode == "build":
        run_build()
    else:
        run_verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
