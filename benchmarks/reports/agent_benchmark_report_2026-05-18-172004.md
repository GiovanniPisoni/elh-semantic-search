# Phase 3 Agent Benchmark Report

- Generated: `2026-05-18 17:22 UTC`
- Run file: `agent_benchmark_2026-05-18-172004.jsonl`
- Total queries: 20
- Success: 20  |  Failed: 0

## Overall

| Metric | Value |
|---|---|
| Tool routing coverage | 100% (20/20) |
| Failure rate | 0% (0/20) |
| Latency avg | 9.5 s |
| Latency p50 | 8.9 s |
| Latency p95 | 14.0 s |
| Latency max | 14.5 s |
| Hops avg | 2.3 |
| Hops max | 3 |
| Tokens in (avg / total) | 3038 / 60756 |
| Tokens out (avg / total) | 612 / 12231 |
| Cost total | $0.37 USD |

## Per category

| Category | n | Coverage | Lat. avg | Lat. p95 | Tok in (avg) | Tok out (avg) | Cost USD |
|---|---|---|---|---|---|---|---|
| cost | 4 | 100% (4/4) | 10.1s | 12.9s | 1874 | 825 | $0.07 |
| multilingual | 4 | 100% (4/4) | 9.5s | 13.3s | 2374 | 630 | $0.07 |
| policy | 4 | 100% (4/4) | 7.9s | 12.7s | 1718 | 323 | $0.04 |
| semantic | 4 | 100% (4/4) | 10.2s | 13.4s | 5039 | 595 | $0.10 |
| structural | 4 | 100% (4/4) | 9.9s | 13.8s | 4183 | 685 | $0.09 |

## Per language

| Language | n | Coverage | Lat. avg | Tok in (avg) | Tok out (avg) |
|---|---|---|---|---|---|
| de | 1 | 100% | 6.6s | 1254 | 456 |
| en | 16 | 100% | 9.5s | 3204 | 607 |
| es | 1 | 100% | 13.6s | 1614 | 885 |
| it | 1 | 100% | 6.1s | 1188 | 312 |
| pt | 1 | 100% | 11.5s | 5442 | 865 |

## Per query

| ID | Cat | Lang | Status | Tools used | Hops | Tok (in/out) | Lat. (s) | Coverage |
|---|---|---|---|---|---|---|---|---|
| structural_01 | structural | en | OK | find_rooms | 2 | 3768/741 | 10.1 | OK |
| structural_02 | structural | en | OK | find_rooms | 2 | 2352/573 | 7.5 | OK |
| structural_03 | structural | en | OK | find_rooms | 2 | 3825/540 | 7.7 | OK |
| structural_04 | structural | en | OK | find_rooms | 2 | 6787/886 | 14.5 | OK |
| policy_01 | policy | en | OK | answer_policy_question | 2 | 1232/245 | 5.2 | OK |
| policy_02 | policy | en | OK | answer_policy_question | 2 | 1199/267 | 6.0 | OK |
| policy_03 | policy | en | OK | answer_policy_question, search_descriptions | 3 | 3289/525 | 13.8 | OK |
| policy_04 | policy | en | OK | answer_policy_question | 2 | 1154/254 | 6.5 | OK |
| cost_01 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1634/690 | 9.1 | OK |
| cost_02 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1607/737 | 9.0 | OK |
| cost_03 | cost | en | OK | find_available_rooms, find_available_rooms, compute_total_cost, compute_total_cost | 3 | 2567/1165 | 13.5 | OK |
| cost_04 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 1688/709 | 8.6 | OK |
| semantic_01 | semantic | en | OK | search_descriptions | 2 | 3191/613 | 8.2 | OK |
| semantic_02 | semantic | en | OK | search_reviews | 2 | 4122/380 | 10.0 | OK |
| semantic_03 | semantic | en | OK | search_descriptions | 2 | 5861/930 | 14.0 | OK |
| semantic_04 | semantic | en | OK | search_reviews | 2 | 6982/458 | 8.7 | OK |
| multilingual_01 | multilingual | it | OK | answer_policy_question | 2 | 1188/312 | 6.1 | OK |
| multilingual_02 | multilingual | pt | OK | find_available_rooms | 2 | 5442/865 | 11.5 | OK |
| multilingual_03 | multilingual | es | OK | find_available_rooms, compute_total_cost | 3 | 1614/885 | 13.6 | OK |
| multilingual_04 | multilingual | de | OK | answer_policy_question | 2 | 1254/456 | 6.6 | OK |
