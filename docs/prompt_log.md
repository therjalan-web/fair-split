# Prompt Log — Fair Split

Each line is one iteration: version · component · what changed · why.

---

## Receipt Parser Prompt

| Ver | What changed | Why |
|-----|-------------|-----|
| v1 | Initial prompt: "Extract all line items, subtotal, taxes, grand total from this receipt image. Return JSON." | Baseline attempt |
| v2 | Added explicit "DO NOT compute anything — only READ printed values." Introduced `extraction_notes` field. | **Model was computing GST** (e.g., recalculating 5% of subtotal) instead of reading the printed GST figure. When the printed total had a round-off, model's computed value diverged. |
| v3 | Added full field-by-field schema with comments; explicit rule `discount.amount is ALWAYS a positive number`; added `temperature: 0` for determinism. | v2 still returned discount as negative (e.g., "-228") inconsistently. Pinning temperature to 0 eliminated hallucinated line items that appeared in ~10% of free-form responses. |
| v4 | Added: CGST/SGST sum rule; tip/gratuity as line item (not service_charge); complimentary/FOC items with total=0; `delivery_charge` field; loyalty/points deduction as discount. | Extended to cover real-world Indian bill variants: Swiggy/Zomato delivery bills, restaurant CGST+SGST breakdown, on-the-house items, optional tip lines. |

---

## Description Parser Prompt

| Ver | What changed | Why |
|-----|-------------|-----|
| v1 | "Parse this description: who ate what, who paid. Return JSON." No receipt context. | Baseline. |
| v2 | Injected receipt item list into the prompt as JSON context. Added instruction: "Use EXACT item names from the receipt list." | **Model was inventing new item names** — e.g., description said "pasta" and model returned `"item": "Pasta"` instead of `"item": "Penne Arrabiata"`. This caused the normalizer to drop the assignment. |
| v3 | Added explicit rules for: `"rest of us"` (flag + best guess in assumptions), `"I"/"me"` (flag as ambiguous), unaccounted receipt items (flag), items in description not on receipt (flag). Split output into `assumptions` vs `flags`. | v2 silently dropped ambiguous phrases. Evaluator specifically tests for surfacing ambiguity rather than guessing silently. Separating assumptions (interpretive decisions) from flags (unresolvable issues) makes review clearer. |
| v4 | Added: delivery/packing charge defaults to shared by all; tip defaults to unassigned (shared_by: []); "between the two of us" ambiguity rule; "we split X" without names → all people. | Extended to match new receipt types added in receipt parser v4. Prevents tip from being silently split when user didn't intend it. |

---

## Arithmetic: Model vs Code

**Answer: The model does zero arithmetic. All arithmetic is in Python.**

The model's job is purely extraction: read numbers off an ima