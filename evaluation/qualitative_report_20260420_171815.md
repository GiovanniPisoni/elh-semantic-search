# ELH RAG — Qualitative Benchmark Report

**Generated:** 2026-04-20 17:18
**Queries:** 15

## Methodological note

This report is a **qualitative benchmark**, not a rigorous quantitative evaluation. Without a ground-truth labelled dataset (to be built in Phase 4, Step 1) we cannot report precision@k, recall@k, or RAGAS faithfulness / answer relevance.

What you will find below is a side-by-side comparison of three configurations on the same inputs, plus observables — latency, reshuffling rate, rewriting activity — that help describe how the system behaves. Judgements about *quality* are left to the reader and will be replaced by RAGAS metrics in Phase 4.

## Executive summary

### Latency comparison

| Configuration | Avg (s) | Median (s) | Min | Max | Sources |
|---|---:|---:|---:|---:|---:|
| Naive (Phase 1 baseline) | 9.111 | 7.851 | 5.218 | 33.605 | 5.0 |
| +Query rewriting (Phase 2, Step 1) | 8.776 | 8.628 | 5.693 | 12.621 | 5.0 |
| +Query rewriting +Reranking (Phase 2, Step 2) | 17.69 | 18.312 | 8.917 | 27.201 | 5.0 |

### Query rewriting activity

Of 15 queries, the rewriter produced a **different** query **15 times (100.0%)**. The remaining queries were returned unchanged by the rewriter — typically because they were already well-formed search queries.

### Reranking reshuffling rate

Comparing the vector-only order (+Rewrite config) against the reranked order (+Rewrite+Rerank config) on 15 queries:

- **Top-1 result changed** in 14/15 cases (93.3%)
- **Any ordering change** in 15/15 cases (100.0%)

*Interpretation:* a reshuffling rate close to 0% would suggest reranking adds latency without benefit; a rate close to 100% could indicate instability or conflict between the two signals. The sweet spot is typically 30-70%, indicating reranking refines but doesn't overturn the initial retrieval.

## Per-query results

### q01 — conversational_verbose

**Question:** I am looking for a quiet place where I can focus on my studies without being disturbed by neighbours

*Long conversational query, tests query rewriting effectiveness*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 33.605s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Alcantara | Santos, Lisbon | 0.540 | — |
| 2 | Residencia Campo de Ourique | Chiado, Lisbon | 0.526 | — |
| 3 | Belem Student Flat | Belem, Lisbon | 0.523 | — |
| 4 | Casa Azul | Boavista, Porto | 0.520 | — |
| 5 | Massarelos Student Flat | Massarelos, Porto | 0.517 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, I cannot give you a complete answer about noise levels and disturbances from neighbors, as **none of the reviews specifically mention noise levels or neighbor disturbances**.
> 
> However, I can share some positive aspects for studying that students mentioned:
> 
> **Study-friendly features mentioned:**
> - According to reviews of Residencia Alcantara (Santos), Residencia Campo de Ourique (Chiado), Belem Student Flat, and Massarelos Student Flat, all properties had **dedicated study desks that were "perfect for long university work sessions"**
> - Multiple reviews me…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 8.282s · **Sources:** 5
- **Rewritten query:** *quiet accommodation peaceful low noise study focus minimal disturbance neighbours*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Porto | Ramalde, Porto | 0.469 | — |
| 2 | Cosy Home Porto | Cedofeita, Porto | 0.449 | — |
| 3 | Cosy Home Porto | Cedofeita, Porto | 0.439 | — |
| 4 | Casa Azul | Boavista, Porto | 0.435 | — |
| 5 | Casa Verde | Foz do Douro, Porto | 0.434 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several properties mention having **dedicated study desks** which could support your study needs:
> 
> **Properties with study spaces:**
> - **Cosy Home Porto (Ramalde)** - According to the review, "The dedicated study desk was perfect for long university work sessions — exactly what an Erasmus student needs." (Review 1)
> - **Cosy Home Porto (Cedofeita)** - A reviewer noted "The dedicated study desk was perfect for long university work sessions — exactly what an Erasmus student needs." (Review 3)
> - **Casa Azul (Boavista)** - Similarly mentioned "The dedicated st…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 27.201s · **Sources:** 5
- **Rewritten query:** *quiet accommodation peaceful low noise study focus minimal disturbance neighbours*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Casa Azul | Boavista, Porto | 0.418 | 0.002 |
| 2 | Cosy Home Porto | Massarelos, Porto | 0.417 | 0.001 |
| 3 | Casa do Sol | Bairro Alto, Lisbon | 0.431 | 0.000 |
| 4 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.422 | 0.000 |
| 5 | Cosy Home Porto | Ramalde, Porto | 0.469 | 0.000 |

**Answer (first 600 chars):**

> Based on the student reviews provided, several properties appear to offer good conditions for focused studying, though none specifically mention noise levels or disturbances from neighbors.
> 
> **Properties with dedicated study spaces:**
> 
> According to reviews of **Cosy Home Porto in Massarelos** and **Cosy Home Lisbon in Bairro Alto**, both properties feature "dedicated study desks that were perfect for long university work sessions — exactly what an Erasmus student needs."
> 
> **Additional study-friendly features mentioned:**
> 
> - **Casa Azul in Boavista, Porto**: The reviewer mentions "excellent nat…

---

### q02 — short_direct

**Question:** comfortable bed

*Minimal query, should change little with rewriting*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 6.264s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Belem, Lisbon | 0.621 | — |
| 2 | Residencia Campo de Ourique | Chiado, Lisbon | 0.579 | — |
| 3 | Residencia Campanha | Foz do Douro, Porto | 0.576 | — |
| 4 | Casa do Sol | Boavista, Porto | 0.569 | — |
| 5 | Bright Apartment Alfama | Alfama, Lisbon | 0.560 | — |

**Answer (first 600 chars):**

> Based on the student reviews, the beds across different properties are consistently described as comfortable:
> 
> **King and Queen-size beds:** According to reviews of Residencia Intendente in Belem and Bright Apartment Alfama, both properties feature larger beds that "provided the best sleep I had all semester — completely restful every night."
> 
> **Double beds:** A review of Residencia Campanha in Porto mentions "The double bed was really comfortable and the mattress was in excellent condition."
> 
> **Single beds:** Reviews from both Residencia Campo de Ourique in Chiado and Casa do Sol in Boavista …

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 5.693s · **Sources:** 5
- **Rewritten query:** *comfortable bed, good mattress, quality bedding, cozy sleeping*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Belem, Lisbon | 0.682 | — |
| 2 | Residencia Campanha | Foz do Douro, Porto | 0.635 | — |
| 3 | Bright Apartment Alfama | Alfama, Lisbon | 0.635 | — |
| 4 | Residencia Campo de Ourique | Chiado, Lisbon | 0.625 | — |
| 5 | Casa do Sol | Boavista, Porto | 0.618 | — |

