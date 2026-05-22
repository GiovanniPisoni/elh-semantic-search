# ELH RAG — Custom evaluation report — Phase 3 — Agentic RAG

**Generated:** 2026-05-22 20:06
**System under test:** `agentic-RAG`
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
| faithfulness | 0.879 | 1.0 | 0.375 | 1.0 | 8 | 12 |
| context_recall | 0.293 | 0.0 | 0.0 | 1.0 | 20 | 0 |
| answer_relevancy | 0.935 | 1.0 | 0.3 | 1.0 | 20 | 0 |
| task_success | 0.9 | 1.0 | 0.0 | 1.0 | 20 | 0 |

'Skipped' counts queries where the metric was not applicable, e.g. 
`context_recall` on queries with empty `must_mention`, or 
`faithfulness` when the answer correctly said 'I don't know'. 
These are NOT failures — they are the metrics opting out cleanly.

## Problems detected (prioritised)

Found **16 sub-threshold case(s)** out of 20 queries.

Thresholds:
- faithfulness < 0.7
- context_recall < 0.6
- answer_relevancy < 0.7
- task_success < 0.5

| # | Query ID | Metric | Score | Severity (gap) | Question |
|---|---|---|---:|---:|---|
| 1 | structural_01 | context_recall | 0.0 | 0.6 | Find the cheapest single rooms in Lisbon |
| 2 | structural_02 | context_recall | 0.0 | 0.6 | Show me rooms with a private bathroom under 600 EUR in Porto |
| 3 | structural_03 | context_recall | 0.0 | 0.6 | What rooms are available within 500 meters of a metro statio... |
| 4 | structural_04 | context_recall | 0.0 | 0.6 | Find rooms larger than 20 square meters in Lisbon under 700 ... |
| 5 | policy_03 | context_recall | 0.0 | 0.6 | What is included in the monthly rent? |
| 6 | cost_01 | context_recall | 0.0 | 0.6 | Find the cheapest room in Lisbon and tell me the total cost ... |
| 7 | cost_02 | context_recall | 0.0 | 0.6 | Find the cheapest room in Porto available for the full acade... |
| 8 | cost_03 | context_recall | 0.0 | 0.6 | Compare the total cost of the cheapest room in Lisbon vs the... |
| 9 | cost_04 | context_recall | 0.0 | 0.6 | What is the total cost for a 12-month stay in Lisbon startin... |
| 10 | semantic_04 | context_recall | 0.0 | 0.6 | What do students say about how responsive the hosts are at E... |
| 11 | multilingual_02 | context_recall | 0.0 | 0.6 | Procuro quartos com varanda em Lisboa para setembro de 2026 |
| 12 | multilingual_03 | context_recall | 0.0 | 0.6 | ¿Cuál es la habitación más barata en Porto para 6 meses desd... |
| 13 | semantic_04 | task_success | 0.0 | 0.5 | What do students say about how responsive the hosts are at E... |
| 14 | semantic_04 | answer_relevancy | 0.3 | 0.4 | What do students say about how responsive the hosts are at E... |
| 15 | policy_03 | faithfulness | 0.375 | 0.325 | What is included in the monthly rent? |
| 16 | policy_04 | context_recall | 0.333 | 0.267 | How does the check-in process work? |

## Per-query details

### structural_01 — structural

**Question (en):** `Find the cheapest single rooms in Lisbon`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 13.837s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **228 single rooms in Lisbon**. Here are the **10 cheapest options**:
> 
> | Rank | Room | Zone | Neighborhood | Price/Month | Bathroom | Distance to Transport | Min. Contract |
> |------|------|------|--------------|-------------|----------|----------------------|---------------|
> | 1 | Intendente #HSE_1886AA11 | Intendente | Intendente | **€370** | Shared | 605m (Green line) | 5 months |...

**Judge reasoning (relevancy):** _The answer directly and completely addresses the user's question. The user asked to 'find the cheapest single rooms in Lisbon' and the answer provides exactly that: a comprehensive list of the 10 cheapest single rooms in Lisbon, sorted by price from lowest to highest (€370-€420). The answer includes relevant details (price, location, bathroom type, distance to transport, minimum contract) that help the user make an informed decision. It also highlights the absolute cheapest option (€370/month in Intendente) and offers helpful follow-up options. The response is on-topic, complete, and directly fulfills the request without any digressions._

---

### structural_02 — structural

