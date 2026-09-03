# M6 Step 3 — Failure taxonomy

Read-only analysis of all 37 M6-repaired records scored below 1.0 by human judgement (of 52 total). For each, I derived a cause classification independently from the answer text and the truth table, then reconciled it against the human's note and the judge's rationale — I did not defer to either. Several records required pulling the raw room-level JSON to settle a factual dispute; those checks are called out explicitly because they change the conclusion.

## 1. Per-record table

| query_id | system | human | judge | primary | other causes | retrieval_ok | evidence |
|---|---|---:|---:|---|---|:---:|---|
| constraint_satisfaction_01 | phase2 | 0.0 | 0.0 | D | A, C | N | claims 3 rooms fit (true 35); "Residencia Santos" doesn't exist; "Cosy Home Lisbon" misplaced at Santos |
| constraint_satisfaction_01 | phase3 | 0.0 | 0.5 | **H** | — | Y | verified: every zone/neighbourhood pair the human flagged as "hallucinated" (Alvalade/Intendente, Mouraria/Santos, Arroios/Campo de Ourique, Alfama/Benfica) is an exact DB match; only real defect is a one-room bed-type nuance |
| constraint_satisfaction_02 | phase2 | 0.0 | 0.0 | F | D | Y | claims 0 rooms have both amenities (true 47); the 5 rooms it lists ARE real matches, washer=True falsely denied |
| constraint_satisfaction_02 | phase3 | 0.0 | 1.0 | **H** | — | Y | verified: all 7 disputed zone/neighbourhood pairs (e.g. Ramalde/Ribeira, Foz do Douro/Miragaia) are exact DB matches; "geographic hallucination" claim is incorrect |
| constraint_satisfaction_03 | phase2 | 0.0 | 0.0 | D | B, C | N | claims 2 rooms fit (true 59); invents a seasonal "Garden View Room"; swaps size/bed on the one real room cited |
| constraint_satisfaction_03 | phase3 | 0.0 | 0.5 | A | — | Y | count (59) and prices correct, but merges two distinct real rooms into a fake "older/newer version" of one ID, and another pair into a false price range |
| constraint_satisfaction_04 | phase2 | 0.0 | 0.0 | C | F | N | all 5 named properties absent from the 29-room truth table |
| constraint_satisfaction_04 | phase3 | 0.0 | 0.5 | **H** | G | Y | verified: the "fabricated ID" claim is false — the bracketed IDs are verbatim real internal room_ids incl. timestamp; remaining concern is asserting the query's own (DB-unverifiable) metro-line constraint as satisfied |
| constraint_satisfaction_05 | phase2 | 0.0 | 0.0 | D | B, C | N | claims 2 rooms fit (true 78); invents a Double Deluxe at Ramalde (real one is only at Boavista, €560); wrong bed/size for two real rooms |
| constraint_satisfaction_05 | phase3 | 0.0 | 0.5 | **H** | — | Y | verified: all disputed zone/neighbourhood pairs (7+ prices checked) are exact DB matches |
| constraint_satisfaction_06 | phase2 | 0.0 | 0.0 | D | C, F | N | claims 2 rooms fit (true 64); "Economy Room Graça" / "Bright Single Santos" don't match any real property; falsely claims transport-distance isn't in the sources |
| constraint_satisfaction_07 | phase2 | 0.0 | 0.0 | F | C, E | N | denies female_preferred despite ALL 42 results carrying it; 2 of 5 cited rooms don't exist |
| constraint_satisfaction_07 | phase3 | 0.0 | 1.0 | **H** | — | Y | verified: all disputed zone/neighbourhood pairs are exact DB matches; judge's 1.0 looks correct |
| constraint_satisfaction_08 | phase2 | 0.0 | 0.0 | E | B | N | filter structurally returns 0 (minreservemonths is NULL DB-wide); answer correctly says so, then contradicts itself by pricing 3 "candidate" rooms anyway |
| constraint_satisfaction_09 | phase2 | 0.5 | 0.5 | E | C | Y | 2 real, correct recommendations presented as if they were the whole match set (true 41); 3 additional "above budget" rooms are invented |
| constraint_satisfaction_10 | phase2 | 0.5 | 0.5 | E | B | Y | 2 real, correct recommendations (true 27); Casa Verde Economy Room price wrong (1,160 claimed vs 580 real), wrongly excluding a real cheap match |
| constraint_satisfaction_11 | phase2 | 0.0 | 1.0 | **H?** | — | n/a | declines, citing no availability data; neither system shows evidence of a real reservation-exclusion tool — ground truth may test a capability never exposed to the agent (flagged, not fully certain — see §5) |
| constraint_satisfaction_11 | phase3 | 0.0 | 0.0 | D | E | N | claims 556 available (true 156); dumps the unfiltered city inventory, ignoring the reservation-exclusion constraint entirely |
| constraint_satisfaction_12 | phase2 | 0.0 | 0.0 | C | B | N | "Room in Cosy Home Lisbon (Santos)" and "Bright Single (Anjos)" don't exist; fabricates an `accepts_couples` attribute (no such DB column) |
| constraint_satisfaction_12 | phase3 | 0.0 | 0.5 | F | — | Y | count (63) and cited prices correct, but asserts "accept couples" as a satisfied filter when `accepts_couples` has no DB column and was silently dropped (also recommends a single bed for a couple) |
| constraint_satisfaction_13 | phase2 | 0.0 | 0.0 | F | C, D | N | denies internet=True despite it being the literal filter criterion for all 27 real matches; fabricates candidate rooms; claims 0 vs true 27 |
| constraint_satisfaction_14 | phase2 | 0.0 | 0.0 | B | A, C | Y | real properties (Bright Apartment Arroios, Residencia Santos) given fabricated/wrong seasonal prices and the wrong zone |
| factual_lookup_01 | phase2 | 0.0 | 0.0 | D | F | Y | claims 5 rooms total (true 556); falsely claims all rooms are under one property name |
| factual_lookup_01 | phase3 | 0.0 | 0.0 | D | — | N | bare unsupported claim of 435 rooms (true 556), no grounding given |
| factual_lookup_02 | phase3 | 0.0 | 0.0 | E | — | N | lists only 5 of 9 real zones as if exhaustive, nesting the other 4 real zones as fake "neighbourhoods" of the 5 |
| factual_lookup_03 | phase2 | 0.0 | 0.0 | C | B | N | "Cosy Double in Cosy Home Porto (Ramalde)" doesn't exist there; 3 more rooms fully invented; only 1 of 5 cited rooms is real |
| factual_lookup_03 | phase3 | 0.0 | 0.0 | D | B | Y | count 23 vs true 20 (outside tolerance); one garbled/fabricated price (€-20); 9 of 10 other rows are real |
| factual_lookup_04 | phase2 | 0.0 | 0.0 | D | A | Y | claims 5 rooms total (true 188); 2 of 5 cited rooms verified real |
| factual_lookup_05 | phase2 | 0.0 | 1.0 | F | — | Y | declines, citing that metro-line colour isn't in the sources — disagree with judge (see §5): a zone→metro-line mapping is a reasoned inference the agent could plausibly make, human's tool-usage framing is more persuasive |
| factual_lookup_06 | phase2 | 0.0 | 0.0 | C | — | N | fails to resolve the literal room ID given in the query; invents 5 alternative rooms/fees, none matching the real €95 fee |
| factual_lookup_07 | phase2 | 0.0 | 0.0 | F | C | N | denies gender-restriction info despite ALL 92 results carrying female_preferred=True |
| factual_lookup_07 | phase3 | 0.5 | 0.5 | **H** | — | Y | the human's stated objection (Anjos/Campo de Ourique) is verified incorrect; judge's own rationale is inconclusive/truncated too — record likely closer to 1.0 |
| factual_lookup_09 | phase2 | 0.0 | 0.0 | B | — | N | invents a m²-filtered list for a field the DB cannot filter on at all |
| factual_lookup_09 | phase3 | 0.0 | 0.5 | B | — | N | correctly states m² isn't filterable, then still fabricates 2 example rooms — ground truth explicitly requires not doing this |
| factual_lookup_10 | phase2 | 0.0 | 0.0 | D | C | N | claims 1 option (true 169); 3-4 named alternative properties fully fabricated despite one correct citation |
| factual_lookup_11 | phase2 | 0.0 | 0.0 | D | — | Y | claims 5 rooms total (true 375); 3 of 5 cited room/price combinations verified real — judge's rationale wrongly calls them fabricated (see §5) |
| factual_lookup_11 | phase3 | 0.0 | 0.0 | D | — | N | bare unsupported claim of 295 rooms (true 375), no grounding given |

