# Pre-registration — Comprehensive Evaluation v2 (Phase 2 vs Phase 3)

**Project:** ELH Agentic RAG — MSc thesis

**Author:** Giovanni Pisoni · University of Bologna

**Supervisor:** Prof. Enrico Gallinucci · University of Bologna

**Rule:** this document is immutable once committed. Changes are made only by dated *addenda* appended at the bottom — never by editing the text above. Results live in separate files produced *after* this document.

---

## 0. Why this document exists

A prior comparative evaluation produced mixed signals between Pipelined RAG (Phase 2) and Agentic RAG (Phase 3). On review, the supervisor correctly observed that "if Phase 2 looks as good as Phase 3, why Phase 3?". The honest answer is methodological, not a matter of rigging the dataset: the v1 evaluation had four documented weaknesses (see below). This pre-registration fixes the design of a more rigorous v2 evaluation **in advance**, so that the question "what was decided before vs measured after" is verifiable from git history.

The core integrity commitment: **the system is frozen and the analysis plan is fixed before any result is seen.**

### The 4 documented weaknesses of v1
1. **Golden set biased toward Phase 2** — the 20-query set was built during Phase 2, before Phase-3 tools (`find_available_rooms`, `compute_total_cost`) existed, so it under-exercises Phase 3's distinctive capabilities.
2. **`task_success` too lenient** — the v1 judge accepted partial answers (e.g. rent components instead of a computed total), giving Phase 2 credit for incomplete outputs.
3. **`task_success` penalized correct behavior** — Phase 3 asking for clarification on ambiguous queries scored 0.0, although asking is the appropriate action.
4. **Single metric insufficient** — a production system has multiple quality dimensions; collapsing everything to one lenient metric hides real differences.

---

## 1. Systems under evaluation — FREEZE

Both systems are frozen at fixed commits. Neither is modified in response to any v2 result (see §8, Commitment).

| System | Branch / source | Commit | Notes |
|---|---|---|---|
| **Agentic RAG** (Phase 3) | `main` (production), release v3.2.0 | `62e28328ee468851dc6dc04a0b1d6c58626863e5` (2026-05-27) | System under test |
| **Pipelined RAG** (Phase 2) | `v2-pipelined-RAG-archive` | `34397f9` | Frozen archive baseline |

**Freeze contract for Phase 3.** The agent code under test is exactly the v3.2.0 agent. The evaluation branch (`feature/eval-v2-comprehensive`, created from `develop`) adds **only** benchmark, script, and report files. It does **not** modify `src/elh_rag/agent/` or `src/elh_rag/tools/`. This is to be verified with a diff before Phase B.

**Disclosure (to be repeated in the thesis).** Phase 3 was refined on formative stakeholder feedback during development through 2026-05-27 (including iterative human-eval rounds dated 2026-05-18 and 2026-05-20). Two behaviors that matter for this evaluation are explicit, prompt-level policies present in the frozen system:
- **Rule 12 — ambiguous entity references.** A general policy: when a query uses terms that may refer to ELH-the-company or to individual landlords (`hosts`, `staff`, `support`, `they`, `team`), the agent asks for clarification before searching. **The system prompt contains a worked example whose query is verbatim the formative `semantic_04` query ("how responsive are the hosts?").** Consequence for design: see §3, ambiguous category.
- **Rule 13 — weak-match flagging.** When semantic search returns low-similarity hits, the agent flags low confidence (the "similarity 0.42" behavior).

These are legitimate capabilities, but because they are prompt-engineered and one of them carries the formative eval query as its example, the golden set is designed to test them on **novel** cases (§3) and the thesis claims are calibrated to what the evaluation actually shows (general capability vs policy-specific capability).

**8 tools (frozen).** `find_rooms`, `find_available_rooms`, `compute_total_cost`, `answer_policy_question`, `get_property_details`, `get_booking_stats`, `search_descriptions`, `search_reviews`.

---

## 2. Hypotheses (falsifiable; reported regardless of outcome)

These state the *expected* direction. They are predictions, not conclusions. Each names what would falsify it.

