# M6 Step 3 REDO — failure taxonomy on the corrected human scores

Read-only analysis. **Supersedes `m6_failure_taxonomy.md` (v1 — originally
written as `m6_step3_failure_taxonomy.md`, since renamed), which is kept on
disk unmodified.** The gap between the two versions is itself documentation of why a
measurement instrument has to be validated before its output is trusted: v1's
own conclusion — "6 of phase3's 14 failures are instrument artefacts, true
failure rate ~31%, not 54%" — turns out to not survive a second, stricter pass
on the same evidence. See §4 for the full account.

## 0. Why this redo, and what changed

v1 was written against `human_score` as it stood before two instrument defects
in the human-eval workbook were fixed: the 40-row cap on rendered truth tables,
and the renderer stripping `room_id`/`neighborhood`/`house_id`/and most `attrs`
columns. v1 used the *pre-fix* scores and inferred, by manually checking the
raw JSON, that 6 of phase3's 14 failures were probably instrument artefacts.

Since then: (a) `m6_rescore_full_columns.xlsx` blind-re-scored the 7
query_ids most implicated (14 records: both systems, paired) against the
COMPLETE truth table — every row, every column, no omissions; (b) the human
then reconciled that re-score into two explicit rubric interpretations on the
full 52-record workbook: `human_score_strict` (the rubric applied literally —
an attribute absent from the truth table is UNVERIFIABLE, therefore ignored,
never counted as either support or contradiction) and `human_score_lenient` (a
later, informally-applied tolerance criterion — introduced mid-way through
re-scoring and not applied retroactively to every record — that excuses
specific fabricated-but-plausible-sounding metadata, e.g. metro-line colours,
as harmless "enrichment"). The judge never saw the lenient criterion; it was
invented during human re-scoring. **This taxonomy runs on `human_score_strict`
only**, per instruction. Lenient values are reported where relevant but do not
drive any conclusion.

Sanity check against the supplied reference values:

| system | strict mean (computed) | reference | fail count (strict<1.0) | fail rate |
|---|---:|---:|---:|---:|
| phase2 | 0.115 | 0.115 | 23 / 26 | 88.5% |
| phase3 | 0.500 | 0.500 | 14 / 26 | 53.8% |

Both match exactly. Note the fail *counts* per system are numerically the same
as v1's (23 phase2 / 14 phase3) — but this is coincidence, not stability: the
underlying set of *which* (query_id, system) pairs fails under strict is
**identical, record-for-record**, to v1's original 37-record failing set (see
§4 — verified directly, not assumed). What changed between v1 and v2 is not
which records fail, but *why* several of them fail and whether that "why" is
the system's fault or the instrument's.

## 1. Per-record table (37 records, human_score_strict < 1.0)

Cause codes: A wrong_association, B fabricated_value (a specific, checkable-
sounding fact — price, amenity, metro line, bathroom count, review text —
asserted with confidence but absent from every column of the truth table), C
fabricated_entity, D wrong_count, E partial_as_total (a subset misrepresented
as exhaustive, correctly ordered, or otherwise mischaracterized), F
false_absence (denies/contradicts a value the truth table actually carries), G
unverifiable_detail (not a failure — attribute genuinely outside the table,
correctly treated as neutral), H instrument_artefact. `retrieval_ok` = Y if
the system's core cited facts (count and/or the specific prices/entities/
attributes it commits to) match real truth-table rows; N if they don't.