Legend: **H** = confirmed instrument artefact (verified against raw DB); **H?** = flagged, unresolved. `retrieval_ok`: Y = the stated count and/or specific prices/zones correspond to real truth-table rows; N = they don't.

## 2. Cause frequency per system

Primary cause only, counted over each system's classified failures (phase2: 23, phase3: 14):

| cause | phase2 (n=23) | phase3 (n=14) |
|---|---:|---:|
| D — WRONG_COUNT | 8 (35%) | 4 (29%) |
| F — FALSE_ABSENCE | 5 (22%) | 1 (7%) |
| C — FABRICATED_ENTITY | 4 (17%) | 0 |
| E — PARTIAL_AS_TOTAL | 3 (13%) | 1 (7%) |
| B — FABRICATED_VALUE | 2 (9%) | 1 (7%) |
| A — WRONG_ASSOCIATION | 0 | 1 (7%) |
| H — INSTRUMENT_ARTEFACT | 1 (4%, unresolved) | 6 (43%) |

Phase2's failures are dominated by D/F/C — wrong counts, false denial of the very attribute the query asked about, and entities invented from nothing. Phase3's genuine failures (excluding H) are almost all D/E — undercounting or misrepresenting the *scope* of a result set, not inventing facts. **Phase3's single largest "cause" bucket is not a system failure at all: 6 of its 14 failures (43%) are instrument artefacts**, all of the same kind (see §4).