- **H1 (per-category split).** On `factual_lookup` (1-hop), Phase 2 ties or wins. On multi-hop categories (`quantitative_reasoning`, multi-hop `constraint_satisfaction`), Phase 3 wins. *Falsified if* Phase 3 fails to beat Phase 2 on multi-hop categories.
- **H2 (the central architectural claim — dose-response).** The Phase-3-minus-Phase-2 gap on `task_success_v2` increases monotonically with `hop_count`. *Falsified if* the gap is flat or non-monotonic across hop counts. This is the strongest test because it predicts a *relationship*, not a single win, and it follows mechanistically from architecture (a fixed pipeline cannot chain steps).
- **H3 (computation).** On `quantitative_reasoning`, Phase 3 ≥ Phase 2 on `computational_correctness` (M2). *Falsified if* Phase 2 produces correct totals as often as Phase 3. (Format-independent metric; immune to presentation polish.)
- **H4 (refusal & clarification).** Phase 3 > Phase 2 on `refusal_appropriateness` (M3a, out-of-scope) and on `clarification_appropriateness` (M3b, ambiguous). For M3b, the gap on **novel** ambiguity types is reported separately from the entity-reference type. *Falsified if* Phase 3 does not exceed Phase 2, or if Phase 3's M3b advantage is confined to the entity-reference type (→ honest finding: disambiguation is policy-specific, not general).
- **H5 (latency — expected Phase-2 advantage).** Phase 2 is faster (lower mean/median/p95 latency). Reported in main results, not hidden. *Falsified if* Phase 3 is as fast or faster.
- **H6 (multilingual).** Phase 3 maintains task quality across IT/PT/ES/DE, i.e. non-EN content correctness is close to EN. *Falsified if* quality degrades materially in non-EN.

---

## 3. Golden set v2 — specification

**File:** `benchmarks/queries/golden_set_v2.yaml`. **Total: 96 queries.** Designed **after** the §1 freeze, by the author, and frozen before any run (commit + sha256 recorded in §9).

### 3.1 Categories (need-first, derived from user intent — not from the tool list)

| # | Category | User need | Tool(s) it tends to exercise | N |
|---|---|---|---|---|
| 1 | `factual_lookup` | "find me X", simple search | find_rooms, get_property_details | 12 |
| 2 | `constraint_satisfaction` | multi-filter / date-bounded search | find_rooms, find_available_rooms | 14 |
| 3 | `quantitative_reasoning` | a total / comparison must be computed | find_available_rooms + compute_total_cost, get_booking_stats | 16 |
| 4 | `policy_rules` | rules & policies | answer_policy_question | 12 |
| 5 | `subjective_descriptions` | subjective feature from descriptions | search_descriptions | 10 |
| 6 | `subjective_reviews` | subjective experience from reviews | search_reviews | 10 |
| 7 | `underspecified_ambiguous` | more than one valid reading → clarify/assume-and-state | (none on first turn) | 12 |
| 8 | `out_of_scope` | no answer the system should give → refuse + explain | (none) | 10 |

Cell sizes are a **statistical-power** choice (enough queries per category, and extra for `quantitative_reasoning` because it feeds the deterministic M2), **not** a claim about real-world query frequency. Demand frequency is handled separately and explicitly in §7.

### 3.2 The `hop_count` tag (objective, fixed on the query)

`hop_count` = the **minimum number of distinct retrieval-or-computation steps a correct answer requires**, decided from the query text **before** seeing any system output.
- 1-hop: "Show me single rooms in Lisbon" (one filtered retrieval).
- 2-hop: "Cheapest available room in Porto in September" (find available → select min price).
- 3-hop: "Total cost for 6 months in the cheapest available room in Lisbon from September" (find available → select min → compute total).

Pooled target distribution: ~45 at 1-hop, ~30 at 2-hop, ~21 at 3+ hop. This tag drives the H2 dose-response analysis.

### 3.3 The `language` tag (orthogonal — not a category)

Language is a property of any query, not a need. ~18 of 96 queries are non-EN (IT/PT/ES/DE), **distributed across categories**, not concentrated. The rest EN.

### 3.4 The `difficulty` tag

~40% easy / ~40% medium / ~20% hard.

### 3.5 The ambiguous category — fairness rule (critical)

Because Rule 12 is a prompt-level policy whose worked example **is** a formative eval query, testing Phase 3 on that query (or close kin) measures recall of its own prompt, not capability. Therefore:
- Of the 12 ambiguous queries, **~9 are NOVEL ambiguity types** the system prompt has **no** worked example for: underspecified constraint ("a cheap room near the university" — which university? how cheap?), ambiguous location ("a room in the centre" — which city?), ambiguous time ("available for next semester" — which dates?), ambiguous quantity ("a big room" — how big?).
- **~3 are entity-reference** (ELH-vs-landlord) ambiguities, kept **separate and minoritarian**, and **never** the verbatim "responsive hosts" query.
- M3b (clarification) is reported **split**: novel vs entity-reference. This turns the eval itself into a generalization test (see H4).

