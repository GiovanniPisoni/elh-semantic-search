"""GATE — alignment check: current SQL vs golden-set ground truths.

Read-only. No re-index. No re-run. Prints a VERDICT per section.
SECURITY: reads DB_URI from env only; never prints credentials.
"""
from __future__ import annotations
import os, sys, re, unicodedata
from pathlib import Path
from decimal import Decimal

import psycopg2, psycopg2.extras

_ROOT = Path(__file__).resolve().parents[2]

def load_env():
    p = _ROOT / ".env"
    if not p.exists(): return
    with p.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

def conn():
    uri = os.environ.get("DB_URI")
    if not uri: raise RuntimeError("DB_URI not set")
    c = psycopg2.connect(uri)
    c.autocommit = True
    return c

def q(cur, sql, params=None):
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)
    return cur.fetchall()

BAR  = "=" * 72
THIN = "-" * 72

def _match(label, got, expected, tol=0):
    ok = abs(got - expected) <= tol
    mark = "MATCH" if ok else "DRIFT"
    print(f"    {mark}  {label}: got={got}  expected={expected}")
    return ok

# ---------------------------------------------------------------------------
# §1  COUNTS  §A / §B
# ---------------------------------------------------------------------------
def check_counts(cur):
    print(f"\n{THIN}")
    print("  §1  COUNTS (§A / §B)")
    print(f"{THIN}")

    base_sql = """
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT (r.loc_idhouse, r.idroom)) AS distinct_rooms
FROM room r
JOIN house h ON TRIM(h.idhouse) = TRIM(r.loc_idhouse) AND h.dateupdate = r.loc_dateupdate
WHERE r.status = 'Available' AND h.status = 'Validated'
"""
    # Lisbon
    rows = q(cur, base_sql + " AND TRIM(h.city) = 'Lisbon'")
    row_l, dist_l = rows[0][0], rows[0][1]
    _match("Lisbon row-count",   row_l,  556)
    _match("Lisbon distinct",    dist_l, 435)

    # Porto
    rows = q(cur, base_sql + " AND TRIM(h.city) = 'Porto'")
    row_p, dist_p = rows[0][0], rows[0][1]
    _match("Porto row-count",    row_p,  376)
    _match("Porto distinct",     dist_p, 295)

    # Under-450 Porto (autumnprice, exclude dirty <=0)
    rows = q(cur, base_sql + """
AND TRIM(h.city) = 'Porto'
AND r.autumnprice < 450 AND r.autumnprice > 0
""")
    _match("Porto autumnprice<450 rows", rows[0][0], 20, tol=5)

    # Private bathroom Lisbon (~188)
    rows = q(cur, base_sql + """
AND TRIM(h.city) = 'Lisbon' AND TRIM(r.privatebathroom) = 'Y'
""")
    _match("Lisbon private-bathroom rows", rows[0][0], 188, tol=5)

    # Female-preferred Lisbon (~92)
    rows = q(cur, base_sql + """
AND TRIM(h.city) = 'Lisbon' AND TRIM(h.femalepreferred) = 'Y'
""")
    _match("Lisbon female-preferred rows", rows[0][0], 92, tol=5)

    # Furnished Lisbon (~532)
    rows = q(cur, base_sql + """
AND TRIM(h.city) = 'Lisbon' AND TRIM(h.furnished) = 'Y'
""")
    _match("Lisbon furnished rows", rows[0][0], 532, tol=5)

    # Distance<=500 Porto (~170)
    rows = q(cur, base_sql + """
AND TRIM(h.city) = 'Porto' AND h.distancepublictransport <= 500
""")
    _match("Porto dist<=500 rows", rows[0][0], 170, tol=5)


# ---------------------------------------------------------------------------
# §2  M2 ANCHORS
# ---------------------------------------------------------------------------