**Question (en):** `Show me rooms with a private bathroom under 600 EUR in Porto`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 9.192s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **5 rooms** in Porto with a private bathroom under €600/month. Here they are, sorted by price:
> 
> 1. **Campanha (Ribeira) – €560/month**
>    - Room ID: HSE_28A35B0A
>    - Size: 19 m² with double bed
>    - Features: Private en-suite bathroom, study desk, built-in wardrobe, window with natural light
>    - Distance to transport: 883 m (Blue metro line)
>    - Minimum contract: 7 months
> 
> 2. **R...

**Judge reasoning (relevancy):** _The answer directly and completely addresses the user's request. The user asked for rooms with a private bathroom under 600 EUR in Porto, and the answer provides exactly that: 5 specific rooms in Porto, all with private bathrooms, all priced under €600/month. The response includes relevant details (price, location, size, features, transport distance) that help the user make an informed decision. The additional offer to provide more information or refine the search is helpful without being off-topic. This is a direct, complete, and on-topic response._

---

### structural_03 — structural

**Question (en):** `What rooms are available within 500 meters of a metro station in Lisbon?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 9.408s · **Sources:** 0

**Answer (first 400 chars):**

> Great! I found **69 rooms** in Lisbon within 500 meters of a metro station. Here are the top 10 matches:
> 
> ## **Estrela (6 rooms)**
> All located 470 meters from transport in the Graça neighborhood:
> 
> 1. **28m² room with queen-size bed** – €690/month (autumn rate)
>    - Private bathroom, study desk, built-in wardrobe
>    - Minimum 5-month contract
> 
> 2. **28m² room with queen-size bed** – €665/month (autu...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. It provides exactly what was asked: rooms available within 500 meters of a metro station in Lisbon. The response includes the total count (69 rooms), displays the top 10 results with relevant details (size, price, amenities, distance from transport), and organizes them by property. It also proactively offers helpful follow-up options. The answer is on-topic, complete, and highly useful._

---

### structural_04 — structural

**Question (en):** `Find rooms larger than 20 square meters in Lisbon under 700 EUR`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 10.743s · **Sources:** 0

**Answer (first 400 chars):**

> I found **147 rooms** in Lisbon under €700/month. Here are the top 20 results, sorted by price. However, I notice that the search results don't include a specific "square meters" filter in the database, so I've reviewed the excerpts and identified rooms that are **explicitly larger than 20 m²**:
> 
> ### Rooms Larger Than 20 m² (Under €700/month)
> 
> 1. **Intendente #HSE_1886AA11** – €370/month
>    - 27 m...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. The user asked for rooms larger than 20 square meters in Lisbon under 700 EUR, and the answer: (1) confirms it found 147 rooms in Lisbon under €700/month, (2) explicitly acknowledges the square meter requirement and filters results accordingly, (3) provides a clear list of 7 rooms that meet BOTH criteria (>20 m² AND <€700), (4) includes relevant details like exact square meters, price, location, and amenities, and (5) offers helpful follow-up options. The answer is well-structured, transparent about data limitations (noting the lack of a direct square meter filter), and provides exactly what was requested without going off-topic._

---

### policy_01 — policy

**Question (en):** `What is the cancellation policy if I cancel 45 days before check-in?`

**faithfulness:** 1.000 · **context_recall:** 0.667 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 6.565s · **Sources:** 3

**Answer (first 400 chars):**

> Based on ELH's cancellation policy:
> 
> **If you cancel 45 days before check-in, you are eligible for a 50% refund.**
> 
> Here's how the policy breaks down:
> 
> - **60+ days before check-in** → Full refund (minus applicable fees)
> - **30–59 days before check-in** → 50% refund ← *Your situation*
> - **Less than 30 days before check-in** → No refund
> 
> **Important note:** The 9% reservation fee you paid at bookin...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about the cancellation policy for canceling 45 days before check-in. It clearly states that a 50% refund is eligible, provides context by showing the full policy breakdown (60+ days, 30-59 days, and less than 30 days), correctly identifies where the 45-day scenario falls, and adds relevant information about the non-refundable reservation fee. The answer is well-structured, on-topic, and provides exactly what was asked with helpful additional context that enhances understanding without digressing from the core question._

---

### policy_02 — policy

**Question (en):** `When is the security deposit refunded after I leave?`

**faithfulness:** 1.000 · **context_recall:** 0.667 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 7.002s · **Sources:** 3

**Answer (first 400 chars):**

> Based on ELH's policy:
> 
> **The security deposit is refunded at check-out.** Here's how it works:
> 
> - **Timing:** At the moment you leave (check-out), the landlord assesses the condition of the room and shared spaces.
> - **Refund amount:** If there is no damage, the full deposit is returned to you in full.
> - **Deductions:** If there is damage to the room or shared spaces, the landlord may deduct repai...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about when the security deposit is refunded. It clearly states the deposit is refunded at check-out, explains the assessment process, details conditions for full vs. partial refunds (damage deductions), and provides helpful context about deposit amounts and variations. The answer stays completely on-topic, provides actionable information, and even includes relevant caveats about checking specific listing terms. This is a direct, complete response to exactly what was asked._

---

### policy_03 — policy

**Question (en):** `What is included in the monthly rent?`

**faithfulness:** 0.375 · **context_recall:** 0.000 · **answer_relevancy:** 0.700 · **task_success:** 0.500

**Latency:** 10.129s · **Sources:** 5

**Answer (first 400 chars):**

> The knowledge base doesn't have a specific FAQ entry about what utilities and services are included in the monthly rent. However, I can tell you that **the specific inclusions vary by room and landlord**, and this information is detailed in:
> 
> 1. **The landlord's contract and house rules** – which you receive after booking
> 2. **The individual room listing** – each property description specifies whi...

**Judge reasoning (relevancy):** _The answer is on-topic and addresses the question about what's included in monthly rent, but it doesn't provide a direct answer. Instead, it explains that the information varies by property and directs the user to where they can find this information (room listings, contracts, house rules). While this is honest and useful guidance, it's somewhat indirect. The answer does acknowledge the knowledge base limitation upfront and offers helpful next steps (searching for specific rooms, asking about particular utilities). A more direct answer would have included common examples of what's typically included (if that information were available) before explaining the variability. The response is helpful and transparent but requires the user to take additional steps to get the specific information they're seeking._

**Unsupported claims (5):**

- *The specific inclusions vary by room and landlord.* — This claim is not stated in any of the sources. It is an inference not directly supported by the provided documents.
- *The individual room listing specifies which utilities are covered and whether there are monthly caps.* — None of the sources mention that room listings specify utilities coverage or monthly caps. This information is not present in the provided documents.
- *The listing will show which utilities are included in the monthly rent.* — The sources do not state that listings show which utilities are included. This claim is not supported by any provided source.

---

### policy_04 — policy

**Question (en):** `How does the check-in process work?`

**faithfulness:** 1.000 · **context_recall:** 0.333 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 9.225s · **Sources:** 3

**Answer (first 400 chars):**

> Based on ELH's policies, here's how the check-in process works:
> 
> ## Check-In Overview
> 
> **At check-in, you pay the landlord directly** for:
> - **Refundable security deposit** (equal to one month's rent)
> - **Last-month rent advance** (if applicable to your contract)
> - **Administrative tax** (if applicable)
> 
> This is separate from what you've already paid to ELH at the time of booking (first month's re...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about the check-in process. It provides specific, actionable information including: what payments are required at check-in, who receives those payments, the distinction between check-in payments and booking payments, and the critical 24-hour discrepancy reporting window with documentation requirements. The answer is well-structured, on-topic throughout, and includes helpful context without unnecessary digressions. It also appropriately offers further assistance at the end._

---

### cost_01 — cost

**Question (en):** `Find the cheapest room in Lisbon and tell me the total cost for 6 months from September 2026`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 10.956s · **Sources:** 0

**Answer (first 400 chars):**

> Perfect! Here's what I found:
> 
> ## Cheapest Room in Lisbon (September 2026 – February 2027)
> 
> **Property:** Intendente #HSE_1886AA11  
> **Room:** 27 m² with sofa bed  
> **Monthly rent:** €370.00 (fixed rate, no seasonal variation)  
> **Shared bathroom:** Yes  
> **Distance to metro:** 605 m (Green line)
> 
> ---
> 
> ## Total Cost Breakdown (6 months)
> 
> | Item | Amount |
> |------|--------|
> | **Total stay cost** | ...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. It identifies the cheapest room in Lisbon, provides the monthly rent (€370), and calculates the total cost for 6 months starting September 2026 (€3,074.80 total, with breakdown of refundable vs non-refundable amounts). The answer goes beyond the minimum requirement by providing a detailed payment schedule, property details, and utility information, all of which are relevant and helpful. The response is well-structured, on-topic, and provides exactly what was requested plus useful context._

---

### cost_02 — cost

**Question (en):** `Find the cheapest room in Porto available for the full academic year (September 2026 to June 2027) and compute the total cost`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 11.646s · **Sources:** 0

**Answer (first 400 chars):**

> Perfect! Here's what I found:
> 
> ## Cheapest Room in Porto (Academic Year 2026–2027)
> 
> **Property:** Paranhos #HSE_31AF803C  
> **Room:** 16 m² single bedroom  
> **Monthly rent:** €395.00 (fixed rate, no seasonal variation)  
> **Availability:** September 1, 2026 – June 30, 2027 (10 months)  
> **Bathroom:** Shared (2 shared bathrooms in the flat)  
> **Transport:** 475 m from the nearest metro (Violet line)
> ...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question. It identifies the cheapest room in Porto for the specified academic year period (September 2026 to June 2027), provides the total cost calculation (€4,780.50), and goes beyond by offering a detailed breakdown of all costs including booking fees, deposits, and monthly payments. The answer is well-structured, on-topic, and provides all the information requested plus helpful additional context about payment schedules and utilities. This is a complete and direct response to what was asked._

---

### cost_03 — cost

**Question (en):** `Compare the total cost of the cheapest room in Lisbon vs the cheapest in Porto for 6 months from September 2026`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 15.232s · **Sources:** 0

**Answer (first 400 chars):**

> ## Cost Comparison: Lisbon vs Porto (6 months, September 2026 – February 2027)
> 
> ### **Lisbon – Cheapest Room**
> **Intendente #HSE_1886AA11** – €370/month (fixed rate)
> - **Total stay cost:** €3,074.80
> - **Non-refundable:** €2,609.80
> - **Refundable at checkout:** €465.00 (security deposit)
> - **Payment schedule:**
>   - At booking: €569.80
>   - At check-in: €655.00
>   - Monthly rent (6 months): €370.00/mo...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question. It compares the total cost of the cheapest room in Lisbon versus Porto for a 6-month period starting September 2026, providing exact figures (€3,074.80 vs €3,058.30), breaking down payment schedules, and highlighting the €16.50 difference. The answer goes beyond the basic comparison by adding valuable context about utilities, upfront costs, and practical considerations that help the user make an informed decision. This additional detail enhances rather than detracts from the core answer. The response is well-structured, clear, and completely on-topic._

---

### cost_04 — cost

**Question (en):** `What is the total cost for a 12-month stay in Lisbon starting January 2027 in the cheapest single room?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 12.43s · **Sources:** 0