**Answer (first 600 chars):**

> Based on the student reviews, the beds across these properties are consistently described as comfortable:
> 
> **Excellent comfort:**
> - According to a review of Residencia Intendente in Belem, the "king-size bed provided the best sleep I had all semester — completely restful every night"
> - A review of Bright Apartment Alfama mentions the "queen-size bed provided the best sleep I had all semester — completely restful every night"
> - According to a review of Residencia Campanha in Porto, "The double bed was really comfortable and the mattress was in excellent condition"
> 
> **Good comfort for student ac…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 8.917s · **Sources:** 5
- **Rewritten query:** *comfortable bed, good mattress, quality bedding, cozy sleeping*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Casa Verde | Foz do Douro, Porto | 0.596 | 0.332 |
| 2 | Residencia Graca | Intendente, Lisbon | 0.593 | 0.292 |
| 3 | Residencia Campanha | Foz do Douro, Porto | 0.635 | 0.272 |
| 4 | Bright Apartment Arroios | Arroios, Lisbon | 0.563 | 0.180 |
| 5 | Bright Apartment Alfama | Alfama, Lisbon | 0.635 | 0.042 |

**Answer (first 600 chars):**

> Based on the student reviews provided, the beds are consistently described as very comfortable across all properties.
> 
> According to reviews from multiple locations:
> - **Casa Verde in Foz do Douro, Porto**: "The double bed was really comfortable and the mattress was in excellent condition"
> - **Residencia Graca in Intendente, Lisbon**: "The double bed was really comfortable and the mattress was in excellent condition"
> - **Residencia Campanha in Foz do Douro, Porto**: "The double bed was really comfortable and the mattress was in excellent condition"
> - **Bright Apartment Arroios in Lisbon**: "The…

---

### q03 — abstract_concept

**Question:** a place that feels like home

*Abstract request, tests semantic retrieval beyond keywords*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 7.879s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Lisbon | Belem, Lisbon | 0.582 | — |
| 2 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.560 | — |
| 3 | Cosy Home Porto | Ramalde, Porto | 0.553 | — |
| 4 | Residencia Paranhos | Boavista, Porto | 0.541 | — |
| 5 | Cosy Home Lisbon | Mouraria, Lisbon | 0.536 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several properties seem to create a "home-like" feeling for students:
> 
> **What makes these places feel like home:**
> 
> According to multiple reviews, students found these accommodations created a genuine home atmosphere through several key factors:
> 
> **Community and Relationships:** A review of Cosy Home Lisbon in Belem mentions that "My flatmates turned out to be a wonderful international mix — we explored the city together and became close friends," which contributed to the homey feeling.
> 
> **Personal Comfort Spaces:** Several reviews highlight having person…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 9.916s · **Sources:** 5
- **Rewritten query:** *cozy comfortable welcoming home-like atmosphere friendly community warm inviting space*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Lisbon | Belem, Lisbon | 0.649 | — |
| 2 | Residencia Campo de Ourique | Chiado, Lisbon | 0.581 | — |
| 3 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.580 | — |
| 4 | Residencia Campo de Ourique | Chiado, Lisbon | 0.571 | — |
| 5 | Cosy Home Porto | Ramalde, Porto | 0.570 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several properties seem to create a "home-like" feeling for students:
> 
> **Cosy Home Lisbon — Garden View Room (Belem)** appears to offer the most home-like experience. According to a review from Belem, the student found "My flatmates turned out to be a wonderful international mix — we explored the city together and became close friends." The reviewer also noted it was "A fantastic place to live — comfortable, well-located and with a great landlord" and appreciated the well-equipped kitchen that made "daily life very comfortable."
> 
> **Residencia Campo de Our…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 12.936s · **Sources:** 5
- **Rewritten query:** *cozy comfortable welcoming home-like atmosphere friendly community warm inviting space*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Belem, Lisbon | 0.557 | 0.024 |
| 2 | Residencia Paranhos | Boavista, Porto | 0.556 | 0.006 |
| 3 | Cosy Home Porto | Massarelos, Porto | 0.558 | 0.005 |
| 4 | Cosy Home Lisbon | Mouraria, Lisbon | 0.555 | 0.005 |
| 5 | Cosy Home Lisbon | Belem, Lisbon | 0.649 | 0.004 |

**Answer (first 600 chars):**

> Based on the student reviews, several properties offer that "home-like" feeling through different comfort features:
> 
> **Residencia Intendente in Belem, Lisbon** stands out for creating a homey atmosphere. According to the review, the landlord "went above and beyond — helped me settle in and was always just a message away," and the reviewer described it as "a fantastic place to live — comfortable, well-located and with a great landlord."
> 
> **Cosy Home Porto in Massarelos** also creates a welcoming environment. The review mentions that "cleanliness was a real highlight — the landlord clearly takes…

---

### q04 — landlord_behavior

**Question:** landlords who respond quickly when something breaks

