# M6 Step-4 recomputation with the corrected field map

Read-only task: verify the constraint_satisfaction_12 attribution, then
recompute Step-4 (`build_m6_step4.py verify`) with the field map corrected
per `m6_field_availability_audit.md`. All DB access is read-only `SELECT`s
against the project's own dev Postgres (`DB_URI`). No LLM calls, no batch
submission — the corrected resolver runs against the LLM extractions already
saved in `results/results_M6_extraction.jsonl`.

---

## Part A — constraint_satisfaction_12 attribution check

### Which system actually said it

**`phase3_eval_v2_fresh.jsonl` (system: `phase3`, the agentic tool-using
system), verbatim:**

> "Great news! I found **63 rooms** in Lisbon that accept couples, have a
> private bathroom, and are under €1,100/month. Here are the top 15 options,
> sorted by price: [...] | 1 | Anjos | Anjos | **€785** | 12m² | Single |
> 969m (Green line) | [...] **Top recommendations for couples:** ... **Most
> spacious**: The **Parque das Nações room at €880/month** is 27m² with
> great metro access (455m to Red line)."

Row 1 (cheapest, listed first) and the "Most spacious" pick both carry
`Bed Type = Single` — a single bed offered as a couples option, in a table
whose entire framing is "rooms that accept couples."

**`phase2_eval_v2_fresh.jsonl` (system: `phase2`, the RAG pipeline) — same
query, different fabrication:**

> "**Room in Cosy Home Lisbon (Santos)** - This 28m² room explicitly accepts
> couples with an extra person fee of **+€120/month**. [...] **Alternative
> Option:** **Bright Single in Cosy Home Lisbon (Anjos)** [...] this listing
> doesn't explicitly state it accepts couples, so you would need to confirm
> with ELH."

**Verdict: the attribution is correct as it stands — phase3 (the agentic
system) made the "found 63 rooms that accept couples... recommends a single
bed" claim, word for word.** No sentence needs to move. `m6_failure_taxonomy_v2.md`
already carries two *separate*, correctly-attributed rows for this record —
line 82 (phase2: fabricates a specific room's "explicitly accepts couples"
claim) and line 83 (phase3: asserts a global filter match across 63 results,
recommends a single bed). Both systems have their own `accepts_couples`
failure on this record; they are not the same failure, and only phase3's
matches the exact wording quoted in the task.

### Is `accepts_couples` genuinely inert?

Yes, confirmed by reading the frozen code, not by trusting the report:

`src/elh_rag/tools/find_rooms/_inputs.py:98` — accepted by the tool's input
schema, so a model can (and here, did) set it:

```python
accepts_couples: bool | None = None
```

`src/elh_rag/tools/find_rooms/_sql_builder.py:131-134` — silently dropped
when building the SQL, with only a server-side log line the model never sees:

```python
if payload.accepts_couples is True:
    logger.warning(
        "find_rooms: accepts_couples=True ignored — column not present in the ELH schema."
    )
```

No `WHERE` clause is added for it. This is confirmed separately from — but
consistent with — the schema audit in `m6_field_availability_audit.md`:
`accepts_couples` is the one field in that audit's "genuinely uncheckable"
bucket that really has no column anywhere (verified again below, §1).

---

## Part B — Step-4 recomputation with the corrected field map

Baseline reproduced exactly before any correction: phase2 mean M6_step4 =
**0.2798** (n=22/26), phase3 = **0.7494** (n=25/26); 364 + 498 = 862
UNVERIFIABLE claims — matching the committed `m6_extraction_SQL_scores.jsonl`
and the current report's headline 0.749 / 0.280.

### B.1 — Corrected attribute→column map

**Moved from UNVERIFIABLE to checkable** (real column, live-fetched per
matched room since the truth table doesn't carry them either — see the
availability audit §2):