**Answer (first 400 chars):**

> Perfect! Here's the complete cost breakdown for the cheapest single room in Lisbon for a 12-month stay starting January 2027:
> 
> ## Room Details
> - **Property:** Intendente #HSE_1886AA11
> - **Room Size:** 27 m²
> - **Monthly Rent:** €370.00 (fixed rate, no seasonal variation)
> - **Bathroom:** Shared
> - **Distance to Transport:** 605 m (Green metro line)
> 
> ## Total Cost Summary
> - **Total Stay Cost:** €5,494...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about the total cost for a 12-month stay in Lisbon starting January 2027 in the cheapest single room. It provides: (1) the exact total cost of €5,494.60, (2) detailed breakdown of all payment components, (3) payment schedule showing when each amount is due, (4) property and room details, and (5) utility information. The answer is well-structured, complete, and goes beyond the minimum requirement by providing helpful context about refundable vs. non-refundable amounts. This is exactly what someone asking this question would need to know._

---

### semantic_01 — semantic

**Question (en):** `I am looking for a room with a balcony and a view of the Tagus river in Lisbon`

**faithfulness:** 0.958 · **context_recall:** 0.600 · **answer_relevancy:** 0.700 · **task_success:** 0.500

**Latency:** 14.687s · **Sources:** 5

