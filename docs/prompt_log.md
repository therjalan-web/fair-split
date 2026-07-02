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

The model's job is purely extraction: read numbers off an image (receipt parser)
and map plain-English sentences to structured item→people assignments
(description parser). Everything numeric — per-person subtotals, equal splits of
shared items, proportional tax/service/discount allocation, rupee rounding with
paise absorption, settle-up amounts, and the reconciliation check — happens in
`split_engine.py`, which is pure Python with no model call.

**Why:**

1. **LLMs are unreliable at arithmetic.** During testing the model recomputed
   GST instead of reading it (see `ai_errors.md`, Error 1) and produced values
   that were off by paise — which compound into rupee-level reconciliation
   failures after rounding. Extraction errors are detectable; silent arithmetic
   errors are not.
2. **Code is deterministic and testable.** The split engine has 19 unit +
   integration tests that pin down every fairness rule, including the exact
   grand totals of all four sample receipts. A prompt can't be unit-tested
   this way.
3. **The reconciliation requirement demands it.** The spec mandates a
   `reconciliation` field that checks the system's own arithmetic. That check is
   only meaningful if the arithmetic is independent of the extraction — code
   verifying code-computed totals against the model-extracted printed total is a
   real cross-check; a model verifying its own math is not.
4. **Rounding rules need exactness.** "Round to the rupee; state who absorbs the
   leftover paise" requires a deterministic largest-remainder algorithm. A model
   cannot reliably guarantee that per-person totals sum exactly to the printed
   grand total.

---

## Provider iterations (not prompts, but part of the model-usage story)

| Ver | What changed | Why |
|-----|-------------|-----|
| p1 | Gemini via google-genai SDK, `gemini-2.0-flash` | Best free vision quality |
| p2 | Attempted Groq `llama-3.2-11b-vision-preview` fallback | Gemini key trouble on edu account — but Groq's free vision models were deprecated in 2026 |
| p3 | Unified `llm_client.py`: Gemini `gemini-2.5-flash` primary (2.0-flash deprecated Jun 2026) → OpenRouter `:free` vision models fallback → Groq text-only fallback | One persistent free key (AI Studio), automatic failover so a rate-limited provider never takes the demo down, keys read fresh from env each call |