| query_id | system | strict | judge | primary | other | retrieval_ok | evidence |
|---|---|---:|---:|---|---|:---:|---|
| constraint_satisfaction_01 | phase2 | 0.0 | 0.0 | D | B,C | N | claims 3 rooms (true 35); cited house/zone/price/deposit combos don't exist |
| constraint_satisfaction_01 | phase3 | 0.0 | 0.5 | B | — | Y | count/zone/neighbourhood/price/size/distance all correct; invents a "Metro Line" column (Green/Blue) for 7/10 rows, absent from every DB field |
| constraint_satisfaction_02 | phase2 | 0.0 | 0.0 | F | D | Y | denies washer_drier=True on 5 real, correctly-priced rooms; claims 0 vs true 47 |
| constraint_satisfaction_02 | phase3 | 0.0 | 1.0 | B | — | Y | count/house_id/zone-neighbourhood/price/bathroom/distance/area all verified correct; invents Metro Line colours (Blue/Violet/Orange) not in the DB |
| constraint_satisfaction_03 | phase2 | 0.0 | 0.0 | B | — | Y | count/order/zone-neighbourhood/size/distance/bed-type all correct; invents Metro Line colours (Green/Blue) — geographically plausible in the real world, but not a DB field, so ungrounded under the rubric |
| constraint_satisfaction_03 | phase3 | 0.0 | 0.5 | A | B | Y | count/price/size/distance/bed-type/private_bathroom/house_id all correct; presents 2 distinct real rooms (HSE_1D470764) as "older"/"newer version" of one, and fuses another 2-room pair into one price range; also invents bathroom-share counts, metro colours, and a fake review sentence |
| constraint_satisfaction_04 | phase2 | 0.0 | 0.0 | D | C,F | N | claims 1 property (true 29 across 6 real properties); denies elevator=True though all 29 rows carry it; invents descriptive text and false exclusion reasons |
| constraint_satisfaction_04 | phase3 | 0.0 | 0.5 | B | — | Y | count/real-timestamped-IDs/price/size/distance/bath-type all correct; invents A/C, heating, windows, bed-linen, exact bathroom-share counts (none in any column); self-contradicts on metro line (states "yellow line D" in the intro, "blue"/"violet" in the bullets) |
| constraint_satisfaction_05 | phase2 | 0.0 | 0.0 | D | E | Y | claims 2 rooms (true 78); one cited room (#HSE_0CC1B91F_8) is real with correct price/size/deposit; also self-contradicts by excluding a €700 room from a stated €500–700 range |
| constraint_satisfaction_05 | phase3 | 0.0 | 0.5 | B | — | Y | count/house_id/zone-neighbourhood/price all correct; invents exact shared-bathroom counts and metro-line colours |
| constraint_satisfaction_06 | phase2 | 0.0 | 0.0 | D | C | N | claims 2 rooms (true 64); cited house/zone/price combos don't exist for those zones; self-contradicts on the distance criterion |
| constraint_satisfaction_07 | phase2 | 0.0 | 0.0 | D | F | Y | claims 5 rooms (true 42); denies female_preferred=True though all 42 rows carry it; the 5 example rooms cited are themselves real |
| constraint_satisfaction_07 | phase3 | 0.0 | 1.0 | E | B | Y | count/filters/attribute sample/zone-neighbourhood all correct; but claims the list is "top 10 sorted by price" when the internal order is broken (990 before 970/1005) and far cheaper real rows (545–665) are skipped for pricier ones (up to 1,630); adds a fabricated "(Blue line)" tag on top |
| constraint_satisfaction_08 | phase2 | 0.0 | 0.0 | C | — | N | truth table structurally returns 0 rows; correctly says so, then fabricates 5 specific rooms/prices/sizes wholesale |
| constraint_satisfaction_09 | phase2 | 0.0 | 0.5 | D | E | Y | claims 2 rooms fit (true 41); the 2 recommended rooms are real (balcony=True); frames 3 more as "above budget," implying only 5 rooms exist when many more valid rooms exist in other neighbourhoods |
| constraint_satisfaction_10 | phase2 | 0.0 | 0.5 | D | B | Y | claims 2 options (true 27); the 2 shown are real (private_bathroom=True); states Casa Verde Economy Room costs €1,160 autumn (real: €580), wrongly excluding a valid cheap match |
| constraint_satisfaction_11 | phase2 | 0.0 | 1.0 | F* | — | N | declines citing no availability data (true 156, net of 279 active reservations); *unresolved whether the agent ever had a real reservation-check tool — flagged, not confirmed (carried over from v1 §4/§5, still unresolved) |
| constraint_satisfaction_11 | phase3 | 0.0 | 0.0 | D | E | N | claims 556 (unfiltered city inventory) vs true 156; lists rooms that are actually occupied on the queried date — bypasses the reservation-exclusion mechanism entirely |
| constraint_satisfaction_12 | phase2 | 0.0 | 0.0 | B | — | N | fabricates a "Room in Cosy Home Lisbon (Santos)" combo absent from the table; treats €1,180 as "within" a stated €1,100 budget; invents `accepts_couples`, a non-existent DB column |
| constraint_satisfaction_12 | phase3 | 0.0 | 0.5 | B | — | Y | count (63) correct; asserts `accepts_couples` — a non-existent DB column — as a satisfied filter, and recommends a single bed for a couple (self-contradictory) |
| constraint_satisfaction_13 | phase2 | 0.0 | 0.0 | F | — | N | denies existence of all 27 matching rooms; denies internet=True though it is the literal filter criterion for every one of them |
| constraint_satisfaction_14 | phase2 | 0.0 | 0.0 | B | C | Y | real entity (Bright Apartment Arroios) given fabricated seasonal prices (claims 1290/1010/910 vs real 1050/775/675) and a fake fixed price; Residencia Santos given 2 wholly fictitious room variants (2 real ones exist, at different prices) |
| factual_lookup_01 | phase2 | 0.0 | 0.0 | D | C | N | claims 5 rooms (true 556); falsely claims all rooms sit under one property name, contradicted by numerous other visible properties |
| factual_lookup_01 | phase3 | 0.0 | 0.0 | D | — | N | bare unsupported claim of 435 rooms (true 556), no grounding given |
| factual_lookup_02 | phase3 | 0.0 | 0.0 | E | D,C | N | lists only 5 of 9 real zones as if exhaustive, and fabricates a fake nested hierarchy (zones-inside-zones) that the flat zone_enum truth table does not contain at all; total also off (376 vs 375) |
| factual_lookup_03 | phase2 | 0.0 | 0.0 | C | — | N | fabricates "Cosy Double in Cosy Home Porto (Ramalde)" (only Single Standard exists there); 1 of 2 cited rooms is real |
| factual_lookup_03 | phase3 | 0.0 | 0.0 | D | B | Y | 23 vs true 20 (outside tolerance); one fabricated €-20 price; 7 of the other cited prices are real |
| factual_lookup_04 | phase2 | 0.0 | 0.0 | D | C | Y | implies only 5 rooms (true 188); fabricates a "Cosy Home Lisbon — Room" combo at Santos and misplaces Residencia Benfica's real zone; 2 of the cited rooms are verified real |
| factual_lookup_05 | phase2 | 0.0 | 1.0 | F | — | N | declines citing missing metro-line data though the DB returns 203 real matches; tool-usage failure, not fabrication (judge disagreement carried over — see §5) |
| factual_lookup_06 | phase2 | 0.0 | 0.0 | C | — | N | fails the literal anchor-room-ID lookup; invents 5 alternative rooms with fully fictitious extra-person fees, none matching the real €95 |
| factual_lookup_07 | phase2 | 0.0 | 0.0 | F | C | N | denies female_preferred=True despite all 92 rows carrying it; cites 5 decontextualized/fabricated "sources" unrepresentative of the real inventory |
| factual_lookup_07 | phase3 | 0.5 | 0.5 | F | — | Y | count/prices/sizes/bed-bath types/the Anjos-Campo de Ourique zone-neighbourhood pair all correct; contradicts desk=False on 2 of the cited rooms (€540, €560) by claiming "all rooms include a study desk"; generic "Room 1/Room 2" labelling (omitting real flatname/house_id) is an omission, not a false claim, so not separately penalized under strict |
| factual_lookup_09 | phase2 | 0.0 | 0.0 | B | — | N | query targets a non-filterable field (m²); hallucinates a filtered result instead of stating the limitation |
| factual_lookup_09 | phase3 | 0.0 | 0.5 | D | B | N | same non-filterable field; invents a total (556) and 2 fully specific example rooms — directly against the ground-truth note that explicitly forbids fabricating a room list here |
| factual_lookup_10 | phase2 | 0.0 | 0.0 | D | C | N | claims 1 option (true 169); names a single fabricated-context property, ignoring all 169 real rows |
| factual_lookup_11 | phase2 | 0.0 | 0.0 | D | — | Y | claims 5 rooms (true 375); the 5 cited room/price combos are verified real |
| factual_lookup_11 | phase3 | 0.5 | 0.0 | D | — | N | invents an aggregate total (295 vs true 375); no other specific data offered to validate |

## 2. Cause frequency per system (primary cause, strict)

| cause | phase2 (n=23) | phase3 (n=14) |
|---|---:|---:|
| D — WRONG_COUNT | 11 (48%) | 5 (36%) |
| F — FALSE_ABSENCE | 5 (22%) | 1 (7%) |
| B — FABRICATED_VALUE | 4 (17%) | 5 (36%) |
| C — FABRICATED_ENTITY | 3 (13%) | 0 |
| E — PARTIAL_AS_TOTAL | 0 | 2 (14%) |
| A — WRONG_ASSOCIATION | 0 | 1 (7%) |
| H — INSTRUMENT_ARTEFACT | 0 | 0 |

Phase2's profile is essentially unchanged from v1: undercounting/misreading
scope (D) and denying the very attribute the query asked about (F) still
dominate, with a handful of entities fabricated from nothing (C). **Phase3's
profile has fundamentally changed from v1.** In v1, phase3's largest bucket by
far was H (43%, "instrument artefact") — under strict scoring that bucket is
now **zero**. In its place, phase3's dominant failure is now B — a
consistent, systematic pattern of inventing specific, confident-sounding
ancillary facts (metro-line colours, exact bathroom-share counts, amenities
like A/C or bed linen, even fabricated review sentences) that are absent from
every column of the truth table — tied with D (wrong count/total) at 36%
each.

## 3. The key number — correct retrieval vs. broken retrieval (genuine failures only)

Since **zero** records are excluded as confirmed artefacts (§4), this split
now runs over the full 37-record failing set, unmodified — there is no
"excluding H" adjustment to make.

| system | retrieval_ok = Y (fetched/grounded the right core data, mis-stated or mis-supplemented it) | retrieval_ok = N (retrieval itself wrong) |
|---|---:|---:|
| phase2 (n=23) | 10/23 (43%) | 13/23 (57%) |
| phase3 (n=14) | 9/14 (64%) | 5/14 (36%) |

These numbers are close to v1's *raw, uncorrected* figures (v1 §3: phase2
36%, phase3 64% before any H-adjustment) — which makes sense now that no
records are being pulled out as artefacts. **The interpretation is different
from v1, though.** v1 read phase3's 64% as partly an artefact of a broken
instrument. This redo shows phase3's 64% retrieval_ok=Y is genuine: phase3
really does fetch and correctly ground its core numeric/entity data (counts,
IDs, prices, zone/neighbourhood pairs) most of the time when it fails — its
failure mode is not "wrong data," it's confidently supplementing correct
retrieved data with specific invented details the retrieval never returned.
Phase2, unchanged from v1, is architecturally different: more than half its
failures (57%) are retrieval itself being wrong — mistaking a small retrieved
window for the whole database, or denying an attribute that's on every single
retrieved row.