**Answer (first 400 chars):**

> I found several rooms in Lisbon with balconies, but I need to be transparent: **the descriptions in our database do not explicitly confirm Tagus river views**. The top similarity score is 0.42, which indicates these are related but not a direct match for your specific request.
> 
> However, here are the rooms with **private balconies** that I found, which are located in neighborhoods that could potent...

**Judge reasoning (relevancy):** _The answer is on-topic and addresses the user's request for a room with a balcony in Lisbon. It provides three concrete options with balconies and relevant details (price, size, location). However, it explicitly fails to deliver on the 'Tagus river view' requirement, which was a key part of the question. The AI is transparent about this limitation (noting the low 0.42 similarity score and lack of explicit river view confirmation), and offers helpful next steps by suggesting neighborhoods known for river views. While the response is useful and honest, it only partially fulfills the original request - delivering on 'balcony' and 'Lisbon' but not on 'Tagus river view.' The proactive suggestions for refinement are valuable, but the core question about river views remains unaddressed in the actual listings provided._

**Unsupported claims (1):**

- *Neighborhoods like Alfama, Cais do Sodré, and Miradouro de São Jorge are traditionally known for Tagus river views in Lisbon* — This claim is not mentioned in any of the provided sources

---

### semantic_02 — semantic

**Question (en):** `Is the Alfama neighborhood quiet at night according to student reviews?`

