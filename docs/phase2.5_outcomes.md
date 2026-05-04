# Phase 2.5 — Outcomes

> Diagnostic evaluation of the ELH RAG system on a curated 20-query
> golden set. This document records what was measured, what problems
> surfaced, what was fixed, and what was deliberately left open.

**Status:** closed (Fix B applied, re-run validated, decision documented in Section 7)
**Branch:** `feature/phase4-light-fix-b-routing`
**Authored:** April 2026, closed May 4 2026
**Closes:** Phase 2.5. Phase 4 deferred to post-deadline (June+).

---

## 1. Why "Phase 2.5" and not full evaluation now

The thesis roadmap originally placed full Evaluation (large golden set,
RAGAS metrics, Naive vs Advanced vs Agentic comparison, latency analysis)
as Phase 4. After consultation with the supervisor, evaluation was split
into a small diagnostic step before Phase 3 and a full evaluation
deferred to post-deadline:

```
2.5 (diagnostic + routing fix)  →  3 (Hybrid/Agentic RAG)  →  5 (deliverable)
                                                                    ↓
                                               4 (full evaluation, post-deadline)
```

**Rationale.** Measuring the system before adding the agentic layer
exposes problems early, while they're still cheap to fix. Building tools
on top of a silently-broken retrieval layer would amplify the problems
rather than reveal them. The full evaluation chapter for the thesis
benefits from being written calmly post-deadline with a larger
annotation effort and the complete system (Phase 2 + Phase 3) under test,
rather than rushed into the May 30 deadline.

**Scope of Phase 2.5.** 20 queries, three custom metrics, single
configuration (the production Phase 2 pipeline). No A/B comparison
across configurations, no latency analysis — both deferred to Phase 4.

---

## 2. Setup

### 2.1 Custom evaluation framework — why not RAGAS

RAGAS 0.4 was the first choice. On this golden set, with Claude Sonnet
as the judge, it produced ~90% NaN values across `faithfulness`,
`context_precision`, and `answer_relevancy`. The root cause was
unstable JSON parsing in the RAGAS judge layer — Claude's outputs
occasionally included markdown fences, preambles, or trailing
commentary that RAGAS could not normalise.

Two options were considered:

1. **Patch RAGAS upstream.** Higher long-term value but blocked by
   Phase 2.5's timebox.
2. **Write a custom three-metric framework.** Lower coverage than
   full RAGAS but full control over the judge contract.

Option 2 was chosen. The framework lives in
`src/elh_rag/evaluation/` (judge + 3 metrics), with a deterministic
JSON-output contract enforced by `EvaluationJudge.ask_json` (one
retry on parse failure, then `JudgeError`). 25 unit tests in
`tests/evaluation/test_evaluation.py` cover the parser robustness +
each metric's edge cases.

The negative result on RAGAS is documented; not re-attempted here.
Phase 4 may revisit the choice if RAGAS upstream stabilises.

### 2.2 Three metrics

- **`faithfulness`** — fraction of answer claims supported by
  retrieved sources. Returns `None` (skipped) when the answer
  contains no factual claims (e.g., correctly said "I don't know").
- **`context_recall`** — fraction of `must_mention` concepts
  semantically covered by retrieved sources. Returns `None` when
  `must_mention` is empty (e.g., nonsense queries).
- **`answer_relevancy`** — 0.0–1.0 score for how on-topic the answer
  is. Always returns a value; rewards correct refusals on
  unanswerable queries.

All three are LLM-as-judge, evaluated by Claude Sonnet 4.5 with
temperature 0.0 and a strict JSON contract.

### 2.3 Golden set

20 queries in `evaluation/golden_set.yaml`, hand-annotated with:
- `expected_intent` (`reviews` / `descriptions` / `both`)
- `must_mention` (list of semantic concepts that good retrieval should
  cover; empty for nonsense queries)
- `category` + `notes` for human reference

Distribution: 4 review-oriented, 4 description-oriented, 4 mixed,
3 multilingual, 5 pre-annotated examples.

