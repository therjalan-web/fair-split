"""
receipt_parser.py
Calls a vision model to OCR the receipt image → structured dict.
ALL arithmetic is done by split_engine.py, NOT here.

Model calls go through llm_client (Gemini primary, OpenRouter fallback).
"""

from __future__ import annotations
import base64
import json
import re

from llm_client import call_vision, AllProvidersFailed
from prompts import RECEIPT_PARSER_PROMPT


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a model response."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in response: {text[:200]}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError(f"Unbalanced JSON in response: {text[:200]}")


# ── Normalization ─────────────────────────────────────────────────────────────

def _normalize_receipt(raw: dict) -> dict:
    def safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    items = []
    for item in raw.get("items", []):
        items.append({
            "name": str(item.get("name", "Unknown item")),
            "qty": int(item.get("qty") or 1),
            "total": safe_float(item.get("total")),
        })

    sc = raw.get("service_charge") or {}
    tax = raw.get("tax") or {}
    disc = raw.get("discount") or {}
    delivery = raw.get("delivery_charge") or {}

    return {
        "items": items,
        "subtotal": safe_float(raw.get("subtotal")),
        "service_charge_amount": safe_float(sc.get("amount")),
        "service_charge_pct": safe_float(sc.get("pct")),
        "tax_amount": safe_float(tax.get("amount")),
        "tax_pct": safe_float(tax.get("pct")),
        "tax_label": str(tax.get("label") or "GST"),
        "discount_amount": abs(safe_float(disc.get("amount"))),  # always positive
        "discount_pct": safe_float(disc.get("pct")),
        "discount_code": disc.get("code"),
        "delivery_charge_amount": safe_float(delivery.get("amount")),
        "round_off": safe_float(raw.get("round_off")),
        "grand_total": safe_float(raw.get("grand_total")),
        "extraction_notes": raw.get("extraction_notes") or [],
    }


# ── Public API ────────────────────────────────────────────────────────────────

def parse_receipt(receipt_base64: str) -> tuple[dict, list[str]]:
    """
    Parse a base64-encoded receipt image.

    Returns
    -------
    receipt_data : dict  — normalized receipt fields
    flags        : list  — extraction warnings
    """
    if "," in receipt_base64:
        receipt_base64 = receipt_base64.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(receipt_base64)
    except Exception as e:
        return {}, [f"Could not decode base64 image: {e}"]

    raw_text = None
    last_error = None
    for attempt in range(2):
        try:
            raw_text = call_vision(image_bytes, RECEIPT_PARSER_PROMPT)
            raw_json = _extract_json(raw_text)
            receipt_data = _normalize_receipt(raw_json)
            flags = []

            for note in receipt_data.pop("extraction_notes", []):
                flags.append(f"OCR note: {note}")

            if receipt_data["grand_total"] == 0:
                flags.append("Could not extract grand total from receipt — check image quality")

            return receipt_data, flags

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            continue

    return {}, [
        f"Could not parse receipt response as JSON: {last_error}",
        f"Raw model output: {(raw_text or '')[:300]}",
    ]
