# Edge Cases — Fair Split

Each case: input shape · how the tool handles it · verified (✓/✗/partial).

---

## 1. No service charge on bill

**Input:** Receipt with `service_charge_amount = 0`.  
**Handling:** `service_charge_amount` defaults to 0; every person gets `service_share = 0`. No flag raised (this is valid).  
**Verified:** ✓ — `test_no_service_charge` in `tests/test_split_engine.py` passes.

---

## 2. Printed total doesn't match extracted line items

**Input:** Line items sum to ₹980 but printed grand total is ₹1000.  
**Handling:** Two separate checks:
- `reconciliation` reports `sum_of_person_totals` vs `grand_total` (always shown).
- A second flag fires: "Extracted line items + charges sum to ₹980.00 but printed grand total is ₹1000 — ₹20.00 unexplained."  
**Handling choice:** The split is still computed using the printed grand total as the target. The unexplained gap is flagged, not silently absorbed.  
**Verified:** ✓ — `test_bill_total_mismatch_flagged` passes.

---

## 3. Item in description not on receipt

**Input:** Description says "we also had gulab jamun" but receipt has no such item.  
**Handling:** Description parser is instructed: "If description mentions an item not on the receipt → add to flags, do NOT add to assignments." The flag reads: "Description references 'gulab jamun' which is not on the receipt — skipped."  
**Verified:** Partial — prompt engineering confirmed; requires live Gemini test.

---

## 4. Receipt item not covered by description