# Expected values from §J (quantitative_reasoning cassette, DB 2026-06-23)
ANCHORS = {
    # (idhouse, idroom, dateupdate): {field: expected}
    ("HSE_AB145FF2", "RM_HSE_AB145FF2_5", "2023-03-17"):  {
        "autumnprice":220, "springprice":None, "summerprice":None,
        "fixedprice":"Y", "deposit":"Y", "depositvalue":160,
        "lastmonthdeposit":"N", "admintax":70, "extrapersonallowed":"N",
        "extrapersoncost":None,
    },
    ("HSE_77C4AFBA", "RM_HSE_77C4AFBA_15", "2021-05-22"): {
        "autumnprice":135, "springprice":100, "summerprice":80,
        "fixedprice":"N", "deposit":"Y", "depositvalue":75,
        "lastmonthdeposit":"N", "admintax":110, "extrapersonallowed":"Y",
        "extrapersoncost":90,
    },
    ("HSE_77C4AFBA", "RM_HSE_77C4AFBA_6", "2021-05-22"):  {
        "autumnprice":205, "springprice":165, "summerprice":150,
        "fixedprice":"N", "deposit":"N", "depositvalue":None,
        "lastmonthdeposit":"Y", "admintax":150, "extrapersonallowed":"Y",
        "extrapersoncost":65,
    },
    ("HSE_90DB55C7", "RM_HSE_90DB55C7_3", "2022-07-04"):  {
        "autumnprice":250, "springprice":210, "summerprice":175,
        "fixedprice":"N", "deposit":"N", "depositvalue":None,
        "lastmonthdeposit":"Y", "admintax":110, "extrapersonallowed":"Y",
        "extrapersoncost":95,
    },
    ("HSE_90DB55C7", "RM_HSE_90DB55C7_9", "2022-07-04"):  {
        "autumnprice":240, "springprice":180, "summerprice":145,
        "fixedprice":"N", "deposit":"N", "depositvalue":None,
        "lastmonthdeposit":"Y", "admintax":75, "extrapersonallowed":"N",
        "extrapersoncost":None,
    },
    ("HSE_D1F41EC3", "RM_HSE_D1F41EC3_15", "2021-07-30"): {
        "autumnprice":155, "springprice":None, "summerprice":None,
        "fixedprice":"Y", "deposit":"Y", "depositvalue":150,
        "lastmonthdeposit":"N", "admintax":140, "extrapersonallowed":"N",
        "extrapersoncost":None,
    },
    ("HSE_E6069573", "RM_HSE_E6069573_4", "2020-11-18"):  {
        "autumnprice":980, "springprice":None, "summerprice":None,
        "fixedprice":None, "deposit":"Y", "depositvalue":1140,
        "lastmonthdeposit":None, "admintax":None, "extrapersonallowed":"Y",
        "extrapersoncost":95,
    },
}

def _val_eq(got, exp):
    if exp is None:
        return True   # not checked
    if isinstance(exp, (int, float)):
        try:
            return abs(float(got) - exp) < 0.01
        except Exception:
            return False
    return str(got).strip() == str(exp)

def check_anchors(cur):
    print(f"\n{THIN}")
    print("  §2  M2 ANCHOR ROOMS")
    print(f"{THIN}")

    # Discover room fields first (graceful column detection)
    cur.execute("""
SELECT column_name FROM information_schema.columns
WHERE table_name='room' ORDER BY ordinal_position
""")
    room_cols = {r[0] for r in cur.fetchall()}

    for (idhouse, idroom, dateupdate_prefix), expected in ANCHORS.items():
        label = f"{idhouse}|{idroom}"
        # dateupdate may be stored with time component; use LIKE or CAST
        rows = q(cur, """
SELECT r.*, TRIM(h.city) AS _city, TRIM(h.status) AS _hstatus
FROM room r
JOIN house h ON TRIM(h.idhouse) = TRIM(r.loc_idhouse) AND h.dateupdate = r.loc_dateupdate
WHERE TRIM(r.idroom) = %s
  AND TRIM(r.loc_idhouse) = %s
  AND CAST(r.dateupdate AS TEXT) LIKE %s
""", (idroom, idhouse, f"{dateupdate_prefix}%"))

        if not rows:
            print(f"  MISSING  {label}  (no row found with dateupdate {dateupdate_prefix}...)")
            continue

        row = rows[0]
        # Build column→value dict
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='room' ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        r_dict = dict(zip(cols, row[:len(cols)]))

        drifts = []
        for field, exp_val in expected.items():
            if exp_val is None:
                continue
            if field not in r_dict:
                drifts.append(f"{field}=MISSING_COLUMN")
                continue
            got_val = r_dict[field]
            if isinstance(got_val, Decimal):
                got_val = float(got_val)
            if not _val_eq(got_val, exp_val):
                drifts.append(f"{field}: got={got_val!r} expected={exp_val!r}")

        city = r_dict.get("_city", "?")
        if drifts:
            print(f"  DRIFT    {label}  [{city}]")
            for d in drifts:
                print(f"           !! {d}")
        else:
            print(f"  MATCH    {label}  [{city}]  all checked fields correct")


