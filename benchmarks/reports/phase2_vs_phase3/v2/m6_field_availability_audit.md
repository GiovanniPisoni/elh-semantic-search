# M6 field-availability audit — does "no column in the database" hold up?

Read-only audit (schema files + local DB `SELECT`s against the project's own
dev Postgres via `DB_URI`; no LLM/API calls). Triggered by the report's and
the human-eval rubric's claim that heating, air conditioning, wardrobe, room
area, desk, bathroom type "have no column in the database" and are therefore
UNVERIFIABLE. That claim is **false as stated** — the columns exist — but the
real picture has three independent layers that the report collapsed into
one, and untangling them changes the verdict on ~90 previously-dismissed
claims and on two human-eval records that currently score a perfect 1.0.

**Bottom line up front:**
- The room table has 37 columns (not 38 — see §1), and it does carry
  `heating`, `airconditioning`, `closet`, `bedlinen`, `pillows`, `haswindow`,
  `desk`, `area`, `privatebathroom`. The schema claim is wrong.
- The **truth tables** built for M6 never fetch those columns (§2) — that part
  of the report's premise is actually correct, just mislabeled: it's an
  omission in *our instrument*, not an absence in the *database*.
- **`get_property_details` returns every one of them** to the model (§3). But
  it was called on **1 of the 26** M6 list-returning queries. `find_rooms` /
  `find_available_rooms` — the tools that actually answered these 26 queries —
  never return them as structured fields (`amenities=[]` is a hard-coded
  stub); they leak through only via a truncated 200-character text excerpt
  that mentions them roughly half the time at best (§3.3).
- Fixing the verifier's column map and re-running it against the live DB
  reclassifies **89 of the 862** UNVERIFIABLE claims (31 phase2, 58 phase3):
  74 turn out SUPPORTED, but **15 turn out CONTRADICTED** — real, DB-provable
  fabrications that were previously invisible to every scoring method (§4b).
  *(Corrected after this report's first pass: an air-conditioning keyword
  match on the bare token `" ac "` degenerated into a substring test after
  normalization and false-matched "machine," mis-scoring one washing-machine
  claim as an air-conditioning check — see `m6_step4_corrected.md` §B.2 for
  the full account. Fixed by requiring `"ac"` to match as its own word; the
  numbers here are post-fix.)*
- Verdict on (c): **our error** — the claims were checkable and we wrongly
  excluded them, not a case of "the tools never showed the model this, so it
  doesn't matter." Checkability is a DB-verification question, independent of
  what a specific tool call happened to return (§4c).
- Two human-eval records (`constraint_satisfaction_09`, `factual_lookup_05`,
  both phase3) carry a `human_score_strict = 1.0` that a newly-surfaced,
  DB-confirmed CONTRADICTED claim should have knocked down. Correcting just
  these two moves phase3's headline `human_score_strict` from 0.500 to
  ≈0.442 (§4d).

---

## 1 — IN SCHEMA

Source: `DB/our-development-DB/schema_public.sql` (the project's own frozen
schema dump, one directory up from `elh-semantic-search`).

### `room` — 37 columns (verified by parsing the `CREATE TABLE` block; the
brief that triggered this audit said 38 — off by one, corrected here)

```
loc_idhouse            singlebed              doublebed
kingbed                queenbed               couchbed
secondbed              area                   privatebathroom
balcony                desk                   closet
heating                haswindow              bedlinen
pillows                airconditioning        fixedprice
springprice            summerprice            autumnprice
extrapersonallowed     extrapersoncost        lastmonthdeposit
deposit                depositvalue           administrativetax
roomname               description            status
idroom                 datevalidation         dateinsert
dateupdate             username               own_username
loc_dateupdate
```

Every field named in the brief as "no column" is here: `heating`,
`airconditioning`, `closet` (= wardrobe), `desk`, `area`, `privatebathroom`
(= bathroom type), plus two more in the same family the brief's "etc."
implied: `bedlinen`, `pillows`, `haswindow`.

