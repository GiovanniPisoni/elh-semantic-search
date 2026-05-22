# ELH RAG — Custom evaluation report — Phase 3 — Agentic RAG

**Generated:** 2026-05-22 18:14
**System under test:** `agentic-RAG`
**Queries:** 20 total · 20 OK · 0 errored

Custom evaluation framework — written from scratch after RAGAS 0.4 
produced ~90% NaN values on this golden set. Three metrics measured:
**faithfulness**, **context_recall**, **answer_relevancy**. Each metric 
is judged by Claude Sonnet 4.5 with a deterministic JSON-output 
contract; per-claim reasoning is preserved in the JSONL companion file.

## Aggregates

| Metric | Avg | Median | Min | Max | Valid (N) | Skipped |
|---|---:|---:|---:|---:|---:|---:|
| faithfulness | 0.622 | 0.78 | 0.0 | 1.0 | 10 | 10 |
| context_recall | 0.361 | 0.0 | 0.0 | 1.0 | 18 | 2 |
| answer_relevancy | 0.885 | 1.0 | 0.3 | 1.0 | 20 | 0 |

'Skipped' counts queries where the metric was not applicable, e.g. 
`context_recall` on queries with empty `must_mention`, or 
`faithfulness` when the answer correctly said 'I don't know'. 
These are NOT failures — they are the metrics opting out cleanly.

## Problems detected (prioritised)

Found **20 sub-threshold case(s)** out of 20 queries.

Thresholds:
- faithfulness < 0.7
- context_recall < 0.6
- answer_relevancy < 0.7

| # | Query ID | Metric | Score | Severity (gap) | Question |
|---|---|---|---:|---:|---|
| 1 | q16 | faithfulness | 0.0 | 0.7 | Flat in a quiet neighbourhood with a lift |
| 2 | q18 | faithfulness | 0.0 | 0.7 | Posso ter outra pessoa no quarto comigo? |
| 3 | q02 | context_recall | 0.0 | 0.6 | Apartments with balcony in Porto |
| 4 | q04 | context_recall | 0.0 | 0.6 | Os senhorios respondem rapidamente? |
| 5 | q06 | context_recall | 0.0 | 0.6 | Are the doors or windows in good condition, or do they creak... |
| 6 | q07 | context_recall | 0.0 | 0.6 | Rooms without mould or damp smell? |
| 7 | q10 | context_recall | 0.0 | 0.6 | Rooms with a balcony or terrace? |
| 8 | q11 | context_recall | 0.0 | 0.6 | Could you tell me which rooms have an en-suite bathroom? |
| 9 | q12 | context_recall | 0.0 | 0.6 | Is there a living room or a communal area in the flats? |
| 10 | q13 | context_recall | 0.0 | 0.6 | Studio apartments with kitchen and washing machine |
| 11 | q14 | context_recall | 0.0 | 0.6 | Recommend a flat in Lisbon that's good for international stu... |
| 12 | q17 | context_recall | 0.0 | 0.6 | Could you find me a double room near the city centre, with a... |
| 13 | q19 | context_recall | 0.0 | 0.6 | Il propretario è gentile e disponibile? |
| 14 | q04 | answer_relevancy | 0.3 | 0.4 | Os senhorios respondem rapidamente? |
| 15 | q13 | answer_relevancy | 0.3 | 0.4 | Studio apartments with kitchen and washing machine |
| 16 | q03 | faithfulness | 0.35 | 0.35 | Quiet room to study in Lisbon |
| 17 | q07 | faithfulness | 0.556 | 0.144 | Rooms without mould or damp smell? |
| 18 | q03 | context_recall | 0.5 | 0.1 | Quiet room to study in Lisbon |
| 19 | q17 | answer_relevancy | 0.6 | 0.1 | Could you find me a double room near the city centre, with a... |
| 20 | q19 | answer_relevancy | 0.6 | 0.1 | Il propretario è gentile e disponibile? |

## Per-query details

### q01 — review_safety

**Question (en):** `Did students feel safe at night in their accommodations?`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 14.998s · **Sources:** 10

**Answer (first 400 chars):**

