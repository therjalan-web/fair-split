"""
prompts.py - All Gemini prompt templates.
"""

RECEIPT_PARSER_PROMPT = """You are a receipt OCR extractor. READ values printed on the bill -- do NOT compute anything.

Return ONLY valid JSON, no markdown, no explanation.

{
  "items": [
    {"name": "<item name as printed>", "qty": <integer>, "total": <float>}
  ],
  "subtotal": <float>,
  "service_charge": {"amount": <float>, "pct": <float>},
  "tax": {"amount": <float>, "pct": <float>, "label": "<GST/VAT>"},
  "discount": {"amount": <float as positive number>, "pct": <float>, "code": "<code or null>"},
  "round_off": <float>,
  "grand_total": <float>,
  "extraction_notes": ["<any uncertainty>"]
}

Rules:
- Do NOT recompute GST or subtotal -- read what is printed
- discount.amount is always positive even if printed with minus sign
- If a field is absent, use 0
- temperature=0 deterministic read
"""

DESCRIPTION_PARSER_PROMPT_TEMPLATE = """You are a bill-splitting parser. Given receipt items and a plain-English description, produce a structured assignment map.

Receipt line items (use EXACT names in your output):
{items_json}

Description: "{description}"

Return ONLY valid JSON, no markdown.

{{
  "people": ["<all person names from description>"],
  "assignments": [
    {{"item": "<EXACT receipt item name>", "shared_by": ["name1", "name2"]}}
  ],
  "paid_by": "<person name or null>",
  "assumptions": ["<interpretive decisions made>"],
  "flags": ["<unresolvable ambiguities or items not on receipt>"]
}}

Rules:
1. Every receipt item must appear exactly once in assignments
2. Use EXACT item names from the receipt list above
3. "shared by all" / "common to all" / "we all" means all people in shared_by
4. "the rest of us" -- flag it and make best guess, state guess in assumptions
5. "I" or "me" -- flag as ambiguous unless clearly resolvable
6. If payer not stated -- paid_by: null
7. Items in description not on receipt -- add to flags, skip in assignments
8. Receipt items not mentioned in description -- flag as unaccounted
"""