## 4. INSTRUMENT_ARTEFACT (H) — corrected count: 0 of 7 candidates survive strict scoring

v1 named 6 confirmed-H records (constraint_satisfaction_01/02/04/05/07 phase3,
factual_lookup_07 phase3), all traced to one renderer defect: the Step-1
workbook hid `room_id`/`neighborhood` (and, it later turned out, `house_id`,
`area_m2`, `bed_type`, `deposit(_value)`, and every `attrs` key outside that
query's narrow `relevant_attrs` list). A later pass (documented in
`m6_rescore_full_columns_diff.md`) added a 7th candidate on the same grounds:
constraint_satisfaction_03 phase3, whose "invented ID codes" claim was also
verified false against the raw JSON.

**What actually happened to all 7, traced through both correction stages:**

| query_id | v1 human (pre-fix) | blind re-score, complete columns (`m6_rescore_full_columns.xlsx`) | final `human_score_strict` | net |
|---|---:|---:|---:|---|
| constraint_satisfaction_01 phase3 | 0.0 | 0.0 (still fails — a *different* real defect: fabricated metro lines) | 0.0 | **not confirmed** |
| constraint_satisfaction_02 phase3 | 0.0 | **1.0** (raised — room_id/neighbourhood claim cleared) | **0.0** (strict rubric reverts it — same fabricated-metro-line defect the blind re-scorer had informally excused) | **not confirmed** |
| constraint_satisfaction_03 phase3 | 0.0 | 0.0 (still fails — versioning/fusion hallucination is real, independent of the ID claim) | 0.0 | **not confirmed** |
| constraint_satisfaction_04 phase3 | 0.0 | 0.0 (still fails — fabricated amenities + self-contradictory metro line) | 0.0 | **not confirmed** |
| constraint_satisfaction_05 phase3 | 0.0 | **1.0** (raised) | **0.0** (reverted, same reason as cs_02) | **not confirmed** |
| constraint_satisfaction_07 phase3 | 0.0 | 0.0 (still fails — false "sorted, cheapest 10" claim, a real ordering/selection defect) | 0.0 | **not confirmed** |
| factual_lookup_07 phase3 | 0.5 | 0.0 ("moved the other way" — the complete `desk` column revealed a genuine, previously-invisible contradiction) | **0.5** (strict gives partial credit: the desk contradiction is real and penalized, but the generic-label naming complaint that drove the 0.0 blind-rescore verdict is not, under a literal reading, a false claim) | **net unchanged from v1, different reason** |