**faithfulness:** 0.700 · **context_recall:** 0.600 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 11.526s · **Sources:** 5

**Answer (first 400 chars):**

> Based on the student reviews in our database, **I cannot find specific feedback about nighttime noise levels in Alfama**. The search returned reviews from properties in Alfama, but none of them directly address whether the neighborhood is quiet at night.
> 
> The closest relevant reviews I found are from two Alfama properties (both from Residencia Alvalade):
> 
> 1. **"Would recommend"** (Oct 2023) – A st...

**Judge reasoning (relevancy):** _The answer directly and completely addresses the question. The user asked whether Alfama is quiet at night according to student reviews. The AI correctly states it cannot find specific information about nighttime noise levels in the reviews, explains what information it did find (reviews that mention nighttime views but not noise), and provides helpful context about why it cannot answer definitively. This is the appropriate response when the source data doesn't contain the requested information. The AI does not hallucinate an answer or go off-topic; instead, it acknowledges the limitation and offers constructive alternatives. This is exactly the correct behavior for an unanswerable question due to lack of data in the RAG sources._

**Unsupported claims (3):**

- *A review titled 'Would recommend' is from October 2023* — Source 2 has the title 'Would recommend' but does not include a date of October 2023 or any date
- *A review titled 'Perfect stay!' is from September 2024* — Source 5 has the title 'Perfect stay!' but does not include a date of September 2024 or any date
- *The 'Perfect stay!' review gave a 5-star overall rating* — Source 5 does not mention a star rating or overall rating score

---

### semantic_03 — semantic

**Question (en):** `Find rooms in bright spaces with lots of natural light in Lisbon`

**faithfulness:** N/A · **context_recall:** 1.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 13.635s · **Sources:** 10

**Answer (first 400 chars):**

> Great! I found 10 bright rooms with lots of natural light in Lisbon. Here's what's available:
> 
> ## Bright Rooms in Lisbon
> 
> **1. Garden View Room in Bright Apartment Principe Real** (Mouraria)
> - 20m² with double bed
> - Private bathroom, desk, wardrobe
> - **Proper window with natural light** — highlighted as important for long study days
> - A/C and heating included
> - **€875/month** (fixed year-round)
> - ...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's request for bright rooms with natural light in Lisbon. It provides 10 specific options, each explicitly highlighting natural light features (e.g., 'plenty of natural light floods in through the window,' 'proper window with natural light'). The response includes relevant details like pricing, room size, location, and amenities. It also adds helpful context by identifying best value options and the largest space. The answer is well-organized, actionable, and stays completely on-topic throughout. This is an exemplary response to the query._

---

### semantic_04 — semantic