*Tests retrieval of experiential content not in structured fields*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 5.218s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Alfama | Belem, Lisbon | 0.378 | — |
| 2 | Boavista Student Flat | Boavista, Porto | 0.357 | — |
| 3 | Residencia Alfama | Belem, Lisbon | 0.353 | — |
| 4 | Bright Apartment Ramalde | Ramalde, Porto | 0.326 | — |
| 5 | Bright Apartment Arroios | Arroios, Lisbon | 0.321 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are clear differences in landlord responsiveness:
> 
> **Landlords who respond quickly:**
> 
> According to a review of Boavista Student Flat in Porto, "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> 
> Similarly, a review of Bright Apartment Arroios in Lisbon states: "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> 
> **Landlords with poor response times:**
> 
> In contrast, multiple reviews highlight slow responses. Two reviews of Residenci…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 7.135s · **Sources:** 5
- **Rewritten query:** *landlord responsive quick repairs maintenance issues broken appliances fast communication*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Ramalde | Ramalde, Porto | 0.447 | — |
| 2 | Residencia Alfama | Belem, Lisbon | 0.398 | — |
| 3 | Cosy Home Lisbon | Belem, Lisbon | 0.386 | — |
| 4 | Bright Apartment Arroios | Arroios, Lisbon | 0.370 | — |
| 5 | Residencia Campo de Ourique | Chiado, Lisbon | 0.367 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, **landlords who respond quickly when something breaks are NOT found among these properties**. In fact, all the reviews that mention landlord communication describe the opposite experience:
> 
> **Poor landlord responsiveness reported:**
> 
> - **Bright Apartment Ramalde (Porto)**: "Getting responses from the landlord was frustrating — very stressful when something needed fixing."
> 
> - **Residencia Alfama (Belem, Lisbon)**: "The landlord was very slow to respond — sometimes days passed without a reply to urgent messages."
> 
> - **Cosy Home Lisbon (Belem, Lisbon)**: "Th…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 17.246s · **Sources:** 5
- **Rewritten query:** *landlord responsive quick repairs maintenance issues broken appliances fast communication*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Arroios | Arroios, Lisbon | 0.300 | 0.330 |
| 2 | Boavista Student Flat | Boavista, Porto | 0.363 | 0.289 |
| 3 | Bright Apartment Santos | Santos, Lisbon | 0.311 | 0.040 |
| 4 | Bright Apartment Principe Real | Principe Real, Lisbon | 0.264 | 0.038 |
| 5 | Casa Verde | Foz do Douro, Porto | 0.269 | 0.033 |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are **mixed experiences with landlord responsiveness** when issues arise:
> 
> **Landlords who respond quickly:**
> - **Arroios, Lisbon (Bright Apartment Arroios)**: According to the review, "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> - **Boavista, Porto (Boavista Student Flat)**: The review states "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> - **Principe Real, Lisbon (Bright Apartment Principe Real)**: The student noted "Th…

---

### q05 — negative_query

**Question:** apartments with noise complaints or maintenance issues

*Negative sentiment retrieval — important for ELH quality monitoring*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 7.851s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Ramalde | Ramalde, Porto | 0.606 | — |
| 2 | Bright Apartment Arroios | Arroios, Lisbon | 0.599 | — |
| 3 | Casa Verde | Foz do Douro, Porto | 0.574 | — |
| 4 | Cosy Home Lisbon | Belem, Lisbon | 0.571 | — |
| 5 | Casa Verde | Foz do Douro, Porto | 0.569 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several apartments have significant noise complaints and maintenance issues:
> 
> ## Apartments with Maintenance Issues:
> 
> **Casa Verde in Foz do Douro, Porto** has multiple maintenance problems according to two reviews:
> - Poor cleanliness on arrival with "grime in the bathroom and a dirty oven" 
> - Mattresses needing replacement - one review mentions "the single bed felt cramped for a longer stay and the mattress needed replacing"
> - Communication issues with landlords being "difficult to reach when maintenance issues arose"
> 
> **Bright Apartment Arroios in Lisbo…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 8.625s · **Sources:** 5
- **Rewritten query:** *noisy apartments, loud neighbours, noise problems, maintenance issues, repairs, broken facilities, poor upkeep*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Ramalde | Ramalde, Porto | 0.582 | — |
| 2 | Bright Apartment Arroios | Arroios, Lisbon | 0.564 | — |
| 3 | Casa Verde | Foz do Douro, Porto | 0.560 | — |
| 4 | Casa Verde | Foz do Douro, Porto | 0.556 | — |
| 5 | Bright Apartment Santos | Santos, Lisbon | 0.546 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several apartments have significant maintenance issues, though no specific noise complaints are mentioned in these reviews.
> 
> **Apartments with Maintenance Issues:**
> 
> **Casa Verde (Foz do Douro, Porto)** - Multiple reviews cite maintenance problems:
> - According to reviews of Casa Verde, "the landlord was difficult to reach when maintenance issues arose" and there were issues with bathroom cleanliness and mattresses needing replacement.
> 
> **Bright Apartment Santos (Lisbon)** - Serious maintenance concerns:
> - According to a review of Bright Apartment Santos, …

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 19.856s · **Sources:** 5
- **Rewritten query:** *noisy apartments, loud neighbours, noise problems, maintenance issues, repairs, broken facilities, poor upkeep*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Santos | Santos, Lisbon | 0.546 | 0.056 |
| 2 | Residencia Chiado | Santos, Lisbon | 0.522 | 0.048 |
| 3 | Casa Verde | Foz do Douro, Porto | 0.556 | 0.037 |
| 4 | Residencia Alfama | Belem, Lisbon | 0.527 | 0.033 |
| 5 | Casa Verde | Foz do Douro, Porto | 0.560 | 0.019 |

**Answer (first 600 chars):**

> Based on the student reviews provided, several apartments have significant noise complaints and maintenance issues:
> 
> ## Apartments with Maintenance Issues:
> 
> **Bright Apartment Santos — Studio Loft (Santos, Lisbon)** - According to a review rating it 2/5, this property had "persistent mould in the private bathroom that was never properly fixed despite repeated requests." The reviewer also mentioned a mattress that "needed replacing" and poor cleanliness upon arrival.
> 
> **Residencia Chiado — Double Deluxe (Santos, Lisbon)** - A 1/5 rated review reported identical issues: "persistent mould in the …

---

### q06 — multilingual_pt

**Question:** quarto tranquilo para estudar

*Portuguese native query, tests EN+PT embeddings*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 8.431s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Mouraria | Chiado, Lisbon | 0.688 | — |
| 2 | Massarelos Student Flat | Massarelos, Porto | 0.687 | — |
| 3 | Boavista Student Flat | Boavista, Porto | 0.682 | — |
| 4 | Casa Nova | Principe Real, Lisbon | 0.656 | — |
| 5 | Casa Verde | Foz do Douro, Porto | 0.652 | — |

**Answer (first 600 chars):**

> Com base nas avaliações dos estudantes, todos os quartos mencionados parecem ser adequados para estudar de forma tranquila:
> 
> **Espaços de estudo dedicados**: Todas as 5 avaliações destacam que "a secretária dedicada para estudar era perfeita para longas sessões de trabalho universitário — exatamente o que um estudante Erasmus precisa."
> 
> **Iluminação natural**: Duas avaliações específicas mencionam condições ideais para estudar:
> - Segundo uma avaliação do Massarelos Student Flat no Porto: "O quarto tinha excelente luz natural durante todo o dia, o que realmente melhorou o meu humor enquanto est…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 11.359s · **Sources:** 5
- **Rewritten query:** *quarto tranquilo, silencioso, bom para estudar, ambiente calmo, sem ruído*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Mouraria | Chiado, Lisbon | 0.679 | — |
| 2 | Massarelos Student Flat | Massarelos, Porto | 0.674 | — |
| 3 | Boavista Student Flat | Boavista, Porto | 0.666 | — |
| 4 | Residencia Alcantara | Santos, Lisbon | 0.645 | — |
| 5 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.644 | — |