### `house` — 56 columns (same method)

Includes, among others: `centralheating`, `airconditioning` (house-level,
distinct from the room-level column), `balcony`, `cctv`, `codeentry`,
`security24h`, `smokedetector`, `armoreddoor`, `elevator`,
`reducedmobilityaccess`, `parking`, `thermalinsulation`,
`doubleglazedwindows`, `kitchenequipment`, `fridge`, `microwaveoven`,
`gaselectricstove`, `dishwasher`, `washerdrier`, `internet`, `cabletv`,
`smarttv`, `cityview`, `fieldview`, `seaview`, `sharedspace`, `furnished`,
`bathroom` (count), `area`, `internetspeed`, `allownightguests`,
`allowpets`, `smokingallowed`, `genreirrelevant`, `otherameneties`,
plus identity/PII/audit columns (`address`, `floor`, `buildingnumber`,
`fraction`, `postalcode`, `username`, `date*`) correctly never surfaced to
the model.

**Fact 1 verdict:** every field named in the brief IS a real column. Confirmed
by parsing the schema file directly, not by trusting the report.

---

## 2 — IN TRUTH TABLE

Source: `benchmarks/runs/phase2_vs_phase3/v2/judge_batches_fresh/m6_repair_truth_tables.json`
(26 entries, one per list-returning query), each room entry shaped as:

```json
{
  "room_id": "...", "house_id": "...", "flatname": "...", "roomname": "...",
  "city": "...", "zone": "...", "neighborhood": "...",
  "price_eur": 990.0, "spring_price": 745.0, "summer_price": 680.0,
  "fixed_price": false, "area_m2": 12.77, "bed_type": "queen",
  "deposit": false, "deposit_value": 930.0,
  "attrs": {
    "private_bathroom": true, "balcony": false, "desk": true,
    "min_reserve_months": null, "extra_person_allowed": true,
    "extra_person_cost": 55.0, "elevator": false,
    "distance_to_transport_m": "961.86", "female_preferred": false,
    "male_preferred": false, "internet": true, "furnished": true,
    "allow_pets": false, "washer_drier": true
  }
}
```

Aggregating every key that appears in *any* of the 26 tables' room entries
(`rooms`/`rooms_full`, 35 rooms in the example above) gives exactly this set
— confirmed by scanning all 26 tables, not just one:

- **top-level:** `room_id, house_id, flatname, roomname, city, zone, neighborhood, price_eur, spring_price, summer_price, fixed_price, area_m2, bed_type, deposit, deposit_value`
- **`attrs`:** `private_bathroom, balcony, desk, min_reserve_months, extra_person_allowed, extra_person_cost, elevator, distance_to_transport_m, female_preferred, male_preferred, internet, furnished, allow_pets, washer_drier`

**`heating`, `airconditioning`, `closet`, `bedlinen`, `pillows`, `haswindow`
never appear — not once, in any of the 26 tables.** `area_m2` and `desk` DO
appear (both already checkable, contradicting the brief on those two
specifically — see §4a).

Root cause, found in `scripts/benchmarks/build_m6_repair.py`:

```python
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
```

This `SELECT` — the one query that builds the ground truth for all 26
records — simply never lists `r.heating`, `r.airconditioning`, `r.closet`,
`r.bedlinen`, `r.pillows`, `r.haswindow`, or any of the ~25 unfetched `house`
amenity columns. **This part of the report is correct**: the truth table
genuinely doesn't carry these fields. The report's error was equating "not in
our truth table" with "no column in the database" — the fix is a five-minute
edit to `ROOM_LIST_COLUMNS`, not a schema limitation.

---

## 3 — IN THE AGENT'S CONTEXT

This is the fact that actually decides whether a claim is *grounded* — a tool
returning a field to the model is what could make the model's assertion
about it non-arbitrary. Read directly from the frozen tool code.

### 3.1 `find_rooms` / `find_available_rooms` (share `RoomMatch`)

`src/elh_rag/tools/find_rooms/_schemas.py` — `RoomMatch.to_dict()` returns:

```
room_id, house_id, house_name, city, zone, neighborhood,
price_per_month_eur, price_label, private_bathroom,
distance_to_transport_m, nearest_metro_line, available_from,
min_reserve_months, amenities, excerpt, match_score, is_fixed_price
```

Of the fields under audit, only **`private_bathroom`** is a real, always-
populated structured field here. Everything else is absent, and not because
of a missing DB column — `_sql_builder.py::_row_to_match` **hard-codes**:

```python
amenities=[],  # Future: collect 'Y' columns into a list
```

`_build_sql` also `SELECT`s `r.haswindow` (needed only to build the `WHERE`
clause when `must_have_window` is set) but `_row_to_match` never reads it —
the value is fetched and silently discarded. So `heating`, `air
conditioning`, `closet`, `bedlinen`, `pillows`, `haswindow`, `desk`, `area`
are **structurally impossible** for the model to see through `find_rooms` /
`find_available_rooms`, regardless of what the DB contains. This is the one
part of the report's framing that lands on the right practical conclusion
for the wrong stated reason.

### 3.2 `get_property_details`

`src/elh_rag/tools/get_property_details/_property_details.py` builds
`RoomDetails.amenities` from:

```python
_ROOM_AMENITY_COLUMNS = (
    ("privatebathroom", "Private bathroom"), ("balcony", "Balcony"),
    ("desk", "Desk"), ("closet", "Closet"), ("heating", "Heating"),
    ("haswindow", "Has window"), ("bedlinen", "Bed linen provided"),
    ("pillows", "Pillows provided"), ("airconditioning", "Air conditioning"),
)
```

...plus `area_sqm` (from `room.area`), `bed_types` (from the six bed-flag
columns), and `HouseDetails.amenities` from 27 house-level columns including
`centralheating` and `airconditioning`. **Every single field named in the
brief is returned here**, as human-readable labels, when the column is `'Y'`.

### 3.3 But `get_property_details` was barely used in this evaluation

Cross-referencing `tool_trace` / `tools_used` in
`benchmarks/runs/phase2_vs_phase3/v2/phase3_eval_v2_fresh.jsonl` for the
26 query_ids in scope: **`get_property_details` was called on exactly 1 of
26 phase3 records** (`factual_lookup_06`, a question about extra-person cost,
unrelated to heating/AC). Phase2 has no per-tool trace field at all (it's the
RAG pipeline, not the agent). So for the actual 52 records scored, this
fully-exposing tool essentially never fired.

### 3.4 The channel that actually carries these fields — and usually loses them

`find_rooms` does select `r.description` and truncates it into `excerpt =
description[:200]`. A live query shows `room.description` is a **generated
field that encodes the structured Y/N columns almost perfectly**:

| column | Y rows mentioning it in `description` | N rows mentioning it |
|---|---|---|
| `heating` | 677/677 | 0/255 |
| `closet` (wardrobe) | 874/874 | 0/58 |
| `desk` | 821/821 | 0/111 |
| `bedlinen` | 894/894 | 0/38 |
| `pillows` | 878/878 (of a 60-sample: 59/60) | 0/54 |
| `haswindow` | 913/913 (sample: 53/60) | 0/19 |
| `airconditioning` | 421/421 present when Y (sample: 34/60), 0/511 when N | |

So the description text is truthful relative to the columns. But `excerpt`
keeps only the **first 200 characters**, and template position varies by
attribute (random 60-row samples, DB-measured):

| attribute | mentioned within first 200 chars |
|---|---|
| `closet`/wardrobe | 31/60 (~52%) |
| `desk` | 36/60 (~60%) |
| `haswindow` | 20/60 (~33%) |
| `airconditioning` | 2/60 (~3%) |
| `bedlinen` | 9/60 (~15%) |
| `pillows` | 9/60 (~15%) |