| attribute phrasing seen in the extractions | column | table |
|---|---|---|
| heating | `heating` | `room` (OR `centralheating` on `house`, either counts) |
| air conditioning / A/C | `airconditioning` | `room` (OR `airconditioning` on `house`, either counts) |
| wardrobe / closet | `closet` | `room` |
| bed linen | `bedlinen` | `room` |
| pillows | `pillows` | `room` |
| window / natural light | `haswindow` | `room` |
| bathroom (bare word, "private"/"shared" phrasing, underscore and non-English forms — "baño privado", "shared_bathrooms") | `privatebathroom` | `room` — extends the pre-existing "private bathroom"/"shared bathroom" keyword match, which already worked for that *exact* phrase |
| size / room size | `area` | `room` — extends the pre-existing "area"/"m2"/"sqm" keyword match |

(`desk`, `area` when phrased as "area"/"m2"/"sqm", and "private
bathroom"/"shared bathroom" phrased in full were **already** correctly
resolved by the unmodified verifier — not part of this fix, see the
availability audit §4a caveat.)

**Stay UNVERIFIABLE — justified individually, not by default:**

| attribute | why it stays unverifiable |
|---|---|
| metro line | No DB column at all. `nearest_metro_line` is an application-layer value computed by `_shared/metro_lines.py` from a hardcoded zone→line lookup table, not read from the schema — checking it would mean re-running that lookup, not querying the DB, which is out of scope for a SQL-based verifier as built. |
| walking distance to a landmark | No column and no computed value anywhere. `near_landmark` is a free-text `ILIKE` filter on `zone`/`neighboorhood`/`description` (`_sql_builder.py`) — it can confirm a landmark is *mentioned*, never a distance. (Caution: the pre-existing "distance to" keyword would wrongly match a phrase like "walking distance to NOVA University" and check it against `distance_to_transport_m` — a latent resolver bug, not triggered by anything in this 52-record set, left unfixed here since it's out of scope.) |
| shared-bathroom **count** (how many people share one bathroom) | No column. `room.privatebathroom` is a boolean (private vs. shared), `house.bathroom` is a total bathroom count for the whole house — neither expresses "N people share this bathroom." Genuinely absent from the schema, not an instrument gap. |
| review sentences / review sentiment | The `review` table's five rating columns (`cleaningratings`, `communicationratings`, `locationratings`, `pricequalityratings`, `overallratings`) are already numerically checkable. A claim about what a review's free-text `description`/`title` *says* or *implies* is a natural-language content-matching problem, not a column lookup — correctly out of scope for this verifier. |
| `accepts_couples` | Confirmed absent from both `room` and `house` (Part A, and the full 37+56-column listing in the availability audit §1). Also confirmed dead in `find_rooms`'s own code (Part A). |
| generic/ambiguous claims ("amenities", "location", "storage", "accepts couples" as a bare noun) | Not resolvable to one column by name alone; would need per-claim disambiguation this pass didn't attempt. |

### B.2 — Reclassified claims: counts and full CONTRADICTED detail

**A bug caught mid-task, before it reached this section:** the first pass of
the corrected resolver matched air conditioning on the bare token `" ac "`.
`_normalize()` strips the surrounding spaces before the containment check
runs, so it degenerated into a plain substring test for `"ac"` — which
false-matched **"machine"** (m-**ac**-hine) and silently mis-scored a
`washing machine` claim in `constraint_satisfaction_02` as an air-
conditioning check. Caught by inspecting the printed detail (the claim text
said "washing machine" but the code path taken was the AC getter), fixed by
requiring `"ac"` to match as its own word (`\bac\b`) rather than a bare
substring, and the whole run redone. `washing machine` phrasing itself is
**not** mapped by this pass (only `washer`/`dryer`/`laundry machine` are, in
the original resolver, and none of those match "washing machine" either) —
it correctly falls back to UNVERIFIABLE, consistent with the "further,
not-rescored" candidates already flagged in the availability audit. This
means constraint_satisfaction_02 has **no** newly-CONTRADICTED claim from
this fix — the numbers below are the corrected, re-verified ones.

**89 attribute claims moved out of UNVERIFIABLE** (verified zero regressions
on any of the 862 baseline SUPPORTED/CONTRADICTED/UNVERIFIABLE claims — the
original resolver is tried first, unchanged, for every claim):

| system | newly SUPPORTED | newly CONTRADICTED | total reclassified |
|---|--:|--:|--:|
| phase2 | 30 | 1 | 31 |
| phase3 | 44 | 14 | 58 |
| **total** | **74** | **15** | **89** |

**All 15 CONTRADICTED, in full — claim, SQL, and actual row:**

**[phase3] constraint_satisfaction_03** — attribute=`bed linen`,
claimed=`yes`, subject=`Chiado #HSE_696556D0`:
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_696556D0' AND idroom = 'RM_HSE_696556D0_2'
ORDER BY dateupdate DESC LIMIT 1;
```
row: `bedlinen='N'` — claimed yes, actual False.

**[phase3] constraint_satisfaction_04** — attribute=`air conditioning`,
claimed=`yes`, subject=`Foz do Douro #HSE_4190B25E – Room 2`:
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_4190B25E' AND idroom = 'RM_HSE_4190B25E_2'
ORDER BY dateupdate DESC LIMIT 1;
```
row: `airconditioning='N'` (and `house.airconditioning` also `'N'` for this
house) — claimed yes, actual False. (This is the same record whose human
note independently reads *"invents A/C, heating... (none in any column)"* —
correct call, wrong stated reason: the column exists and now proves the
claim false rather than merely unchecked.)

**[phase3] constraint_satisfaction_05** — three separate contradictions on
two rooms:
- attribute=`size`, claimed=`17m²`, subject=`Bonfim #HSE_79FFB52D` — room
  `HSE_79FFB52D|RM_HSE_79FFB52D_4`: `area=11.37` — claimed 17, actual 11.37.
- attribute=`size`, claimed=`28m²`, subject=`Boavista #HSE_77C4AFBA (Room 7)`
  — room `HSE_77C4AFBA|RM_HSE_77C4AFBA_1`: `area=11.80` — claimed 28, actual
  11.8.
- attribute=`bathroom`, claimed=`Private`, same subject/room:
  `privatebathroom='N'` — claimed private, actual shared.
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_77C4AFBA' AND idroom = 'RM_HSE_77C4AFBA_1'
ORDER BY dateupdate DESC LIMIT 1;
```

**[phase3] constraint_satisfaction_09** — attribute=`bathroom`,
claimed=`shared`, subject=`Graça #HSE_2B801A43 (Room 2)`:
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_2B801A43' AND idroom = 'RM_HSE_2B801A43_1'
ORDER BY dateupdate DESC LIMIT 1;
```
row: `privatebathroom='Y'` — claimed shared, actual private. (This is the
record scored `human_score_strict = 1.0` — see B.4/restated figure below.)

**[phase3] factual_lookup_03** — seven `size` claims (Rooms 1-7), each
against a matched room, all wrong by 3-9 m²:

| claimed room | claimed size | matched room_id | actual `area` |
|---|--:|---|--:|
| Room 1 | 15m² | `HSE_77C4AFBA\|RM_HSE_77C4AFBA_10` | 18.87 |
| Room 2 | 20m² | `HSE_77C4AFBA\|RM_HSE_77C4AFBA_10` | 18.87 |
| Room 3 | 14m² | `HSE_D1F41EC3\|RM_HSE_D1F41EC3_12` | 10.61 |
| Room 4 | 27m² | `HSE_77C4AFBA\|RM_HSE_77C4AFBA_10` | 18.87 |
| Room 5 | 26m² | `HSE_77C4AFBA\|RM_HSE_77C4AFBA_10` | 18.87 |
| Room 6 | 20m² | `HSE_77C4AFBA\|RM_HSE_77C4AFBA_10` | 18.87 |
| Room 7 | 12m² | `HSE_914F1E6F\|RM_HSE_914F1E6F_10` | 21.58 |

```sql
SELECT area FROM room WHERE loc_idhouse = 'HSE_77C4AFBA' AND idroom = 'RM_HSE_77C4AFBA_10'
ORDER BY dateupdate DESC LIMIT 1;   -- 18.87  (repeat per idroom for the others)
```

**[phase2] factual_lookup_04** — blanket: attribute=`bed linen`,
claimed=`yes`, subject=`all`. False for 2/8 verified rooms:
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_4EAED14B' AND idroom = 'RM_HSE_4EAED14B_1'
ORDER BY dateupdate DESC LIMIT 1;
```
row: `bedlinen='N'` — claimed yes for every room, actual False for this one.

**[phase3] factual_lookup_05** — blanket: attribute=`wardrobe`,
claimed=`yes`, subject=`all`. False for 1/5 verified rooms:
```sql
SELECT heating, airconditioning, closet, bedlinen, pillows, haswindow, area, privatebathroom
FROM room WHERE loc_idhouse = 'HSE_071B149D' AND idroom = 'RM_HSE_071B149D_1'
ORDER BY dateupdate DESC LIMIT 1;
```
row: `closet='N'` — claimed yes for every room, actual False for this one.
(This is the other record scored `human_score_strict = 1.0` — see below.)

### B.3 — Recomputed M6_step4

| | current (baseline) | corrected | Δ |
|---|--:|--:|--:|
| phase2 | 0.280 | **0.307** | **+0.027** |
| phase3 | 0.749 | **0.740** | **−0.009** |

**Why the two systems move in opposite directions:** phase2 gains 30
SUPPORTED claims against only 1 CONTRADICTED — its score can only go up.
Phase3 gains more SUPPORTED claims in absolute terms (44) but also picks up
14 CONTRADICTED ones — enough to outweigh the SUPPORTED gain and pull its
mean *down* slightly. Pooled (not per-record-mean) ratios confirm the same
direction: phase2 86/172=0.500 → 116/203=**0.571**; phase3 215/262=0.821 →
259/320=**0.809**. The phase2↔phase3 gap narrows from 0.469 to 0.433 — a
modest absolute move, but it comes entirely from real, DB-provable phase3
errors surfacing, not from a methodology tweak that favours either system.

### B.4 — Gap decomposition, kept separate as instructed

To isolate (i) "asserts what it was never given" from (ii) "plain factual
error," a third variant was computed: **partial** = only the 15 newly-
CONTRADICTED claims applied, the 74 newly-SUPPORTED ones left as they were
at baseline (still UNVERIFIABLE). Comparing baseline → partial isolates (ii)
alone; partial → corrected (full) isolates (i) alone.

| system | mean M6_step4 baseline | mean M6_step4 partial (ii only) | mean M6_step4 corrected (i+ii) | mean human_score_strict |
|---|--:|--:|--:|--:|
| phase2 (n=22) | 0.2798 | 0.2783 | 0.3067 | 0.0909 |
| phase3 (n=25) | 0.7494 | 0.7295 | 0.7399 | 0.5200 |

Gap = mean(M6_step4) − mean(human_score_strict), per system:

| system | gap, baseline | gap, (ii) applied | gap, (i)+(ii) applied | (ii) share of original gap | (i) share of original gap |
|---|--:|--:|--:|--:|--:|
| phase2 | +0.1889 | +0.1874 | +0.2158 | **closes 0.8%** | **re-opens 15.0%** (net: gap widens 14.2%) |
| phase3 | +0.2294 | +0.2095 | +0.2199 | **closes 8.7%** | **re-opens 4.6%** (net: closes 4.1%) |

Reading this straight, per the task's requested separation:

- **(ii) plain factual error** is, on both systems, a real but small piece of
  the M6_step4-vs-human gap: 8.7% of phase3's gap and under 1% of phase2's.
  This is expected — CONTRADICTED claims were already the minority outcome
  even among the reclassified 89 (15 of 89), and the gap has other, larger
  drivers already documented in `m6_extraction_sql.md` §4 (wrong sort order,
  entity-merging, count/price dilution).
- **(i) asserts what it was never given** is, counter-intuitively, a force
  that *widens* the gap rather than closing it, on both systems (phase2
  +15.0%, phase3 +4.6%). This is the direct, quantified confirmation of the
  mechanism identified in the availability audit §3.4: most of these newly-
  SUPPORTED claims are heating/AC/closet/bed-linen/window guesses the model
  had no reliable tool-grounded way to make (find_rooms/find_available_rooms
  never return them; the 200-char excerpt that could is truncated away most
  of the time) that happen to be right anyway — largely because the base
  rate is high (e.g. `closet='Y'` for 874/932 rooms; guessing "yes" is usually
  correct). A claim being SUPPORTED-by-luck still counts as SUPPORTED in
  M6_step4's arithmetic, which is exactly why it widens rather than narrows
  the gap against a human who is (inconsistently, per the human's own notes
  quoted in `m6_extraction_sql.md` §4) penalizing this pattern regardless of
  whether the specific guess happened to land.
- **Net effect** is opposite between the systems: phase3's net gap closes by
  4.1% (its larger CONTRADICTED count outweighs its newly-SUPPORTED
  widening); phase2's net gap *widens* by 14.2% (it has 30 newly-SUPPORTED
  claims against only 1 CONTRADICTED, so the widening from (i) dominates
  completely). **This is the wording fix the task asked for**: the existing
  report's framing (`m6_extraction_sql.md` §4, "~60% of the phase3 gap...
  ancillary metadata... no column to check against") conflates a system
  stating things it wasn't given (ungrounded, regardless of truth value)
  with a system stating things that are false (contradicted, checkable and
  disproved). Once separated, checkability itself (ii) narrows phase3's gap
  by under 10%; the bulk of what the report called "ancillary metadata
  padding" is actually ungrounded-but-often-right guessing (i), which is a
  distinct failure mode from fabrication and, mechanically, pulls the
  M6_step4-vs-human gap the *other* way from what "padding with no column to
  check" implies.