**Answer (first 600 chars):**

> Com base nas avaliações dos estudantes, todos os quartos mencionados parecem ser adequados para estudar de forma tranquila:
> 
> **Características que favorecem o estudo:**
> 
> - **Secretária dedicada**: Todas as 5 avaliações mencionam que "a secretária dedicada era perfeita para longas sessões de trabalho universitário — exatamente o que um estudante Erasmus precisa"
> 
> - **Luz natural excelente**: Duas avaliações destacam este aspeto - tanto no Massarelos Student Flat no Porto como no Cosy Home Lisbon em Bairro Alto mencionam que "o quarto tinha excelente luz natural durante todo o dia, o que realmen…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 21.189s · **Sources:** 5
- **Rewritten query:** *quarto tranquilo, silencioso, bom para estudar, ambiente calmo, sem ruído*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Belem Student Flat | Belem, Lisbon | 0.610 | 0.006 |
| 2 | Cosy Home Lisbon | Mouraria, Lisbon | 0.618 | 0.003 |
| 3 | Massarelos Student Flat | Massarelos, Porto | 0.674 | 0.003 |
| 4 | Graca Student Flat | Graca, Lisbon | 0.637 | 0.002 |
| 5 | Residencia Mouraria | Chiado, Lisbon | 0.679 | 0.002 |

**Answer (first 600 chars):**

> Com base nas avaliações dos estudantes, várias propriedades oferecem quartos tranquilos e adequados para estudar:
> 
> **Características ideais para estudo encontradas:**
> 
> **Luz natural excelente** - Segundo as avaliações do Belem Student Flat, Cosy Home Lisbon, Massarelos Student Flat e Graca Student Flat, todos os quartos têm "excelente luz natural durante todo o dia, o que realmente melhorou o humor durante os estudos".
> 
> **Secretárias dedicadas para estudo** - As avaliações do Belem Student Flat, Massarelos Student Flat e Residencia Mouraria mencionam que "a secretária dedicada era perfeita par…

---

### q07 — multilingual_it

**Question:** stanza luminosa con buona connessione internet

*Italian query, tests the multilingual reranker beyond EN+PT*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 6.378s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Chiado | Chiado, Lisbon | 0.598 | — |
| 2 | Bright Apartment Ribeira | Ribeira, Porto | 0.586 | — |
| 3 | Bright Apartment Arroios | Arroios, Lisbon | 0.578 | — |
| 4 | Residencia Mouraria | Chiado, Lisbon | 0.567 | — |
| 5 | Bright Apartment Ribeira | Ribeira, Porto | 0.566 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are several properties that offer bright rooms with good internet connection:
> 
> **For bright rooms with excellent natural light:**
> - According to reviews of the Bright Apartment Chiado and Bright Apartment Ribeira, students specifically mention that "the room had excellent natural light throughout the day, which really boosted my mood while studying."
> 
> **For internet connection:**
> Multiple reviews consistently praise the WiFi quality:
> - Reviews of Bright Apartment Chiado, Bright Apartment Ribeira, and Residencia Mouraria all mention that "the WiFi wa…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 9.325s · **Sources:** 5
- **Rewritten query:** *stanza luminosa, buona connessione internet, wifi veloce, luce naturale*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Ribeira | Ribeira, Porto | 0.646 | — |
| 2 | Bright Apartment Chiado | Chiado, Lisbon | 0.613 | — |
| 3 | Bright Apartment Ribeira | Ribeira, Porto | 0.612 | — |
| 4 | Bright Apartment Arroios | Arroios, Lisbon | 0.612 | — |
| 5 | Residencia Mouraria | Chiado, Lisbon | 0.607 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are several properties that offer bright rooms with excellent internet connection:
> 
> **Rooms with excellent natural light:**
> - According to reviews of the Bright Apartment in Chiado, Lisbon and Ribeira, Porto: "The room had excellent natural light throughout the day, which really boosted my mood while studying"
> - A review of Residencia Mouraria in Chiado also mentions: "The room had excellent natural light throughout the day, which really boosted my mood while studying"
> 
> **Internet connection quality:**
> - Multiple reviews consistently praise the WiFi…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 16.091s · **Sources:** 5
- **Rewritten query:** *stanza luminosa, buona connessione internet, wifi veloce, luce naturale*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Belem Student Flat | Belem, Lisbon | 0.572 | 0.400 |
| 2 | Bright Apartment Ribeira | Ribeira, Porto | 0.612 | 0.274 |
| 3 | Residencia Intendente | Graca, Lisbon | 0.571 | 0.114 |
| 4 | Residencia Mouraria | Chiado, Lisbon | 0.607 | 0.105 |
| 5 | Bright Apartment Chiado | Chiado, Lisbon | 0.613 | 0.104 |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are several properties that offer bright rooms with good internet connection:
> 
> **Rooms with excellent natural light and outstanding internet:**
> 
> According to reviews of **Residencia Mouraria in Chiado** and **Bright Apartment Chiado**, both properties have "excellent natural light throughout the day" and "outstanding WiFi — 500 Mbps" that makes "video calls and online studying completely effortless."
> 
> The **Bright Apartment Ribeira in Porto** also offers "excellent natural light throughout the day" combined with "outstanding WiFi — 500 Mbps."
> 
> Simil…

---

### q08 — multilingual_es

**Question:** habitación acogedora cerca de la universidad

*Spanish query, another Erasmus demographic*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 8.756s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campo de Ourique | Chiado, Lisbon | 0.694 | — |
| 2 | Boavista Student Flat | Boavista, Porto | 0.689 | — |
| 3 | Residencia Mouraria | Chiado, Lisbon | 0.682 | — |
| 4 | Cosy Home Porto | Ramalde, Porto | 0.672 | — |
| 5 | Residencia Campo de Ourique | Chiado, Lisbon | 0.667 | — |

**Answer (first 600 chars):**

> Basándome en las reseñas de estudiantes proporcionadas, puedo destacar varias opciones de habitaciones acogedoras cerca de universidades:
> 
> **Habitaciones especialmente acogedoras:**
> 
> Según una reseña de la **Residencia Mouraria — Garden View Room** en Chiado, Lisboa, un estudiante describe "la cama individual era perfectamente cómoda para una estancia estudiantil — compacta pero muy acogedora" y califica la experiencia como "una de las mejores decisiones que tomé durante mi año Erasmus".
> 
> La **Residencia Campo de Ourique — Room** también en Chiado recibe elogios similares, donde un estudiante …

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 8.628s · **Sources:** 5
- **Rewritten query:** *habitación acogedora, cómoda, cerca de la universidad, ambiente acogedor*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campo de Ourique | Chiado, Lisbon | 0.732 | — |
| 2 | Cosy Home Porto | Ramalde, Porto | 0.712 | — |
| 3 | Boavista Student Flat | Boavista, Porto | 0.707 | — |
| 4 | Casa do Sol | Boavista, Porto | 0.704 | — |
| 5 | Cosy Home Porto | Cedofeita, Porto | 0.702 | — |