A query is *ambiguous* (→ clarify or assume-and-state) and distinct from *out_of_scope* (→ refuse + explain, e.g. the real meeting case: a Portuguese request for landlord personal data, correctly declined with the booking process explained).

### 3.6 Leakage controls

The golden set is **disjoint** from both prior query sets:
- the 20-query TASK-17 golden set, and
- the formative human-eval queries (the `structural_/policy_/cost_/semantic_/multilingual_` items in `human_eval_2026-05-18…` and `human_eval_2026-05-20…`).

No verbatim reuse and no trivial paraphrase of either set.

---

## 4. Metrics (final set)

Seven measured dimensions plus one reported qualitatively. M8 (`category_coverage`) from the draft is **removed**: it re-compressed M1 through an arbitrary, movable threshold and added no information beyond per-category M1.

| ID | Metric | Type | Applies to | Definition |
|---|---|---|---|---|
| **M1** | `task_success_v2` | LLM judge (strict, 0/0.5/1.0) | all | Does the answer solve the user's task? (rubric §5.2) |
| **M2** | `computational_correctness` | deterministic | quantitative | 1.0 if the computed total is correct within ±1 EUR, else 0.0. Format-independent. |
| **M3a** | `refusal_appropriateness` | LLM judge | out_of_scope | 1.0 if refused with clear explanation; 0.0 if it confabulated an answer. |
| **M3b** | `clarification_appropriateness` | LLM judge | ambiguous | 1.0 if it clarified OR made and stated a reasonable assumption; 0.0 if it answered one reading as if it were the only one. **Reported split: novel vs entity-reference.** |
| **M4** | `latency` | deterministic | all | mean, median, p95 (ms). Reported even where Phase 2 wins. |
| **M5** | `auditability` | qualitative | all (illustrative) | Phase 3 exposes which steps led to the answer (tool trace); Phase 2 is a black box. Reported via a worked trace example, **not** as a bar-chart count of tool calls (which would be circular). |
| **M6** | `answer_groundedness` | LLM judge (0/0.5/1.0) | all answerable | 1.0 all claims supported; 0.5 mostly grounded, one unsupported; 0.0 fabricated facts. Tested also on cases the prompt does not pre-flag. |
| **M7** | `multilingual_correctness` | LLM judge | non-EN | Two components: (a) responded in the query's language (yes/no); (b) content quality in that language, on the same scale as M1. Captures that multilingual does not degrade substance, not just form. |

---

## 5. Judge design

### 5.1 Models (judge ≠ generation model, by design)
- **Metric judges (M1, M3a, M3b, M6, M7):** Claude Haiku 4.5. Using a *different* model from the one generating answers reduces self-bias; this is a deliberate design choice, not an unverified caveat.
- **Strict judge (Phase D, lenient-vs-strict comparison):** Claude Sonnet 4.6. Judge quality matters most here, where we demonstrate the v1 leniency; worth the marginal cost.

### 5.2 Strict rubric (fixed here, used verbatim)
The judge always receives the query, category, difficulty, ground truth, and answer, and scores 0.0 / 0.5 / 1.0:
- **1.0 — fully solved:** addresses intent; cost queries include the **computed total** (not just components); list queries return relevant items; multi-hop completes all steps; ambiguous → clarifies OR assumes-and-states; impossible → refuses with explanation; same language as the query.
- **0.5 — partial:** addresses topic but misses a required component; correct but wrong language; one non-core hallucinated fact.
- **0.0 — not solved:** fabricates the core answer; empty / "I don't know" when a valid answer exists; confabulates instead of refusing/clarifying.
- Instruction: be strict; reserve 0.5 for genuinely borderline cases. Output JSON `{score, rationale}` only.

### 5.3 Two agreement checks (this is the rigor that answers "an AI judging an AI")
- **Judge vs human:** on the 25 human-eval queries (Phase E), compare judge scores to human annotator scores; report Cohen's kappa. Establishes the judge tracks human judgment.
- **Haiku vs Sonnet:** on ~30 queries, score with both models; report agreement. Demonstrates that the budget choice (Haiku for metric judges) did not degrade judgment quality. Low agreement on either check is itself reported honestly.

---

## 6. Analysis plan