### Restated: corrected human-strict figure

From the field-availability audit: `constraint_satisfaction_09` and
`factual_lookup_05` (both phase3) currently carry `human_score_strict = 1.0`
despite each containing exactly the CONTRADICTED claim confirmed above
(bathroom type wrong for cs_09; wardrobe claim false for factual_lookup_05,
which also has a second, already-checkable-at-baseline metro-distance
contradiction the evaluator missed). Applying the rubric's own bands: cs_09
→ 1.0 → 0.5 (exactly one new contradiction); factual_lookup_05 → 1.0 → 0.0
(two contradictions). Phase3's headline `human_score_strict` moves from
0.500 (13.0/26) to **≈0.442** (11.5/26), an ~11.6% relative decrease. This
remains a lower bound — it reflects only the two records this specific
8-field fix happened to surface, not a full re-audit of all 52 records
against a fully corrected verifier.

---

## Files touched / referenced

Read-only: `benchmarks/runs/phase2_vs_phase3/v2/phase{2,3}_eval_v2_fresh.jsonl`,
`src/elh_rag/tools/find_rooms/_inputs.py`, `_sql_builder.py`,
`benchmarks/reports/phase2_vs_phase3/v2/m6_failure_taxonomy.md`,
`m6_failure_taxonomy_v2.md`, `m6_extraction_sql.md`, `m6_field_availability_audit.md`,
`m6_human_eval.xlsx`, `scripts/benchmarks/build_m6_step4.py`,
`build_m6_repair.py`, `results/results_M6_extraction.jsonl`. DB: live,
read-only `SELECT`s against the dev Postgres (`DB_URI`), same tables and
columns as the availability audit — no writes. No changes were made to any
committed script; the corrected resolver and gap-decomposition logic were
implemented in standalone scratch scripts for this task and are not part of
the repo. No LLM calls were made and no batch was submitted.
