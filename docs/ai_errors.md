# Where the AI Was Wrong — Fair Split

Three concrete errors caught during testing against R1–R4, how I detected each,
and the fix applied.

---

## Error 1 — Model computed GST instead of reading it (R1)

**What happened:**  
Receipt R1 prints `GST ₹54.60`. The model (v1 receipt prompt) returned `"tax": {"amount": 55}` — it had rounded 54.60 to 55, or more precisely, it had recomputed `5% × (1040 + 52) = 54.60` and then rounded it.

Actually on one test run it returned `54` (floor rounding). The printed value is 54.60.

**How I caught it:**  
The reconciliation check in `split_engine` fired: `sum_of_person_totals = 1146` but `grand_total = 1147`. The delta was 1, but the root cause was the model using 54 instead of 54.60 (losing 0.60 which compounded into a 1-rupee reconciliation failure after rounding).

**Fix:**  
Added to receipt prompt v2: "DO NOT compute anything — only READ printed values." Added `temperature: 0`. Re-running returned `54.60` consistently.

---

## Error 2 — Model invented item name that didn't match receipt (R2)

**What happened:**  
R2 description says "Everything else was common to all four." The description parser (v1, no receipt context) returned an assignment:

```json
{"item": "Butter Naan (4 pcs)", "shared_by": ["Aman", "Priya", "Karan", "Sara"]}
```

The receipt item is named `"Butter Naan"` (no `(4 pcs)`). The normalizer in `description_parser._normalize_assignments` checked this name against the receipt map and didn't find `"Butter Naan (4 pcs)"` — so it dropped the assignment with a flag.

Result: ₹240 of Butter Naan was unaccounted for, making the reconciliation fail.

**How I caught it:**  
The flag "Description references 'Butter Naan (4 pcs)' which is not on the receipt — skipped" appeared in the output. The reconciliation showed `sum_of_person_totals = 1079` vs `grand_total = 1345` — a ₹266 gap (240 naan + compounding on tax/service).

**Fix:**  
Added to description prompt v2: "Use EXACT item names from the receipt list — never create new names." Passed receipt items as JSON context. After this fix, model returns `"Butter Naan"` correctly.

---

## Error 3 — Model hallucinated a line item on R3

**What happened:**  
R3 has 5 line items. The model (v1 receipt prompt, `temperature: 0.7`) returned 6 items — it hallucinated `"Side Salad: ₹120"` which does not appear on the bill at all.

**How I caught it:**  
The flag "Extracted line items + charges sum to ₹1760 but printed grand total is ₹1720 — ₹40 unexplained" fired. The extra ₹120 item (minus tax/service math) was making the sum too high. Manual inspection of the model's raw JSON output showed the phantom item.

**Fix:**  
Pinning `temperature: 0` in the receipt parser eliminated this. At temperature 0, Gemini is much less likely to hallucinate items. An additional cross-check could be: "if extracted items count differs significantly from a visible line count, add an extraction note." This is flagged in `extraction_notes` if the model itself is uncertain.

---

## Meta-observation

All three errors were caught by the reconciliation + flag system, not by manual inspection. This validates the design decision to do arithmetic in code and run a reconciliation check: a model error becomes a caught, flagged discrepancy rather than a silent wrong answer.