**Input:** Receipt has "Masala Papad" but description never mentions it.  
**Handling:** `description_parser._normalize_assignments` checks every receipt item against the assignment list; unaccounted items are flagged: "Receipt item 'Masala Papad' not covered by description — no one assigned."  
The item amount is then excluded from splits (conservative: don't silently distribute it).  
**Verified:** ✓ — `test_unassigned_item_flagged` covers the split-engine side; normalizer logic verified in code review.

---

## 5. Ambiguous "rest of us"

**Input:** "Priya and I had the pasta. The rest of us shared the naan." (first-person + implicit group)  
**Handling:** Description parser prompt v3 instructs: flag it AND make a best-guess based on context (all named people minus any already explicitly excluded), state the guess in `assumptions`. Example: "'rest of us' interpreted as [Aman, Karan, Sara] — Priya excluded as she was named separately."  
**Handling choice:** We don't refuse; we flag and state the assumption explicitly so the user can correct it.  
**Verified:** Partial — prompt designed for this; requires live test.

---

## 6. "I" / first-person in description

**Input:** "Priya and I shared the pasta."  
**Handling:** Prompt instructs model to flag `"I"` as ambiguous unless resolvable from context (e.g., if all other names are listed and only one unnamed person remains). Flag: "First-person 'I' in description is ambiguous."  
**Verified:** Partial — prompt-level only.

---

## 7. Quantities that don't divide evenly

**Input:** 3 people splitting a ₹100 item → ₹33.33 each.  
**Handling:** Split engine uses exact float division. The rounding step absorbs the paise: two people pay ₹33, one pays ₹34 (person with highest fractional remainder). This is stated in `assumptions`.  
**Verified:** ✓ — R3 (Margherita Pizza ₹380 ÷ 3) hits this case; test passes.

---

## 8. Tip not covered by fairness rules

**Input:** Receipt has a "Tip" or "Gratuity" line.  
**Handling:** Receipt parser extracts tip as a line item (NOT as service_charge). If the description doesn't assign it, `shared_by: []` and a flag fires: "'Tip' (₹N) is a tip/gratuity — outside the spec's fairness rules. Include explicitly in description to split it." The tip amount is excluded from the per-person split.  
**Handling choice:** We chose to flag rather than guess. The user's description can explicitly say "we split the tip" to include it.  
**Verified:** ✓ — `test_tip_flagged` passes.

---

## 9. Multiple people owing one payer

**Input:** Five people, one paid. Four others all owe the payer.  
**Handling:** Settle-up loop generates one `{"from": ..., "to": payer, "amount": ...}` entry per non-payer. Standard case; no simplification needed since there's one payer.  
**Verified:** ✓ — All R1–R4 tests cover this pattern.

---

## 10. No payer named in description

**Input:** "Aman had the sandwich. Priya had the pasta."  
**Handling:** `paid_by` is `null`, `settle_up` is `[]`, and a flag fires: "No payer identified in description — settle-up cannot be computed."  
**Verified:** ✓ — `test_no_payer_flagged` passes.

---

## 11. Discount present with proportional allocation

**Input:** R4 — 15% WELCOME15 coupon.  
**Handling:** `discount_share` for each person = `-(discount_amount × person_subtotal / total_subtotal)`. Proportional, so higher spenders benefit more from the discount.  
**Verified:** ✓ — `test_r4_with_discount` passes; `discount_share` values are all ≤ 0.

---

## 12. Discount present but model reads it as positive on bill (minus sign)

**Input:** Bill shows "Discount −₹228". Model might return `-228`.  
**Handling:** Receipt parser prompt explicitly states: "discount.amount is ALWAYS a positive number even if printed with a minus sign." `_normalize_receipt` calls `safe_float` and takes the absolute value path. Split engine applies it as negative.  
**Verified:** Partial — prompt instruction in place; requires live test.

---

## 13. Round-off on bill

**Input:** Bill shows "Round-off +₹0.40" (R1) or "Round-off −₹0.05" (R2).  
**Handling:** `round_off` is extracted as a float (can be positive or negative). The grand total already includes it. Our split targets `round(grand_total)` which is the printed total — so round-off is automatically absorbed into the paise distribution step.  
**Verified:** ✓ — R1 (+0.40) and R2 (−0.05) both pass.

---

## 14. Item split across only a subset of people (partial sharing)

**Input:** R2 — Gulab Jamun shared by Priya and Karan only (not all four).  
**Handling:** Assignment `shared_by: ["Priya", "Karan"]` → each gets ₹60. Aman and Sara get ₹0 from that item. Standard equal-split among named sharers.  
**Verified:** ✓ — `test_r2_partial_share` passes with correct subtotals.

---

## 15. Image completely unreadable (blurry / dark / wrong file)

**Input:** A non-receipt image or very low-quality photo.  
**Handling:** Gemini may return a response with `grand_total: 0` or fail to extract fields. `parse_receipt` catches this: if `grand_total == 0` a flag fires; if JSON extraction fails entirely, HTTP 422 is returned with the error and any partial flags.  
**Handling choice:** Fail loudly rather than return zeros. The user will see: "Could not extract grand total from receipt — check image quality."  
**Verified:** Partial — error path tested in code review; requires a bad-image test.

---

## 16. Same item ordered multiple times as separate lines

**Input:** Two "Butter Naan" lines on the same bill.  
**Handling:** Each line gets its own assignment entry. The description parser should assign each line independently; if description says "we all shared the naan" it maps to whichever naan lines exist. If receipt has two naan lines and description only mentions one, edge case #4 fires.  
**Verified:** Partial — not covered by R1–R4.

---

## 17. Person named in description not seen in people list

**Input:** Assignments reference "Rahul" but he wasn't in `all_people`.  
**Handling:** Split engine detects new name, adds to `all_people`, and flags: "Person 'Rahul' from description not in initial people list — added."  
**Verified:** ✓ — `test_new_person_from_description` passes.

---

## 18. Settle-up when payer owes others (negative net)

**Input:** Heavily discounted bill where payer's own share is less than zero (theoretical).  
**Handling:** If `floored[payer] < 0`, split engine creates a reverse settle-up entry (`from: payer, to: person`). Practically won't happen on real bills.  
**Verified:** Not verified — theoretical edge case.

---

## 19. Tip / Gratuity line on bill

**Input:** Receipt has a "Tip" or "Staff Tip" line item.  
**Handling:** The spec's fairness rules don't define how to allocate a tip. The receipt parser is instructed to include tips as line items (not as service_charge). In split_engine, if a tip item has no one assigned (`shared_by: []`), it fires a specific flag: *"'Tip' (₹N) is a tip/gratuity — outside the spec's fairness rules. Include explicitly in description to split it."* The tip is excluded from the per-person split; grand_total is still the authoritative target.  
**Handling choice:** Fail loudly, don't silently add tip to everyone's share. The user's description can explicitly say "we split the tip" to include it.  
**Verified:** ✓ — `test_tip_flagged` passes.

---

## 20. Delivery / Packing charge on bill

**Input:** Swiggy/Zomato-style bill with a "Delivery Fee ₹50" or "Packing Charge ₹30".  
**Handling:** The receipt parser extracts it into a `delivery_charge.amount` field (not service_charge). Split engine allocates it proportionally to each person's subtotal, the same as service charge. An assumption is recorded: *"Delivery/packing charge ₹50 allocated proportionally (outside spec fairness rules — reasonable default)."*  
**Handling choice:** Proportional allocation is the fairest default — those who ordered more pay more of the delivery fee.  
**Verified:** ✓ — `test_delivery_charge` passes.

---

## 21. CGST + SGST shown as two separate lines

**Input:** Indian restaurant bill shows "CGST 2.5% ₹27.30" and "SGST 2.5% ₹27.30" on separate lines.  
**Handling:** Receipt parser prompt v4 explicitly instructs: sum CGST + SGST into `tax.amount` (27.30 + 27.30 = 54.60), set `tax.label` to "CGST+SGST". Split engine receives a single combined `tax_amount` — no change needed there.  
**Verified:** ✓ — `test_cgst_sgst_combined` passes (arithmetic is identical to single-GST bills).

---

## 22. Complimentary / free item on bill

**Input:** Bill includes "Complimentary Dessert" at ₹0 (e.g., loyalty reward or house gift).  
**Handling:** Receipt parser includes it in `items[]` with `total: 0`. Split engine detects `amount == 0`, records *"'Complimentary Dessert' is complimentary (₹0) — included in split with no cost"* in assumptions, and skips the cost allocation. The item name still appears in each person's `items` list so they can see they received it.  
**Verified:** ✓ — `test_complimentary_item` passes.

---

## 23. Loyalty points / wallet balance deducted

**Input:** Bill shows "Zomato Credits −₹80" as a deduction.  
**Handling:** Receipt parser prompt v4 instructs: treat loyalty/points deductions as a `discount.amount` (positive number), note the type in `discount.code`. Split engine then allocates proportionally just like any other discount.  
**Verified:** Partial — prompt instruction in place; requires live test.

---

## 24. Large group (6+ people) rounding

**Input:** ₹1000 among 6 people → ₹166.67 each exactly.  
**Handling:** Floor each person to ₹166, leaving residual of ₹4. Assign +₹1 to the 4 people with the largest fractional remainders (all equal at 0.6667, so the first 4 in sorted order). Result: 4 people pay ₹167, 2 pay ₹166. Stated in assumptions.  
**Verified:** ✓ — `test_large_group_6_people` passes; totals.count(167) == 4.

---

## 25. One person ordered everything (solo within a group)

**Input:** Alice ate all items; Bob was present but had nothing. Bob paid.  
**Handling:** Bob gets subtotal=0, total=0. Alice's total = grand_total. Settle-up: Alice owes Bob the full amount.  
**Verified:** ✓ — `test_one_person_all_items` passes.
