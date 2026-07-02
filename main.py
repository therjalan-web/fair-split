"""
main.py - FastAPI backend for Fair Split.
POST /split  -- main API
GET  /       -- frontend
GET  /health -- health check
"""
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from receipt_parser import parse_receipt
from description_parser import parse_description
from split_engine import compute_split

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="Fair Split", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class SplitRequest(BaseModel):
    receipt_base64: str
    description: str


@app.post("/split")
async def split_bill(request: SplitRequest):
    if not request.receipt_base64.strip():
        raise HTTPException(status_code=422, detail="receipt_base64 is empty")
    if not request.description.strip():
        raise HTTPException(status_code=422, detail="description is empty")

    receipt_data, receipt_flags = parse_receipt(request.receipt_base64)

    if not receipt_data:
        raise HTTPException(status_code=422, detail={
            "error": "Could not extract data from receipt image",
            "flags": receipt_flags,
        })

    desc_data, desc_assumptions, desc_flags = parse_description(
        request.description, receipt_data.get("items", [])
    )

    all_people = desc_data.get("people", [])
    paid_by = desc_data.get("paid_by")

    if not all_people:
        desc_flags.append("Could not identify any people from the description")

    result = compute_split(
        bill=receipt_data,
        assignments=desc_data.get("assignments", []),
        paid_by=paid_by,
        all_people=all_people,
        extra_assumptions=desc_assumptions,
        extra_flags=receipt_flags + desc_flags,
    )
    return JSONResponse(content=result)


@app.get("/health")
async def health():
    return {"status": "ok", "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY"))}


FRONTEND_PATH = Path(__file__).parent / "frontend" / "index.html"

@app.get("/", response_class=HTMLResponse)
async def frontend():
    if FRONTEND_PATH.exists():
        return HTMLResponse(content=FRONTEND_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Fair Split API</h1><p>POST /split</p>")


@app.exception_handler(Exception)
async def generic_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content={"error": str(exc), "type": type(exc).__name__})
