# Phase 3 Agent Benchmark Report

- Generated: `2026-05-21 11:56 UTC`
- Run file: `agent_benchmark_2026-05-20-after-eval2-fixes.jsonl`
- Total queries: 20
- Success: 20  |  Failed: 0

## Overall

| Metric | Value |
|---|---|
| Tool routing coverage | 100% (20/20) |
| Failure rate | 0% (0/20) |
| Latency avg | 10.4 s |
| Latency p50 | 11.1 s |
| Latency p95 | 15.4 s |
| Latency max | 16.1 s |
| Hops avg | 2.2 |
| Hops max | 3 |
| Tokens in (avg / total) | 2683 / 53663 |
| Tokens out (avg / total) | 625 / 12495 |
| Cost total | $0.35 USD |

## Per category

| Category | n | Coverage | Lat. avg | Lat. p95 | Tok in (avg) | Tok out (avg) | Cost USD |
|---|---|---|---|---|---|---|---|
| cost | 4 | 100% (4/4) | 12.6s | 15.5s | 1969 | 892 | $0.08 |
| multilingual | 4 | 100% (4/4) | 10.1s | 13.6s | 2084 | 596 | $0.06 |
| policy | 4 | 100% (4/4) | 8.4s | 11.6s | 1824 | 373 | $0.04 |
| semantic | 4 | 100% (4/4) | 10.9s | 14.9s | 3356 | 540 | $0.07 |
| structural | 4 | 100% (4/4) | 10.1s | 12.0s | 4183 | 723 | $0.09 |

## Per language

| Language | n | Coverage | Lat. avg | Tok in (avg) | Tok out (avg) |
|---|---|---|---|---|---|
| de | 1 | 100% | 7.8s | 1271 | 460 |
| en | 16 | 100% | 10.5s | 2833 | 632 |
| es | 1 | 100% | 12.4s | 1686 | 774 |
| it | 1 | 100% | 6.5s | 1466 | 366 |
| pt | 1 | 100% | 13.8s | 3913 | 785 |

## Per query

| ID | Cat | Lang | Status | Tools used | Hops | Tok (in/out) | Lat. (s) | Coverage |
|---|---|---|---|---|---|---|---|---|
| structural_01 | structural | en | OK | find_rooms | 2 | 3768/754 | 12.3 | OK |
| structural_02 | structural | en | OK | find_rooms | 2 | 2352/721 | 8.7 | OK |
| structural_03 | structural | en | OK | find_rooms | 2 | 3825/688 | 8.9 | OK |
| structural_04 | structural | en | OK | find_rooms | 2 | 6787/730 | 10.5 | OK |
| policy_01 | policy | en | OK | answer_policy_question | 2 | 1320/253 | 6.2 | OK |
| policy_02 | policy | en | OK | answer_policy_question | 2 | 1442/339 | 7.4 | OK |
| policy_03 | policy | en | OK | answer_policy_question, search_descriptions | 3 | 3289/492 | 12.2 | OK |
| policy_04 | policy | en | OK | answer_policy_question | 2 | 1246/408 | 8.0 | OK |
| cost_01 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1730/762 | 11.7 | OK |
| cost_02 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1673/725 | 10.5 | OK |
| cost_03 | cost | en | OK | find_available_rooms, find_available_rooms, compute_total_cost, compute_total_cost | 3 | 2715/1261 | 16.1 | OK |
| cost_04 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1758/819 | 12.1 | OK |
| semantic_01 | semantic | en | OK | search_descriptions | 2 | 3215/538 | 15.4 | OK |
| semantic_02 | semantic | en | OK | search_reviews | 2 | 4008/374 | 12.2 | OK |
| semantic_03 | semantic | en | OK | search_descriptions | 2 | 5861/1154 | 11.9 | OK |
| semantic_04 | semantic | en | OK |  | 1 | 338/92 | 4.1 | OK |
| multilingual_01 | multilingual | it | OK | answer_policy_question | 2 | 1466/366 | 6.5 | OK |
| multilingual_02 | multilingual | pt | OK | find_available_rooms | 2 | 3913/785 | 13.8 | OK |
| multilingual_03 | multilingual | es | OK | find_available_rooms, compute_total_cost | 3 | 1686/774 | 12.4 | OK |
| multilingual_04 | multilingual | de | OK | answer_policy_question | 2 | 1271/460 | 7.8 | OK |