**Question (en):** `What do students say about how responsive the hosts are at ELH?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 0.300 · **task_success:** 0.000

**Latency:** 3.856s · **Sources:** 0

**Answer (first 400 chars):**

> To give you the most accurate answer, could you clarify whether you're asking about:
> 
> - **the ELH team** (the company staff who run the platform and provide support to students), or
> - **the individual landlords** (the people who own and manage each specific room/property)?
> 
> Once you let me know which you meant, I'll search the student reviews for feedback on their responsiveness.

**Judge reasoning (relevancy):** _The answer does not address the user's question. Instead of providing information about host responsiveness at ELH from student reviews, it asks for clarification between 'ELH team' and 'landlords.' While this distinction might be relevant in some contexts, the question clearly asks about 'hosts' at ELH, which in student housing contexts typically refers to landlords/property managers. The answer is evasive and delays providing any actual information. A better response would either: (1) provide information about host responsiveness based on available data, or (2) if truly ambiguous, provide information about both interpretations. The clarification request appears unnecessary and unhelpful, making this largely off-topic from what was asked._

---

### multilingual_01 — multilingual

**Question (it):** `Quanto costa la cauzione e quando viene restituita?`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 7.91s · **Sources:** 3

**Answer (first 400 chars):**

> Ecco le informazioni sulla cauzione:
> 
> **Importo della cauzione:**
> - La cauzione standard è pari a **un mese di affitto** e viene pagata al proprietario al momento del check-in.
> - Tuttavia, i termini esatti variano a seconda del proprietario: alcuni richiedono un importo fisso (ad esempio €250), altri potrebbero richiedere due mesi di affitto. **L'importo esatto applicabile alla tua camera è indica...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses both parts of the question: 'Quanto costa la cauzione' (How much is the deposit) and 'quando viene restituita' (when is it returned). It provides clear information that the standard deposit is one month's rent, explains variations, specifies it's returned at check-out minus any deductions for damages, and adds helpful context about checking the listing for exact amounts. The answer is well-structured, on-topic, and complete._

---

### multilingual_02 — multilingual

**Question (pt):** `Procuro quartos com varanda em Lisboa para setembro de 2026`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 12.122s · **Sources:** 0

**Answer (first 400 chars):**

> Ótimo! Encontrei **35 quartos com varanda em Lisboa disponíveis em setembro de 2026**. Aqui estão os 10 melhores resultados:
> 
> | Bairro | Quarto | Preço/mês | Tamanho | Wc Privado | Distância Transporte | Contrato Mín. |
> |--------|--------|-----------|---------|-----------|----------------------|----------------|
> | **Estrela** | 16m² cama solteira | €690 | 16m² | Não (3 partilhados) | 470m | 7 mese...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the user's question about rooms with balconies in Lisbon for September 2026. It provides: (1) the exact number of available rooms (35), (2) a detailed table with 10 best options showing all relevant information (neighborhood, price, size, private bathroom, transport distance, minimum contract), (3) highlights of best options by different criteria, (4) confirmation that all rooms include private balconies, and (5) helpful follow-up options. The answer is completely on-topic, well-structured, and provides actionable information in the user's language (Portuguese). It addresses exactly what was asked with no digressions._

---

### multilingual_03 — multilingual

**Question (es):** `¿Cuál es la habitación más barata en Porto para 6 meses desde septiembre 2026?`

**faithfulness:** N/A · **context_recall:** 0.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 13.2s · **Sources:** 0

**Answer (first 400 chars):**

> ## La habitación más barata en Porto para 6 meses desde septiembre 2026
> 
> **Casa Paranhos** (Zona: Paranhos, Barrio: Miragaia)
> - **Precio:** €395/mes (tarifa fija, sin variación estacional)
> - **Tipo de habitación:** Habitación individual de 16 m² con cama individual
> - **Baño:** Compartido (2 baños compartidos en el piso)
> - **Transporte:** A 475 metros de la estación de metro (línea violeta)
> 
> ### Re...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about the cheapest room in Porto for 6 months starting September 2026. It provides: (1) the specific property name and location, (2) the exact monthly price (€395/mes), (3) room specifications, (4) complete financial breakdown for the 6-month period, (5) detailed payment schedule. The answer is well-structured, on-topic, and provides more useful detail than minimally required without being digressive. This is an exemplary response to the user's query._

---

### multilingual_04 — multilingual

**Question (de):** `Wie funktioniert die Stornierung bei Erasmus Life Housing?`

**faithfulness:** 1.000 · **context_recall:** 1.000 · **answer_relevancy:** 1.000 · **task_success:** 1.000

**Latency:** 9.84s · **Sources:** 3

**Answer (first 400 chars):**

> Gerne! Hier ist, wie die Stornierung bei Erasmus Life Housing funktioniert:
> 
> ## Stornierungsrichtlinie
> 
> Die Rückerstattung hängt davon ab, wie lange vor dem Check-in Sie stornieren:
> 
> - **60 oder mehr Tage vor Check-in**: Vollständige Rückerstattung (abzüglich anwendbarer Gebühren)
> - **30–59 Tage vor Check-in**: 50% Rückerstattung
> - **Weniger als 30 Tage vor Check-in**: Keine Rückerstattung
> 
> Die Se...

**Judge reasoning (relevancy):** _The answer directly and comprehensively addresses the question about how cancellation works at Erasmus Life Housing. It provides a clear breakdown of the cancellation policy with specific timeframes (60+ days, 30-59 days, <30 days) and corresponding refund percentages, mentions non-refundable service fees, explains special cases (landlord cancellation, room not as described), and offers an alternative solution (finding a replacement tenant). The answer is well-structured, on-topic, and provides all relevant information a user would need to understand the cancellation process. It even appropriately suggests contacting ELH directly for special cases, which is helpful guidance._

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