**Corrected artefact count: 0 of 7.** Two records (cs_02, cs_05 phase3) *were*
genuinely raised to 1.0 by the complete-data blind re-score — that part of
the process worked exactly as intended, and the original room_id/neighbourhood
complaint against them is definitively retracted; it was never real. But a
second, independent defect was sitting underneath both answers the whole
time — invented Metro Line data, asserted with the same unqualified
confidence as the real data next to it — and the blind re-scorer tolerated it
under an informal "enrichment" allowance that the strict rubric does not
grant (an absent field is UNVERIFIABLE only if the answer doesn't assert a
specific value for it; asserting "Blue line" for a room the DB is silent on
is not unverifiable, it's an unsupported factual claim). Applying the rubric
literally reverts both to 0.0. `factual_lookup_07` phase3 is the clearest
illustration that the artefact story was doing real work in v1: it was
counted as one of the "6 confirmed," but the complete data shows its true
score was always going to land at 0.5, for a defect (`desk=False` denied) that
the *original*, capped/column-stripped workbook could never have shown the
human in the first place, because `desk` wasn't in that query's
`relevant_attrs`.

**Confirmed genuine full artefacts across the entire 52-record set (any
record where the pre-fix v1 score was <1.0 and `human_score_strict` is now
1.0): zero.** Checked directly — see §0; the failing set is record-for-record
identical between v1 and this redo. Every record v1 called a failure is still
a failure under strict scoring, and vice versa; only the *causes* moved.

## 5. Notes written under the lenient criterion — where they point one way and strict scores another

Per instruction, note text is evidence of *content only*; the score is
`human_score_strict`. 4 records have `change_reason = "BOTH -> review
manually"` — meaning strict and lenient actually disagree on the final score
and both needed a manual call. All 4 use lenient-tolerance language
("tollerato", "arricchimento", "nuove regole"/"nuove istruzioni"/"nuove linee
guida") that argues in a different direction than the strict score lands:

| query_id / system | note's implied direction (lenient reading) | human_score_strict | divergence |
|---|---|---:|---|
| constraint_satisfaction_02 phase3 | "non inficia il punteggio massimo" → argues for 1.0 | 0.0 | note argues 1.0, strict says 0.0 |
| constraint_satisfaction_03 phase2 | "mantenendo il punteggio a 1.0" → argues for 1.0 | 0.0 | note argues 1.0, strict says 0.0 |
| constraint_satisfaction_05 phase3 | "non vi sono contraddizioni dirette sui requisiti principali" → argues for 1.0 | 0.0 | note argues 1.0, strict says 0.0 |
| factual_lookup_07 phase3 | "esattamente come nel caso precedente" (referring to cs_07 phase3, scored 0.0 for the same naming pattern) → argues for 0.0 | 0.5 | note argues 0.0, strict says 0.5 |

4 further records use the same lenient-tolerance vocabulary but strict and
lenient happen to *agree* on the final score anyway (0.0 either way, because
an independent defect fails the record regardless of how the tolerated detail
is treated) — flagged here for completeness since the instruction asks to
scan by phrase, not just by `change_reason`: constraint_satisfaction_01
phase3, constraint_satisfaction_03 phase3, constraint_satisfaction_04 phase3,
constraint_satisfaction_07 phase3. In these 4, the lenient-flavoured language
describes only *part* of the record's problems (typically the metro-line
issue), while a separate, more serious defect (fabricated amenities, a
versioning hallucination, a false "sorted" claim) fails it either way — so
the note's tolerant framing doesn't actually change the bottom line here, it
just risks being misread as more forgiving than the final score is.

## 6. Cross-check — carried over from v1, re-verified against current data

1. **constraint_satisfaction_11 phase2** — still unresolved (v1 §4/§5): the
   query asks about actual reservation-date availability, computed by the
   harness via a direct SQL join the agent may never have had tool access to.
   Neither system shows behaviour consistent with a real "check reservation"
   tool. Not re-examined further in this redo; still flagged, not resolved.
2. **factual_lookup_05 phase2** — human strict 0.0 (declines, citing missing
   metro-line data), judge 1.0 (calls the decline appropriately humble). This
   redo sides with the human, same as v1: the ground truth's own 203-match
   figure implies a well-defined zone→metro-line mapping the agent could
   plausibly have applied; declining reads as an under-used capability, not
   appropriate caution.
3. Two of v1's other judge-disagreement entries (cs_01/cs_02/cs_05/cs_07
   phase3, factual_lookup_07 phase3 — v1 §5 items 1–4, 6) are now moot: the
   human's original *reasoning* in each case has already been superseded by
   the corrected notes in §1/§4 above, so there is nothing further to
   reconcile — the strict score already reflects the corrected read.

