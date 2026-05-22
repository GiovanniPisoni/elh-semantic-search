# ELH RAG — Custom evaluation report — Phase 2 — Pipelined RAG

**Generated:** 2026-05-22 19:54
**System under test:** `pipelined-RAG`
**Queries:** 20 total · 20 OK · 0 errored

Custom evaluation framework — written from scratch after RAGAS 0.4 
produced ~90% NaN values on this golden set. Four metrics measured:
**faithfulness**, **context_recall**, **answer_relevancy**, **task_success**. 
Each metric is judged by Claude Sonnet 4.5 with a deterministic JSON-output 
contract; per-claim reasoning is preserved in the JSONL companion file. 
`task_success` is architecture-agnostic — it judges (question, answer) 
without retrieved contexts, so it applies equally to pipeline and agentic systems.

## Aggregates

| Metric | Avg | Median | Min | Max | Valid (N) | Skipped |
|---|---:|---:|---:|---:|---:|---:|
| faithfulness | 0.969 | 1.0 | 0.8 | 1.0 | 18 | 2 |
| context_recall | 0.485 | 0.45 | 0.0 | 1.0 | 20 | 0 |
| answer_relevancy | 0.94 | 1.0 | 0.7 | 1.0 | 20 | 0 |
| task_success | 0.725 | 0.75 | 0.0 | 1.0 | 20 | 0 |

'Skipped' counts queries where the metric was not applicable, e.g. 
`context_recall` on queries with empty `must_mention`, or 
`faithfulness` when the answer correctly said 'I don't know'. 
These are NOT failures — they are the metrics opting out cleanly.

## Problems detected (prioritised)

Found **12 sub-threshold case(s)** out of 20 queries.

Thresholds:
- faithfulness < 0.7
- context_recall < 0.6
- answer_relevancy < 0.7
- task_success < 0.5

| # | Query ID | Metric | Score | Severity (gap) | Question |
|---|---|---|---:|---:|---|
| 1 | policy_01 | context_recall | 0.0 | 0.6 | What is the cancellation policy if I cancel 45 days before c... |
| 2 | policy_03 | context_recall | 0.0 | 0.6 | What is included in the monthly rent? |
| 3 | cost_01 | context_recall | 0.0 | 0.6 | Find the cheapest room in Lisbon and tell me the total cost ... |
| 4 | multilingual_04 | task_success | 0.0 | 0.5 | Wie funktioniert die Stornierung bei Erasmus Life Housing? |
| 5 | cost_02 | context_recall | 0.2 | 0.4 | Find the cheapest room in Porto available for the full acade... |
| 6 | multilingual_02 | context_recall | 0.25 | 0.35 | Procuro quartos com varanda em Lisboa para setembro de 2026 |
| 7 | policy_02 | context_recall | 0.333 | 0.267 | When is the security deposit refunded after I leave? |
| 8 | policy_04 | context_recall | 0.333 | 0.267 | How does the check-in process work? |
| 9 | multilingual_04 | context_recall | 0.333 | 0.267 | Wie funktioniert die Stornierung bei Erasmus Life Housing? |
| 10 | cost_03 | context_recall | 0.4 | 0.2 | Compare the total cost of the cheapest room in Lisbon vs the... |
| 11 | cost_04 | context_recall | 0.4 | 0.2 | What is the total cost for a 12-month stay in Lisbon startin... |
| 12 | multilingual_03 | context_recall | 0.5 | 0.1 | ¿Cuál es la habitación más barata en Porto para 6 meses desd... |

## Per-query details

### structural_01 — structural

**Question (en):** `Find the cheapest single rooms in Lisbon`