## 3. The key number — correct retrieval vs. broken retrieval

Operationalised per the task: `retrieval_ok` = the stated count and/or the stated prices/zones correspond to real truth-table rows, independent of whether they're correctly associated.

| system | retrieval_ok = Y (fetched right data, mis-stated it) | retrieval_ok = N (retrieval itself wrong) |
|---|---:|---:|
| phase2 (n=23, or 22 excl. the n/a decline) | 8/22 (36%) | 14/22 (64%) |
| phase3 (n=14) | 9/14 (64%) | 5/14 (36%) |
| phase3, excluding the 6 H records (n=8 genuine failures) | 3/8 (37%) | 5/8 (63%) |

The raw phase3 number (64% retrieval_ok) is misleading — it's inflated by the 6 H records, which by definition retrieved everything correctly (that's exactly why they're artefacts, not failures). **Once the instrument artefacts are removed, phase2 and phase3 have a strikingly similar genuine-failure profile: roughly two-thirds of real failures on both systems are retrieval itself breaking (mostly on count/scope: "5 rooms" when the true total is in the hundreds), not a presentation layer mis-stating good data.** This is the single most important number in this analysis: architecturally, the two systems fail the same way when they fail for real. The narrower A/B/D-vs-E/F cut the task also asked for: 4 phase2 records (fl_01, fl_04, fl_11, cs_14) and 2 phase3 records (cs_03, fl_03) are clean "right data, wrong presentation" cases; 4 phase2 records (cs_08, cs_07, cs_13, fl_07) and 1 phase3 record (fl_02) are clean "retrieval itself wrong" cases in the E/F sense — the rest carry a C (fabricated-from-nothing) or H primary cause that doesn't sit cleanly in either bucket.