# ---------------------------------------------------------------------------
# §3  RESERVATION CALENDAR
# ---------------------------------------------------------------------------
def check_reservation(cur):
    print(f"\n{THIN}")
    print("  §3  RESERVATION CALENDAR")
    print(f"{THIN}")

    # Total rows
    rows = q(cur, "SELECT COUNT(*) FROM reservation")
    n_res = rows[0][0]
    print(f"    Total reservation rows: {n_res}  (expected ~7260)")
    _match("reservation row-count", n_res, 7260, tol=50)

    # Date span
    rows = q(cur, """
SELECT
  TO_CHAR(MIN(blockeddatestart), 'YYYY-MM') AS min_start,
  TO_CHAR(MAX(blockeddataend),   'YYYY-MM') AS max_end
FROM reservation
""")
    min_s, max_e = rows[0][0], rows[0][1]
    span_ok = (min_s == "2023-01" and max_e == "2024-11")
    mark = "MATCH" if span_ok else "DRIFT"
    print(f"    {mark}  span: got={min_s}→{max_e}  expected=2023-01→2024-11")

    # cs_11 mechanism: Sep-2024 Lisbon exclusion → distinct 435→156
    rows = q(cur, """
SELECT COUNT(DISTINCT (r.loc_idhouse, r.idroom)) AS cnt
FROM room r
JOIN house h ON TRIM(h.idhouse) = TRIM(r.loc_idhouse) AND h.dateupdate = r.loc_dateupdate
WHERE r.status = 'Available' AND h.status = 'Validated' AND TRIM(h.city) = 'Lisbon'
  AND NOT EXISTS (
    SELECT 1 FROM reservation res
    WHERE TRIM(res.loc_idhouse) = TRIM(r.loc_idhouse)
      AND TRIM(res.idroom)      = TRIM(r.idroom)
      AND res.blockeddatestart <= '2024-09-30'
      AND res.blockeddataend   >= '2024-09-01'
  )
""")
    avail_sep24 = rows[0][0]
    _match("cs_11: Lisbon available Sep-2024", avail_sep24, 156, tol=2)

    # Check 2026 window yields 0 exclusions (sanity)
    rows = q(cur, """
SELECT COUNT(DISTINCT (r.loc_idhouse, r.idroom)) AS cnt
FROM room r
JOIN house h ON TRIM(h.idhouse) = TRIM(r.loc_idhouse) AND h.dateupdate = r.loc_dateupdate
WHERE r.status = 'Available' AND h.status = 'Validated' AND TRIM(h.city) = 'Lisbon'
  AND NOT EXISTS (
    SELECT 1 FROM reservation res
    WHERE TRIM(res.loc_idhouse) = TRIM(r.loc_idhouse)
      AND TRIM(res.idroom)      = TRIM(r.idroom)
      AND res.blockeddatestart <= '2026-09-30'
      AND res.blockeddataend   >= '2026-09-01'
  )
""")
    avail_2026 = rows[0][0]
    no_excl = (avail_2026 == 435)   # same as unfiltered distinct
    mark = "MATCH" if no_excl else "NOTE"
    print(f"    {mark}  2026-09 window: distinct={avail_2026}  "
          f"(expected 435 = no reservation exclusions in 2026)")


# ---------------------------------------------------------------------------
# §4  CORPUS PROVENANCE & THEME CHECK
# ---------------------------------------------------------------------------

# Review themes: keyword patterns to search in review.description (ILIKE)
_REV_IN_CORPUS = [
    ("cleanliness",         ["limpeza", "limpas", "limpo", "clean", "dirty", "higiene",
                              "cuidado", "sujo"]),
    ("wifi/internet",       ["wifi", "internet", "wi-fi", "conexão", "connection",
                              "velocidade", "speed", "signal"]),
    ("safety/CCTV",         ["security", "câmera", "cctv", "camera", "segurança",
                              "safe", "lock", "chave", "code", "entry", "entrada"]),
    ("natural light",       ["luz natural", "natural light", "luz", "light", "janela",
                              "window", "bright", "claro", "escuro", "dark"]),
    ("kitchen/washing machine", ["cozinha", "kitchen", "máquina de lavar", "washing machine",
                                  "lavar roupa", "electrodomésticos", "appliance"]),
    ("heating polarity",    ["aquecimento", "heating", "frio", "cold", "quente", "warm",
                              "temperatura", "temperature", "radiador", "radiator"]),
]

