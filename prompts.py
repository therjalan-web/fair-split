"""
prompts.py
All Gemini prompt templates as versioned constants.
Kept here so iterations are easy to track in the prompt log.
"""

# ── v4: Receipt OCR prompt ──────────────────────────────────────────────────
# v1: basic extraction — model computed GST instead of reading it (WRONG)
# v2: added "DO NOT compute" rule + extraction_notes field
# v3: explicit field-by-field schema + discount always positive + temperature 0
# v4: added CGST/SGST handling, tip as line item, complimentary items,
#     delivery/packing charge field, loyalty/points deduction as discount
RECEIPT_PARSER_PROMPT = """You are a receipt OCR extractor. Your ONLY job is to READ values that are
printed on the bill image — do NOT compute, infer, or recalculate anything.

Return ONLY a valid JSON object. No markdown fences, no explanation, no preamble.

Required JSON schema:
{
  "items": [
    {
      "name": "<item name exactly as printed>",
      "qty": <integer, default 1 if not shown>,
      "total": <float — the line total as printed, 0 for complimentary/free items>
    }
  ],
  "subtotal": <float — the subtotal line as printed, 0 if not shown>,
  "service_charge": {
    "amount": <float — service charge amount as printed, 0 if absent>,
    "pct":    <float — service charge percentage as printed, 0 if absent>
  },
  "tax": {
    "amount": <float — TOTAL tax amount (see CGST/SGST rule below), 0 if absent>,
    "pct":    <float — total tax percentage as printed, 0 if absent>,
    "label":  "<e.g. GST, CGST+SGST, VAT, Service Tax>"
  },
  "discount": {
    "amount": <float — discount amount as a POSITIVE number, 0 if absent>,
    "pct":    <float — discount percentage as printed, 0 if absent>,
    "code":   "<coupon/promo code if shown, else null>"
  },
  "delivery_charge": {
    "amount": <float — delivery/packing/platform fee as printed, 0 if absent>,
    "label":  "<e.g. Delivery Fee, Packing Charge, Platform Fee, null if absent>"
  },
  "round_off": <float — round-off amount (can be negative), 0 if absent>,
  "grand_total": <float — final total as printed>,
  "extraction_notes": ["<list any values you were uncertain about or could not read clearly>"]
}

Critical rules:
1. discount.amount is ALWAYS a positive number even if printed with a minus sign
2. If a field is not present on the bill, use 0 (or null for string fields)
3. Do NOT add up line items to compute subtotal — read the printed subtotal line
4. Do NOT calculate any tax — read the printed tax line(s)
5. If you cannot read a number clearly, set it to null and add a note to extraction_notes
6. qty must be an integer; if fractional quantity like "2 pc", use 2

CGST / SGST rule: Indian bills often show CGST and SGST as two separate lines (e.g.,
"CGST 2.5% ₹27.30" and "SGST 2.5% ₹27.30"). ADD them together into tax.amount
(e.g., 27.30 + 27.30 = 54.60) and set tax.label to "CGST+SGST".

Tip / Gratuity rule: A "Tip", "Staff Tip", or "Gratuity" line is a LINE ITEM, not a
service_charge. Include it in items[] with the printed amount. Example:
{"name": "Tip", "qty": 1, "total": 100}.

Complimentary / Free items rule: If an item is marked "Complimentary", "FOC" (Free of
Charge), "On the house", or has a printed price of ₹0, include it in items[] with
total: 0. Do NOT skip it.

Delivery / Packing charge rule: Any "Delivery Fee", "Packing Charge", "Platform Fee",
or "Convenience Fee" is NOT a service_charge — put it in delivery_charge.amount.

Loyalty / Points deductions rule: If a bill shows "Points Redeemed", "Loyalty Discount",
or "Wallet Balance" as a deduction, treat it as a discount (add to discount.amount as a
POSITIVE number) and note the type in discount.code.
"""


# ── v4: Description parser prompt ──────────────────────────────────────────
# v1: returned new item names, didn't match receipt items (WRONG)
# v2: added receipt items context; model still used fuzzy names sometimes
# v3: explicit instruction to use EXACT receipt names + stronger handling of
#     ambiguous phrases + separate assumptions vs flags
# v4: added delivery/packing charge rule, tip assignment rule, "between the
#     two of us" ambiguity, "we split X" rule
DESCRIPTION_PARSER_PROMPT_TEMPLATE = """You are a bill-splitting parser. Given the receipt's line items and a plain-English
description of who ate what, produce a structured assignment map.

Receipt line items (use these EXACT names in your output):
{items_json}

Description: "{description}"

Return ONLY a valid JSON object. No markdown, no explanation.

Required JSON schema:
{{
  "people": ["<all person names you can identify from the description>"],
  "assignments": [
    {{
      "item": "<EXACT item name from the receipt list above>",
      "shared_by": ["<name1>", "<name2>", ...]
    }}
  ],
  "paid_by": "<person name, or null if not stated>",
  "assumptions": ["<one entry per interpretive decision you made>"],
  "flags": ["<one entry per ambiguity you could NOT resolve, or item in description not on receipt>"]
}}

Critical rules:
1. EVERY receipt item must appear exactly once in assignments
2. Use EXACT item names from the receipt list — never create new names
3. "shared by all" / "common to all" / "we all" / "all of us" → all people in shared_by
4. "the rest of us" → flag it AND make your best guess based on context; state the guess in assumptions
5. "I" / "me" → flag as ambiguous unless clearly resolvable from context
6. If payer not explicitly stated → paid_by: null
7. If description mentions an item not on the receipt → add to flags, do NOT add to assignments
8. Items not mentioned in description but present on receipt → flag them as unaccounted-for
9. Quantities like "each had one" on a multi-quantity line → still one assignment entry, shared_by lists those people
10. Never invent people not mentioned in the description
11. Delivery / Packing / Platform fee items on the receipt → if description does not assign them,
    default shared_by to ALL identified people; note "delivery charge assigned to all" in assumptions
12. Tip / Gratuity items → if description does not explicitly assign the tip, set shared_by: []
    (it will be flagged as unassigned); if description says "we left a tip" without naming who, assign to all
13. "between the two of us" / "just us two" → flag which two people you identified; state in assumptions
14. "we split X" / "we shared X" without naming who → use all identified people; note in assumptions
"""
