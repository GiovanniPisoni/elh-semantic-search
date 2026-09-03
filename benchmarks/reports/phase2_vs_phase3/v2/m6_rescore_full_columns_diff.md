# M6 full-column re-scoring -- fabrication-claim diff

For each record re-scored in `m6_rescore_full_columns.xlsx`, this documents what the human previously called fabricated/invented and whether it is present in the complete truth-table JSON, checked directly against `m6_repair_truth_tables.json` before any re-scoring happened.

## constraint_satisfaction_01 / phase3
- **Human called fabricated:** Zone/neighborhood pairs "Alvalade/Intendente", "Mouraria/Santos", "Arroios/Campo de Ourique", "Alfama/Benfica" -- called "allucinazioni sulla gerarchia geografica" (score 0.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** Verbatim rows in the truth table: Alvalade|Intendente @ EUR815 & EUR820 (Alvalade Student Flat); Mouraria|Santos @ EUR820 (Casa da Paz); Arroios|Campo de Ourique @ EUR835 (Arroios Student Flat); Alfama|Benfica @ EUR870 (Casa Nova) -- all exact zone/neighborhood/price/flatname matches, all among the 10 cheapest rows the answer cites.

## constraint_satisfaction_02 / phase3
- **Human called fabricated:** Zone/neighborhood pairs incl. "Ramalde/Ribeira", "Foz do Douro/Miragaia" and "codici hash alfanumerici inventati (#HSE_0CC1B91F, #HSE_1549E93A, ...)" (score 0.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** All 7 disputed zone/neighborhood pairs and all cited #HSE_... house_ids match real rows exactly (e.g. HSE_0CC1B91F -> Cosy Home Porto, Ramalde/Ribeira, EUR550 fixed).

## constraint_satisfaction_03 / phase3
- **Human called fabricated:** "Allucinazione su ID fittizi: ... sostituendoli con codici identificativi inventati (#HSE_...)" for Casa Azul / Casa da Saudade / Bright Apartment Chiado / Residencia Graca (score 0.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** HSE_195B4BC5, HSE_1D470764, HSE_696556D0, HSE_2B801A43, HSE_09FD1D8B are all real house_id values in the truth table, verbatim -- not invented. (Separately, the human's OTHER complaint -- that the model presents two distinct real rooms at HSE_1D470764, EUR1060 and EUR1090, as 'older'/'newer version' of one room -- is a genuine defect, not touched by this fix.)

## constraint_satisfaction_04 / phase3
- **Human called fabricated:** "Allucinazione sui nomi delle strutture e ID: ... sostituendoli con identificativi alfanumerici fittizi (es. #HSE_4190B25E) e inventando ID di sistema con timestamp completi (es. [Room ID: HSE_4190B25E|RM_HSE_4190B25E_1|2021-07-15T00:00:00]) non presenti nei dati" (score 0.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** The bracketed room_id, including the timestamp suffix, is the real, verbatim primary key in the truth table for that row.

## constraint_satisfaction_05 / phase3
- **Human called fabricated:** Systematic zone nesting ("annida ... Bonfim dentro Campanha, Campanha dentro Boavista, Foz dentro Bonfim, ...") and "codici identificativi fittizi" (score 0.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** All disputed zone/neighborhood pairs (7+ prices checked in Step 3) are exact DB matches; the zones the human read as nested sub-neighbourhoods are each room's real, independent `neighborhood` column value.

## constraint_satisfaction_07 / phase3
- **Human called fabricated:** Zone/neighborhood re-assignment: "attribuisce le stanze ... della zona Campanha ... al quartiere Cedofeita" etc. (score 0.0, judge scored 1.0).
- **Status:** PRESENT (not fabricated)
- **Evidence:** All disputed zone/neighborhood pairs are exact DB matches.

## factual_lookup_07 / phase3
- **Human called fabricated:** "tutte le 10 stanze ... ad Anjos (Campo de Ourique neighborhood). Questo e geograficamente e logicamente errato" (score 0.5).
- **Status:** PRESENT (not fabricated)
- **Evidence:** Anjos Student Flat's real `neighborhood` field is literally "Campo de Ourique" -- the answer's zone/neighborhood pairing is correct, not a hallucination.
