# M6 Step 2 — Judge context-sensitivity analysis

Read-only analysis joining judge scores, human scores (from `m6_human_eval.xlsx`), and the truth-table size / actual prompt token count of all 52 M6-repaired judge calls. No API calls were made: prompt token counts are the **actual measured `usage.in`** values recorded in `results_M6_repaired.jsonl` when the batch was run, not an estimate.

## Verdict

**No general, monotonic evidence that the judge degrades as the truth table grows.** Across all 52 records, Spearman correlation between size (row count or actual prompt tokens) and judge score, human score, delta, or |delta| is weak in every case (|rho| <= 0.14) and never significant (p >= 0.31, section 4). Whatever is happening at the extremes is not a smooth, sample-wide trend.

**The one place agreement collapses is small, and has a rival explanation that isn't judge behaviour at all.** The >200-row bin (n=8 records, but only **4 distinct queries** — each scored once per system) is where kappa drops to 0.06 (chance level) and exact agreement drops to 50% (section 2). The sharpest case is `factual_lookup_12` (532 rooms, both phase2 and phase3): judge=0.0, human=1.0 both times. But the human's own note for that record says the specific examples were "ammessi per beneficio del dubbio... compatibili con le 492 righe non visibili della tabella" (492 = 532 minus the 40-row cap the Step-1 workbook renders for readability). **The human was scoring a 40-row excerpt; the judge was scoring the complete 532-row table.** That is a confound built into the human-eval instrument, not evidence about the judge's context handling — on this record the judge, which could see rows 41-532, may simply have caught something the truncated human view structurally could not. This directly undermines using the large-row bin's low kappa as proof of judge degradation: part or all of the gap could be the human's information deficit, not the judge's.

**The two signals that would most directly fingerprint "judge chokes on long context" both point the other way.** Truncation at max_tokens (verbose rationale cut off) is 0/8 in the large-row bin and concentrates instead in the medium bin (7/16) and the third token quartile, not the fourth/highest (section 6). The judge's own hedge score (0.5) is 0/8 in the large-row bin, concentrating instead in small (6/28) and medium (5/16) (section 7). If long tables were overwhelming the judge, both of these should skew toward the largest tables — they don't.

**Bottom line:** the evidence for size-driven judge degradation is weak and not separable from two other explanations at this sample size: query difficulty (ruled out — human score does not drop with size either, rho=-0.02, p=0.89, section 5) and an instrument confound (not ruled out — the human literally saw less truth-table content than the judge on exactly the records driving the large-bin disagreement). Before trusting the large-bin kappa as a judge finding, re-score `factual_lookup_12` (and ideally `factual_lookup_05`/`factual_lookup_11`, the other two large-bin queries with disagreement) with the human given the untruncated table. Until then: **not proven, and the cleanest available signals (truncation, hedging) argue against it.**

## 1. Per-record data

