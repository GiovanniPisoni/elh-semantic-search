# Phase 3 Agent Benchmark Report

- Generated: `2026-05-20 11:06 UTC`
- Run file: `agent_benchmark_2026-05-20-after-human-eval-fixes.jsonl`
- Total queries: 20
- Success: 20  |  Failed: 0

## Overall

| Metric | Value |
|---|---|
| Tool routing coverage | 100% (20/20) |
| Failure rate | 0% (0/20) |
| Latency avg | 9.6 s |
| Latency p50 | 10.2 s |
| Latency p95 | 12.6 s |
| Latency max | 13.0 s |
| Hops avg | 2.2 |
| Hops max | 3 |
| Tokens in (avg / total) | 2928 / 58558 |
| Tokens out (avg / total) | 647 / 12939 |
| Cost total | $0.37 USD |

## Per category

| Category | n | Coverage | Lat. avg | Lat. p95 | Tok in (avg) | Tok out (avg) | Cost USD |
|---|---|---|---|---|---|---|---|
| cost | 4 | 100% (4/4) | 10.7s | 12.2s | 2874 | 831 | $0.08 |
| multilingual | 4 | 100% (4/4) | 9.4s | 12.6s | 2258 | 621 | $0.06 |
| policy | 4 | 100% (4/4) | 7.7s | 11.8s | 1982 | 356 | $0.05 |
| semantic | 4 | 100% (4/4) | 9.6s | 12.5s | 3343 | 567 | $0.07 |
| structural | 4 | 100% (4/4) | 10.6s | 11.8s | 4183 | 861 | $0.10 |

## Per language

| Language | n | Coverage | Lat. avg | Tok in (avg) | Tok out (avg) |
|---|---|---|---|---|---|
| de | 1 | 100% | 7.0s | 1271 | 481 |
| en | 16 | 100% | 9.7s | 3095 | 654 |
| es | 1 | 100% | 13.0s | 2550 | 775 |
| it | 1 | 100% | 7.4s | 1297 | 438 |
| pt | 1 | 100% | 10.2s | 3913 | 789 |

## Per query

| ID | Cat | Lang | Status | Tools used | Hops | Tok (in/out) | Lat. (s) | Coverage |
|---|---|---|---|---|---|---|---|---|
| structural_01 | structural | en | OK | find_rooms | 2 | 3768/761 | 9.8 | OK |
| structural_02 | structural | en | OK | find_rooms | 2 | 2352/738 | 10.3 | OK |
| structural_03 | structural | en | OK | find_rooms | 2 | 3825/700 | 10.4 | OK |
| structural_04 | structural | en | OK | find_rooms | 2 | 6787/1244 | 12.0 | OK |
| policy_01 | policy | en | OK | answer_policy_question | 2 | 1320/274 | 5.4 | OK |
| policy_02 | policy | en | OK | answer_policy_question | 2 | 1273/245 | 5.4 | OK |
| policy_03 | policy | en | OK | answer_policy_question, search_descriptions | 3 | 4087/497 | 12.6 | OK |
| policy_04 | policy | en | OK | answer_policy_question | 2 | 1246/407 | 7.6 | OK |
| cost_01 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 2590/751 | 9.6 | OK |
| cost_02 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 2534/787 | 10.7 | OK |
| cost_03 | cost | en | OK | find_available_rooms, find_available_rooms, compute_total_cost, compute_total_cost | 3 | 4094/1031 | 12.5 | OK |
| cost_04 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 2279/754 | 10.3 | OK |
| semantic_01 | semantic | en | OK | search_descriptions | 2 | 3215/559 | 9.2 | OK |
| semantic_02 | semantic | en | OK | search_reviews | 2 | 3958/466 | 12.3 | OK |
| semantic_03 | semantic | en | OK | search_descriptions | 2 | 5861/1150 | 12.6 | OK |
| semantic_04 | semantic | en | OK |  | 1 | 338/92 | 4.2 | OK |
| multilingual_01 | multilingual | it | OK | answer_policy_question | 2 | 1297/438 | 7.4 | OK |
| multilingual_02 | multilingual | pt | OK | find_available_rooms | 2 | 3913/789 | 10.2 | OK |
| multilingual_03 | multilingual | es | OK | find_available_rooms, compute_total_cost | 3 | 2550/775 | 13.0 | OK |
| multilingual_04 | multilingual | de | OK | answer_policy_question | 2 | 1271/481 | 7.0 | OK |