_REV_GAP = [
    ("wheelchair access",   ["cadeira de rodas", "wheelchair", "acessível", "accessible",
                              "ramp", "rampa", "mobility", "mobilidade"]),
    ("floor/lift",          ["andar", "floor", "lift", "elevator", "elevador", "escadas",
                              "stairs", "piso"]),
    ("party suitability",   ["party", "festa", "barulho", "noise", "vizinhos", "neighbours",
                              "social", "fiesta"]),
    ("building age",        ["renovado", "renovated", "antigo", "old", "moderno", "modern",
                              "construção", "built", "renovação"]),
]

# Description themes: keyword patterns in house/room description text
_DESC_IN_CORPUS = [
    ("room size/spacious",  ["m²", "sqm", "square", "espaçoso", "spacious", "área",
                              "área útil", "metros"]),
    ("desk/study setup",    ["secretária", "desk", "study", "trabalhar", "work", "mesa",
                              "escritório", "office"]),
    ("bathroom type",       ["casa de banho privada", "private bathroom", "en-suite",
                              "shared bathroom", "partilhada", "ensuite"]),
    ("balcony/outdoor",     ["varanda", "balcony", "terraço", "terrace", "jardim",
                              "garden", "exterior"]),
    ("furnished/wardrobe",  ["mobilado", "furnished", "roupeiro", "wardrobe", "cama",
                              "bed", "móveis", "furniture"]),
    ("heating/AC",          ["aquecimento", "heating", "ar condicionado", "air conditioning",
                              "AC", "A/C", "radiador", "radiator"]),
]

_DESC_GAP = [
    ("window orientation",  ["norte", "norte", "sul", "este", "oeste", "north", "south",
                              "east", "west", "compass"]),
    ("smell/damp",          ["cheiro", "smell", "odor", "húmido", "damp", "mold", "mofo",
                              "bolor", "musty"]),
    ("furniture condition", ["novo", "novo", "usado", "worn", "desgastado", "old furniture",
                              "state of", "condição dos móveis"]),
    ("named-univ distance", ["nova sbe", "carcavelos", "nova", "fcsh", "ist", "universidade",
                              "campus"]),
]


def _count_reviews_with_theme(cur, keywords: list[str]) -> int:
    """Count distinct reviews whose description contains any of the keywords."""
    like_clauses = " OR ".join(
        [f"LOWER(rv.description) LIKE %s" for _ in keywords]
    )
    params = [f"%{kw.lower()}%" for kw in keywords]
    rows = q(cur, f"""
SELECT COUNT(*) FROM review rv
WHERE rv.status = 'approved'
  AND ({like_clauses})
""", params)
    return int(rows[0][0])


def _count_desc_with_theme(cur, keywords: list[str], desc_col: str) -> int:
    """Count distinct house+room rows whose description column contains any keyword."""
    like_h = " OR ".join([f"LOWER(h.{desc_col}) LIKE %s" for _ in keywords])
    like_r = " OR ".join([f"LOWER(r.{desc_col}) LIKE %s" for _ in keywords])
    params = [f"%{kw.lower()}%" for kw in keywords] * 2
    try:
        rows = q(cur, f"""
SELECT COUNT(*) FROM (
  SELECT h.idhouse FROM house h
  WHERE h.status = 'Validated' AND h.{desc_col} IS NOT NULL
    AND ({like_h})
  UNION ALL
  SELECT r.loc_idhouse FROM room r
  JOIN house h ON TRIM(h.idhouse)=TRIM(r.loc_idhouse) AND h.dateupdate=r.loc_dateupdate
  WHERE r.status='Available' AND r.{desc_col} IS NOT NULL
    AND ({like_r})
) sub
""", params)
        return int(rows[0][0])
    except Exception as e:
        return -1   # column may not exist


def _find_desc_col(cur) -> str | None:
    """Find the text/description column in house table."""
    cur.execute("""
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name='house' ORDER BY ordinal_position
""")
    cols = cur.fetchall()
    candidates = [c[0] for c in cols
                  if any(x in c[0].lower()
                         for x in ("desc", "text", "about", "info", "detail", "notes"))]
    return candidates[0] if candidates else None


