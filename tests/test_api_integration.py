"""
End-to-end API test with mocked model calls.
Proves the full pipeline (endpoint → receipt parse → description parse →
split engine → response contract) without needing an API key or network.

Run: python -m pytest tests/test_api_integration.py -q
"""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import llm_client
import main

client = TestClient(main.app, raise_server_exceptions=False)

FAKE_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes").decode()

# Canned model outputs for spec receipt R1 (Brew & Bite Cafe)
R1_RECEIPT_JSON = json.dumps({
    "items": [
        {"name": "Cappuccino", "qty": 1, "total": 180},
        {"name": "Grilled Chicken Sandwich", "qty": 1, "total": 260},
        {"name": "Penne Arrabiata", "qty": 1, "total": 320},
        {"name": "Fresh Lime Soda", "qty": 1, "total": 120},
        {"name": "Brownie", "qty": 1, "total": 160},
    ],
    "subtotal": 1040,
    "service_charge": {"amount": 52, "pct": 5},
    "tax": {"amount": 54.60, "pct": 5, "label": "GST"},
    "discount": {"amount": 0, "pct": 0, "code": None},
    "delivery_charge": {"amount": 0, "label": None},
    "round_off": 0.40,
    "grand_total": 1147,
    "extraction_notes": [],
})

R1_DESC_JSON = json.dumps({
    "people": ["Ravi", "Neha", "Sameer"],
    "assignments": [
        {"item": "Cappuccino", "shared_by": ["Ravi"]},
        {"item": "Grilled Chicken Sandwich", "shared_by": ["Ravi"]},
        {"item": "Penne Arrabiata", "shared_by": ["Neha"]},
        {"item": "Fresh Lime Soda", "shared_by": ["Neha"]},
        {"item": "Brownie", "shared_by": ["Sameer"]},
    ],
    "paid_by": "Sameer",
    "assumptions": [],
    "flags": [],
})


@pytest.fixture
def mock_models(monkeypatch):
    monkeypatch.setattr(llm_client, "_CHAIN",
                        [("mock", "MOCK_KEY", lambda p, img: R1_RECEIPT_JSON if img else R1_DESC_JSON)])
    monkeypatch.setenv("MOCK_KEY", "x")


def test_full_pipeline_r1(mock_models):
    resp = client.post("/split", json={
        "receipt_base64": FAKE_PNG,
        "description": "Three of us — Ravi, Neha, Sameer. Ravi had the cappuccino "
                       "and the sandwich. Neha had the pasta and the lime soda. "
                       "Sameer had the brownie. Sameer paid.",
    })
    assert resp.status_code == 200
    d = resp.json()

    # Exact contract fields
    for key in ("per_person", "grand_total", "reconciliation", "paid_by",
                "settle_up", "assumptions", "flags"):
        assert key in d, f"missing contract field {key}"

    assert d["grand_total"] == 1147
    assert d["reconciliation"]["matches_bill"] is True
    assert d["reconciliation"]["sum_of_person_totals"] == 1147
    assert d["paid_by"] == "Sameer"

    totals = {p["name"]: p["total"] for p in d["per_person"]}
    assert totals == {"Ravi": 485, "Neha": 485, "Sameer": 177}

    settle = {(s["from"], s["to"]): s["amount"] for s in d["settle_up"]}
    assert settle == {("Ravi", "Sameer"): 485, ("Neha", "Sameer"): 485}

    per_person_fields = {"name", "items", "subtotal", "tax_share",
                         "service_share", "discount_share", "total"}
    for p in d["per_person"]:
        assert per_person_fields <= set(p)


def test_empty_inputs_rejected():
    assert client.post("/split", json={"receipt_base64": "", "description": "x"}).status_code == 422
    assert client.post("/split", json={"receipt_base64": FAKE_PNG, "description": ""}).status_code == 422


def test_no_api_key_returns_503(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    resp = client.post("/split", json={"receipt_base64": FAKE_PNG, "description": "Sameer paid."})
    assert resp.status_code == 503
    assert "No API key configured" in json.dumps(resp.json())


def test_bad_base64_flagged(mock_models):
    resp = client.post("/split", json={"receipt_base64": "!!!not-base64!!!", "description": "Sameer paid."})
    assert resp.status_code == 422