## 4. INSTRUMENT_ARTEFACT (H) — full reasoning

**7 records were flagged H; 6 are confirmed by direct verification against the raw truth-table JSON, 1 is an unresolved flag.**

The 6 confirmed cases (constraint_satisfaction_01/02/04/05/07 phase3, factual_lookup_07 phase3) share one root cause: **the Step-1 human-eval workbook's `truth_table_summary` renderer strips the `room_id` and `neighborhood` fields for readability** (`scripts/benchmarks/build_m6_human_eval.py`, `format_room_line`). Phase3's answers frequently cite exactly those two fields verbatim and correctly — e.g. reporting a room's `zone`/`neighbourhood` pair as two columns ("Ramalde | Ribeira"), or quoting the full internal `room_id` including its timestamp suffix. Because the human's rendered truth table never showed those fields, every one of these correct citations looked like fabrication — a plausible reaction given the workbook did not explain that `neighborhood` is an independent DB column whose vocabulary happens to reuse zone names, or that the bracketed `HSE_.../RM_..._N/<timestamp>` strings are the real primary keys, not synthetic-looking noise. I checked this hypothesis directly against `m6_repair_truth_tables.json` in every case listed as "verified" above, matching the exact prices/zones/IDs the answers cited row-for-row — all matched.

The 7th (constraint_satisfaction_11 phase2) is different in kind and not confirmed: the query asks about actual room availability on a specific past date, and the ground truth is computed by the evaluation harness directly against a reservations table. Neither phase2 (which declines) nor phase3 (which returns the unfiltered inventory, clearly not applying any date filter) shows behaviour consistent with the agent having a real "check reservation status" tool. If that capability was never exposed to the agent, holding it to a ground truth computed via direct SQL access it doesn't have would itself be a ground-truth/scope mismatch (H). This could not be confirmed from the artifacts read for this task — it requires knowing the deployed tool surface — so it is reported as a flag, not a finding.

**What fraction of the measured deficit is attributable to our measurement rather than the systems:** on this 37-record sample, 6/37 (16%) confirmed, 7/37 (19%) if the unresolved flag is included. The effect is not evenly spread: it is 0/23 confirmed on phase2 and 6/14 (43%) confirmed on phase3. In other words, **phase3's true M6 groundedness is materially better than its raw score suggests; phase2's is not** — none of phase2's 23 failures survived scrutiny as an artefact.

## 5. Cross-check — where my classification disagrees with the note

I did not defer to either scorer. Nine records surfaced a disagreement worth flagging explicitly, with the reading I consider correct and why:

1. **cs_01 phase3** — human says 0.0 (systematic geographic hallucination). *I side with neither fully but lean toward the judge*: every specific zone/neighbourhood pair the human cites as wrong is an exact DB match (verified). The record's only real defect is a one-room bed-type nuance the judge caught, worth 0.5 at most, possibly 1.0. Human's reasoning is factually incorrect.
2. **cs_02 phase3** — human says 0.0, judge says 1.0. *I side with the judge*: all 7 disputed zone/neighbourhood pairs verified correct; the human's "hallucination" claim does not survive a DB check.
3. **cs_05 phase3** — same pattern and same conclusion as #2 (7+ prices verified against real zone/neighbourhood pairs).
4. **cs_07 phase3** — same pattern; judge's 1.0 verified correct.
5. **cs_04 phase3** — human's *stated reason* (fabricated IDs) is factually wrong — verified the bracketed IDs are real, verbatim primary keys. The judge's 0.5, however, rests on a different and more defensible point (asserting the metro-line-D constraint is satisfied when that's explicitly DB-unverifiable) — I don't overturn the 0.5, but the human's justification for it is wrong.
6. **factual_lookup_07 phase3** — human's stated reason (Anjos/Campo de Ourique mismatch) is verified incorrect — Anjos Student Flat's real `neighborhood` field is literally "Campo de Ourique". The judge's own rationale is inconclusive and cuts off mid-truncation without landing on a clear contradiction either. I believe this record is undervalued at 0.5 by both.
7. **factual_lookup_11 phase2** — human says 0.0, and I agree with the *score* (5 vs true 375 is dispositive on its own), but the *judge's rationale* is factually wrong here, not the human's: the judge calls three specific room/price combinations "fabricated" (Master Suite €780/625/525, Economy Room €955 fixed private, Massarelos Studio Loft €615 fixed) that I verified are exact matches in the raw truth table. The human's note correctly said these matched. Worth flagging because it shows the judge itself hallucinating a contradiction that isn't there — a different failure mode from everything else in this report, and one that would matter if this record's score depended on that specific claim (here it doesn't, since the count error is independently disqualifying).
8. **factual_lookup_05 phase2** — human says 0.0 (tool-usage failure), judge says 1.0 (correctly declines on unverifiable data). *I side with the human*: unlike a bare "not in the DB" attribute, mapping a zone to a metro line is a reasoned inference from real-world/domain knowledge the agent could plausibly apply (and the benchmark's own ground truth of 203 matches implies the mapping is well-defined), so declining reads more like an under-used capability than an appropriately humble refusal.
9. **cs_11 phase2** — human says 0.0, judge says 1.0. Genuinely unresolved (see §4): depends on agent tool-surface facts not available from these artifacts.

## 6. Verdict — scenario 1 vs scenario 2

**The evidence is mixed, and it splits cleanly along system lines rather than pointing to one scenario for the whole M6 result.**

**For phase3, scenario 1 (measurement problem) explains a real and large share of its measured deficit.** 6 of its 14 human-scored failures (43%) are confirmed instrument artefacts, all traceable to one specific, fixable defect: the Step-1 workbook's truth-table renderer drops two fields (`room_id`, `neighborhood`) that phase3 frequently and correctly cites. Once those are removed, phase3's remaining genuine failure rate on this metric is 8/26 (31%), not 14/26 (54%), and its true mean M6-repaired score is higher than the 0.154 headline figure. For scenario 2 to hold *for phase3* — i.e., for phase3's measured deficit to reflect real LLM reasoning limits rather than measurement — one would have to show that the 6 records I verified are wrong: that the cited zone/neighbourhood pairs and room IDs do *not* actually match the raw JSON. I checked this directly for all 6 and they matched every time, so I don't think that's available.

**For phase2, scenario 2 (genuine reasoning/architecture limits) is the better-supported reading.** None of its 23 failures survived scrutiny as an artefact. Its dominant failure signature — claiming "3 rooms" or "5 rooms" fit when the true total is 27-556 — is not a fabrication of facts so much as a **retrieval-scope failure**: phase2 appears to mistake a small retrieved context window for the entire database, a known and plausible RAG limitation, not a measurement quirk. On top of that, phase2 repeatedly denies the presence of the *exact attribute the query asked about* (female_preferred, internet, washer_drier) when every single result in a 27-to-92-room truth table carries it — a pattern too consistent and too central to the query to be a measurement artefact; it reads as the model not actually consulting the retrieved rows' boolean attributes before answering. For scenario 1 to hold *for phase2*, one would need to find a comparable rendering/rubric defect that makes real, correct phase2 answers look wrong across at least a third of these 23 records — I found no such pattern; phase2's fabricated entities, wrong counts, and false attribute denials describe answers that are actually wrong by any reading of the truth table.

**Net read for the M6 thesis result overall:** the measured 0.558/0.154 gap between phase2 and phase3 is *partly* a measurement artefact (phase3 is being under-scored) and *partly* real (phase2 has a genuine, systematic retrieval-scope problem that phase3 mostly does not share once corrected). Both things are true at once; the M6 score as currently computed overstates the gap, but does not manufacture it — phase2 has a real problem, phase3 has a smaller one than reported. I would not defer further headline M6 comparisons to the current human-eval numbers without first re-rendering the Step-1 workbook with `room_id` and `neighborhood` included, since that single fix is what's driving the phase3 correction.