> Based on the student reviews, **yes, students generally felt safe at night in their ELH accommodations**. Here's what they reported:
> 
> ## Security Features That Made Students Feel Safe
> 
> Multiple students specifically mentioned that **CCTV cameras and secure digital entry systems gave them complete peace of mind about safety**. This was highlighted in reviews from:
> 
> - **Porto, Cedofeita** (Bright Ap...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about whether students felt safe at night in their accommodations. It provides a clear 'yes' answer supported by specific evidence from student reviews, including direct quotes about security features (CCTV, digital entry systems) that contributed to their sense of safety. The answer is well-structured with relevant sections covering security features and overall sentiment. It stays completely on-topic throughout and provides exactly the information the question seeks._

---

### q02 — desc_balcony_porto

**Question (en):** `Apartments with balcony in Porto`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 12.044s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **36 rooms with balconies in Porto**. Here are the top 10 options:
> 
> | **House** | **Zone** | **Room Size** | **Bed Type** | **Bathroom** | **Price/Month** | **Min. Stay** |
> |-----------|----------|--------------|-------------|-------------|-----------------|--------------|
> | **Boavista** | Boavista | 21m² | Double | Shared | €585 | 8 months |
> | **Cedofeita** | Cedofeita | 12m² | Sin...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about apartments with balconies in Porto. It provides exactly what was requested: a list of 36 rooms with balconies in Porto, displaying the top 10 options in a well-organized table format with relevant details (location, size, price, minimum stay). The answer includes practical information like price range, highlights the cheapest option, and offers helpful follow-up actions. This is a complete, on-topic response that fully satisfies the user's query._

---

### q03 — both_quiet_study

**Question (en):** `Quiet room to study in Lisbon`

**faithfulness:** 0.350 · **context_recall:** 0.500 · **answer_relevancy:** 1.000

**Latency:** 15.428s · **Sources:** 5

**Answer (first 400 chars):**

> Great! I found **209 rooms in Lisbon with a study desk**, and I've also gathered feedback from students about quiet, study-friendly spaces. Here are my top recommendations:
> 
> ## **Budget-Friendly Options**
> 
> 1. **Intendente - €410/month** (Alcantara neighborhood)
>    - 18m² private room with double bed
>    - Study desk + built-in wardrobe
>    - Window with natural light
>    - Shared bathrooms
>    - 833m ...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's request for a quiet room to study in Lisbon. It provides: (1) specific room listings with study desks, prices, and locations; (2) relevant details like room size, amenities, and proximity to transport; (3) student feedback specifically about study conditions (quiet spaces, desks, lighting, internet); and (4) actionable next steps. The answer is well-organized, on-topic throughout, and provides exactly the type of information someone looking for a study-friendly room would need. There are no digressions or off-topic content._

**Unsupported claims (13):**

- *209 rooms in Lisbon with a study desk were found* — No source mentions finding 209 rooms or any specific number of available rooms
- *Intendente room costs €410/month in Alcantara neighborhood* — No source mentions Intendente, Alcantara neighborhood, or any room priced at €410/month
- *Intendente €410 room is 18m² with double bed* — No source provides room size specifications or mentions an 18m² room

---

### q04 — review_landlord_pt

**Question (pt):** `Os senhorios respondem rapidamente?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 0.300

**Latency:** 5.225s · **Sources:** 0

**Answer (first 400 chars):**

> Para dar-lhe a resposta mais precisa, poderia esclarecer se está a perguntar sobre:
> 
> - **a equipa da ELH** (a empresa que gere a plataforma e apoia os estudantes), ou
> - **os senhorios individuais** (as pessoas que são proprietárias e gerem cada quarto/apartamento)?
> 
> Vou pesquisar nas avaliações dos estudantes conforme o que pretende saber.

**Judge reasoning (relevancy):** _The question asks 'Do landlords respond quickly?' which is a straightforward inquiry about landlord responsiveness. The answer does not provide any information about landlord response times. Instead, it asks for clarification about whether the user is asking about the ELH team or individual landlords. While this clarification might be useful in some contexts, the question is clear enough that it refers to 'senhorios' (landlords), not the platform team. A better answer would either: (1) provide information about landlord responsiveness based on available data, or (2) if no data exists, state that directly. The answer is somewhat related to the topic but mostly avoids addressing the actual question, making it largely off-topic._

---

### q05 — edge_nonsense

**Question (en):** `asdfgh zxcvbn`

**faithfulness:** N/A · **context_recall:** N/A · **answer_relevancy:** 1.000

**Latency:** 7.081s · **Sources:** 0

**Answer (first 400 chars):**

> I'm not sure what you're asking! It looks like you may have typed something by accident, or perhaps you're testing the chat.
> 
> I'm here to help you with **Erasmus Life Housing** in Lisbon and Porto. I can assist you with:
> 
> - 🔍 **Finding rooms** that match your preferences (location, price, amenities, dates)
> - 💰 **Calculating total costs** for your stay
> - 📋 **Explaining ELH policies** (cancellation,...

**Judge reasoning (relevancy):** _The question 'asdfgh zxcvbn' is clearly unanswerable - it consists of random keyboard characters with no meaningful content or intent. The AI correctly identified this as either accidental typing or a test, did not attempt to hallucinate an answer, and instead politely acknowledged the situation while offering helpful guidance about what it can actually assist with. This is the appropriate response to an unanswerable/nonsense query and deserves full marks._

---

### q06 — review_infrastructure

**Question (en):** `Are the doors or windows in good condition, or do they creak or make noise?`

**faithfulness:** 0.833 · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 11.841s · **Sources:** 10

**Answer (first 400 chars):**

> I searched the student reviews for feedback about doors and windows, but unfortunately the results don't contain specific comments about door or window condition, creaking, or noise. The top matches (with similarity scores below 0.4) focus on other maintenance issues like mould, cleanliness, and WiFi problems rather than doors and windows specifically.
> 
> **What I found instead:** Several reviews me...

**Judge reasoning (relevancy):** _The answer directly addresses the question by explicitly stating that it searched for information about doors and windows but found no specific comments about their condition, creaking, or noise in the available data. It transparently explains what was searched, why no relevant results were found (low similarity scores, focus on other issues), and provides helpful alternative actions the user can take. This is the correct response when the RAG system lacks the requested information - it doesn't hallucinate details about door/window conditions that don't exist in the data. The answer stays completely on-topic and provides actionable next steps._

**Unsupported claims (1):**

- *The top matches have similarity scores below 0.4.* — The sources contain only review text and do not include any similarity scores or metadata about search matching.

---

### q07 — review_humidity

**Question (en):** `Rooms without mould or damp smell?`

**faithfulness:** 0.556 · **context_recall:** 0.000 · **answer_relevancy:** 0.900

**Latency:** 10.952s · **Sources:** 10

**Answer (first 400 chars):**

> Based on the student reviews in our database, **I did not find any complaints about mould or damp smells** in ELH properties. In fact, the reviews that came up emphasize cleanliness and freshness:
> 
> **Rooms with strong cleanliness ratings:**
> 
> 1. **Residencia Miragaia, Foz do Douro (Porto)** — Single Standard & Room
>    - "One of the cleanest apartments I have lived in — kitchen, bathroom and floors ...

**Judge reasoning (relevancy):** _The answer directly addresses the user's question about rooms without mould or damp smell. It provides highly relevant information by: (1) stating no complaints about mould/damp were found in the database, (2) listing specific properties with strong cleanliness ratings and spotless conditions, (3) providing practical advice about ventilation and moisture control, and (4) offering to help further with specific amenity searches. The answer is comprehensive, on-topic, and actionable. Minor deduction only because the user asked a simple yes/no style question ('Rooms without mould?') and received a longer response than strictly necessary, though the additional context is valuable rather than digressive._

**Unsupported claims (8):**

- *Residencia Miragaia Single Standard & Room has a cleaning rating of 5/5* — The sources do not contain any numerical cleaning ratings. This information is not present in the provided sources.
- *Residencia Miragaia Single Standard & Room has an overall rating of 5/5* — The sources do not contain any numerical overall ratings. This information is not present in the provided sources.
- *Residencia Nevogilde Superior Room has a cleaning rating of 5/5* — The sources do not contain any numerical cleaning ratings. This information is not present in the provided sources.

---

### q08 — review_maintenance

**Question (en):** `If something goes wrong, is the maintenance carried out promptly, or is there a long delay in finding a solution?`

**faithfulness:** 0.727 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 12.489s · **Sources:** 6

**Answer (first 400 chars):**

> Based on student reviews, **maintenance response times appear to be a significant concern** at ELH. Here's what residents report:
> 
> **Common complaints:**
> - **Slow landlord responses**: Multiple students mention that landlords take days to reply to urgent maintenance messages, sometimes leaving problems unresolved for extended periods.
> - **Persistent issues not fixed**: Several reviews describe pro...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about maintenance response times and delays. It provides specific information about whether maintenance is carried out promptly (it often isn't, according to reviews), gives concrete examples of delays (days to respond, persistent unresolved issues), and explains the context (individual landlords vs. the company). The answer stays completely on-topic throughout, provides actionable recommendations, and even offers follow-up assistance. This is a direct, complete, and highly relevant response to the question asked._

**Unsupported claims (3):**

- *Several reviews describe WiFi issues that were reported repeatedly but never properly resolved* — While sources 2, 3, 4, 5, and 6 mention WiFi problems, none state that WiFi issues were 'reported repeatedly' or that requests were made to fix them
- *These reviews reflect experiences with individual landlords (who own the rooms), not necessarily the ELH company itself* — The sources do not explain the relationship between landlords and ELH, or clarify that landlords own the rooms rather than ELH
- *The quality and responsiveness of maintenance can vary significantly depending on which landlord manages your specific room* — While the sources show different reviews, they do not explicitly state that quality varies by landlord or that different landlords manage different rooms

---

### q09 — review_atmosphere

**Question (en):** `What's the social atmosphere like with other tenants in shared apartments?`

**faithfulness:** 0.857 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 19.808s · **Sources:** 10

**Answer (first 400 chars):**

> Based on student reviews, the social atmosphere in ELH shared apartments is **generally very positive**. Here's what students report:
> 
> ## Positive Social Experiences
> 
> **International community & friendships:** The most common theme across reviews is that flatmates form genuine friendships. Multiple students mention that their flatmates were "a wonderful international mix" and that they "explored t...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about social atmosphere in shared apartments. It provides specific details about the international community, friendship formation, and social dynamics, supported by concrete examples from student reviews across multiple properties. The answer also balances the positive social aspects with practical considerations (shared facilities), giving a complete picture. The response stays entirely on-topic and provides exactly the information requested._

**Unsupported claims (2):**

- *ELH specifically caters to Erasmus students.* — While multiple reviews mention 'Erasmus student' in recommendations (e.g., 'I would highly recommend this place to any Erasmus student'), none of the sources explicitly state that ELH specifically caters to or targets Erasmus students as an organizational policy.
- *You'll be living with other exchange students in similar situations.* — While reviews mention international flatmates and Erasmus students, no source explicitly states that residents will be living with other exchange students. This is an inference not directly supported by the sources.

---

### q10 — desc_balcony_terrace

**Question (en):** `Rooms with a balcony or terrace?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 10.579s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **71 rooms with a balcony or terrace** across ELH's portfolio. Here are the top 10 matches:
> 
> | Room | City | Zone | Price/Month | Bed | Bathroom | Details |
> |------|------|------|-------------|-----|----------|---------|
> | **Estrela** | Lisbon | Estrela | €690 | Single | Shared | 16m², private balcony, A/C & heating, desk included |
> | **Graca** | Lisbon | Graca | €835 | Double | **P...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about rooms with a balcony or terrace. It provides: (1) the total number of matching rooms (71), (2) a detailed table of top 10 options with relevant information (location, price, room type, balcony/terrace feature), (3) price range summary, and (4) helpful follow-up options. The response is completely on-topic, well-organized, and goes beyond minimal compliance by offering actionable next steps. This is exactly what someone asking this question would want to see._

---

### q11 — desc_ensuite

**Question (en):** `Could you tell me which rooms have an en-suite bathroom?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 13.92s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **145 rooms with en-suite (private) bathrooms** across ELH's portfolio. Here are the top 10 matches:
> 
> ### Lisbon Rooms with Private Bathrooms
> 
> 1. **Intendente #HSE_00F7359B - Room 1**
>    - €510/month (autumn rate)
>    - 13 m², single bed
>    - Green metro line, 833m away
>    - Includes: desk, wardrobe, heating, bed linen & pillows
>    - Minimum 12-month contract
> 
> 2. **Intendente #HSE_00...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about rooms with en-suite bathrooms. It provides: (1) a clear count of 145 rooms matching the criteria, (2) detailed listings of 10 specific rooms with en-suite bathrooms including relevant details like price, size, location, and amenities, and (3) helpful follow-up options to explore more results or filter further. The response is completely on-topic, well-structured, and provides exactly what was requested without any digressions._

---

### q12 — desc_communal_area

**Question (en):** `Is there a living room or a communal area in the flats?`

**faithfulness:** 0.900 · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 14.057s · **Sources:** 10

**Answer (first 400 chars):**

> Based on the property descriptions in our database, **the flats do not appear to have dedicated living rooms or communal lounges**. The descriptions focus on individual rooms with shared bathrooms, but do not mention common living areas, lounges, or communal spaces where tenants can gather.
> 
> The flats are structured around:
> - **Individual bedrooms** (ranging from 11m² to 27m²) with study desks and...

**Judge reasoning (relevancy):** _The answer directly addresses the question about living rooms and communal areas in the flats. It provides a clear, definitive response that such spaces do not appear to exist based on available property descriptions, then explains what amenities ARE available (individual bedrooms, shared bathrooms, private room features). The answer goes beyond a simple 'no' by offering helpful context about the flat structure and practical next steps (contacting ELH directly, checking specific properties). This is exactly the kind of comprehensive, on-topic response that fully addresses what was asked._

**Unsupported claims (1):**

- *Rooms have A/C* — Only Source 4 mentions air conditioning ('air conditioning and heating'). This is not a general feature across the properties described, so claiming rooms have A/C as a standard amenity is not supported.

---

### q13 — desc_amenities_combo

**Question (en):** `Studio apartments with kitchen and washing machine`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 0.300

**Latency:** 11.15s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **369 rooms** with a washing machine and equipped kitchen. Here are the top 15 matches:
> 
> ## **Most Affordable Options:**
> 
> 1. **Graca, Lisbon** – €415/month
>    - 20m², single bed, 2 shared bathrooms, desk & wardrobe
>    - Min. 4-month contract
> 
> 2. **Graca, Lisbon** – €420/month
>    - 14m², double bed, 2 shared bathrooms, desk & wardrobe
>    - Min. 4-month contract
> 
> 3. **Graca, Lisbon** ...

**Judge reasoning (relevancy):** _The user asked for 'studio apartments' but the answer provides shared rooms in co-living spaces (indicated by 'shared bathrooms', room sizes of 10-28m², and the format of listings). Studio apartments are self-contained units with private kitchens and bathrooms, not individual rooms in shared accommodations. While the answer does address the 'kitchen and washing machine' amenities (these appear to be shared facilities in the building), it fundamentally misunderstands the housing type requested. The answer is tangentially related because it provides housing options with the requested amenities, but it completely misses the core requirement of 'studio apartments' versus shared rooms._

---

### q14 — both_recommendation

**Question (en):** `Recommend a flat in Lisbon that's good for international students`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000

**Latency:** 13.547s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found 228 rooms in Lisbon with internet. Let me highlight two excellent options for international students:
> 
> ## **Top Recommendation: Intendente House** 🌟
> 
> **Best for:** Budget-conscious students who want a vibrant neighborhood
> 
> - **Location:** Intendente, Alcantara (Green metro line, 833m away)
> - **Room Options:**
>   - **13m² Single Room** – €510/month (autumn) | Private bathroom, desk, h...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's request for flat recommendations in Lisbon suitable for international students. It provides two detailed property options (Intendente House and Estrela House) with specific information highly relevant to students: pricing, room sizes, locations near metro/transport, amenities like internet and study desks, and neighborhood characteristics. The answer explains why each option is good for students, includes practical details like heating and bed linen, and offers helpful next steps. The response is well-organized, on-topic throughout, and provides actionable information that directly fulfills the user's need._

---

### q15 — both_porto_balcony

**Question (en):** `Are the rooms in central Porto suitable for students, and do they usually have a balcony?`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 16.081s · **Sources:** 10

**Answer (first 400 chars):**

> Based on the property descriptions and student reviews, **yes, central Porto rooms are very suitable for students**, though balconies are not universal.
> 
> ## Student Suitability
> 
> Central Porto properties are explicitly designed with students in mind:
> 
> - **Cedofeita** is described as "one of Porto's most vibrant areas, popular with students and young creatives," with excellent amenities like high-sp...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses both parts of the user's question: (1) whether central Porto rooms are suitable for students, and (2) whether they usually have balconies. It provides specific evidence for student suitability (amenities, student reviews, proximity to universities) and clearly answers the balcony question by explaining that not all rooms have them but several do, with concrete examples. The answer is well-structured, on-topic throughout, and even offers helpful follow-up assistance. This is a complete, direct response to exactly what was asked._

---

### q16 — both_quiet_lift

**Question (en):** `Flat in a quiet neighbourhood with a lift`

**faithfulness:** 0.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 13.518s · **Sources:** 5

**Answer (first 400 chars):**

> Great! I found **103 rooms with elevators** in our ELH database. Here are the top 10 options:
> 
> ## Rooms with Elevators
> 
> ### **Lisbon - Estrela (Graça neighborhood)**
> All rooms in this building have elevators and are in a quieter residential area:
> 
> 1. **28m² Double Room** – €665–690/month
>    - Queen-size bed + second bed
>    - Private en-suite bathroom
>    - Study desk & built-in wardrobe
>    - Minimu...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's request for a flat in a quiet neighbourhood with a lift. It provides 7 specific room options that all have elevators (lifts), explicitly highlights the Estrela/Graça neighborhood as quiet and residential, includes supporting evidence from student reviews about the peaceful atmosphere, and offers relevant follow-up options. The answer is well-structured, on-topic, and provides exactly what was requested with appropriate detail._

**Unsupported claims (15):**

- *103 rooms with elevators were found in the ELH database* — None of the sources mention 103 rooms or provide any database statistics about rooms with elevators
- *There is a 28m² Double Room in Lisbon - Estrela (Graça neighborhood) priced at €665–690/month* — None of the sources mention any properties in Estrela or Graça neighborhood
- *The 28m² Double Room has a queen-size bed plus second bed* — No source describes this room or its bed configuration

---

### q17 — both_double_central

**Question (en):** `Could you find me a double room near the city centre, with a desk for studying, a washing machine and fast Wi-Fi?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 0.600

**Latency:** 11.43s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found 4 rooms matching your criteria. Here are the results:
> 
> **1. Foz do Douro, Porto – Double Room (28m²) – €620/month**
>    - **Room ID:** HSE_32C54BAC|RM_HSE_32C54BAC_2
>    - **Features:** Double bed, desk, wardrobe, shared bathrooms
>    - **Minimum stay:** 8 months
>    - **Price note:** €620/month (autumn rate; spring and summer rates differ)
>    - **Distance to transport:** 331m
> 
> **2. Foz...

**Judge reasoning (relevancy):** _The answer is partially on-topic but has significant issues. The user asked for a double room, and the system correctly identifies this need. However, the results include two single rooms (#3 and #4), which directly contradicts the request. Additionally, the answer claims all rooms are 'near the city centre' but all results are in Foz do Douro, which is a coastal neighborhood in Porto, not typically considered city centre. The answer does address the desk, washing machine, and Wi-Fi requirements, and provides structured information about each option. The system also offers helpful follow-up actions. However, the inclusion of irrelevant single rooms and the questionable 'city centre' claim significantly reduce the directness and accuracy of the response. The answer is useful but not fully aligned with what was asked._

---

### q18 — edge_multilingual_pt

**Question (pt):** `Posso ter outra pessoa no quarto comigo?`

**faithfulness:** 0.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000

**Latency:** 12.642s · **Sources:** 4

**Answer (first 400 chars):**

> A resposta ainda não foi específica. Deixe-me procurar nos detalhes das propriedades, pois essa informação pode estar relacionada aos amenities dos quartos.
> 
> A política sobre ter outra pessoa no quarto depende de cada propriedade específica. Algumas casas e quartos da ELH permitem uma pessoa extra no quarto (isso é indicado como "extra_person_allowed" nos detalhes do quarto), enquanto outras não p...

**Judge reasoning (relevancy):** _The question asks 'Can I have another person in the room with me?' and the answer directly addresses this by explaining that the policy depends on the specific property, some rooms allow an extra person (indicated by 'extra_person_allowed' in room details) while others don't. The answer provides actionable information on how to find this information (filtering by amenities, checking room details), mentions there's an additional cost, and offers to help search for rooms that allow extra persons. This is a complete, on-topic response that fully addresses what was asked._

**Unsupported claims (7):**

- *A política sobre ter outra pessoa no quarto depende de cada propriedade específica* — This claim is not stated or implied in any of the provided sources
- *Algumas casas e quartos da ELH permitem uma pessoa extra no quarto* — None of the sources mention extra person policies or allowances
- *A informação sobre pessoa extra é indicada como 'extra_person_allowed' nos detalhes do quarto* — The sources do not mention this field or any details about extra person information

---

### q19 — edge_multilingual_it

**Question (it):** `Il propretario è gentile e disponibile?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 0.600

**Latency:** 5.218s · **Sources:** 0

**Answer (first 400 chars):**

> Per darti una risposta accurata, potresti chiarire se ti stai riferendo a:
> 
> - **il team di ELH** (l'azienda che gestisce la piattaforma e supporta gli studenti), oppure
> - **i singoli proprietari** (le persone che possiedono e gestiscono le singole stanze)?
> 
> Una volta che mi indichi quale dei due intendi, cercherò nelle recensioni degli studenti per vedere cosa dicono sulla gentilezza e disponibili...

**Judge reasoning (relevancy):** _The question asks 'Is the owner kind and available?' in Italian. The answer is on-topic as it addresses the question about owner kindness/availability, but instead of providing information, it asks for clarification about whether the user means ELH team or individual property owners. While this clarification request is reasonable and shows understanding of the ambiguity, it doesn't actually answer the question. A better response would either assume the most likely interpretation (individual property owners) and provide information, or briefly address both possibilities. The answer is helpful but incomplete, as it defers providing any actual information about owner kindness/availability._

---

### q20 — edge_unanswerable

**Question (en):** `Is good at work Sofia?`

**faithfulness:** N/A · **context_recall:** N/A · **answer_relevancy:** 1.000

**Latency:** 5.747s · **Sources:** 0

**Answer (first 400 chars):**

> I'd be happy to help you with information about Erasmus Life Housing accommodations! However, I'm not quite sure what you're asking about.
> 
> Could you clarify what you mean by "Is good at work Sofia?"? 
> 
> Are you asking about:
> - A specific property or room named "Sofia" in Lisbon or Porto?
> - Someone's work experience or reviews related to ELH?
> - Something else related to student housing?
> 
> Please pro...

**Judge reasoning (relevancy):** _The question 'Is good at work Sofia?' is grammatically broken and unclear in intent. It could be asking about a person named Sofia, a location, or something else entirely, but the phrasing makes it impossible to determine what information is actually being requested. The AI correctly identifies that the question is unclear and cannot be answered without clarification. Rather than hallucinating an answer, it appropriately asks for clarification while offering possible interpretations within its domain (housing accommodations). This is the correct behavior for an unanswerable/unclear question._

---

## How to interpret these numbers

**faithfulness** — fraction of answer claims supported by sources. 
Avg < 0.7 means the LLM is fabricating facts. Likely fix: tighten 
the system prompt to enforce 'use only the sources'.

**context_recall** — fraction of must-mention concepts covered by 
retrieved sources. Avg < 0.6 means the retriever is missing 
relevant documents. Likely fix: increase top_k, investigate 
reranker behaviour, or revisit chunk size for long descriptions.

**answer_relevancy** — how on-topic the answer is. Avg < 0.7 means 
the LLM is rambling, off-topic, or hallucinating answers to 
unanswerable queries. Likely fix: prompt clarity, or upstream 
retrieval quality (irrelevant sources push the LLM to improvise).

**Skipped queries (None scores)** are the metrics opting out cleanly. 
Queries q05 and q20 are unanswerable — `must_mention` is empty so 
`context_recall` correctly skips. If the LLM said 'I don't know', 
`faithfulness` skips too (no claims to verify). This is the SUCCESS 
path for those queries — not a failure.