| query_id | system | n_truth_rooms | prompt_tokens | judge | human | delta | agree | truncated |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|
| constraint_satisfaction_08 | phase3 | 0 | 1182 | 1.0 | 1.0 | 0.00 | Y |  |
| constraint_satisfaction_08 | phase2 | 0 | 1472 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_08 | phase3 | 0 | 1055 | 1.0 | 1.0 | 0.00 | Y |  |
| factual_lookup_08 | phase2 | 0 | 1023 | 1.0 | 1.0 | 0.00 | Y |  |
| factual_lookup_09 | phase3 | 0 | 1279 | 0.5 | 0.0 | 0.50 | N |  |
| factual_lookup_09 | phase2 | 0 | 1471 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_06 | phase3 | 1 | 1447 | 0.5 | 1.0 | -0.50 | N |  |
| factual_lookup_06 | phase2 | 1 | 1673 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_02 | phase3 | 9 | 1430 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_02 | phase2 | 9 | 1580 | 0.0 | 1.0 | -1.00 | N |  |
| factual_lookup_03 | phase3 | 20 | 3657 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_03 | phase2 | 20 | 3378 | 0.0 | 0.0 | 0.00 | Y | Y |
| constraint_satisfaction_10 | phase3 | 27 | 5098 | 1.0 | 1.0 | 0.00 | Y |  |
| constraint_satisfaction_10 | phase2 | 27 | 4110 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_13 | phase3 | 27 | 4703 | 1.0 | 1.0 | 0.00 | Y |  |
| constraint_satisfaction_13 | phase2 | 27 | 4379 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_04 | phase3 | 29 | 4994 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_04 | phase2 | 29 | 4323 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_01 | phase3 | 35 | 5081 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_01 | phase2 | 35 | 4955 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_09 | phase3 | 41 | 5844 | 1.0 | 1.0 | 0.00 | Y |  |
| constraint_satisfaction_09 | phase2 | 41 | 5565 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_07 | phase3 | 42 | 5995 | 1.0 | 0.0 | 1.00 | N |  |
| constraint_satisfaction_07 | phase2 | 42 | 5803 | 0.0 | 0.0 | 0.00 | Y | Y |
| constraint_satisfaction_02 | phase3 | 47 | 6931 | 1.0 | 0.0 | 1.00 | N |  |
| constraint_satisfaction_02 | phase2 | 47 | 6628 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_14 | phase3 | 48 | 6832 | 0.0 | 1.0 | -1.00 | N | Y |
| constraint_satisfaction_14 | phase2 | 48 | 6239 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_03 | phase3 | 59 | 7350 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_03 | phase2 | 59 | 6825 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_12 | phase3 | 63 | 7927 | 0.5 | 0.0 | 0.50 | N |  |
| constraint_satisfaction_12 | phase2 | 63 | 7571 | 0.0 | 0.0 | 0.00 | Y | Y |
| constraint_satisfaction_06 | phase3 | 64 | 8429 | 1.0 | 1.0 | 0.00 | Y |  |
| constraint_satisfaction_06 | phase2 | 64 | 8151 | 0.0 | 0.0 | 0.00 | Y | Y |
| constraint_satisfaction_05 | phase3 | 78 | 9011 | 0.5 | 0.0 | 0.50 | N | Y |
| constraint_satisfaction_05 | phase2 | 78 | 8499 | 0.0 | 0.0 | 0.00 | Y | Y |
| factual_lookup_07 | phase3 | 92 | 10539 | 0.5 | 0.5 | 0.00 | Y | Y |
| factual_lookup_07 | phase2 | 92 | 10347 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_11 | phase3 | 156 | 16483 | 0.0 | 0.0 | 0.00 | Y |  |
| constraint_satisfaction_11 | phase2 | 156 | 16018 | 1.0 | 0.0 | 1.00 | N |  |
| factual_lookup_10 | phase3 | 169 | 19575 | 0.5 | 1.0 | -0.50 | N |  |
| factual_lookup_10 | phase2 | 169 | 19588 | 0.0 | 0.0 | 0.00 | Y | Y |
| factual_lookup_04 | phase3 | 188 | 20548 | 1.0 | 1.0 | 0.00 | Y |  |
| factual_lookup_04 | phase2 | 188 | 20542 | 0.0 | 0.0 | 0.00 | Y | Y |
| factual_lookup_05 | phase3 | 203 | 20615 | 1.0 | 1.0 | 0.00 | Y |  |
| factual_lookup_05 | phase2 | 203 | 20318 | 1.0 | 0.0 | 1.00 | N |  |
| factual_lookup_11 | phase3 | 375 | 36165 | 0.0 | 0.5 | -0.50 | N |  |
| factual_lookup_11 | phase2 | 375 | 36596 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_12 | phase3 | 532 | 53859 | 0.0 | 1.0 | -1.00 | N |  |
| factual_lookup_12 | phase2 | 532 | 53826 | 0.0 | 1.0 | -1.00 | N |  |
| factual_lookup_01 | phase3 | 556 | 52981 | 0.0 | 0.0 | 0.00 | Y |  |
| factual_lookup_01 | phase2 | 556 | 53095 | 0.0 | 0.0 | 0.00 | Y |  |

