"""
main.py
FastAPI backend for Fair Split.

Routes:
  POST /split  — main API endpoint (exact contract from spec)
  GET  /       — serves the frontend HTML
"""

from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from llm_client import AllProvidersFailed, configured_providers
from receipt_parser import parse_receipt
from description_parser import parse_description
from split_engine import compute_split

# Load .env for local development (no-op on Railway where env vars are set directly)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(
    title="Fair Split",
    description="Restaurant bill splitter: image + description → per-person breakdown",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────

class SplitRequest(BaseModel):
    receipt_base64: str = Field(
        ...,
        description="Base64-encoded image bytes (no data-URI prefix)",
    )
    description: str = Field(
        ...,
        description="Plain-English description of who had what and who paid",
    )


# ── Main endpoint ─────────────────────────────────────────────────────────

@app.post("/split")
async def split_bill(request: SplitRequest):
    """
    Accept a receipt image + description, return a fully-reconciled bill split.
    All arithmetic is computed in Python — the model only extracts structured data.
    """
    # ── 1. Validate inputs ────────────────────────────────────────────────
    if not request.receipt_base64.strip():
        raise HTTPException(status_code=422, detail="receipt_base64 is empty")
    if not request.description.strip():
        raise HTTPException(status_code=422, detail="description is empty")

    # ── 2. Parse receipt image via vision model ───────────────────────────
    try:
        receipt_data, receipt_flags = parse_receipt(request.receipt_base64)
    except AllProvidersFailed as e:
        raise HTTPException(status_code=503, detail={"error": str(e)})

    if not receipt_data:
        # Parser returned empty dict → image unreadable
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Could not extract data from receipt image",
                "flags": receipt_flags,
            },
        )

    if receipt_data.get("grand_total", 0) == 0:
        receipt_flags.append("Grand total extracted as 0 — result may be unreliable")

    # ── 3. Parse description via text model ───────────────────────────────
    try:
        desc_data, desc_assumptions, desc_flags = parse_description(
            request.description,
            receipt_data.get("items", []),
        )
    except AllProvidersFailed as e:
        raise HTTPException(status_code=503, detail={"error": str(e)})

    all_people: list[str] = desc_data.get("people", [])
    paid_by: str | None = desc_data.get("paid_by")

    if not all_people:
        desc_flags.append("Could not identify any people from the description")

    # ── 4. Run split engine (pure Python arithmetic) ──────────────────────
    result = compute_split(
        bill=receipt_data,
        assignments=desc_data.get("assignments", []),
        paid_by=paid_by,
        all_people=all_people,
        extra_assumptions=desc_assumptions,
        extra_flags=receipt_flags + desc_flags,
    )

    return JSONResponse(content=result)


# ── Health check ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    providers = configured_providers()
    return {
        "status": "ok" if providers else "no_api_key_configured",
        "providers": providers,
    }


# ── Frontend ──────────────────────────────────────────────────────────────

FRONTEND_PATH = Path(__file__).parent / "frontend" / "index.html"

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if FRONTEND_PATH.exists():
        return HTMLResponse(content=FRONTEND_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Fair Split API</h1><p>POST /split</p>")


# ── Error handlers ────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__},
    )