**Answer (first 600 chars):**

> Basándome en las reseñas de estudiantes proporcionadas, puedo destacar varias opciones de habitaciones acogedoras cerca de universidades:
> 
> **Habitaciones especialmente acogedoras:**
> 
> Según una reseña de **Casa do Sol en Boavista, Porto**, "la cama individual era perfectamente cómoda para una estancia de estudiante — compacta pero muy acogedora" y describe la experiencia general como "excelente".
> 
> Una reseña de **Cosy Home Porto en Cedofeita, Porto** también menciona que "la cama individual era perfectamente cómoda para una estancia de estudiante — compacta pero muy acogedora", además de tener …

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 19.843s · **Sources:** 5
- **Rewritten query:** *habitación acogedora, cómoda, cerca de la universidad, ambiente acogedor*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campo de Ourique | Chiado, Lisbon | 0.732 | 0.207 |
| 2 | Massarelos Student Flat | Massarelos, Porto | 0.680 | 0.144 |
| 3 | Cosy Home Porto | Ramalde, Porto | 0.685 | 0.124 |
| 4 | Cosy Home Porto | Ramalde, Porto | 0.712 | 0.073 |
| 5 | Boavista Student Flat | Boavista, Porto | 0.707 | 0.048 |

**Answer (first 600 chars):**

> Basándome en las reseñas de estudiantes proporcionadas, puedo destacar varias opciones de habitaciones acogedoras cerca de universidades:
> 
> **Habitaciones especialmente acogedoras:**
> 
> Según las reseñas, tanto la **Residencia Campo de Ourique en Chiado, Lisboa** como el **Massarelos Student Flat en Porto** ofrecen habitaciones muy acogedoras. Los estudiantes describen las camas individuales como "perfectamente cómodas para una estancia estudiantil — compactas pero muy acogedoras" en ambas propiedades.
> 
> **Características que las hacen acogedoras:**
> 
> - **Calefacción eficiente**: Según reseñas de C…

---

### q09 — location_constraint

**Question:** properties in Porto that students recommend for first-time visitors

*Factual constraint (Porto) plus qualitative judgement*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 8.081s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Paranhos | Boavista, Porto | 0.681 | — |
| 2 | Casa Verde | Foz do Douro, Porto | 0.668 | — |
| 3 | Casa Verde | Foz do Douro, Porto | 0.654 | — |
| 4 | Residencia Foz | Boavista, Porto | 0.639 | — |
| 5 | Cosy Home Porto | Ramalde, Porto | 0.628 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, here are the Porto properties that students recommend for first-time visitors:
> 
> **Highly Recommended Properties:**
> 
> 1. **Casa Verde in Foz do Douro** - This property received particularly strong endorsements:
>    - According to a review of Casa Verde's Room, one student called it "one of the best decisions I made during my Erasmus year" and "strongly recommended" it
>    - Another review of Casa Verde's Master Suite noted that "living in Foz do Douro was fantastic — great neighbourhood and easy access to the rest of Porto"
>    - Students praised the spectacul…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 9.108s · **Sources:** 5
- **Rewritten query:** *student accommodation Porto first-time visitors recommended popular well-reviewed*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Paranhos | Boavista, Porto | 0.723 | — |
| 2 | Casa Verde | Foz do Douro, Porto | 0.712 | — |
| 3 | Residencia Ribeira | Paranhos, Porto | 0.699 | — |
| 4 | Cosy Home Porto | Ramalde, Porto | 0.698 | — |
| 5 | Residencia Campanha | Ribeira, Porto | 0.697 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, here are the Porto properties that students specifically recommend for first-time visitors:
> 
> **Highly Recommended Properties:**
> 
> 1. **Casa Verde (Foz do Douro)** - According to a review with a 5/5 rating, this property is "highly recommended" for Erasmus students. The student praised the excellent natural light, fast internet, clean shared bathroom, and especially highlighted that "the landlord went above and beyond — helped me settle in and was always just a message away."
> 
> 2. **Residencia Ribeira (Paranhos)** - A student gave this 4/5 stars and called i…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 18.918s · **Sources:** 5
- **Rewritten query:** *student accommodation Porto first-time visitors recommended popular well-reviewed*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Casa Azul | Boavista, Porto | 0.680 | 0.696 |
| 2 | Residencia Ribeira | Paranhos, Porto | 0.699 | 0.504 |
| 3 | Cosy Home Porto | Ramalde, Porto | 0.668 | 0.382 |
| 4 | Cosy Home Porto | Ramalde, Porto | 0.698 | 0.038 |
| 5 | Casa Verde | Foz do Douro, Porto | 0.681 | 0.024 |

**Answer (first 600 chars):**

> Based on the student reviews provided, here are the Porto properties that students recommend for first-time visitors:
> 
> **Highly Recommended Properties:**
> 
> 1. **Casa Azul (Boavista)** - According to a review, this property offers "exceptional value — far better than other options I considered." The student specifically states "I would highly recommend this place to any Erasmus student looking for quality accommodation." They praised the excellent WiFi (300 Mbps), helpful landlord, and great location.
> 
> 2. **Cosy Home Porto (Ramalde)** - Two separate reviews recommend this property. One student s…

---

### q10 — amenity_specific

**Question:** rooms with fast WiFi praised by students

*Specific amenity combined with positive sentiment*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 8.436s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Graca, Lisbon | 0.631 | — |
| 2 | Bright Apartment Bonfim | Bonfim, Porto | 0.592 | — |
| 3 | Bright Apartment Ribeira | Ribeira, Porto | 0.577 | — |
| 4 | Bright Apartment Bonfim | Bonfim, Porto | 0.570 | — |
| 5 | Residencia Mouraria | Chiado, Lisbon | 0.567 | — |

**Answer (first 600 chars):**