**Fact 3 verdict:** `get_property_details` fully exposes every audited
field but was invoked once in 52 records. `find_rooms`/`find_available_rooms`
never expose them as structured data, and the one text channel that could
(`excerpt`) is truncated away most of the time — reliably for closet/desk
(coin flip), almost never for A/C/bed-linen/pillows. A claim about
heating/AC in one of these 52 answers is very likely ungrounded in what the
model actually saw — **which is a separate question from whether it's
checkable against the DB**, addressed next.

---

## 4 — Consequences, quantified

All numbers below come from re-running
`scripts/benchmarks/build_m6_step4.py` (`verify` mode) against the existing
`results/results_M6_extraction.jsonl` (already-completed LLM extractions —
no new LLM calls were made) plus live, read-only `SELECT`s against the same
dev Postgres the rest of the M6 pipeline already uses. Baseline reproduction
matched the committed `m6_extraction_SQL_scores.jsonl` exactly (phase2 mean
0.280/n=22, phase3 mean 0.749/n=25, 364+498=862 unverifiable) before any
correction was applied.

### 4a — The exact attribute→column map, and what's misclassified

`ATTRIBUTE_RESOLVERS` in `build_m6_step4.py` (verbatim, abridged to the
keyword lists):

```
["shared bathroom"]                          -> attrs.private_bathroom (inverted)
["private bathroom","ensuite","en-suite",
 "own bathroom"]                             -> attrs.private_bathroom
["balcony"]                                  -> attrs.balcony
["desk"]                                     -> attrs.desk
["elevator","lift"]                          -> attrs.elevator
["internet","wifi","wi-fi"]                  -> attrs.internet
["furnished"]                                -> attrs.furnished
["pet"]                                      -> attrs.allow_pets
["washer","dryer","laundry machine"]         -> attrs.washer_drier
["female"]                                   -> attrs.female_preferred
["male"]                                     -> attrs.male_preferred
["deposit value","deposit amount"]           -> deposit_value
["deposit"]                                  -> deposit
["area","m2","sqm","square met"]             -> area_m2
["distance to","transport distance",...]     -> attrs.distance_to_transport_m
["minimum stay","min reserve",...]           -> attrs.min_reserve_months
["extra person cost",...]                    -> attrs.extra_person_cost
["extra person","extra guest",...]           -> attrs.extra_person_allowed
["bed type","bed size"]                      -> bed_type
["zone","neighborhood","neighbourhood",
 "district"]                                 -> zone
```

with the comment directly above it:

> "Anything NOT matched here has no column in the schema and is UNVERIFIABLE
> by design (e.g. metro line, bathroom count, air conditioning, heating, bed
> linen, kitchen access, view, floor number, photos, review sentiment)."

That comment is the exact false claim. `desk` and `area` are already in the
map above (so the brief overstates the problem for those two specifically —
see the caveat at the end of this section). `heating`, `air conditioning`,
`closet`/wardrobe, `bed linen`, `pillows`, `haswindow`/window are **not** in
the map, and — per §2 — the underlying getter (`r["attrs"][...]`) wouldn't
exist even if a keyword were added, because the truth table never fetches
those columns either. Fixing this needs both a resolver entry *and* a live
DB fetch (done in §4b).

Classifying every UNVERIFIABLE-because-unmapped **attribute claim** (462 of
943 total attribute claims, extracted from the real `results_M6_extraction.jsonl`)
by what it's actually asking about:

| group | total | phase2 | phase3 | in schema? |
|---|--:|--:|--:|---|
| bathroom (bare "bathroom"/"bathrooms"/underscore/Spanish forms) | 81 | 18 | 63 | yes — `privatebathroom`, already-mapped keyword just doesn't match bare/underscore/non-English forms |
| room size ("size"/"room size", not "area") | 65 | 5 | 60 | yes — `area`, same keyword-phrasing gap |
| wardrobe/closet | 48 | 34 | 14 | yes — `closet` |
| heating | 43 | 29 | 14 | yes — `heating` |
| metro/transit | 33 | 7 | 26 | no column (derived from zone via a lookup table), but *is* returned to the model as `nearest_metro_line` |
| air conditioning | 33 | 22 | 11 | yes — `airconditioning` (room and/or house) |
| window / natural light | 24 | 15 | 9 | yes — `haswindow` |
| bed linen | 24 | 15 | 9 | yes — `bedlinen` |
| pillows | 5 | 2 | 3 | yes — `pillows` |
| other (price sub-fields, bed_type/bed bare forms, washing machine, second-person phrasing, overnight guests, admin tax, "amenities", "accepts couples", landmark proximity, ...) | 106 | 59 | 47 | mixed — see note below |