- **Primary: per-category.** Mean of each metric by category, per system. Immune to weighting choices. This is where legitimate Phase 2 wins (e.g. `factual_lookup`) are shown in the main results.
- **Secondary: per-`hop_count` (the H2 curve).** Phase-3-minus-Phase-2 gap on M1 as a function of hop count. The central architectural argument.
- **Splits:** by difficulty; by language (M7); ambiguous split novel vs entity-reference (M3b).
- **Lenient vs strict (Phase D):** agreement %, pass→fail and fail→pass counts with examples; quantifies the v1 leniency.
- **Statistical honesty:** report n per cell; acknowledge medium statistical power at n=96; report agreement statistics for all judge-based claims.

---

## 7. Aggregation & the demand-weighting question

There are **no real ELH query logs.** The demo queries (author-chosen to showcase tools) and the human-eval categories (uniform by author choice) are *supply/coverage* signals, not measured demand. We do **not** claim an empirical demand distribution.

Aggregate scores (when reported at all) are presented as **sensitivity analysis over three pre-registered weight vectors over the 8 categories**, none privileged as "the truth":

| Category | Uniform | Plausible-demand (reasoned prior) | Simple-heavy (Phase-2-favorable stress test) |
|---|---|---|---|
| factual_lookup | 0.125 | 0.18 | 0.30 |
| constraint_satisfaction | 0.125 | 0.18 | 0.20 |
| quantitative_reasoning | 0.125 | 0.14 | 0.08 |
| policy_rules | 0.125 | 0.14 | 0.15 |
| subjective_descriptions | 0.125 | 0.10 | 0.07 |
| subjective_reviews | 0.125 | 0.08 | 0.06 |
| underspecified_ambiguous | 0.125 | 0.10 | 0.08 |
| out_of_scope | 0.125 | 0.08 | 0.06 |

- **Uniform**: no prior.
- **Plausible-demand**: a *reasoned prior* from the student booking journey (finding/filtering rooms and checking cost/availability dominate; subjective and edge cases are the tail), plus two qualitative signals — the demo notes availability is "a question the sales team asks every day", and the meeting showed out-of-scope requests do occur. **Labeled a reasoned prior, not a measurement.**
- **Simple-heavy**: deliberately overweights 1-hop categories where Phase 2 is strong. If Phase 3 still wins/ties here, the result is robust; if Phase 2 wins here, that is reported honestly and is expected.

Weights are applied at aggregation time to the per-category means (which were measured with fixed cell sizes). The per-category and per-hop results remain primary and are independent of any weighting.

---

## 8. Budget plan & cost gate

- **Budget:** $5.70 USD API credit.
- **Levers:** L1 metric judges on Haiku ($1/$5 per MTok) instead of Sonnet ($3/$15); L2 deterministic metrics (M2, M4) are free; L4 prompt caching on the agent system prompt + tool definitions for the run; L5 Batch API (50% off) for all offline judge scoring.
- **Estimate:** ~$3.70 total, leaving ~$2.00 margin for a re-run.
- **COST GATE (hard rule):** the full 96-query run launches **only** if the 5-query smoke-test projection (run + judging) is **≤ $4.50**. Otherwise: STOP, reduce N or move the strict judge to Haiku, and re-project. No blind full run.

---

## 9. Freeze record (filled at commit time, before any run)

- Phase 3 commit: `62e28328ee468851dc6dc04a0b1d6c58626863e5` (v3.2.0, 2026-05-27)
- Phase 2 commit: `34397f9` (v2-pipelined-RAG-archive)
- `golden_set_v2.yaml` sha256: `__TO BE FILLED WHEN THE SET IS FROZEN__`
- This pre-registration commit hash: `__git records this automatically on commit__`

---

## 10. Commitment

1. **All results reported in full, regardless of direction.** Phase 2 wins appear in the main results, not relegated to an appendix.
2. **The system is not modified in response to results.** If, after seeing v2 results, the system is improved (e.g. extending the clarification policy), that is a **new, dated experiment outside this pre-registration**, requiring a fresh held-out set. The v2-as-frozen results are not replaced or hidden.
3. **The honest path on a discovered limitation** is: report it as a finding in the thesis (Discussion), and propose the fix as future work — *not* patch-and-re-measure on the same set.
4. This document is amended only by dated addenda below.

---

## 11. Limitations (acknowledged up front)

