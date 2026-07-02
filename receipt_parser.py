"""
receipt_parser.py
Calls Gemini vision to OCR the receipt image → structured dict.
ALL arithmetic is done by split_engine.py, NOT here.
"""

from __future__ import annotations
import base64
import json
import os
import re
import struct

import google.generativeai as genai

from prompts import RECEIPT_PARSER_PROMPT


def _configure_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")
    genai.configure(api_key=api_key)


def _detect_mime_type(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    # Default to JPEG for unknown formats
    return "image/jpeg"


def _extract_json(text: str) -> dict:
    """
    Extract the first JSON object from a Gemini response.
    Handles markdown fences and leading prose.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    # Find JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")

    # Find matching closing brace
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])

    raise ValueError(f"Unbalanced JSON in response: {text[:200]}")


def _call_gemini_vision(image_bytes: bytes, prompt: str, model_name: str) -> str:
    """Make the Gemini API call with vision input."""
    mime_type = _detect_mime_type(image_bytes)
    model = genai.GenerativeModel(model_name)

    # Build content parts: image first, then text prompt
    image_part = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(image_bytes).decode(),
        }
    }
    response = model.generate_content(
        [image_part, prompt],
        generation_config=genai.GenerationConfig(
            temperature=0,          # deterministic OCR
            max_output_tokens=2048,
        ),
    )
    return response.text


def _normalize_receipt(raw: dict) -> dict:
    """
    Normalize the raw Gemini output into the canonical receipt dict
    consumed by split_engine.compute_split.
    Fills defaults for missing fields.
    """
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

    return {
        "items": items,
        "subtotal": safe_float(raw.get("subtotal")),
        "service_charge_amount": safe_float(sc.get("amount")),
        "service_charge_pct": safe_float(sc.get("pct")),
        "tax_amount": safe_float(tax.get("amount")),
        "tax_pct": safe_float(tax.get("pct")),
        "tax_label": str(tax.get("label") or "GST"),
        "discount_amount": safe_float(disc.get("amount")),   # positive
        "discount_pct": safe_float(disc.get("pct")),
        "discount_code": disc.get("code"),
        "round_off": safe_float(raw.get("round_off")),
        "grand_total": safe_float(raw.get("grand_total")),
        "extraction_notes": raw.get("extraction_notes") or [],
    }


def parse_receipt(
    receipt_base64: str,
    model_name: str = "gemini-2.0-flash",
) -> tuple[dict, list[str]]:
    """
    Parse a base64-encoded receipt image.

    Returns
    -------
    receipt_data : dict — normalized receipt fields
    flags : list[str]   — any extraction warnings
    """
    _configure_gemini()

    # Decode base64 (handle both raw and data-URI prefixed)
    if "," in receipt_base64:
        receipt_base64 = receipt_base64.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(receipt_base64)
    except Exception as e:
        return {}, [f"Could not decode base64 image: {e}"]

    # Call Gemini with retry on JSON parse failure
    raw_text = None
    last_error = None
    for attempt in range(2):
        try:
            raw_text = _call_gemini_vision(image_bytes, RECEIPT_PARSER_PROMPT, model_name)
            raw_json = _extract_json(raw_text)
            receipt_data = _normalize_receipt(raw_json)
            flags = []

            # Add extraction notes as flags
            for note in receipt_data.pop("extraction_notes", []):
                flags.append(f"OCR note: {note}")

            # Validate grand total is non-zero
            if receipt_data["grand_total"] == 0:
                flags.append("Could not extract grand total from receipt — check image quality")

            return receipt_data, flags

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            continue

    # Both attempts failed
    return {}, [
        f"Could not parse receipt response as JSON: {last_error}",
        f"Raw model output: {(raw_text or '')[:300]}",
    ]