The first eight rows (**356 of the 462** unmapped attribute claims — 130
phase2, 226 phase3) name a field that unambiguously **is** a real column.
The "other" bucket is a mix: genuinely uncheckable claims (`accepts couples`
— confirmed absent from the schema; `find_rooms/tool.py` itself logs
`"ignored — column not present in the ELH schema"` for this exact input),
generic/ambiguous claims ("amenities", "location", "storage"), and further
real-but-differently-phrased columns this audit did not attempt to fix
(price fields, bare `bed_type`/`bed`, `distance_to_transport` written with
an underscore, "washing machine" instead of "washer", `allownightguests`,
`administrativetax`, computed `rooms_total`) — flagged here as further
instrument gaps but out of scope for the rescoring in §4b, which targets only
the eight fields named or implied by the original brief.

**Caveat on the brief's own premise:** `desk`, `area` ("area"/"m2"/"sqm"
phrasing), and private/shared **bathroom** (when phrased as "private
bathroom"/"shared bathroom", not bare "bathroom") were *already* correctly
resolved by the unmodified verifier — they are not in the unmapped-462 set at
all. The rubric text used for the human evaluation (`m6_human_eval.xlsx`,
`rubric` sheet, quoted verbatim) also never lists desk, area, or bathroom
type as unverifiable — its "Fields NOT captured" note names only *"heating/AC,
closet, window, cable TV, specific views, exact floor/building number,
photos, review sentiment"*. So the brief's inclusion of desk/area/bathroom-type
overstates what was actually excluded by name; the reason `bathroom`/`size`
claims still ended up UNVERIFIABLE in practice is a separate, narrower bug —
the keyword list requiring the exact phrase "private bathroom"/"shared
bathroom"/"area" rather than the bare or underscore forms the LLM extraction
actually produced.

### 4b — Corrected re-run

Extended `ATTRIBUTE_RESOLVERS` with `heating`, `air_conditioning` (room OR
house column), `closet`, `bedlinen`, `pillows`, `haswindow`, plus
bare/underscore-tolerant matching for `bathroom` and `size`/`room size` —
fetching the extra room/house columns live, per matched room, from the DB
(76 distinct rooms were resolved as SUPPORTED room-identity matches across
the 52 records). Original resolvers are tried first and unchanged, so
nothing already-correct regresses (verified: 0 regressions on any
previously-SUPPORTED/CONTRADICTED claim across all 52 records).

| | M6_step4 mean (per-record) | pooled SUPPORTED/(SUP+CON) | n unverifiable |
|---|---|---|---|
| phase2 baseline | 0.280 | 86/172 = 0.500 | 364 |
| phase2 corrected | **0.307** | 116/203 = **0.571** | 333 |
| phase3 baseline | 0.749 | 215/262 = 0.821 | 498 |
| phase3 corrected | **0.740** | 259/320 = **0.809** | 440 |

**89 attribute claims move out of UNVERIFIABLE** (31 phase2: 30 SUPPORTED +
1 CONTRADICTED; 58 phase3: 44 SUPPORTED + 14 CONTRADICTED). The
phase2↔phase3 M6_step4 gap narrows from 0.469 to 0.433 — modest, but the
direction matters: phase2's score only goes up (it gains SUPPORTED claims
and loses almost none), while phase3's score is dragged down by the 14
newly-surfaced CONTRADICTED claims, exactly the "ungrounded ancillary
metadata" pattern the existing report (`m6_extraction_sql.md`) already
flagged as ~60% of the phase3/human gap — this shows that pattern is *worse*
than "harmless padding with no column to check": some of it is DB-provably
false. (`m6_step4_corrected.md` §B.4 decomposes this further: checkability
alone only closes ~9% of that gap — most of the effect is ungrounded-but-
often-right guessing, not fabrication.)

