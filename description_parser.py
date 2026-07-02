"""
description_parser.py - Gemini text description parser (google-genai SDK).
"""
from __future__ import annotations
import json
import os
import re

from google import genai
from google.genai import types
from prompts import DESCRIPTION_PARSER_PROMPT_TEMPLATE


def _client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON found: {text[:200]}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])
    raise ValueError("Unbalanced JSON")


def _normalize(raw: dict, receipt_items: list) -> tuple:
    receipt_map = {item["name"]: item for item in receipt_items}
    receipt_names = set(receipt_map.keys())
    raw_assignments = raw.get("assignments", [])
    assigned_names = {a["item"] for a in raw_assignments}
    flags = list(raw.get("flags", []))
    assumptions = list(raw.get("assumptions", []))

    for name in receipt_names:
        if name not in assigned_names:
            flags.append(f"Receipt item '{name}' not covered by description -- no one assigned")

    normalized = []
    for asgn in raw_assignments:
        item_name = asgn.get("item", "")
        sharers = asgn.get("shared_by", [])
        if item_name not in receipt_map:
            flags.append(f"Description references '{item_name}' not on receipt -- skipped")
            continue
        normalized.append({
            "item": item_name,
            "amount": receipt_map[item_name]["total"],
            "shared_by": [str(s) for s in sharers],
        })

    return {"people": [str(p) for p in raw.get("people", [])],
            "assignments": normalized,
            "paid_by": raw.get("paid_by")}, assumptions, flags


def parse_description(description: str, receipt_items: list,
                      model_name: str = "gemini-2.5-flash") -> tuple:
    items_json = json.dumps(
        [{"name": i["name"], "qty": i["qty"], "total": i["total"]} for i in receipt_items],
        indent=2
    )
    prompt = DESCRIPTION_PARSER_PROMPT_TEMPLATE.format(
        items_json=items_json, description=description
    )
    raw_text = None
    last_error = None
    for _ in range(2):
        try:
            client = _client()
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=2048,
                )
            )
            raw_text = resp.text
            raw_json = _extract_json(raw_text)
            data, assumptions, flags = _normalize(raw_json, receipt_items)
            return data, assumptions, flags
        except Exception as e:
            last_error = e
    return ({"people": [], "assignments": [], "paid_by": None}, [],
            [f"Description parse failed: {last_error}", f"Raw: {(raw_text or '')[:300]}"])