## 2. Binned by truth-table row count (n_truth_rooms)

| bin | n | mean judge | mean human | mean delta (judge-human) | exact agreement % | kappa |
|---|---:|---:|---:|---:|---:|---:|
| small (<50) | 28 | 0.393 | 0.321 | 0.071 | 64.3 | 0.372 |
| medium (50-200) | 16 | 0.344 | 0.219 | 0.125 | 68.8 | 0.452 |
| large (>200) | 8 | 0.250 | 0.438 | -0.188 | 50.0 | 0.059 |

## 3. Binned by prompt-token quartile (actual usage.in)

Quartile boundaries (tokens): Q1 <= 4270 < Q2 <= 6726 < Q3 <= 16134 < Q4

| bin | n | token range | mean judge | mean human | mean delta | exact agreement % | kappa |
|---|---:|---|---:|---:|---:|---:|---:|
| Q1 | 13 | 0-4270 | 0.346 | 0.385 | -0.038 | 69.2 | 0.469 |
| Q2 | 13 | 4270-6726 | 0.423 | 0.231 | 0.192 | 69.2 | 0.464 |
| Q3 | 13 | 6726-16134 | 0.385 | 0.192 | 0.192 | 53.8 | 0.212 |
| Q4 | 13 | 16134-53859 | 0.269 | 0.423 | -0.154 | 61.5 | 0.278 |

## 4. Correlations (Spearman, n=52)

| x | y | rho | p | significant (p<0.05)? |
|---|---|---:|---:|:---:|
| n_truth_rooms | judge_score | -0.139 | 0.3247 | no |
| n_truth_rooms | human_score | -0.020 | 0.8885 | no |
| n_truth_rooms | delta (judge-human) | -0.100 | 0.4796 | no |
| n_truth_rooms | |delta| | 0.134 | 0.3427 | no |
| prompt_tokens | judge_score | -0.120 | 0.3985 | no |
| prompt_tokens | human_score | 0.004 | 0.9775 | no |
| prompt_tokens | delta (judge-human) | -0.102 | 0.4739 | no |
| prompt_tokens | |delta| | 0.144 | 0.3075 | no |

n=52 for the whole-sample correlations. Per-bin subgroup stats above (section 2/3) have n as low as 8 (large-table bin) — treat those subgroup numbers as descriptive, not statistically decisive.

## 5. Confound check — does the human score also drop with size?

| predictor | outcome | rho | p |
|---|---|---:|---:|
| n_truth_rooms | human_score | -0.020 | 0.8885 |
| n_truth_rooms | judge_score | -0.139 | 0.3247 |
| prompt_tokens | human_score | 0.004 | 0.9775 |
| prompt_tokens | judge_score | -0.120 | 0.3985 |

## 6. Truncation check (10/52 judge responses hit max_tokens)

| bin | truncated | total | % truncated |
|---|---:|---:|---:|
| small (<50) | 3 | 28 | 10.7 |
| medium (50-200) | 7 | 16 | 43.8 |
| large (>200) | 0 | 8 | 0.0 |

| token quartile | truncated | total | % truncated |
|---|---:|---:|---:|
| Q1 | 1 | 13 | 7.7 |
| Q2 | 1 | 13 | 7.7 |
| Q3 | 6 | 13 | 46.2 |
| Q4 | 2 | 13 | 15.4 |

Overall truncation rate: 10/52 = 19.2%.

## 7. Judge vs human use of the 0.5 (hedge) score, per size bin

| bin | judge=0.5 | human=0.5 | n |
|---|---:|---:|---:|
| small (<50) | 6 | 0 | 28 |
| medium (50-200) | 5 | 1 | 16 |
| large (>200) | 0 | 1 | 8 |
| **all** | **11** | **2** | **52** |
