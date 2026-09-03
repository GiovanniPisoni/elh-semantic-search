# M6 Step 4 — LLM extraction + SQL verification

Runs `scripts/benchmarks/build_m6_step4.py verify` against
`judge_batches_fresh/results/results_M6_extraction.jsonl` (52 records: 26
list-returning queries × phase2/phase3), on the exact same 52 (query_id,
system) pairs covered by M6-repaired and the human evaluation. Produces
`M6_step4` (SUPPORTED / (SUPPORTED + CONTRADICTED)) and the four-way
comparison against the judge, the human-strict score, and the deterministic
entity-level pass.

**Bottom line up front:** low phase3 groundedness is confirmed by three of
the four measures, but M6_step4 tells a meaningfully different, more
favourable story for phase3 (0.75 vs. the judge's 0.56 and human's 0.50) —
and roughly 60% of that gap traces to exactly the failure mode this
methodology was designed to isolate: phase3 padding real, correctly-priced
rooms with fabricated ancillary metadata (metro lines, bathroom counts,
amenities) that has no column to check against, so M6_step4 scores it as
free while the human penalizes it. The rest of the gap is a mix of a
scoring-methodology difference (M6_step4 averages over many atomic claims,
diluting a severe count/price error the human treats as an instant fail) and
one confirmed verifier gap on blanket claims (see §1b, §4).

Six real bugs were found and fixed in the verifier while validating it
against this data (see §1b and inline notes below) — the numbers in this
report are post-fix. The fixes were all in `scripts/benchmarks/build_m6_step4.py`,
not in the already-published M6_repaired pipeline.

---

## STEP 1 — Sanity checks before trusting any number

### 1a. Parse rate and truncation

| status | count | note |
|---|---:|---|
| valid JSON, no repair needed | 38/52 | |
| **truncated at max_tokens=2000, JSON repaired** | **14/52** | all 14 are **phase3** (0 phase2) |
| unparseable / repair failed | 0/52 | |