> Based on the student reviews, several rooms received high praise for their fast WiFi connections:
> 
> **Top WiFi Speeds Praised:**
> 
> According to reviews of **Bright Apartment Bonfim in Porto**, students were thrilled with **1000 Mbps WiFi**. One student noted "The WiFi was outstanding — 1000 Mbps made video calls and online studying completely effortless" for both the regular room and Garden View Room.
> 
> **Other Highly-Rated WiFi Connections:**
> 
> - **Bright Apartment Ribeira, Porto** and **Residencia Mouraria, Lisbon** both received praise for **500 Mbps WiFi**, with students saying it made "video …

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 9.42s · **Sources:** 5
- **Rewritten query:** *fast WiFi internet connection reliable speed praised students accommodation rooms*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Graca, Lisbon | 0.619 | — |
| 2 | Bright Apartment Bonfim | Bonfim, Porto | 0.598 | — |
| 3 | Residencia Mouraria | Chiado, Lisbon | 0.572 | — |
| 4 | Bright Apartment Bonfim | Bonfim, Porto | 0.570 | — |
| 5 | Bright Apartment Bonfim | Bonfim, Porto | 0.568 | — |

**Answer (first 600 chars):**

> Based on the student reviews, several rooms received high praise for their fast WiFi:
> 
> **Top-rated WiFi speeds:**
> 
> According to reviews of **Bright Apartment Bonfim in Porto**, students were extremely satisfied with the **1000 Mbps WiFi**. One student described it as "outstanding — 1000 Mbps made video calls and online studying completely effortless" (Reviews 2 and 5).
> 
> **Residencia Mouraria in Chiado, Lisbon** also received excellent WiFi feedback, with a student praising the **500 Mbps connection** as "outstanding — made video calls and online studying completely effortless" (Review 3).
> 
> **R…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 18.312s · **Sources:** 5
- **Rewritten query:** *fast WiFi internet connection reliable speed praised students accommodation rooms*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Parque das Nacoes Student Flat | Parque das Nacoes, Lisbon | 0.540 | 0.490 |
| 2 | Casa Verde | Foz do Douro, Porto | 0.531 | 0.401 |
| 3 | Residencia Campo de Ourique | Chiado, Lisbon | 0.553 | 0.280 |
| 4 | Casa Azul | Boavista, Porto | 0.536 | 0.237 |
| 5 | Bright Apartment Bonfim | Bonfim, Porto | 0.567 | 0.197 |

**Answer (first 600 chars):**

> Based on the student reviews provided, several rooms have been praised for their fast WiFi connections:
> 
> **Highest Speed WiFi:**
> - **Residencia Campo de Ourique in Chiado, Lisbon** and **Bright Apartment Bonfim in Porto** both offer 1000 Mbps WiFi. According to reviews of these properties, students found the "WiFi was outstanding — 1000 Mbps made video calls and online studying completely effortless."
> 
> **Other Fast WiFi Options:**
> - **Parque das Nacoes Student Flat in Lisbon** offers 500 Mbps WiFi. A student review noted "The WiFi was outstanding — 500 Mbps made video calls and online studying…

---

### q11 — cleanliness

**Question:** properties where cleanliness was specifically praised

*Quality dimension that cross-encoder should weight heavily*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 6.022s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Intendente | Graca, Lisbon | 0.551 | — |
| 2 | Residencia Alfama | Belem, Lisbon | 0.547 | — |
| 3 | Bright Apartment Bonfim | Bonfim, Porto | 0.543 | — |
| 4 | Casa Verde | Foz do Douro, Porto | 0.541 | — |
| 5 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.538 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, cleanliness was specifically praised in **all five properties**:
> 
> **Properties where cleanliness was highlighted:**
> 
> 1. **Residencia Intendente (Graca, Lisbon)** - According to the review, "Cleanliness was a real highlight — the landlord clearly takes great pride in the property."
> 
> 2. **Residencia Alfama (Belem, Lisbon)** - The student described it as "One of the cleanest apartments I have lived in — kitchen, bathroom and floors all spotless" and noted that "The 2 shared bathrooms were always clean."
> 
> 3. **Bright Apartment Bonfim (Bonfim, Porto)** - The r…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 7.5s · **Sources:** 5
- **Rewritten query:** *clean, cleanliness praised, well-maintained, spotless, hygienic, tidy accommodation*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Casa Azul | Boavista, Porto | 0.687 | — |
| 2 | Residencia Campanha | Foz do Douro, Porto | 0.682 | — |
| 3 | Bright Apartment Bonfim | Bonfim, Porto | 0.676 | — |
| 4 | Casa do Sol | Chiado, Lisbon | 0.673 | — |
| 5 | Residencia Intendente | Graca, Lisbon | 0.672 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, cleanliness was specifically praised in **all five properties**:
> 
> **Casa Azul (Boavista, Porto)** - According to the review, "Cleanliness was a real highlight — the landlord clearly takes great pride in the property."
> 
> **Residencia Campanha (Foz do Douro, Porto)** - The student described it as "One of the cleanest apartments I have lived in — kitchen, bathroom and floors all spotless."
> 
> **Bright Apartment Bonfim (Bonfim, Porto)** - The review highlighted that "Cleanliness was a real highlight — the landlord clearly takes great pride in the property" and n…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 16.08s · **Sources:** 5
- **Rewritten query:** *clean, cleanliness praised, well-maintained, spotless, hygienic, tidy accommodation*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Casa do Sol | Boavista, Porto | 0.663 | 0.342 |
| 2 | Residencia Campanha | Foz do Douro, Porto | 0.682 | 0.293 |
| 3 | Casa Nova | Principe Real, Lisbon | 0.640 | 0.288 |
| 4 | Casa do Sol | Bairro Alto, Lisbon | 0.644 | 0.275 |
| 5 | Bright Apartment Bonfim | Bonfim, Porto | 0.676 | 0.245 |

**Answer (first 600 chars):**

> Based on the student reviews provided, cleanliness was specifically praised in **all five properties**:
> 
> **Casa do Sol — Cosy Double (Boavista, Porto)**: According to the review, "The apartment was impeccably clean on arrival and well maintained throughout."
> 
> **Residencia Campanha — Studio Loft (Foz do Douro, Porto)**: The student described it as "One of the cleanest apartments I have lived in — kitchen, bathroom and floors all spotless."
> 
> **Casa Nova — Single Standard (Principe Real, Lisbon)**: The review states "The apartment was impeccably clean on arrival and well maintained throughout."
> 
> …

---

### q12 — value_for_money

**Question:** good value for money according to past students