The 15 newly-CONTRADICTED claims (previously invisible to every scoring
method — judge, human, and M6_step4 alike):

```
[phase3] constraint_satisfaction_03: bed linen: claimed=yes, actual=False
[phase3] constraint_satisfaction_04: air conditioning: claimed=yes, actual=False
[phase3] constraint_satisfaction_05 (x2): room size claimed 17m2/28m2, actual 11.37/11.8
[phase3] constraint_satisfaction_05: bathroom: claimed=Private, actual=shared
[phase3] constraint_satisfaction_09: bathroom: claimed=shared, actual=private
[phase3] factual_lookup_03 (x7): room size claims off by 3-9 m2 against the matched row
[phase2] factual_lookup_04: "bed linen included" (blanket) — false for 2/8 verified rooms
[phase3] factual_lookup_05: "wardrobe" (blanket) — false for 1/5 verified rooms
```

(A "washing machine" blanket claim in constraint_satisfaction_02 was
reported as a 16th CONTRADICTED claim in this report's first pass — it was
wrong. See `m6_step4_corrected.md` §B.2 for the bug and the fix; "washing
machine" phrasing is not resolved by this pass and correctly stays
UNVERIFIABLE.)

(One caveat: these ride on the pre-existing room-identity matcher
(`verify_room_claim`), unchanged by this fix — the same matcher already
underlies all 862 baseline UNVERIFIABLE/SUPPORTED/CONTRADICTED calls, so
this carries the same identity-matching precision as the rest of the M6_step4
pipeline, no more and no less.)

### 4c — Which of the two is true

**The first: the fields were verifiable and we wrongly excluded them — our
error.** Evidence: §1 confirms the columns exist; §4b DB-verifies 89 of the
462 unmapped claims with zero regressions, 15 of them CONTRADICTED. A claim's
checkability against the DB does not depend on which tool happened to run —
M6_step4's entire design is to catch a system asserting something the *DB*
disproves, regardless of what excuse the system might have for asserting it.

The tool-exposure finding in §3 is real and adds something the pure
schema/truth-table facts don't: it explains *why* these claims are common
and *why* they're often plausible-sounding half-truths rather than random
noise (§3.4 — the model has plausibly seen a truncated, boilerplate-adjacent
version of the truth, or is pattern-matching on a high base rate — e.g.
closet='Y' for 874/932 rooms, so guessing "yes" is usually right and wrong
here specifically). But that explains the *mechanism* of the errors, not
whether they should count. It does not make case two ("the tools never
expose them, so ungrounded regardless of schema") the operative reason for
exclusion — get_property_details *does* expose every one of them, and even
where a tool genuinely never returns a field, "ungrounded" is an argument for
scoring it as suspect (closer to CONTRADICTED-leaning or at least penalised),
not for exempting it from verification entirely as this pipeline did.

### 4d — Human-eval impact

The rubric actually shown to the human evaluator (`m6_human_eval.xlsx`,
sheet `rubric`, quoted verbatim) states:

> "Fields NOT captured in this table (heating/AC, closet, window, cable TV,
> specific views, exact floor/building number, photos, review sentiment, and
> any amenity not listed in the columns below) are UNVERIFIABLE — their
> presence in the answer is neither confirmed nor denied by this table. Do
> not treat a mention of them as fabrication."

**All 52 of the 52 human-eval records** were scored under this instruction
(single rubric sheet, applied uniformly, confirmed by reading the sheet
directly — not a subset).

Cross-referencing the 7 (query_id, system) pairs that contain at least one of
the 15 newly-CONTRADICTED claims from §4b against `m6_human_eval.xlsx`'s
`human_score_strict` (the column the companion taxonomy report,
`m6_failure_taxonomy_v2.md`, states is the one actually used for headline
numbers):