## 7. Verdict — scenario 1 vs scenario 2, corrected magnitude

**The number that decides this: what fraction of phase3's measured deficit
survives after removing confirmed instrument artefacts. Answer: all of it.
100%, not 69% (v1's implied figure: 8/26 → 14/26 is v1's own math, i.e. v1
claimed roughly 43% of the *phase3 failure count* was artefact, or
equivalently that ~31% of the true failure rate, not the reported 54%, was
real). Zero of phase3's 14 strict failures are confirmed instrument
artefacts. Phase3's true M6-repaired mean score is 0.500 — exactly what the
raw, uncorrected number says, not the higher figure v1 projected.**

**For phase3, scenario 1 (measurement problem) is rejected under strict
scoring.** v1's central claim — that a broken renderer was responsible for
43% of phase3's measured failures — does not survive a second pass using the
rubric the judge was actually built around. The renderer defect was real (the
6+1 candidate records really did get their room_id/neighbourhood claims
wrongly called fabrication in the first pass), and fixing it really did
change 3 records' provisional scores upward during the blind complete-data
re-score. But underneath every one of those records sat a second, independent
defect — invented ancillary metadata, most often a specific metro-line colour
asserted as fact — that a rubric applied literally cannot excuse, and that a
human scorer, working quickly through a complete but still large table,
informally waved through as harmless the first time round. The corrected
picture is not "phase3 was unfairly penalized"; it's "phase3 has a real,
systematic groundedness defect that happens to look similar to, but is
distinct from, the defect the instrument bug obscured." Concretely: phase3
gets its core numbers right 64% of the time it fails (§3) — a genuinely good
retrieval signal, not an artefact-inflated one — but routinely dresses that
correct core data up with invented specifics (a metro line, a bathroom count,
an amenity, once even a fabricated review snippet) that were never in the
retrieved context. That is a real architectural failure mode: an LLM that
treats "sounds like the kind of detail this answer should have" as license to
assert it as fact.