*Subjective economic judgement from reviews*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 7.707s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Boavista Student Flat | Boavista, Porto | 0.382 | — |
| 2 | Casa Verde | Foz do Douro, Porto | 0.371 | — |
| 3 | Graca Student Flat | Graca, Lisbon | 0.344 | — |
| 4 | Residencia Campanha | Ribeira, Porto | 0.320 | — |
| 5 | Residencia Ribeira | Bonfim, Porto | 0.316 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, **all five properties received positive feedback regarding value for money**, with each review specifically titled "Good value for money" and rated 4/5 stars overall.
> 
> According to these past students, the properties offer good value because they provide:
> 
> **Essential student amenities:**
> - Dedicated study desks described as "perfect for long university work sessions" (mentioned in all 5 reviews)
> - Comfortable beds (single or double) suitable for student stays
> - Well-equipped kitchens with washing machines and full cooking setups
> 
> **Quality connectivity a…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 8.984s · **Sources:** 5
- **Rewritten query:** *good value for money, affordable, cheap, budget-friendly, worth the price, reasonable rent, excellent value, cost-effective accommodation*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Lisbon | Alvalade, Lisbon | 0.632 | — |
| 2 | Residencia Foz | Boavista, Porto | 0.623 | — |
| 3 | Residencia Campanha | Ribeira, Porto | 0.612 | — |
| 4 | Residencia Campo de Ourique | Chiado, Lisbon | 0.602 | — |
| 5 | Residencia Chiado | Santos, Lisbon | 0.599 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, **past students consistently consider these properties to offer good value for money**.
> 
> **Strong consensus on value:**
> - **Three reviews explicitly state "For the price, this apartment offers exceptional value — far better than other options I considered"** (Reviews from Cosy Home Lisbon in Alvalade, Residencia Foz in Boavista Porto, and Residencia Campanha in Ribeira Porto)
> - **Three reviews are specifically titled "Good value for money"** (Cosy Home Lisbon in Alvalade, Residencia Campo de Ourique in Chiado, and Residencia Chiado in Santos)
> 
> **What stud…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 19.184s · **Sources:** 5
- **Rewritten query:** *good value for money, affordable, cheap, budget-friendly, worth the price, reasonable rent, excellent value, cost-effective accommodation*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campanha | Ribeira, Porto | 0.612 | 0.262 |
| 2 | Cosy Home Lisbon | Alvalade, Lisbon | 0.632 | 0.250 |
| 3 | Residencia Alfama | Belem, Lisbon | 0.597 | 0.201 |
| 4 | Casa Azul | Boavista, Porto | 0.598 | 0.191 |
| 5 | Casa Azul | Boavista, Porto | 0.578 | 0.155 |

**Answer (first 600 chars):**

> Based on the student reviews provided, **past students consistently rate these properties as excellent value for money**.
> 
> **Overwhelmingly positive feedback on value:**
> All five reviews explicitly mention exceptional value for the price. According to reviews from properties in Ribeira Porto, Alvalade Lisbon, Belem Lisbon, and Boavista Porto, students consistently state that "for the price, this apartment offers exceptional value — far better than other options I considered."
> 
> **Specific value highlights mentioned by students:**
> - **Residencia Campanha (Porto)**: Despite some cleanliness issue…

---

### q13 — social_atmosphere

**Question:** friendly flatmates and social atmosphere

*Social experience, not captured by any structured field*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 8.286s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campanha | Foz do Douro, Porto | 0.506 | — |
| 2 | Residencia Intendente | Belem, Lisbon | 0.494 | — |
| 3 | Massarelos Student Flat | Massarelos, Porto | 0.477 | — |
| 4 | Cosy Home Porto | Ramalde, Porto | 0.468 | — |
| 5 | Bright Apartment Bairro Alto | Bairro Alto, Lisbon | 0.462 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, there is excellent evidence of friendly flatmates and a social atmosphere across multiple properties.
> 
> **Friendly International Community:**
> According to reviews from Residencia Campanha in Foz do Douro, Residencia Intendente in Belem, Massarelos Student Flat, and Bright Apartment Bairro Alto, students consistently report that "My flatmates turned out to be a wonderful international mix — we explored the city together and became close friends." This exact sentiment appears in 4 out of 5 reviews, indicating a strong pattern of positive social experiences.
> …

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 8.185s · **Sources:** 5
- **Rewritten query:** *friendly flatmates social atmosphere community welcoming inclusive fun activities shared spaces*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Porto | Ramalde, Porto | 0.453 | — |
| 2 | Residencia Intendente | Belem, Lisbon | 0.451 | — |
| 3 | Residencia Campanha | Foz do Douro, Porto | 0.429 | — |
| 4 | Cosy Home Lisbon | Bairro Alto, Lisbon | 0.419 | — |
| 5 | Bright Apartment Bairro Alto | Bairro Alto, Lisbon | 0.413 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, there are several positive mentions of friendly flatmates and social atmosphere:
> 
> **Friendly Flatmates & Social Connections:**
> According to multiple reviews, students had excellent experiences with their flatmates. A review of Residencia Intendente in Belem mentions: "My flatmates turned out to be a wonderful international mix — we explored the city together and became close friends." This same positive experience is echoed in reviews of Residencia Campanha in Foz do Douro and Bright Apartment Bairro Alto, where students also described their flatmates as …

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 14.645s · **Sources:** 5
- **Rewritten query:** *friendly flatmates social atmosphere community welcoming inclusive fun activities shared spaces*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Bright Apartment Bairro Alto | Bairro Alto, Lisbon | 0.413 | 0.001 |
| 2 | Massarelos Student Flat | Massarelos, Porto | 0.410 | 0.001 |
| 3 | Residencia Campanha | Foz do Douro, Porto | 0.429 | 0.001 |
| 4 | Residencia Intendente | Belem, Lisbon | 0.451 | 0.001 |
| 5 | Residencia Alfama | Belem, Lisbon | 0.389 | 0.001 |

**Answer (first 600 chars):**

> Based on the student reviews provided, there is consistently excellent feedback about friendly flatmates and social atmosphere across all properties.
> 
> **Flatmate Experience:**
> According to all five reviews from different properties in both Lisbon and Porto, students consistently report that "My flatmates turned out to be a wonderful international mix — we explored the city together and became close friends." This appears across reviews from:
> - Bright Apartment Bairro Alto in Lisbon
> - Massarelos Student Flat in Porto  
> - Residencia Campanha in Porto
> - Residencia Intendente in Lisbon
> - Residenci…

---

### q14 — problem_solving

**Question:** places where the host was helpful in emergencies

*Stress situations — tests retrieval of rare but important content*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 6.301s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campo de Ourique | Chiado, Lisbon | 0.392 | — |
| 2 | Casa Verde | Foz do Douro, Porto | 0.384 | — |
| 3 | Casa Verde | Foz do Douro, Porto | 0.378 | — |
| 4 | Casa Verde | Foz do Douro, Porto | 0.376 | — |
| 5 | Residencia Intendente | Belem, Lisbon | 0.365 | — |