1. **Single corpus** (ELH) — results may not transfer to other domains.
2. **n = 96** — medium statistical power; per-cell n is small, hence per-category + pooled hop analysis rather than fine slicing.
3. **Author-constructed evaluation** — no independent blinding of set design; pre-registration + freeze + leakage controls are the mitigation, not a substitute for an external evaluator.
4. **LLM judge** — mitigated by judge≠generator, fixed rubric, and the two agreement checks (§5.3); residual risk acknowledged.
5. **No real query logs** — aggregate weights are reasoned priors under sensitivity analysis (§7), never presented as measured demand.
6. **Asymmetric refinement** — Phase 3 received formative polish that the frozen Phase 2 did not. Mitigated by leaning on the format-independent deterministic metric (M2) and the architectural hop-count axis (H2) for the core claims, and by disclosing this explicitly (§1).

---

### Addendum 2026-06-19 — Dataset characteristics found during Phase A reconnaissance (before any system run)

1. **Reservation calendar coverage.** The provided reservation table spans
   2023-01 to 2024-11 only; no reservations exist in 2025–2026. Therefore
   `find_available_rooms` excludes no rooms for any future-dated window (verified:
   0 overlaps for Sep 2026; control: 483 overlaps for Sep 2024).
   - Decision: date-bearing golden-set queries use realistic future windows
     (2026–2027). On these, the behavior under test is season-aware pricing and
     multi-tool chaining, NOT occupancy exclusion; claims are calibrated
     accordingly. The exclusion mechanism is verified to work on 2023–2024 windows
     and is reported as a dataset limitation, not a system limitation.
   - H2 (hop-count dose-response) is unaffected: multi-hop quantitative queries
     still require chaining find_available_rooms → compute_total_cost regardless of
     whether the availability filter removes any row.
2. **Dirty data.** One Porto room has a non-positive autumnprice (−€20); all
   price-based ground truth excludes autumnprice <= 0.
3. **Two room-count lenses.** find_rooms reports a row count (556 Lisbon / 376
   Porto) without version dedup; compute_total_cost / get_property_details use
   distinct-room counts (435 / 295). "How many rooms" ground truth uses the row
   lens (the user-visible total_matches).
4. **M2 ground-truth anchors.** Eight anchor rooms (§J of the data reference) with
   all compute_total_cost fields were captured; worked totals A1 and A8 were
   independently re-verified by hand against the frozen formula. M2 ground truth is
   computed only on fully-specified catalogue rooms, never estimated.

These are data characteristics, not design changes: taxonomy, metrics, hop
definition, judge design, and weight scenarios are unchanged.

### Addendum 2026-06-19 (b) — Synthetic data disclosure

The catalogue, pricing, reservation, review and policy data are SYNTHETIC,
generated by an author-written population script (direct access to ELH's
production database was not granted). Consequences:
- All Phase 2 vs Phase 3 comparisons remain valid: both systems run on the
  identical dataset, so any difference is attributable to architecture, not data.
- No claim is made about real-world ELH catalogue statistics, market prices, or
  real query/demand distributions. Figures in the data reference describe the
  synthetic corpus only.
- System behaviors measured (computation, chaining, disambiguation, grounding,
  multilingual handling) are real regardless of data realism.
This positions the evaluation as a controlled architectural comparison on a
domain-representative synthetic testbed, not a production-data study.

### Addendum 2026-06-23 — Golden set frozen

Phase A complete. The 8 cassettes were merged into a single artifact:
- benchmarks/queries/golden_set_v2.yaml — 96 queries
- Composition: out_of_scope 10, policy_rules 12, subjective_reviews 10,
  subjective_descriptions 10, underspecified_ambiguous 12, factual_lookup 12,
  constraint_satisfaction 14, quantitative_reasoning 16.
- Languages: 82 EN + 14 non-EN (IT/PT/ES/DE 3 each, FR 2).
- hop_count distribution: 0→22, 1→58, 2→8, 3→8. NB the ≥2-hop evidence for H2
  rests on 16 queries (8 at hop-2, 8 at hop-3); the dose-response is reported
  with the corresponding statistical uncertainty.
- sha256: 17a9d590ff6b7d15e2ac5c87640a649581b1ba7d6f4a1cffdae64c0157d5849f
- Merge script: benchmarks/queries/_merge_golden_set.py (deterministic order).
- M2 ground-truth totals independently validated against the frozen
  compute_total_cost implementation (all 16 quantitative queries match to ±1 EUR).

From this commit the golden set is immutable. Any change requires a new dated
addendum and re-hashing.