**faithfulness:** N/A · **context_recall:** 0.667 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 42.791s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, here are the cheapest single rooms in Lisbon:
> 
> **Cheapest Options:**
> 
> 1. **Room in Cosy Home Lisbon (Alvalade)** - **€460/month** (summer rate)
>    - 11m² with single bed, shared bathrooms, private balcony
>    - Seasonal pricing: Summer €460, Spring €505, Autumn €710
> 
> 2. **Bright Single in Cosy Home Lisbon (Santos)** - **€505/month** (summer rate)  
>    - Larg...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about finding the cheapest single rooms in Lisbon. It provides a well-organized list of options ranked by price, starting with the absolute cheapest at €460/month. The response includes relevant details such as room sizes, amenities, locations, and importantly notes seasonal pricing variations that affect the actual cost. The answer goes beyond just listing prices by providing context about fixed vs. seasonal rates, which helps the user make an informed decision. This is exactly what someone asking for 'the cheapest single rooms' would need to know._

---

### structural_02 — structural

**Question (en):** `Show me rooms with a private bathroom under 600 EUR in Porto`

**faithfulness:** N/A · **context_recall:** 0.750 · **answer_relevancy:** 0.900 · **task_success:** 0.500

**Latency:** 16.105s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, here are the rooms with private bathrooms under €600 in Porto:
> 
> **1. Master Suite in Cosy Home Porto (Massarelos)**
> - **Price**: €495/month (spring), €390/month (summer)
> - **Details**: 12m² private room with double bed, study desk, built-in wardrobe, window with natural light, and independent heating
> - **Important note**: This room has a **shared bathroom**...

**Judge reasoning (relevancy):** _The answer directly addresses the user's request for rooms with private bathrooms under €600 in Porto. It provides a specific room that meets the criteria (Economy Room at €545/month), correctly identifies that another room mentioned does NOT meet the private bathroom requirement, and transparently explains that most options with private bathrooms exceed the budget. The answer is well-structured, provides relevant details (price, size, amenities), and offers helpful context about seasonal pricing and alternatives. The only minor issue preventing a perfect score is the inclusion of the Master Suite which doesn't meet the criteria - while this is acknowledged, it adds slight clutter to what should be a focused answer. Overall, this is a highly on-topic, useful, and complete response._

---

### structural_03 — structural

**Question (en):** `What rooms are available within 500 meters of a metro station in Lisbon?`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 0.700 · **task_success:** 0.500

**Latency:** 21.373s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the house descriptions provided, I can identify properties within 500 meters of metro stations in Lisbon, but I need to clarify that the sources don't contain specific room availability information - only house-level details.
> 
> **Properties within 500 meters of metro stations:**
> 
> **Residencia Intendente** - This is the only property that falls within your 500-meter requirement. According t...

**Judge reasoning (relevancy):** _The answer is on-topic and attempts to address the question about rooms near metro stations in Lisbon. It correctly identifies properties within or near the 500-meter requirement and provides specific distance information. However, there are two issues that prevent a higher score: (1) The answer admits it cannot provide room-level availability information, only house-level details, which is a significant gap given the question specifically asks about 'rooms available', and (2) The main property mentioned (Residencia Intendente) is actually stated to be 605m away, which exceeds the 500-meter requirement, though the answer tries to frame it as 'close'. The answer is useful and relevant but doesn't fully deliver what was asked for - specific room availability within the distance constraint._

---

### structural_04 — structural

**Question (en):** `Find rooms larger than 20 square meters in Lisbon under 700 EUR`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000 · **task_success:** 0.500

**Latency:** 18.435s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, I found **2 rooms** that meet your criteria of being larger than 20 square meters in Lisbon under 700 EUR:
> 
> **Room 3 - Garden View Room in Residencia Telheiras (Arroios)**
> - Size: Exactly 20m² (meets your size requirement)
> - Price: €455/month (well under your budget)
> - Features: King-size bed, shared bathroom, study desk, bed linen included
> - According to t...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's query. It identifies rooms matching the criteria (>20m², Lisbon, <700 EUR), provides specific details about each room including size, price, location, and features. The answer also demonstrates thoroughness by explaining why other rooms don't qualify and includes an important clarification about the '20m²' threshold (noting that the rooms found are exactly 20m², not larger). This is a complete, on-topic response that gives the user exactly what they asked for with helpful context._

---

### policy_01 — policy

**Question (en):** `What is the cancellation policy if I cancel 45 days before check-in?`