**Answer (first 600 chars):**

> Based on the reviews provided, I can only find one clear example of a host being helpful in emergencies or urgent situations:
> 
> **Casa Verde in Foz do Douro, Porto** - According to one 5-star review, "Communication with the landlord was excellent. Any request was handled professionally and promptly." This suggests the host was responsive and helpful when issues arose.
> 
> However, the reviews actually show more examples of the opposite situation. Multiple reviews mention communication problems with landlords:
> 
> - At **Residencia Campo de Ourique in Chiado, Lisbon**, a reviewer stated "Communication…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 6.852s · **Sources:** 5
- **Rewritten query:** *host helpful emergency responsive quick assistance crisis problem support*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Residencia Campo de Ourique | Chiado, Lisbon | 0.280 | — |
| 2 | Bright Apartment Ramalde | Ramalde, Porto | 0.257 | — |
| 3 | Casa Verde | Foz do Douro, Porto | 0.248 | — |
| 4 | Residencia Alfama | Belem, Lisbon | 0.246 | — |
| 5 | Cosy Home Lisbon | Belem, Lisbon | 0.244 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, I cannot identify any places where the host was helpful in emergencies. In fact, all the reviews indicate the opposite problem.
> 
> The reviews consistently describe poor communication and unresponsive landlords during urgent situations:
> 
> - According to reviews of Residencia Campo de Ourique in Chiado and Casa Verde in Foz do Douro: "Communication was the weakest point. The landlord was difficult to reach when maintenance issues arose."
> 
> - Reviews of Residencia Alfama and Cosy Home Lisbon in Belem state: "The landlord was very slow to respond — sometimes day…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 16.315s · **Sources:** 5
- **Rewritten query:** *host helpful emergency responsive quick assistance crisis problem support*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Boavista Student Flat | Boavista, Porto | 0.207 | 0.004 |
| 2 | Bright Apartment Belem | Belem, Lisbon | 0.192 | 0.001 |
| 3 | Casa Verde | Foz do Douro, Porto | 0.197 | 0.000 |
| 4 | Cosy Home Lisbon | Belem, Lisbon | 0.244 | 0.000 |
| 5 | Bright Apartment Principe Real | Principe Real, Lisbon | 0.191 | 0.000 |

**Answer (first 600 chars):**

> Based on the student reviews provided, several properties had hosts who were helpful in emergencies and responsive situations:
> 
> **Properties with responsive hosts:**
> 
> 1. **Boavista Student Flat (Porto)** - According to the review, "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> 
> 2. **Bright Apartment Belem (Lisbon)** - A student reported that "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> 
> 3. **Casa Verde in Foz do Douro (Porto)** - The review states "Communication wit…

---

### q15 — study_focused

**Question:** best accommodation for thesis writing with desk and peace

*Composite query: amenity + concept + user context*

#### Naive (Phase 1 baseline)

- **Mode:** `naive-pinecone` · **Latency:** 7.449s · **Sources:** 5

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Boavista Student Flat | Boavista, Porto | 0.595 | — |
| 2 | Casa Nova | Principe Real, Lisbon | 0.591 | — |
| 3 | Residencia Alcantara | Santos, Lisbon | 0.587 | — |
| 4 | Massarelos Student Flat | Massarelos, Porto | 0.576 | — |
| 5 | Casa Verde | Foz do Douro, Porto | 0.574 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, all five properties would be excellent choices for thesis writing, as **every single review mentions having "a dedicated study desk that was perfect for long university work sessions — exactly what an Erasmus student needs."**
> 
> For the best thesis writing environment, I'd particularly recommend:
> 
> **Casa Nova — Single Standard in Principe Real, Lisbon** - According to this review, the room has "excellent natural light throughout the day, which really boosted my mood while studying" and includes a private en-suite bathroom for "complete privacy throughout m…

#### +Query rewriting (Phase 2, Step 1)

- **Mode:** `advanced-rewrite` · **Latency:** 12.621s · **Sources:** 5
- **Rewritten query:** *quiet peaceful accommodation with desk study space thesis writing minimal noise*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Massarelos Student Flat | Massarelos, Porto | 0.636 | — |
| 2 | Boavista Student Flat | Boavista, Porto | 0.634 | — |
| 3 | Residencia Mouraria | Chiado, Lisbon | 0.627 | — |
| 4 | Casa Nova | Principe Real, Lisbon | 0.626 | — |
| 5 | Cosy Home Lisbon | Graca, Lisbon | 0.619 | — |

**Answer (first 600 chars):**

> Based on the student reviews provided, several accommodations would be excellent for thesis writing:
> 
> **Top recommendations for thesis writing:**
> 
> **Residencia Mouraria — Garden View Room (Chiado, Lisbon)** appears to be the best option. According to the review, it offers "a dedicated study desk perfect for long university work sessions" and "outstanding WiFi — 500 Mbps made video calls and online studying completely effortless." The reviewer gave it a perfect 5/5 rating and called it "one of the best decisions I made during my Erasmus year."
> 
> **Casa Nova — Single Standard (Principe Real, Lisb…

#### +Query rewriting +Reranking (Phase 2, Step 2)

- **Mode:** `advanced-rewrite+rerank` · **Latency:** 18.611s · **Sources:** 5
- **Rewritten query:** *quiet peaceful accommodation with desk study space thesis writing minimal noise*

**Top sources:**

| # | Property | Location | Vector score | Rerank score |
|---|---|---|---:|---:|
| 1 | Cosy Home Porto | Ramalde, Porto | 0.576 | 0.007 |
| 2 | Casa Nova | Principe Real, Lisbon | 0.626 | 0.007 |
| 3 | Residencia Graca | Intendente, Lisbon | 0.572 | 0.006 |
| 4 | Massarelos Student Flat | Massarelos, Porto | 0.636 | 0.006 |
| 5 | Cosy Home Lisbon | Graca, Lisbon | 0.619 | 0.005 |

**Answer (first 600 chars):**

> Based on the student reviews provided, several accommodations would be excellent for thesis writing with desk and peaceful conditions:
> 
> **Top recommendations:**
> 
> **Residencia Graca (Intendente, Lisbon)** - According to the review, this property offers "the dedicated study desk was perfect for long university work sessions" and has "excellent natural light throughout the day, which really boosted my mood while studying." The reviewer gave it a perfect 5/5 rating and called it the "Melhor alojamento Erasmus."
> 
> **Casa Nova (Principe Real, Lisbon)** - A review highlights that it has "the dedicated…

---