**For phase2, nothing changes: scenario 2 (genuine reasoning/architecture
limits) remains the better-supported reading**, exactly as in v1. Its
dominant defect (D, 48%: claiming "2 rooms" or "5 rooms" fit when the truth
table has dozens to hundreds) is a retrieval-scope failure — phase2 appears to
still be mistaking a small retrieved context window for the entire database.
Its second-largest defect (F, 22%) is denying the literal attribute the query
filtered on, present on every single retrieved row. Neither pattern is
touched by, or explicable by, the column-omission instrument defect that
affected phase3's scoring.

**Net read for the M6 thesis result, corrected:** the measured phase2/phase3
gap (0.115 / 0.500 under strict) is **not** a measurement artefact in any
material part. The complete-data, strict-rubric re-analysis leaves the gap
essentially where the raw numbers already put it. What the instrument-defect
investigation *did* genuinely deliver is a more accurate account of *why*
phase3 fails when it fails: not geographic/ID hallucination (that charge is
fully retracted — 0 of the 7 candidate records hold up), but a distinct and
real over-eager-fabrication pattern documented for the first time in §1/§2 of
this redo. The thesis should report phase3's true M6-repaired mean as 0.500
(matching the original headline, not the v1-projected higher figure), and
should characterise phase3's dominant failure mode as fabricated ancillary
metadata (B, 36%) tied with wrong counts (D, 36%) — not as an instrument
artefact.