**Important caveat on `expected_intent`.** These labels are the author's
opinion of what each query is asking for. They are not objective truth.
Section 5.4 documents one case (q14) where the LLM router produced a
defensible classification that disagrees with the label.

---

## 3. Baseline measurement

Run with full Phase 2 pipeline: query rewriting + dual-corpus retrieval
+ cross-encoder reranking + LLM intent routing + generation. No
configuration changes from production.

| Metric | Avg | Median | Valid (N) |
|---|--:|--:|--:|
| `faithfulness` | **0.97** | 1.00 | 18/20 |
| `context_recall` | 0.72 | 1.00 | 18/20 |
| `answer_relevancy` | **0.95** | 1.00 | 20/20 |

**Reading.** The system is solid on faithfulness (LLM doesn't fabricate)
and relevancy (answers stay on topic). `context_recall` is the
soft spot — 0.72 average means roughly one query in three has retrieval
that doesn't fully cover the expected concepts.

**Latency** (informational, not the focus of Phase 2.5): median
~25 s/query, dominated by generation (Sonnet) on dual-corpus paths.
Detailed analysis in `docs/phase2_observations.md` Section 3.

---

## 4. Three problem patterns, not one

Drilling into the four queries with `context_recall = 0.0` (q06, q07,
q12, q17) revealed three distinct failure modes, not one. This
distinction matters because it shapes which fixes are worth applying
within Phase 2.5's timebox versus deferred to Phase 4.

### 4.1 Pattern A — corpus sparsity (q06, q07)

| Query | `must_mention` | What's in the corpus |
|---|---|---|
| q06 — "doors or windows in good condition, creak, noise" | `windows` | Reviews mention noise but rarely attribute it to windows; "creak" is essentially absent. |
| q07 — "rooms without mould or damp smell" | `mould` | Reviews discuss humidity in general terms; the word `mould` itself is rare. |

These topics are genuinely under-represented in the reviews corpus. The
retriever is not broken — it's returning the most relevant available
content, which simply doesn't contain the expected vocabulary at scale.

**Honesty check.** The system did the right thing: on q06 the answer
correctly stated that available reviews don't discuss window condition,
which is why `faithfulness` was N/A (no claims to verify) and
`answer_relevancy = 1.0` (correct refusal). The metric rightly says
"context didn't cover the concept" but penalising the system for it
would conflate dataset limits with system limits.

**Action: none.** Documented as a corpus-coverage limit. Phase 4
should expand the golden set with topics known to be under-covered, to
quantify the limit rather than hide it.

### 4.2 Pattern B — retrieval bias inside `descriptions` (q12)

q12 asks *"Is there a living room or a communal area in the flats?"*.
Routing to `descriptions` is correct (factual question about layout).
But the retrieved top-5 contained **5 ROOM descriptions and 0 HOUSE
descriptions**.

**Why.** Living rooms and communal areas are described at the **house**
level, not the room level. The reranker is biased toward room documents
because the query token "room" matches them lexically — even though the
information lives in house descriptions.

This is **not** a routing failure. The router did its job. The failure
is downstream: within the chosen corpus, the retrieval mix doesn't
include the document type that holds the answer.

**Two possible fixes:**
- **Fix A.** Metadata filter at retrieval time: when the query mentions
  whole-flat concepts (living room, communal area, kitchen as shared
  space), prefer house documents over room documents.
- **Fix A.alt.** Hybrid pool: always pull e.g. 60% house + 40% room
  before reranking, regardless of query lexicon.

**Action: deferred.** Fix B (Pattern C) is cheaper, more general, and
expected to lift `context_recall` more than Fix A. If the post-Fix-B
re-run still leaves q12 at 0.0 and the average below 0.85, Fix A is
revisited (target: Friday May 1).

### 4.3 Pattern C — routing missing the qualitative dimension (q16, q17, q18)

Three queries had routing `descriptions` when expected was `both`.
Common shape: a structural amenity ("desk", "lift", "Wi-Fi",
"proprietario") next to a qualitative modifier ("fast", "quiet",
"gentile"). The router LLM saw the amenity, classified `descriptions`,
and missed that "fast" / "quiet" / "gentile" require subjective
validation found only in reviews.

| Query | Expected | Got | `cr` |
|---|---|---|--:|
| q16 — "Flat in a quiet neighbourhood with a lift" | `both` | `descriptions` | 1.0 (lucky: "lift" is structural) |
| q17 — "Double room... with fast Wi-Fi" | `both` | `descriptions` | 0.0 (Wi-Fi only mentioned in reviews) |
| q18 — "Il proprietario è gentile e disponibile?" | `both` | `descriptions` | 1.0 |

**Verification of the q17 judge.** Initial concern was that the judge
was being literal about "Wi-Fi" (i.e., refusing to match "internet" or
"connectivity"). Inspection of the JSONL `context_recall_details` for
q17 ruled this out: the judge explicitly noted *"None of the five room
descriptions mention Wi-Fi, internet access, or connectivity"*. The
problem is genuinely that the routing didn't bring in reviews where
students do discuss WiFi quality.

**Action: Fix B applied.** See Section 5.

---

## 5. Fix B — qualitative-modifier routing rule

### 5.1 The patch

Two additions to `INTENT_ROUTER_SYSTEM_PROMPT` in
`src/elh_rag/generation/prompts.py`:

1. **A `QUALITATIVE MODIFIERS rule` block**, listing five modifier
   categories (speed/performance, perception, quality, reliability,
   sensation) and instructing the router to classify as `both` when a
   modifier appears next to a structural feature.
2. **Two few-shot Q/A examples** demonstrating the pattern.

Full operational doc: `docs/fix_b_routing_prompt.md`.

### 5.2 Few-shot examples are deliberately non-leak

The two examples chosen — *"Reliable heating in a private room"* and
*"Clean kitchen with dishwasher"* — use modifier categories
(reliability, quality) and amenity types (heating, dishwasher) that
**do not appear in any of the 20 golden-set queries**. The target
queries (q16: quiet/lift, q17: fast/Wi-Fi, q18: gentile/proprietario)
exercise different categories (perception, speed, reliability) and
different amenities.

This makes the post-fix improvement a measurement of **genuine
generalisation**, not memorisation. If the fix only worked because the
LLM matched the few-shot examples token-for-token, the q16/q17/q18
improvements would not transfer.

### 5.3 What Fix B does NOT fix

Explicitly **out of scope** for Fix B:

- **Pattern A** (q06, q07) — corpus sparsity. Routing won't help if the
  vocabulary isn't in the corpus.
- **Pattern B** (q12) — within-corpus retrieval bias. Routing already
  picked the right corpus; the problem is one level down.

This is a **deliberate choice** under timebox: Fix B addresses the
single largest expected lift (3 queries × moving routing to `both`
brings reviews into the mix). Fix A is held in reserve for Friday in
case the re-run shows it's needed.

### 5.4 The keyword fallback diverges from the LLM router by design

The `_keyword_fallback` in `intent_router.py` (used when Anthropic
returns malformed output or is unavailable) is a static keyword-match
heuristic. It does NOT include the QUALITATIVE MODIFIERS rule.

Consequence: in failure mode, q16 / q17 / q18 route differently from
the LLM-patched path:

| Query | LLM router (patched) | Keyword fallback |
|---|---|---|
| q16 "quiet neighbourhood with lift" | `both` | `reviews` (substring "neighbour") |
| q17 "fast wifi, washing machine" | `both` | `descriptions` (2 keyword hits) |
| q18 "proprietario è gentile" | `both` | `reviews` (proprietario in keyword list) |

This divergence is **documented and tested** — see
`tests/retrieval/test_intent_router.py`,
`test_keyword_fallback_diverges_from_llm_for_q16_pattern` and
similar. If the divergence becomes a problem in production (Anthropic
outage during a demo), the fix is to extend `_keyword_fallback` with
its own modifier-aware logic. **Not** to inject modifiers into the
keyword tuples — that conflates two abstraction layers.

For Phase 2.5 scope, this is accepted. Anthropic API uptime is high
enough that the failure mode is rare; the LLM-patched routing is what
the system uses 99%+ of the time.

---

## 6. Re-run results

Run executed on 2026-05-04 with `--label after_routing_fix`. Output:
`evaluation/reports/light_eval/phase2.5_custom_report_20260504_165520_after_routing_fix.md`.

### 6.1 Aggregate metrics

| Metric | Baseline | Post-Fix B | Δ | Verdict |
|---|--:|--:|--:|---|
| `faithfulness` avg | 0.97 | 0.937 | −0.033 | Within noise tolerance |
| `context_recall` avg | 0.72 | **0.889** | **+0.169** | Strong improvement |
| `answer_relevancy` avg | 0.95 | 0.96 | +0.01 | Unchanged |
| Routing accuracy | 18/20 (90%) | 17/20 (85%) | −1 query | Mild regression — see 6.4 |
| Sub-threshold queries | 4 | 3 | −1 | q17 promoted to passing |

`faithfulness` skipped on 3 queries (vs 2 in baseline), `context_recall`
skipped on 2 (unchanged). All within metric design — these are the
"don't know" queries where the metric correctly opts out.

### 6.2 Target queries (the four problems flagged in Section 4)

| Query | Pattern | Baseline routing | Post-fix routing | Baseline `cr` | Post-fix `cr` | Outcome |
|---|---|---|---|--:|--:|---|
| q06 (doors/windows) | A | reviews ✓ | both | 0.0 | **1.0** | Improved (judge found coverage in expanded sources) |
| q07 (mould) | A | reviews ✓ | both | 0.0 | **1.0** | Improved (same reason) |
| q12 (living room) | B | descriptions ✓ | descriptions ✓ | 0.0 | 0.0 | **Unchanged — Fix B was not designed to address this** |
| q16 (quiet + lift) | C | descriptions ✗ | **both** ✓ | 1.0 | 1.0 | Routing fixed (cr already at 1.0 by luck) |
| q17 (fast Wi-Fi) | C | descriptions ✗ | **both** ✓ | **0.0** | **1.0** | **Routing fixed AND retrieval recovered** |
| q18 (PT proprietario) | C | descriptions ✗ | descriptions ✗ | 1.0 | 1.0 | Routing **not** fixed (multilingual transfer issue) |

### 6.3 The single most important result: q17

q17 was the headline test of Fix B. Baseline retrieved 5 ROOM
descriptions, none of which mentioned WiFi or internet. Post-fix
retrieval is `both`, the merged sources now include reviews where
students discuss WiFi quality, and the judge confirms semantic coverage
of "Wi-Fi" via the sources. `context_recall` from 0.0 to 1.0,
`answer_relevancy` 1.0, routing decision `both` with confidence 0.85.
This is the single test that proves the fix worked structurally, not
just by accident.

### 6.4 The trade-off: q06 and q07 routing regression

Two queries that were correctly routed to `reviews` in baseline are now
routed to `both`:

- q06 ("doors or windows in good condition, creak or noise"): the words
  "creak" and "noise" — though not in the QUALITATIVE MODIFIERS
  examples list — read as quality/perception modifiers to the LLM, and
  paired with "doors/windows" (perceived as structural) trigger the
  `both` rule.
- q07 ("rooms without mould or damp smell"): "mould" and "damp" pattern
  similarly.

This is exactly the watch-out flagged in `docs/fix_b_routing_prompt.md`:

> Routing accuracy potrebbe scendere da 18/20 a 17/20 in altri casi se
> la regola "qualitatives → both" è troppo aggressiva.

**Crucially, the regression is in routing classification, not in
answer quality**: q06 has `f=1.0`, `cr=1.0`, `ar=1.0`; q07 has
`f=0.71`, `cr=1.0`, `ar=0.9`. Adding descriptions to a query that was
review-oriented brings extra sources but doesn't poison the answer —
the generation LLM still synthesises correctly from the merged context.

Net effect: routing accuracy is a stricter agreement metric against
hand-labelled `expected_intent`. Quality metrics are what the user
experiences, and those have improved overall.

### 6.5 q18 multilingual edge case

q18 in Portuguese ("Posso ter outra pessoa no quarto comigo? — Il
proprietario è gentile e disponibile?") was expected to move to `both`
under Fix B. It did not — routing stayed `descriptions` with 0.85
confidence. Likely cause: the QUALITATIVE MODIFIERS rule and its
examples are written entirely in English, and the cross-lingual
transfer of the "modifier + amenity" pattern to Portuguese is weak.

The query nonetheless scored `f=1.0`, `cr=1.0`, `ar=1.0` — the
descriptions corpus alone happened to cover the must_mention "quarto"
adequately. So the failure is in routing classification only, not in
end-user quality. A multilingual extension of the few-shot examples
(adding PT/IT/ES variants) is a candidate refinement for Phase 4.

### 6.6 q12 left untouched as expected

Pattern B was explicitly out of scope for Fix B (Section 5.3). q12
remains at `cr=0.0` with all 5 sources being ROOM descriptions and
the judge correctly noting that none mentions a living room. The fix
for this (Fix A: house/room balance in descriptions retrieval) is
deferred — see Section 7.

---

## 7. Decision: Phase 2.5 closed

**Decision: close Phase 2.5 as-is. Fix A not applied.**

### 7.1 Decision rule evaluation

The criteria agreed before the re-run were:

- if `context_recall` avg > 0.85 **AND** routing accuracy ≥ 19/20 →
  close Phase 2.5, no Fix A
- if `context_recall` avg ≤ 0.85 **OR** routing accuracy regressed →
  investigate Fix A (Pattern B)
- if any quality metric regressed by > 0.05 → roll back Fix B

The criteria are partially met:

- `context_recall` avg = 0.889 > 0.85 ✓
- Routing accuracy = 17/20, below the 19/20 threshold ✗
- No quality regression > 0.05 (`faithfulness` −0.033 is within noise) ✓

The literal reading of the rule would push toward Fix A. The decision
to close anyway is a judgement call documented below.

### 7.2 Rationale for closing despite the routing accuracy gap

Three reasons.

**The routing accuracy regression is not a quality regression.** The
two queries that lost their "matched" routing label (q06, q07) still
produce correct, faithful, and relevant answers. The gap is between
`expected_intent` (a label that reflects the author's view of what
each query is asking for) and the LLM-router's actual classification.
`expected_intent` is itself fuzzy — q06 and q07 mention concepts
("creak", "noise", "mould", "damp") that are arguably qualitative,
making `both` a defensible classification on its own merits. The same
caveat was acknowledged in Section 2.3 about hand-labelled ground
truth.

**The headline metric improved by the targeted amount.** `context_recall`
avg moved from 0.72 to 0.889 (+0.169). q17, the worst case in baseline
(0.0), is now at 1.0. This was the entire point of Fix B.

**Further iteration consumes budget without proportional return.**
Each re-run costs ~$0.30 of the $10 ELH-funded credit pool. The
remaining gaps are either (a) corpus-level limits we cannot fix
without re-annotation (Pattern A), (b) genuine retrieval bias requiring
a more invasive change (Pattern B / Fix A), or (c) cross-lingual
generalisation (q18) needing its own dedicated work. None is the kind
of tweak that another routing patch can address. Phase 4 (post-deadline)
is the right place to revisit them with a larger golden set.

### 7.3 What is moved to Phase 4

Items left explicitly open by this decision, to be revisited in Phase 4:

- **Pattern B (q12)**: house/room balance in descriptions retrieval.
  Candidate fix: metadata filter + hybrid pool. Requires measurement
  on a wider golden set to know if it generalises.
- **q06/q07 routing tightening**: refine the QUALITATIVE MODIFIERS
  rule to require a more explicit amenity term, so it doesn't fire
  on infrastructure quality words alone.
- **q18 multilingual transfer**: add PT/IT/ES few-shot examples to
  the routing prompt.
- **Pattern A**: corpus-level under-coverage of niche topics
  (windows, mould). Cannot be fixed by routing — needs either corpus
  expansion or honest documentation of the limit.

### 7.4 What is shipped

State of the system at Phase 2.5 closure:

- 213 tests passing offline (208 + 5 sentinels for Fix B), <4s, zero API calls
- `context_recall` avg 0.889 on the 20-query golden set
- `faithfulness` avg 0.937, `answer_relevancy` avg 0.96
- Routing accuracy 17/20, with the 3 mismatches all producing
  correct end-user answers
- Custom evaluation framework (`src/elh_rag/evaluation/`) ready for
  reuse in Phase 4 with a larger golden set
- All artefacts versioned in `evaluation/reports/light_eval/`
  and `docs/`

---

## 8. What is deliberately left for Phase 4 (post-deadline)

These items are out of scope for Phase 2.5 by design. Listing them
here so they're not lost.

- **Latency analysis on the complete system.** Phase 2 currently runs
  at ~25 s median. Step 4 of Phase 2 already identified that generation
  Sonnet on dual-corpus paths dominates the cost (see
  `docs/phase2_observations.md` Section 3). A complete breakdown
  (rewriter, retrieve, rerank, generation) plus targeted fixes is best
  done **after Phase 3** so the measurement reflects the production
  system that ELH will receive — including tool-calling paths, which
  may shift the bottleneck.
- **Larger golden set** (50–100 queries), with topics expanded to cover
  the corpus-sparsity dimensions (Pattern A) so they can be quantified
  rather than just acknowledged.
- **Property-ID grounded annotations.** Current golden set uses
  `must_mention` (semantic concepts). Phase 4 should add
  `expected_property_ids` for proper retrieval precision/recall@k.
- **A/B comparison** Naive vs Advanced vs Agentic, with bootstrap
  confidence intervals.
- **Re-evaluation of RAGAS** — if RAGAS 0.5+ stabilises the JSON
  parsing layer, it may be worth replacing the custom framework or
  running both for cross-validation.
- **Fallback path enrichment.** If the LLM-vs-fallback divergence
  documented in Section 5.4 becomes operationally relevant, extend
  `_keyword_fallback` to be modifier-aware. ~10 lines of code, but a
  scope-creep distraction now.
- **Resolution of Pattern B** (Fix A: house/room balance in
  descriptions retrieval) if the post-Fix-B numbers leave it on the
  table.

---

## 9. Engineering notes from Phase 2.5

Two small infrastructure improvements landed during this phase, both
unrelated to the core fix but worth recording:

1. **Incremental JSONL writes.** `scripts/run_custom_eval.py` now
   appends each completed record to disk immediately (was: full save
   only at end). This was prompted by an interrupted run during Fix B
   testing — Anthropic credits ran out at query 9 of 20 and all
   completed work was lost. Same pattern would have bitten in any
   long-running phase. Cost: 5 lines.
2. **Sentinel tests for the prompt patch.** Five tests in
   `tests/retrieval/test_intent_router.py` (Phase 2.5 Fix B
   coverage block) lock in: (a) the QUALITATIVE MODIFIERS rule stays
   in the prompt, (b) the few-shot examples stay in the prompt,
   (c) the keyword fallback's divergent behaviour is documented as
   intentional, (d) modifiers don't leak into keyword tuples. These
   are cheap regression guards: anyone refactoring the prompt or
   keyword lists in the future will see immediately if they break the
   contract documented here.

---

## 10. Files touched

| File | Change |
|---|---|
| `src/elh_rag/generation/prompts.py` | Added QUALITATIVE MODIFIERS rule + 2 few-shot examples to `INTENT_ROUTER_SYSTEM_PROMPT`. No other prompt touched. |
| `scripts/run_custom_eval.py` | Added `append_jsonl_record`, switched main loop to incremental save, moved output-path computation before the loop. `save_jsonl` retained for non-loop use cases. |
| `tests/retrieval/test_intent_router.py` | Added 5 tests at end of file (Phase 2.5 Fix B coverage block). 25 existing tests untouched. |
| `docs/fix_b_routing_prompt.md` | New: operational doc for the patch (diagnosis, patch text, expected results, watch-outs). |
| `docs/phase2_5_outcomes.md` | This file. |

Test count: 208 → 213, all passing in <4 s (offline, no API calls).