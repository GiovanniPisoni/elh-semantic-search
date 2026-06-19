# Phase 3 Agent Benchmark Report

- Generated: `2026-05-18 14:49 UTC`
- Run file: `agent_benchmark_2026-05-18-144741.jsonl`
- Total queries: 20
- Success: 20  |  Failed: 0

## Overall

| Metric | Value |
|---|---|
| Tool routing coverage | 100% (20/20) |
| Failure rate | 0% (0/20) |
| Latency avg | 50.8 s |
| Latency p50 | 49.6 s |
| Latency p95 | 69.5 s |
| Latency max | 111.6 s |
| Hops avg | 2.5 |
| Hops max | 5 |
| Tokens in (avg / total) | 26936 / 538725 |
| Tokens out (avg / total) | 659 / 13185 |
| Cost total | $1.81 USD |

## Per category

| Category | n | Coverage | Lat. avg | Lat. p95 | Tok in (avg) | Tok out (avg) | Cost USD |
|---|---|---|---|---|---|---|---|
| cost | 4 | 100% (4/4) | 63.2s | 66.0s | 31375 | 850 | $0.43 |
| multilingual | 4 | 100% (4/4) | 49.5s | 63.0s | 23591 | 609 | $0.32 |
| policy | 4 | 100% (4/4) | 58.1s | 101.2s | 28976 | 388 | $0.37 |
| semantic | 4 | 100% (4/4) | 53.3s | 65.4s | 27926 | 584 | $0.37 |
| structural | 4 | 100% (4/4) | 30.1s | 48.8s | 22813 | 866 | $0.33 |

## Per language

| Language | n | Coverage | Lat. avg | Tok in (avg) | Tok out (avg) |
|---|---|---|---|---|---|
| de | 1 | 100% | 37.6s | 20256 | 462 |
| en | 16 | 100% | 51.2s | 27773 | 672 |
| es | 1 | 100% | 65.5s | 30980 | 737 |
| it | 1 | 100% | 48.9s | 20190 | 275 |
| pt | 1 | 100% | 46.1s | 22938 | 962 |

## Per query

| ID | Cat | Lang | Status | Tools used | Hops | Tok (in/out) | Lat. (s) | Coverage |
|---|---|---|---|---|---|---|---|---|
| structural_01 | structural | en | OK | find_rooms | 2 | 22786/834 | 14.4 | OK |
| structural_02 | structural | en | OK | find_rooms | 2 | 21354/965 | 16.1 | OK |
| structural_03 | structural | en | OK | find_rooms | 2 | 22827/598 | 39.2 | OK |
| structural_04 | structural | en | OK | find_rooms | 2 | 24284/1067 | 50.4 | OK |
| policy_01 | policy | en | OK | answer_policy_question | 2 | 20234/233 | 38.5 | OK |
| policy_02 | policy | en | OK | answer_policy_question | 2 | 20201/225 | 42.3 | OK |
| policy_03 | policy | en | OK | answer_policy_question, answer_policy_question, answer_policy_question, search_descriptions | 5 | 55314/769 | 111.6 | OK |
| policy_04 | policy | en | OK | answer_policy_question | 2 | 20156/323 | 40.1 | OK |
| cost_01 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 31013/724 | 63.8 | OK |
| cost_02 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 30961/728 | 61.8 | OK |
| cost_03 | cost | en | OK | find_available_rooms, find_available_rooms, compute_total_cost, compute_total_cost | 3 | 32454/1196 | 66.4 | OK |
| cost_04 | cost | en | OK | find_available_rooms, compute_total_cost | 3 | 31072/753 | 60.8 | OK |
| semantic_01 | semantic | en | OK | search_descriptions, search_descriptions | 3 | 37734/704 | 67.3 | OK |
| semantic_02 | semantic | en | OK | search_reviews | 2 | 23124/410 | 54.4 | OK |
| semantic_03 | semantic | en | OK | search_descriptions | 2 | 24863/687 | 41.4 | OK |
| semantic_04 | semantic | en | OK | search_reviews | 2 | 25984/533 | 50.3 | OK |
| multilingual_01 | multilingual | it | OK | answer_policy_question | 2 | 20190/275 | 48.9 | OK |
| multilingual_02 | multilingual | pt | OK | find_available_rooms | 2 | 22938/962 | 46.1 | OK |
| multilingual_03 | multilingual | es | OK | find_available_rooms, compute_total_cost | 3 | 30980/737 | 65.5 | OK |
| multilingual_04 | multilingual | de | OK | answer_policy_question | 2 | 20256/462 | 37.6 | OK |