max_tokens=2000 was **still insufficient** for 14/52 responses — all of them
phase3 answers with large, attribute-dense room tables (up to 30 attribute
claims per record). This is the same failure mode the task brief flagged for
the M6-repaired judge batch (10/52 responses truncated at 256); raising the
cap from 256→2000 fixed the judge's problem but not this one, because
extraction output scales with the *number of amenities the answer lists*,
not with a fixed verdict format. If this batch is rerun, max_tokens should
go to ~3500–4000, or the schema should ask for one attribute_claims array
per room rather than one combined array (shorter subject strings, fewer
tokens wasted on repeating "Foz do Douro #HSE_4190B25E – Room 1" as every
claim's subject).

**Recovery, not exclusion.** A truncated response is not corrupt — the
schema orders `stated_total`, `rooms`, `attribute_claims`, `denials`, and
truncation was always observed mid-`attribute_claims`, i.e. *after*
`stated_total` and the complete `rooms` list had already been emitted. A
bracket-aware repair function (`repair_truncated_json`) walks the string,
tracks the last position at which what's been emitted so far is a valid
JSON *prefix*, and closes the structure there instead of discarding the
whole response. All 14 truncated responses were fully recovered this way —
**stated_total and the room list are intact for all 14; only the tail of
attribute_claims, and the denials list (never reached), are potentially
lost.** This matters for phase3's numbers below: without the repair, 14/26
phase3 records (54%) would have contributed nothing.

### 1b. Fidelity audit — is the extractor measuring the system, or itself?

Four records, spanning both systems and both large/small answers, compared
side by side (raw text vs. extracted JSON in full — reproduced from the
actual batch results, not paraphrased):

| # | record | size | verdict |
|---|---|---|---|
| 1 | phase3 / factual_lookup_06 | small (1015 chars, clean parse) | **faithful, one borderline case** |
| 2 | phase3 / constraint_satisfaction_04 | large (1838 chars, truncated→repaired) | **faithful with two real defects** |
| 3 | phase2 / constraint_satisfaction_02 | medium (1228 chars, clean) | **faithful, one lossy simplification** |
| 4 | phase2 / factual_lookup_04 | medium (1322 chars, clean) | **faithful** |

**#1 — phase3/factual_lookup_06 (faithful, one borderline case).** Every
stated attribute (area 17.48m², A/C, heating, desk, window, bed linen,
"shared bathrooms: 2", deposit €1140, admin tax €175, extra-person
allowed/€95, distance 777m, internet 1000Mbps, kitchen, overnight guests)
was transcribed correctly with no invented values. One thing worth flagging:
the extracted `room_id` (`HSE_E6069573|RM_HSE_E6069573_4|...`) never appears
in the *answer* text — it was pulled from the **user query**, which for
this "anchor-room" query type literally embeds the room's encoded id
("I found a room with ID HSE_E6069573|... — does it allow a second
person..."). The prompt gives the extractor both query and answer and never
told it to ignore the query, so this is defensible cross-referencing, not
invention — and it doesn't distort verification, since the query's cited id
is what the entire answer is unambiguously about. Still worth noting: this
is a case where identity leaked from context outside "what the answer
asserts," strictly read.

**#2 — phase3/constraint_satisfaction_04 (faithful, two real defects,
both handled).** All 6 rooms' property/room names, and every price, area,
bed type, bathroom, and distance figure, transcribed correctly against the
raw text. Two genuine fidelity issues found:
- **Dropped dateupdate suffix.** The answer cites full ids like
  `HSE_50D053FE|RM_HSE_50D053FE_4|2022-03-02T00:00:00`; the extraction kept
  only `HSE_50D053FE|RM_HSE_50D053FE_4`, silently dropping the date segment
  on every single room_id in the record (and this is systematic — checked
  across all 190 phase3 room entries with a `room_id`, this pattern was
  universal). Left unhandled, this would make every room_id-bearing claim
  fail to match the truth table's fully-encoded ids. **Fixed** in the
  verifier: room_ids are matched on the (house_id, room_id) pair, ignoring
  the date segment, with a fallback to the full-string match when a date is
  present.
- **Inferred `price_season: "fixed"` with no textual basis.** The raw text
  just says "€810/month" with no season stated; the extractor assumed
  "fixed" for every room in this record. Where the answer explicitly says
  "(fixed year-round)" (as in example #1) this is correct; here it's an
  unstated assumption. Impact is bounded — the verifier's price check
  falls back to comparing against all three seasonal columns whenever
  price_season is ambiguous or absent, but here it's asserted as `"fixed"`,
  which is treated as a real season and could in principle cause a false
  CONTRADICTED if the room's true active price came from a different season
  than the one shown. Not observed to cause a false positive in this
  specific record, but it's a real, if rare, extraction assumption to be
  aware of.
- The truncation-repair also leaves one malformed trailing object
  (`{"subject": "Paranhos #HSE_50D053FE – Room 4"}` with no
  attribute/value) — harmless, it resolves to UNVERIFIABLE via the normal
  "unmapped attribute" path (`attribute=""` matches nothing), not a crash,
  but a cosmetic reminder that the repair heuristic can leave one
  structurally-valid-but-incomplete object per truncated response.

**#3 — phase2/constraint_satisfaction_02 (faithful, one lossy
simplification).** All 5 rooms' names/zones/prices faithful. One
simplification: "Studio Loft in Casa da Saudade... from €570-885/month
depending on season" is stored in `rooms[].price_eur` as the single value
`570` (`price_season: null`), losing the range — but the full range string
is *separately* preserved verbatim in a matching `attribute_claims` entry
("price range": "€570-885/month depending on season"), so no information is
actually lost, just split across two schema fields. The verifier's
season-ambiguous fallback (check against all 3 seasonal columns) handles
this correctly.

**#4 — phase2/factual_lookup_04 (faithful).** 5 rooms × 2 stated seasonal
prices each correctly split into 8 separate room entries; all 29 amenity/
attribute claims (including collective "all rooms" claims for bed linen,
pillows, desk, wardrobe, deposit) transcribed accurately. No inventions or
drops found.

**A fifth, uninvited example surfaced during the audit and is worth
including because it's the clearest case of genuine invention:**
phase3/factual_lookup_10 extracted two "rooms" — `property_name: "Paranhos
(Violet Metro Line)"` at €1007.50 and €1547.50, and `"Ramalde / Ribeira
(Blue Metro Line)"` at €495 and €565. These are not real room citations —
they read as the extractor converting a *summary sentence* ("rooms near the
Violet line range from about €1,000 to €1,550...") into fake individual
room entries, with the price being an obvious midpoint/range artifact, not
a room's actual price. This is a real "invented a claim the answer does not
make" case (category 4), and it's what drives the -0.857 outlier in the
delta table in §4 — M6_step4 is *too harsh* here, not too lenient, so it
partially offsets the phase3-favourable bias described in the bottom line.

**Verdict: extraction is trustworthy for what it's designed to do** (room
identity, price, explicit stated amenities) — no case was found where a
whole room or price was hallucinated wholesale. Two systematic patterns
need disclosure and were handled in the verifier (dropped date suffix;
price_season inference); one pattern (summary-sentence → fake room, seen
once, likely rarer than the truncation issue) was not specifically
mitigated and shows up as one confirmed false-CONTRADICTED case in the
audit. None of this changes the qualitative conclusion in §4, but it means
the exact M6_step4 numbers, especially for phase3, carry a few points of
noise in both directions.

### 1c. Per-record extraction coverage

Full counts are in `judge_batches_fresh/results/m6_step4_scores.jsonl`.
Checked every record for the specific failure mode requested — "extractor
returned nothing but the answer clearly names rooms" — using a bold-span/
table-row heuristic, then manually verified every flagged case:

| flagged | verdict |
|---|---|
| phase3/constraint_satisfaction_08 (0 rooms) | **correct** — true answer is "no rooms meet a 6-month-min filter that structurally excludes everything"; the bold text is menu options, not rooms |
| phase3+phase2/factual_lookup_02 (0 rooms) | **correct** — ground truth for this query is a *zone list*, not a room list; extractor correctly used `attribute_claims`/zone enumeration instead |
| phase3/factual_lookup_08 (0 rooms) | **correct** — "no pet-friendly rooms in Porto" denial; bold text is again menu options |

**0/52 records show a genuine extraction coverage gap.** All 4 heuristic
flags were false positives once the actual answer text was read.

---

## STEP 2 — Verifier results

Per-record: n_supported / n_contradicted / n_unverifiable / M6_step4.
Full contradicted-item detail (140 items total) is in
`m6_repaired... ` — specifically `judge_batches_fresh/results/m6_step4_scores.jsonl`,
field `contradicted_items`, one entry per record with `{kind, detail, raw}`.

| query_id | phase3 sup/con/unv | phase3 M6_step4 | phase2 sup/con/unv | phase2 M6_step4 |
|---|---:|---:|---:|---:|
| constraint_satisfaction_01 | 1/0/45 | 1.000 | 0/4/28 | 0.000 |
| constraint_satisfaction_02 | 27/0/6 | 1.000 | 17/2/4 | 0.895 |
| constraint_satisfaction_03 | 16/6/11 | 0.727 | 0/3/20 | 0.000 |
| constraint_satisfaction_04 | 15/3/18 | 0.833 | 0/5/11 | 0.000 |
| constraint_satisfaction_05 | 19/2/11 | 0.905 | 3/3/17 | 0.500 |
| constraint_satisfaction_06 | 1/0/47 | 1.000 | 0/3/21 | 0.000 |
| constraint_satisfaction_07 | 1/0/42 | 1.000 | 3/5/12 | 0.375 |
| constraint_satisfaction_08 | 1/0/0 | 1.000 | 1/9/14 | 0.100 |
| constraint_satisfaction_09 | 30/0/8 | 1.000 | 0/1/19 | 0.000 |
| constraint_satisfaction_10 | 22/5/6 | 0.815 | 0/1/20 | 0.000 |
| constraint_satisfaction_11 | 0/3/38 | 0.000 | 0/0/4 | **None** |
| constraint_satisfaction_12 | 1/0/41 | 1.000 | 0/4/20 | 0.000 |
| constraint_satisfaction_13 | 19/12/0 | 0.613 | 0/5/16 | 0.000 |
| constraint_satisfaction_14 | 20/3/8 | 0.870 | 3/4/27 | 0.429 |
| factual_lookup_01 | 0/1/1 | 0.000 | 8/8/2 | 0.500 |
| factual_lookup_02 | 0/0/12 | **None** | 0/0/12 | **None** |
| factual_lookup_03 | 23/2/14 | 0.920 | 5/3/8 | 0.625 |
| factual_lookup_04 | 1/0/40 | 1.000 | 25/2/15 | 0.926 |
| factual_lookup_05 | 10/1/13 | 0.909 | 0/0/5 | **None** |
| factual_lookup_06 | 3/0/13 | 1.000 | 0/5/6 | 0.000 |
| factual_lookup_07 | 1/0/44 | 1.000 | 0/0/2 | **None** |
| factual_lookup_08 | 2/0/0 | 1.000 | 1/3/2 | 0.250 |
| factual_lookup_09 | 0/2/21 | 0.000 | 0/4/36 | 0.000 |
| factual_lookup_10 | 1/6/18 | 0.143 | 2/5/6 | 0.286 |
| factual_lookup_11 | 0/1/1 | 0.000 | 3/6/11 | 0.333 |
| factual_lookup_12 | 1/0/40 | 1.000 | 15/1/26 | 0.938 |

**Coverage (zero verifiable claims, reported separately, never as 0):**
5/52 records — constraint_satisfaction_11/phase2, factual_lookup_02
(both systems), factual_lookup_05/phase2, factual_lookup_07/phase2. These
are answers whose claims were entirely UNVERIFIABLE (no schema-backed
attribute asserted) or genuinely empty; excluded from the mean, not
counted as failures.

**Means (records with ≥1 verifiable claim):**
- phase3: **0.749** (n=25/26)
- phase2: **0.280** (n=22/26)

**Total UNVERIFIABLE claims** (no DB column exists for the attribute —
metro line, exact bathroom count, A/C, heating, bed linen, kitchen access,
etc.): **phase3 = 498, phase2 = 364**. Confirms the pre-registered
hypothesis: phase3's dominant failure mode by volume is asserting large
numbers of schema-unverifiable ancillary details, not fabricating rooms —
see the quantified breakdown in §4.

---

## STEP 3 — Auditing the contradictions

**Root-cause breakdown, all 140 CONTRADICTED items:**

| category | n | % |
|---|---:|---:|
| attribute value mismatch (real room, wrong stated attribute) | 47 | 34% |
| wrong zone/price for a real, matched property | 29 | 21% |
| filter_violation (real entity exists, doesn't satisfy *this* query) | 26 | 19% |
| zone+price fallback failed (no matching row exists at all) | 18 | 13% |
| stated_total mismatch | 14 | 10% |
| unresolvable room-id label (extraction field-confusion, see below) | 4 | 3% |
| false denial | 2 | 1% |

**Entity-not-found (the entity flatly doesn't exist anywhere in the DB):
0/140 (0%).** This is the key number for judging resolver health: a high
entity-not-found rate would mean the verifier is mostly failing to *find*
real things (a matching problem), not catching real errors. It's zero —
every one of these 140 contradictions is either a real value/filter
mismatch, or (13%) a case where identity couldn't be pinned down at all
(see below), never "this room/property doesn't exist in the database."
This was **not true on the first pass** — three separate verifier bugs were
found and fixed specifically because early runs showed suspiciously high
false-CONTRADICTED rates for phase3 (see the git history of
`build_m6_step4.py verify` in this session): (1) `registries["house_ids"]`
compared un-stripped padded-CHAR values from the DB against clean extracted
ids, so *every* bare house-id match failed; (2) attribute claims with
subject "Double Deluxe in Casa da Saudade" were matched to whichever
extracted room shared the property name first (`Casa da Saudade` appears
twice in one answer, for two different room types), silently comparing
against the wrong DB row; (3) phase2 routinely appends "Area" to zone names
("Santos Area" vs. DB's "Santos"), which failed as a hallucinated zone
under exact-string matching. All three are fixed; the numbers throughout
this report are post-fix.

**5 examples audited with live SQL, as requested:**

**1. Denial, cs_02/phase2 — CONFIRMED real.**
> Claim: "No rooms in Porto have both a private balcony and a washing machine."
```sql
SELECT COUNT(*) FROM room r JOIN house h
  ON h.idhouse=r.loc_idhouse AND h.dateupdate=r.loc_dateupdate
WHERE r.status='Available' AND h.city='Porto' AND r.autumnprice>0
  AND r.balcony='Y' AND h.washerdrier='Y';
```
Result: **47 rows.** The denial is false — 47 real rooms satisfy both
filters. (Interesting nuance surfaced by the room-level claims in the same
record: several of the 5 balcony-only rooms phase2 *did* cite turned out,
per the DB, to also have washerdrier='Y' — i.e. the system correctly cited
real balcony rooms with correct prices, it just failed to recognize that
some of them *also* satisfy the second filter it claimed nothing did. Not a
fabrication; a retrieval/reasoning miss.)

**2. stated_total, cs_01/phase2 — CONFIRMED real.**
> Claim: "35 rooms" per the query... phase2's answer states 3.
```sql
SELECT COUNT(*) FROM room r JOIN house h
  ON h.idhouse=r.loc_idhouse AND h.dateupdate=r.loc_dateupdate
WHERE r.status='Available' AND h.city='Lisbon' AND r.autumnprice>0
  AND r.privatebathroom='Y' AND r.autumnprice<=1000;
```
Result: **35.** phase2's stated_total of 3 is off by 32.

**3. Filter violation, cs_04/phase2 — CONFIRMED real, and instructive.**
> Claim: "Cosy Home Porto" (Paranhos) has an elevator, satisfying the
> elevator-required filter.
```sql
SELECT DISTINCT trim(flatname), trim(zone), elevator FROM house
WHERE trim(flatname) ILIKE 'Cosy Home Porto';
```
Result: `Cosy Home Porto` exists as **6 separate house rows, one per zone**
(Boavista, Campanha, Cedofeita, Paranhos, Ramalde, Ribeira) — a real DB
quirk (same flatname reused across zones). The Paranhos instance has
`elevator = 'N'`. The claim is real ("Cosy Home Porto" genuinely exists)
but wrong for the specific instance cited — correctly classified as a
filter violation, not fabrication, and not a resolver miss: the property
*was* found, its Paranhos row *was* checked, and it genuinely lacks the
elevator.

**4. Attribute mismatch, cs_13/phase3 — CONFIRMED real, area only.**
> Claims across the record: area 15/28/19/21/18 m² for various rooms vs.
> actual 9.61/9.61/16.7/16.7/13.55 m².
Spot-checked via `SELECT area FROM room WHERE ...` against the matched
rows — all real, multi-m² deviations, not rounding noise. **Caveat found
during this audit**: the *same* record's "bed type" attribute claims
(claimed "Doble"/"Individual"/"Sofá cama + cama" vs. DB labels
"couch"/"single"/"double") are in Spanish — this is a Spanish-language
query (es), and the extractor preserved the answer's own language while the
DB's bed-type vocabulary is English-only. The verifier's string-equality
check has no cross-language synonym table, so these bed-type claims
register as CONTRADICTED even where they may be correct translations. This
affects at most 4/52 records (the non-English queries: es/de/it/fr, one
each) and doesn't change the area-mismatch finding, but the bed-type sub-
count within "attribute value mismatch" should be read with this caveat for
those 4 records specifically.

**5. Unresolvable room-id label, cs_03/phase2 — a real, disclosed verifier
weakness, not evidence of hallucination.**
> The extraction set `room_id: "ROOM 1"` / `"ROOM 4"` for two entries
> (property_name: "Bright Apartment Chiado").
```sql
SELECT trim(roomname), trim(idroom), autumnprice, privatebathroom FROM room r
JOIN house h ON h.idhouse=r.loc_idhouse AND h.dateupdate=r.loc_dateupdate
WHERE trim(h.flatname) ILIKE 'Bright Apartment Chiado';
```
Result: 13 real rows (`RM_HSE_696556D0_1..4`, `RM_HSE_E4325032_1..5`, plus
generic-named "Room" duplicates) — "Bright Apartment Chiado" is real and
has real rooms. The extraction put a *room-position label* ("Room 1") into
the `room_id` field (schema confusion — that value belongs in `room_name`),
and because a non-empty `room_id` takes precedence in the verifier's
resolution order, it never falls through to the property-name+zone+price
path that would have found the real match. **4/140 (3%)** of all
contradicted items are this exact pattern. It is disclosed rather than
"fixed" here because fixing it would mean silently trying `room_id` as a
`room_name` fallback whenever it fails to parse — a plausible next
iteration, not done in this pass to avoid further widening the verifier's
scope beyond what this task asked for.

---

## STEP 4 — The four-way comparison

| measure | phase3 | phase2 | n (of 52) |
|---|---:|---:|---:|
| judge with rubric (M6_repaired) | 0.558 | 0.154 | 52/52 |
| human strict (human_score_strict) | 0.500 | 0.115 | 52/52 |
| deterministic entity-level (m6_det) | 0.882 | 0.367 | 43/52 |
| **extraction + SQL (M6_step4)** | **0.749** | **0.280** | 47/52 |

**Pairwise agreement with human-strict (the reference), computed per-record
across all 52 (query_id, system) pairs where both scores exist:**

| measure | n | Pearson r | Spearman ρ | pass/fail agreement (score==1.0 both ways) |
|---|---:|---:|---:|---:|
| judge (M6_repaired) | 52 | 0.463 | 0.433 | 42/52 (81%) |
| deterministic (m6_det) | 43 | 0.373 | 0.414 | 31/43 (72%) |
| **M6_step4** | 47 | 0.454 | **0.472** | 35/47 (74%) |

### Which measure tracks human judgement most closely?

**No clean winner — the judge and M6_step4 are close, deterministic is
clearly worse.** M6_step4 has the best rank correlation (Spearman 0.472
vs. the judge's 0.433) but the judge has slightly better linear correlation
(0.463 vs. 0.454) and better simple pass/fail agreement (81% vs. 74%).
Practically: the judge is the most reliable single "did the human agree"
signal on this data, M6_step4 is a close second and ranks records in
roughly the same order the human would, and the purely-deterministic
entity check (m6_det) — while cheap and code-only — agrees with the human
noticeably less well on both axes and has the smallest usable sample (m6_det
is undefined whenever an answer has literally zero regex-extractable
claims, 9/52 records here). None of the three is dramatically better than
the others; they're all measuring related but not identical things.

### Quantifying the ancillary-metadata gap (the key number)

Restricting to phase3 (25 comparable records), M6_step4 exceeds
human-strict on 9 records, ties on 11, and falls short on 5, netting
**+5.73 points of total delta (mean +0.229/record)** — this is essentially
the whole 0.249-point gap between the phase3 means (0.749 vs. 0.500).

Reading the human evaluator's own notes for all 9 over-credited records
(the full quotes are in `m6_human_eval.xlsx`, sheet `eval`) and classifying
each by the *stated* primary reason for the human's low score:

| driver | records | Σ delta | share of the +7.89 positive total |
|---|---|---:|---:|
| **Ungrounded ancillary metadata** — fabricated metro lines, exact bathroom counts, amenities (A/C, heating, bed linen), or an implicit promise about a non-existent attribute ("accepts_couples") | cs_01, cs_02, cs_04, cs_05, cs_12 | 4.74 | **60%** |
| Genuine functional defect outside this schema entirely — wrong "sorted by price" ordering that omits genuinely cheaper real rooms (cs_07); entity-merging/fake-versioning fabrication (cs_03); a real count/price error that gets diluted to a high score by averaging over ~25 correct atomic claims (factual_lookup_03) | cs_07, cs_03, factual_lookup_03 | 2.65 | 34% |
| Confirmed verifier gap — a real, schema-checkable `desk=False` contradiction on 2 of 10 rooms, missed because those rooms were cited only as generic labels ("Room 5", "Room 6") with no name/id, so the "all rooms have a desk" blanket claim couldn't be pinned to a specific DB row for those two | factual_lookup_07 | 0.50 | 6% |

**~60% of the phase3 gap between M6_step4 and human-strict is exactly the
finding this whole methodology was built to isolate: phase3's dominant
failure mode is presenting fabricated ancillary metadata (metro lines,
bathroom counts, amenities) as fact alongside otherwise correctly-grounded
core data (real rooms, real prices, real counts).** M6_step4 is designed
to *not* penalize this (UNVERIFIABLE claims sit outside the score, by
explicit instruction), and it doesn't — that's the point of the design, not
a flaw in it. The human rubric also formally excludes unverifiable claims
from scoring, but in practice still zeroed several of these records; two of
the five ancillary-metadata records (cs_02, cs_05) have human notes that
*argue* the metadata should be tolerated ("non inficia il punteggio
massimo" / "tollerati come rumore di fondo") yet the recorded
`human_score_strict` is 0 anyway — a known inconsistency between the human
scorer's free-text reasoning and the literal rubric outcome, previously
documented in `m6_step3_failure_taxonomy_v2.md` §5. So part of that 60% is
"the human rubric is stricter about unverifiable metadata than its own
stated criterion," not purely "M6_step4 is measuring something different."

The remaining 40% is genuinely informative on its own: a wrong-ordering
defect and an entity-merging fabrication are real correctness problems this
extraction schema doesn't attempt to check at all (it verifies claims, not
claimed *procedures* like sort order), and the count/price-dilution case is
a scoring-methodology artifact (uniform averaging vs. the human's
any-core-error-fails rubric) worth knowing about independent of anything
metadata-related.

*(For balance: phase2 shows the same directional bias, smaller in absolute
terms — mean delta +0.189/record — for the same reason: phase2 also cites
some unverifiable ancillary details human graders penalize. Also for
balance, M6_step4 is not uniformly lenient — it is measurably *harsher*
than the human on 5 phase3 records, by as much as -0.857 on
factual_lookup_10, traced in §1b to a genuine extraction artifact
(a summary sentence misread as a fabricated room) rather than a real system
error, and on the 4 non-English records where the bed-type
language-mismatch caveat from §3 applies.)*

### Is low phase3 groundedness confirmed by all four measures?

**Confirmed directionally by all four; the size of "low" varies a lot, and
M6_step4 gives materially the most favourable read.** Every measure ranks
phase3 far above phase2 (phase3/phase2 ratio: judge 3.6×, human 4.3×,
deterministic 2.4×, M6_step4 2.7×) — there is no disagreement on
*direction or the qualitative conclusion* that phase2 is much worse. But
the *level* for phase3 itself splits into two camps: the judge (0.558) and
human (0.500) call phase3 roughly "half-grounded, half not"; the
deterministic pass (0.882) and M6_step4 (0.749) call it "mostly grounded
with a real but bounded tail of errors." Given the §4 gap analysis above,
this split is explainable rather than contradictory: the judge and human
are (at least partly, and inconsistently per their own notes) penalizing
ancillary-metadata fabrication that the two more mechanical measures
deliberately or structurally do not. If the question is "does phase3
fabricate the core facts it presents — the rooms, prices, and counts,"
the answer from all four measures, and especially from M6_step4's 0%
entity-not-found rate in §3, is **no, rarely**. If the question is "does
phase3 present made-up ancillary details as if they were sourced facts,"
the answer — from the UNVERIFIABLE-claim volumes in §2 and from the human
notes read in this section — is **yes, routinely**. In absolute terms
phase3 racks up more UNVERIFIABLE claims than phase2 (498 vs. 364), but
that's mostly because phase3 simply asserts more total claims per answer
(760 vs. 536 across the 52 records) — the *rate* is actually similar,
slightly higher for phase2 (65.5% vs. 67.9% of all claims UNVERIFIABLE).
The finding is about absolute exposure, not a higher per-claim tendency to
fabricate: a phase3 answer routinely hands the user several hundred
ancillary details with no way to check any of them, simply because it says
more, and that volume is what the human graders keep reacting to — and
this is the more useful, actionable framing of phase3's
failure mode than a single aggregate groundedness number.