| query_id / system | human_score_strict | newly-confirmed contradiction |
|---|---|---|
| constraint_satisfaction_09 / phase3 | **1.0** | bathroom type wrong (claimed shared, is private) |
| factual_lookup_05 / phase3 | **1.0** | wardrobe claim false for 1/5 rooms (+ a pre-existing, already-checkable metro-distance claim also missed) |
| constraint_satisfaction_03 / phase3 | 0.0 | bed linen claim false (already a fail) |
| constraint_satisfaction_04 / phase3 | 0.0 | air conditioning claim false (already a fail — this evaluator's own note *independently* calls out "invents A/C, heating... (none in any column)", correctly flagging the fabrication while still repeating the false "no column" premise) |
| constraint_satisfaction_05 / phase3 | 0.0 | room size + bathroom type wrong (already a fail) |
| factual_lookup_03 / phase3 | 0.0 | room size wrong x7 (already a fail) |
| factual_lookup_04 / phase2 | 0.0 | bed linen claim false (already a fail) |

**2 of the 7 (`constraint_satisfaction_09`, `factual_lookup_05`, both
phase3) currently carry a perfect `human_score_strict = 1.0` that a
DB-confirmed CONTRADICTED claim should have prevented** — i.e., the human
scores on these two records are too generous, not because the human judged
badly, but because the instructions they were following told them to
disregard exactly the claim that turns out to be false. Applying the
rubric's own scoring bands with the new evidence: `constraint_satisfaction_09`
has exactly one new CONTRADICTED claim → 1.0 → 0.5; `factual_lookup_05` has
that one plus a second, already-checkable-at-baseline metro-distance
CONTRADICTED claim the evaluator also missed → 1.0 → 0.0.

Effect on phase3's headline `human_score_strict` (currently 0.500 over 26
records, per `m6_extraction_sql.md`): dropping 1.0+1.0 to 0.5+0.0 moves the
total from 13.0/26 to 11.5/26 → **0.500 → 0.442**, an ~11.6% relative
decrease. Phase2's headline (0.115) is unaffected — its one flagged record
(`factual_lookup_04`) was already scored 0.

This is a lower bound, not an exhaustive re-audit: it only checks the 7
records that happened to surface a newly-CONTRADICTED claim from the
targeted 8-field fix in §4b, against the ~120 further candidate claims noted
in §4a that were not rescored here (price sub-fields, bed type, distance-to-
transport, metro line, washing machine, overnight guests). A full re-score
of all 52 `human_score_strict = 1.0` records against a fully corrected
verifier is the natural next step and would very plausibly move the number
further.

---

## Files touched / referenced

- Read-only: `DB/our-development-DB/schema_public.sql`,
  `benchmarks/runs/phase2_vs_phase3/v2/judge_batches_fresh/m6_repair_truth_tables.json`,
  `scripts/benchmarks/build_m6_repair.py`, `scripts/benchmarks/build_m6_step4.py`,
  `src/elh_rag/tools/find_rooms/*`, `src/elh_rag/tools/find_available_rooms/*`,
  `src/elh_rag/tools/get_property_details/*`,
  `benchmarks/runs/phase2_vs_phase3/v2/phase{2,3}_eval_v2_fresh.jsonl`,
  `benchmarks/reports/phase2_vs_phase3/v2/m6_human_eval.xlsx`,
  `benchmarks/runs/phase2_vs_phase3/v2/judge_batches_fresh/results/m6_extraction_SQL_scores.jsonl`.
- DB: live, read-only `SELECT`s against the dev Postgres (`DB_URI` in `.env`) —
  column value counts, description-text correlation checks, and a live fetch
  of the 9 extra columns for the 76 rooms resolved as SUPPORTED across the 52
  records. No writes.
- No changes were made to `scripts/benchmarks/build_m6_step4.py` or any other
  committed file; the corrected resolver was implemented in a standalone
  scratch script for this audit and is not part of the repo.