**faithfulness:** 1.000 · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 17.751s · **Sources:** 5
**Routing:** descriptions (conf=0.85, src=llm)

**Answer (first 400 chars):**

> I cannot find any information about cancellation policies in the provided sources. The sources contain detailed descriptions of rooms and properties in Porto and Lisbon, including pricing, amenities, and house rules, but none of them mention cancellation policies or what happens if you cancel 45 days before check-in.
> 
> To get accurate information about ELH's cancellation policy for bookings cancell...

**Judge reasoning (relevancy):** _The answer is completely on-topic and appropriate. The user asked a specific question about cancellation policy (45 days before check-in). The AI correctly identified that this information is not available in the provided sources and transparently communicated this limitation. Rather than hallucinating a policy, the AI gave honest guidance on where to find the information (terms and conditions or direct contact). This is the correct behavior when facing an unanswerable question due to missing source material. The answer directly addresses what was asked and provides helpful next steps._

---

### policy_02 — policy

**Question (en):** `When is the security deposit refunded after I leave?`

**faithfulness:** 1.000 · **context_recall:** 0.333 · **answer_relevancy:** 0.800 · **task_success:** 0.500

**Latency:** 18.504s · **Sources:** 5
**Routing:** descriptions (conf=0.85, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, the security deposits are **returned after check-out**, but the sources don't specify the exact timeframe for when this happens.
> 
> According to the descriptions of all the properties mentioned:
> 
> - **Foz do Douro Student Flat (Economy Room)**: "A security deposit of €585 is held for the duration of the stay and returned after check-out"
> - **Foz do Douro Stude...

**Judge reasoning (relevancy):** _The answer is on-topic and directly addresses the user's question about when the security deposit is refunded after leaving. It correctly identifies that deposits are returned after check-out and provides comprehensive evidence from multiple properties. The answer is honest about the limitation that exact timeframes aren't specified in the sources, and appropriately suggests contacting ELH for more specific information. This is a useful, accurate response. The minor deduction from 1.0 is because while the answer is complete given the available information, it doesn't fully satisfy what the user wanted to know (the specific timeframe), though this is due to source limitations rather than the answer being off-topic._

---

### policy_03 — policy

**Question (en):** `What is included in the monthly rent?`

**faithfulness:** 0.938 · **context_recall:** 0.000 · **answer_relevancy:** 0.700 · **task_success:** 0.500

**Latency:** 18.139s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, the monthly rent includes the following items:
> 
> **What's included in all rooms:**
> - Study desk and built-in wardrobe
> - Bed linen and pillows
> - Window with natural light
> - Access to shared bathrooms (2-4 bathrooms depending on the property)
> 
> **Heating/Climate Control:**
> - Independent heating (Residencia Nevogilde and Residencia Miragaia in Porto)
> - Both A/C ...

**Judge reasoning (relevancy):** _The answer is on-topic and provides useful information about what's included in the monthly rent (furniture, amenities, heating/AC). It correctly identifies items explicitly mentioned in the source material and appropriately notes what isn't specified (utilities, internet, cleaning). However, the answer could be more direct - it spends considerable space listing room-by-room details and pricing information that, while related, goes beyond what was asked. The user asked a simple question about rent inclusions, and the core answer (furniture, heating, some amenities) could have been stated more concisely upfront. The additional context about extra fees and deposits, while potentially useful, further dilutes the directness of the response. A more focused answer would have earned a higher score._

**Unsupported claims (1):**

- *Cosy Home Lisbon rooms in Santos have both A/C and heating* — Source 5 (Santos, Intendente) only mentions 'Room heating included', not A/C

---

### policy_04 — policy

**Question (en):** `How does the check-in process work?`

**faithfulness:** 1.000 · **context_recall:** 0.333 · **answer_relevancy:** 1.000 · **task_success:** 0.500

**Latency:** 16.983s · **Sources:** 5
**Routing:** descriptions (conf=0.85, src=llm)

**Answer (first 400 chars):**

> Based on the sources provided, I cannot find specific information about how the check-in process works. The room descriptions from various properties (Foz do Douro Student Flat, Residencia Miragaia, Alfama Student Flat, Residencia Graca, and Principe Real Student Flat) focus on room features, amenities, pricing, and security deposits, but they do not include details about the actual check-in proce...

**Judge reasoning (relevancy):** _The answer directly addresses the question by clearly stating that the specific information about the check-in process is not available in the provided sources. It demonstrates thoroughness by explaining what information IS present in the sources (room features, amenities, pricing) and explicitly listing what check-in details are missing (timing, documents, key collection, contact information). The answer then appropriately directs the user to contact the provider directly. This is the correct response when the RAG sources don't contain the requested information - it's honest, helpful, and on-topic rather than hallucinating an answer._

---

### cost_01 — cost

**Question (en):** `Find the cheapest room in Lisbon and tell me the total cost for 6 months from September 2026`

**faithfulness:** 1.000 · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 15.222s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, the **cheapest room in Lisbon is Room 4 in Graça** at €450/month fixed rate.
> 
> According to the description of the Superior Room in Cosy Home Lisbon located in Graça, this 22m² room with a single bed costs €450/month year-round, with a deposit of €450.
> 
> **Total cost for 6 months from September 2026:**
> - Monthly rent: €450 × 6 months = €2,700
> - Deposit: €450
> ...

**Judge reasoning (relevancy):** _The answer directly and completely addresses the user's question. It identifies the cheapest room in Lisbon (Room 4 in Graça at €450/month), calculates the total cost for 6 months starting September 2026 (€2,700 rent + €450 deposit = €3,150), and provides supporting details about the room. The answer also includes a helpful note comparing it to other rooms with seasonal pricing. This is a thorough, on-topic response that addresses exactly what was asked._

---

### cost_02 — cost

**Question (en):** `Find the cheapest room in Porto available for the full academic year (September 2026 to June 2027) and compute the total cost`

**faithfulness:** 0.800 · **context_recall:** 0.200 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 16.874s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, I need to calculate the total cost for the full academic year (September 2026 to June 2027) for each room.
> 
> **Cost Analysis for Academic Year (10 months: Sep-Jun):**
> 
> **Room 1 - Cosy Home Porto Room (27m²):**
> - Autumn/winter: €565/month × 6 months = €3,390
> - Spring: €455/month × 4 months = €1,820
> - **Total: €5,210**
> 
> **Room 2 - Residencia Miragaia Economy R...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. It systematically analyzes all available Porto rooms, calculates the total cost for the exact period requested (September 2026 to June 2027, which is 10 months), accounts for seasonal pricing variations where applicable, identifies the cheapest option (Room 1 at €5,210), and provides relevant details about that room. The answer is well-structured, shows clear methodology, and includes a helpful note about deposits. This is a complete, on-topic response that fully satisfies the user's request._

**Unsupported claims (5):**

- *Autumn/winter period is 6 months* — Sources do not specify the duration of autumn/winter or spring seasons
- *Spring period is 4 months* — Sources do not specify the duration of spring season
- *Room 5 autumn period is 6 months* — Sources do not specify the duration of autumn season

---

### cost_03 — cost

**Question (en):** `Compare the total cost of the cheapest room in Lisbon vs the cheapest in Porto for 6 months from September 2026`

**faithfulness:** 0.909 · **context_recall:** 0.400 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 15.912s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, I can compare the cheapest options in each city:
> 
> **Cheapest room in Lisbon:**
> According to the room description for the Superior Room in Cosy Home Lisbon (Graca location), this offers a fixed rate of **€450/month** with a €450 deposit.
> 
> **Cheapest room in Porto:**
> According to the room description for the Economy Room in Cosy Home Porto (Ramalde location),...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. It identifies the cheapest rooms in both Lisbon and Porto, calculates the 6-month total costs including deposits for the specified period (September 2026), provides a clear comparison showing the €595 difference, and includes relevant context about pricing assumptions. The response is well-structured, on-topic, and provides exactly the information requested without unnecessary digressions._

**Unsupported claims (1):**

- *The Economy Room in Cosy Home Porto is the cheapest room in Porto* — Only one Porto room is provided in the sources (Source 5), so there is no basis to claim it is the 'cheapest' among multiple Porto options

---

### cost_04 — cost

**Question (en):** `What is the total cost for a 12-month stay in Lisbon starting January 2027 in the cheapest single room?`

**faithfulness:** 1.000 · **context_recall:** 0.400 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 16.451s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the room descriptions provided, the cheapest single room option for a 12-month stay in Lisbon starting January 2027 would be **Room 4 in Cosy Home Lisbon, Alvalade**.
> 
> According to the room description for this 11m² single room in Alvalade, the seasonal rates are:
> - Autumn: €710/month
> - Spring: €505/month  
> - Summer: €460/month
> 
> For a 12-month stay starting January 2027, the total cost wo...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about the total cost for a 12-month stay in Lisbon starting January 2027 in the cheapest single room. It identifies the specific room (Room 4 in Cosy Home Lisbon, Alvalade), provides a detailed month-by-month breakdown of costs accounting for seasonal variations, calculates the total rental cost (€7,540), includes additional costs like security deposit (€700), and arrives at a total upfront cost (€8,240). The answer also provides relevant context about room amenities and acknowledges a potential alternative option with appropriate caveats. This is exactly what was asked for with thorough supporting detail._

---

### semantic_01 — semantic

**Question (en):** `I am looking for a room with a balcony and a view of the Tagus river in Lisbon`

**faithfulness:** 1.000 · **context_recall:** 0.600 · **answer_relevancy:** 0.800 · **task_success:** 0.500

**Latency:** 17.084s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the sources provided, I can identify several rooms with balconies, but unfortunately **none of the sources mention views of the Tagus river specifically**.
> 
> Here are the rooms with private balconies available:
> 
> **Rooms with Private Balconies:**
> 
> 1. **Cosy Home Lisbon in Parque das Nações** - According to the room description, this 25m² room has a "private balcony — not common at this pric...

**Judge reasoning (relevancy):** _The answer is on-topic and directly addresses the user's request for a room with a balcony and Tagus river view. It provides a comprehensive list of 5 rooms with balconies, which is half of what was requested. Crucially, it is transparent about the limitation: none of the sources mention Tagus river views. This honesty is appropriate RAG behavior. The answer loses some points because it cannot fully satisfy the query (no river view information), but it provides maximum useful information given the available data. The response is well-structured, actionable, and doesn't hallucinate information about river views that isn't in the sources._

---

### semantic_02 — semantic

**Question (en):** `Is the Alfama neighborhood quiet at night according to student reviews?`

**faithfulness:** 1.000 · **context_recall:** 0.600 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 22.277s · **Sources:** 5
**Routing:** reviews (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the student reviews provided, there is no specific information about noise levels or how quiet the Alfama neighborhood is at night. 
> 
> The reviews for properties in Alfama (Reviews 1 and 2) focus on other aspects like comfort, amenities, air conditioning, and general location benefits, but neither student mentions anything about nighttime noise levels or the quietness of the area.
> 
> To get ...

**Judge reasoning (relevancy):** _The answer directly addresses the question by clearly stating that the available student reviews do not contain information about noise levels or quietness in Alfama at night. It explains what information IS present in the reviews (comfort, amenities, location) and what is missing (nighttime noise levels). The answer is honest about the limitations of the available data and suggests what would be needed to answer the question properly. This is the correct and appropriate response when the source material doesn't contain the requested information - it's far better than hallucinating an answer. The response is on-topic, complete, and directly addresses what was asked._

---

### semantic_03 — semantic

**Question (en):** `Find rooms in bright spaces with lots of natural light in Lisbon`

**faithfulness:** 0.941 · **context_recall:** 1.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 30.1s · **Sources:** 10
**Routing:** both (conf=0.75, src=llm)

**Answer (first 400 chars):**

> Based on the sources provided, I found several excellent options for bright rooms with lots of natural light in Lisbon:
> 
> ## Available Rooms with Excellent Natural Light:
> 
> **1. Cosy Home Lisbon — Bright Single (Santos)**
> According to the room description, this 26m² room offers "plenty of natural light floods in through the window — a room that never feels dark!" It's priced seasonally: €750/month (...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's request for rooms with lots of natural light in Lisbon. It provides: (1) A curated list of 4 specific rooms that explicitly mention natural light features, (2) Complete details including location, size, and pricing for each option, (3) Supporting evidence from student reviews praising natural light quality, and (4) A clear recommendation for the best options. The answer stays completely on-topic, uses relevant source material, and provides actionable information that directly fulfills the query._

**Unsupported claims (1):**

- *Bright Apartment Estrela — Room is a 14m² room in Estrela* — Source 1 lists the location as 'Lisbon, Estrela, Alvalade' — the room is in Alvalade, not Estrela. The property name is 'Bright Apartment Estrela' but the actual location is Alvalade

---

### semantic_04 — semantic

**Question (en):** `What do students say about how responsive the hosts are at ELH?`

**faithfulness:** 1.000 · **context_recall:** 0.667 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 15.256s · **Sources:** 5
**Routing:** reviews (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Based on the student reviews provided, there are mixed experiences regarding host responsiveness at ELH properties:
> 
> **Positive experiences (majority):**
> - According to a review of Casa do Sol in Intendente, Lisbon: "The landlord was incredibly responsive — always replied within a few hours and resolved every issue quickly."
> - A review of Residencia Miragaia in Foz do Douro, Porto states: "The lan...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about host responsiveness at ELH. It provides specific student testimonials organized into positive and negative categories, includes concrete details (response times, property names, locations), and concludes with a clear summary (4 out of 5 positive reviews). The answer is well-structured, on-topic throughout, and gives the user exactly what they asked for—what students say about host responsiveness._

---

### multilingual_01 — multilingual

**Question (it):** `Quanto costa la cauzione e quando viene restituita?`

**faithfulness:** 0.857 · **context_recall:** 0.667 · **answer_relevancy:** 0.900 · **task_success:** 0.500

**Latency:** 22.292s · **Sources:** 5
**Routing:** descriptions (conf=0.85, src=llm)

**Answer (first 400 chars):**

> Basandomi sulle fonti fornite, posso rispondere riguardo alla cauzione (deposito cauzionale):
> 
> **Importo della cauzione:**
> Gli importi variano a seconda della proprietà:
> - **Residencia Chiado**: €815 (secondo la descrizione della camera in Chiado)
> - **Cosy Home Lisbon**: €315 (secondo la descrizione della Economy Room in Santos)
> - **Santos Student Flat**: €380 (secondo la descrizione della Economy...

**Judge reasoning (relevancy):** _The answer directly addresses both parts of the question: (1) how much the deposit costs - providing specific amounts for multiple properties, and (2) when it is returned - honestly stating that while deposits are refundable, the specific timing is not available in the sources and recommending contacting ELH directly. The answer is well-structured, on-topic, and transparent about information limitations. Minor deduction only because the second part of the question cannot be fully answered from available sources, but the AI handles this appropriately rather than hallucinating information._

**Unsupported claims (1):**

- *All deposits are refundable* — Sources 1, 2, and 3 explicitly state 'refundable', but Sources 4 and 5 only mention 'Deposit' without specifying if they are refundable. The claim overgeneralizes.

---

### multilingual_02 — multilingual

**Question (pt):** `Procuro quartos com varanda em Lisboa para setembro de 2026`

**faithfulness:** 1.000 · **context_recall:** 0.250 · **answer_relevancy:** 1.000 · **task_success:** 0.500

**Latency:** 17.013s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Com base nas informações fornecidas, **nenhum dos quartos disponíveis possui varanda**. Todas as descrições dos quartos mencionam apenas "janela com luz natural" mas não fazem referência a varandas.
> 
> Os quartos disponíveis em Lisboa são:
> 
> **Casa do Sol:**
> - **Master Suite no Chiado** (20m², €930/mês) - quarto com janela e luz natural
> - **Studio Loft no Chiado** (19m², €655/mês) - quarto com janela...

**Judge reasoning (relevancy):** _The answer directly addresses the user's question about rooms with balconies in Lisbon for September 2026. It clearly states upfront that none of the available rooms have balconies, then provides a comprehensive list of what IS available (rooms with windows and natural light). The answer is honest about the limitations of the available data and suggests the user would need to look elsewhere for rooms with balconies. This is the correct and helpful response when the specific criteria (balcony) cannot be met by the available inventory. The answer stays completely on-topic and provides useful alternative information._

---

### multilingual_03 — multilingual

**Question (es):** `¿Cuál es la habitación más barata en Porto para 6 meses desde septiembre 2026?`

**faithfulness:** 1.000 · **context_recall:** 0.500 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 15.413s · **Sources:** 5
**Routing:** descriptions (conf=0.95, src=llm)

**Answer (first 400 chars):**

> Basándome en las fuentes proporcionadas, la habitación más barata en Porto para 6 meses desde septiembre 2026 es la **Economy Room en Residencia Nevogilde** (ubicada en Massarelos).
> 
> Según la descripción de esta habitación, tiene una **tarifa fija mensual de €500**, lo que la convierte en la opción más económica disponible. La habitación ofrece:
> - 13m² con cama doble
> - 2 baños compartidos
> - Escrit...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about the cheapest room in Porto for 6 months starting September 2026. It identifies the specific room (Economy Room at Residencia Nevogilde in Massarelos) with its monthly rate (€500), provides relevant details about the room's features, and even includes helpful comparisons with other affordable options. The answer is well-structured, on-topic, and provides all the information needed to answer the user's query completely._

---

### multilingual_04 — multilingual

**Question (de):** `Wie funktioniert die Stornierung bei Erasmus Life Housing?`

**faithfulness:** 1.000 · **context_recall:** 0.333 · **answer_relevancy:** 1.000 · **task_success:** 0.000

**Latency:** 27.641s · **Sources:** 5
**Routing:** descriptions (conf=0.85, src=llm)

**Answer (first 400 chars):**

> Basierend auf den bereitgestellten Quellen kann ich Ihnen leider keine spezifischen Informationen zur Stornierungspolitik von Erasmus Life Housing geben.
> 
> Die verfügbaren Quellen enthalten ausschließlich Beschreibungen von Zimmern und Wohnungen in verschiedenen Immobilien (Alvalade Student Flat, Casa Azul, Cosy Home Porto und Cosy Home Lisbon) mit Details zu Ausstattung, Größe, Miete und Kautionen...

**Judge reasoning (relevancy):** _The question asks about cancellation procedures at Erasmus Life Housing. The answer correctly identifies that the provided sources do not contain information about cancellation policies, only property descriptions. Rather than hallucinating an answer, the system appropriately states it cannot provide specific information on this topic and directs the user to contact Erasmus Life Housing directly or consult their terms and conditions. This is the correct behavior for a RAG system when the requested information is not available in its knowledge base. The answer is honest, transparent about its limitations, and provides helpful guidance on how to obtain the needed information._

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

**task_success** — did the answer actually solve the user's task? 
3-point scale: 1.0 (fully solved with actionable specifics), 0.5 
(partially helpful), 0.0 (off-topic / evasive). A correct refusal of 
a genuinely unanswerable question scores 1.0. Unlike faithfulness and 
context_recall, this metric needs no retrieved contexts, so it crosses 
architectural paradigms (pipeline vs agentic) cleanly. Avg < 0.5 means 
the system frequently fails to deliver actionable content.

**Skipped queries (None scores)** are the metrics opting out cleanly. 
Queries q05 and q20 are unanswerable — `must_mention` is empty so 
`context_recall` correctly skips. If the LLM said 'I don't know', 
`faithfulness` skips too (no claims to verify). This is the SUCCESS 
path for those queries — not a failure.