def check_corpus(cur):
    print(f"\n{THIN}")
    print("  §4  CORPUS PROVENANCE & THEME CHECK")
    print(f"{THIN}")

    # Total review rows in SQL
    rows = q(cur, "SELECT COUNT(*) FROM review WHERE status='approved'")
    n_rev = int(rows[0][0])
    rows2 = q(cur, "SELECT COUNT(DISTINCT TRIM(loc_idhouse)) FROM review WHERE status='approved'")
    n_rev_hse = int(rows2[0][0])
    print(f"    Approved reviews in SQL: {n_rev} rows, {n_rev_hse} distinct idhouses")

    # Detect description column
    desc_col = _find_desc_col(cur)
    print(f"    House/room description column: {desc_col!r}")

    print()
    print("  §4a  REVIEW THEMES (search review.description):")
    print(f"  {'Theme':<28}  {'SQL_hits':>9}  {'Status'}")
    print(f"  {'-'*28}  {'-'*9}  {'-'*20}")
    for theme, kws in _REV_IN_CORPUS:
        n = _count_reviews_with_theme(cur, kws)
        status = "still-covered" if n >= 1 else "NO-LONGER-COVERED"
        print(f"  {theme:<28}  {n:>9}  {status}")

    print()
    for theme, kws in [("heating polarity", ["aquecimento","heating","frio","cold",
                                              "quente","warm","temperatura","radiador"])]:
        n = _count_reviews_with_theme(cur, kws)
        status = "still-covered" if n >= 1 else "NO-LONGER-COVERED"
        print(f"  {'[polarity] '+theme:<28}  {n:>9}  {status}")

    print()
    print("  §4b  REVIEW GAP THEMES (should be absent or very sparse):")
    print(f"  {'Theme':<28}  {'SQL_hits':>9}  {'Status'}")
    print(f"  {'-'*28}  {'-'*9}  {'-'*20}")
    for theme, kws in _REV_GAP:
        n = _count_reviews_with_theme(cur, kws)
        # "gap" means sparse — threshold < 5% of reviews
        if n == 0:
            status = "still-absent"
        elif n < max(10, n_rev * 0.05):
            status = f"sparse ({n}/{n_rev}) — still-gap"
        else:
            status = f"PRESENT ({n}/{n_rev}) — gap-violated"
        print(f"  {theme:<28}  {n:>9}  {status}")

    if desc_col:
        print()
        print("  §4c  DESCRIPTION THEMES (search house/room description text):")
        print(f"  {'Theme':<28}  {'SQL_hits':>9}  {'Status'}")
        print(f"  {'-'*28}  {'-'*9}  {'-'*20}")
        for theme, kws in _DESC_IN_CORPUS:
            n = _count_desc_with_theme(cur, kws, desc_col)
            status = "still-covered" if n >= 1 else ("NO-LONGER-COVERED" if n == 0 else "ERR")
            print(f"  {theme:<28}  {n:>9}  {status}")

        print()
        print("  §4d  DESCRIPTION GAP THEMES:")
        print(f"  {'Theme':<28}  {'SQL_hits':>9}  {'Status'}")
        print(f"  {'-'*28}  {'-'*9}  {'-'*20}")
        for theme, kws in _DESC_GAP:
            n = _count_desc_with_theme(cur, kws, desc_col)
            if n == 0:
                status = "still-absent"
            elif n < 10:
                status = f"sparse ({n}) — still-gap"
            else:
                status = f"PRESENT ({n}) — gap-violated"
            print(f"  {theme:<28}  {n:>9}  {status}")

    # Provenance inference
    print()
    print("  §4e  PROVENANCE INFERENCE:")
    print("    The golden set notes cite 'DB 2026-06-19/22' for all structured")
    print("    counts. Pinecone is confirmed STALE (FIX 8: all 160 current SQL")
    print("    idhouses absent from both indexes). Since the data reference")
    print("    references SQL timestamps — not Pinecone vector counts — §G was")
    print("    almost certainly derived from SQL review/description text at the")
    print("    time the golden set was authored, not from Pinecone dumps.")
    print("    Corollary: if current SQL reviews share the same corpus authors")
    print("    (same DB regeneration batch), the themes should persist.")
    print("    If reviews were fully replaced during regeneration, theme")
    print("    coverage must be re-verified — see §4a–§4d above.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_env()

    print(f"\n{BAR}")
    print("  GATE — GOLDEN SET ALIGNMENT CHECK vs CURRENT SQL")
    print(f"  Read-only. No re-index. No submission.")
    print(f"{BAR}")

    db = conn()
    cur = db.cursor()

    check_counts(cur)
    check_anchors(cur)
    check_reservation(cur)
    check_corpus(cur)

    print(f"\n{BAR}")
    print("  VERDICT")
    print(f"{BAR}")
    print("  (see individual sections above for MATCH / DRIFT / MISSING details)")
    print("  Sections 1–3 determine structural alignment of counts and room data.")
    print("  Section 4 determines whether subjective cassettes survive re-index.")
    print(f"{BAR}\n")

    cur.close()
    db.close()

if __name__ == "__main__":
    main()
