"""
receipt_parser.py - Gemini vision receipt OCR (google-genai SDK).
"""
from __future__ import annotations
import base64
import json
import os
import re

from google import genai
from google.genai import types
from prompts import RECEIPT_PARSER_PROMPT


def _client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _detect_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


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


def _normalize(raw: dict) -> dict:
    def sf(v, d=0.0):
        try:
            return float(v) if v is not None else d
        except (TypeError, ValueError):
            return d

    items = [{"name": str(x.get("name", "")), "qty": int(x.get("qty") or 1),
               "total": sf(x.get("total"))} for x in raw.get("items", [])]
    sc = raw.get("service_charge") or {}
    tax = raw.get("tax") or {}
    disc = raw.get("discount") or {}
    return {
        "items": items,
        "subtotal": sf(raw.get("subtotal")),
        "service_charge_amount": sf(sc.get("amount")),
        "service_charge_pct": sf(sc.get("pct")),
        "tax_amount": sf(tax.get("amount")),
        "tax_pct": sf(tax.get("pct")),
        "tax_label": str(tax.get("label") or "GST"),
        "discount_amount": sf(disc.get("amount")),
        "discount_pct": sf(disc.get("pct")),
        "discount_code": disc.get("code"),
        "round_off": sf(raw.get("round_off")),
        "grand_total": sf(raw.get("grand_total")),
        "extraction_notes": raw.get("extraction_notes") or [],
    }


def parse_receipt(receipt_base64: str, model_name: str = "gemini-2.5-flash") -> tuple:
    if "," in receipt_base64:
        receipt_base64 = receipt_base64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(receipt_base64)
    except Exception as e:
        return {}, [f"Could not decode base64 image: {e}"]

    raw_text = None
    last_error = None
    for _ in range(2):
        try:
            client = _client()
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=_detect_mime(image_bytes)
            )
            resp = client.models.generate_content(
                model=model_name,
                contents=[image_part, RECEIPT_PARSER_PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=2048,
                )
            )
            raw_text = resp.text
            raw_json = _extract_json(raw_text)
            data = _normalize(raw_json)
            flags = [f"OCR note: {n}" for n in data.pop("extraction_notes", [])]
            if data["grand_total"] == 0:
                flags.append("Grand total extracted as 0 -- check image quality")
            return data, flags
        except Exception as e:
            last_error = e
    return {}, [f"Receipt parse failed: {last_error}", f"Raw output: {(raw_text or '')[:300]}"]
