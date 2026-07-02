"""
description_parser.py
Calls a text model to parse the plain-English "who had what" description
into a structured assignment map that split_engine.compute_split can consume.

Model calls go through llm_client (Gemini primary, OpenRouter fallback).
"""

from __future__ import annotations
import json
import re

from llm_client import call_text, AllProvidersFailed
from prompts import DESCRIPTION_PARSER_PROMPT_TEMPLATE


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in model response: {text[:200]}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError(f"Unbalanced braces in model response: {text[:200]}")


# ── Normalization ─────────────────────────────────────────────────────────────

def _normalize_assignments(raw: dict, receipt_items: list[dict]) -> tuple[dict, list[str], list[str]]:
    receipt_item_map = {item["name"]: item for item in receipt_items}
    receipt_names = set(receipt_item_map.keys())

    raw_assignments = raw.get("assignments", [])
    assigned_names = {a["item"] for a in raw_assignments}

    flags: list[str] = list(raw.get("flags", []))
    assumptions: list[str] = list(raw.get("assumptions", []))

    for name in receipt_names:
        if name not in assigned_names:
            flags.append(f"Receipt item '{name}' not covered by description — no one assigned")

    normalized = []
    for asgn in raw_assignments:
        item_name = asgn.get("item", "")
        sharers = asgn.get("shared_by", [])

        if item_name not in receipt_item_map:
            flags.append(
                f"Description references '{item_name}' which is not on the receipt — skipped"
            )
            continue

        amount = receipt_item_map[item_name]["total"]
        normalized.append({
            "item": item_name,
            "amount": amount,
            "shared_by": [str(s) for s in sharers],
        })

    return {
        "people": [str(p) for p in raw.get("people", [])],
        "assignments": normalized,
        "paid_by": raw.get("paid_by"),
    }, assumptions, flags


# ── Public API ────────────────────────────────────────────────────────────────

def parse_description(
    description: str,
    receipt_items: list[dict],
) -> tuple[dict, list[str], list[str]]:
    """
    Parse a plain-English bill description into structured assignments.

    Returns
    -------
    desc_data   : {"people": [...], "assignments": [...], "paid_by": str|None}
    assumptions : list[str]
    flags       : list[str]
    """
    items_json = json.dumps(
        [{"name": item["name"], "qty": item["qty"], "total": item["total"]}
         for item in receipt_items],
        indent=2,
    )

    prompt = DESCRIPTION_PARSER_PROMPT_TEMPLATE.format(
        items_json=items_json,
        description=description,
    )

    raw_text = None
    last_error = None
    for attempt in range(2):
        try:
            raw_text = call_text(prompt)
            raw_json = _extract_json(raw_text)
            desc_data, assumptions, flags = _normalize_assignments(raw_json, receipt_items)
            return desc_data, assumptions, flags

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            continue

    return (
        {"people": [], "assignments": [], "paid_by": None},
        [],
        [
            f"Could not parse description response as JSON: {last_error}",
            f"Raw model output: {(raw_text or '')[:300]}",
        ],
    )
