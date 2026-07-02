# Fair Split

Takes a photo of a restaurant bill plus a plain-English description of who had
what, and returns a fair, fully-reconciled, per-person breakdown — tax, service
charge, discounts, rounding, and a "who owes whom" settle-up.

**Live demo:** `https://<your-railway-app>.up.railway.app` (frontend at `/`, API at `POST /split`)

## How it works

```
receipt image ──► receipt_parser (vision model: READ printed values only)
                        │ structured bill JSON
description  ──► description_parser (text model: map sentences → item/people assignments)
                        │ assignments + assumptions + flags
                        ▼
                 split_engine.py (pure Python — ALL arithmetic)
                        │ equal splits · proportional tax/service/discount ·
                        │ rupee rounding w/ paise absorption · settle-up ·
                        ▼ reconciliation self-check
                 exact response contract
```

The model does **zero arithmetic** — it only extracts. Every number is computed
and reconciled in code. See `docs/prompt_log.md` for the full rationale.

## API

`POST /split` with `Content-Type: application/json`:

```json
{
  "receipt_base64": "<base64 image bytes, no data-URI prefix>",
  "description": "Three of us — Ravi, Neha, Sameer. Ravi had the cappuccino..."
}
```

Response matches the assignment's exact output shape: `per_person[]`,
`grand_total`, `reconciliation`, `paid_by`, `settle_up[]`, `assumptions[]`,
`flags[]`. Ambiguous or non-reconciling inputs are flagged, never fabricated.

`GET /health` reports which model providers are configured.

## API keys (one-time setup, keys never expire)

The app tries providers in order — set at least one in `.env` locally and in
Railway → Variables:

1. `GEMINI_API_KEY` (recommended) — free at https://aistudio.google.com/apikey,
   no card, ~1,500 requests/day, uses `gemini-2.5-flash`. Use a personal Gmail.
2. `OPENROUTER_API_KEY` (fallback) — free `:free` vision models, 50 req/day.
3. `GROQ_API_KEY` (text-only fallback — Groq's free vision models were deprecated in 2026).

If the primary provider errors or rate-limits, the app fails over automatically.

## Run locally

```
pip install -r requirements.txt
cp .env.example .env        # add your key
uvicorn main:app --reload   # frontend at http://localhost:8000
```

## Tests

```
python -m pytest tests/ -q   # 19 tests: fairness rules, all 4 spec receipts
                             # reconcile exactly, full API pipeline (mocked models),
                             # error paths (bad base64, no key → 503)
```

`samples/` holds a stress-test kit of receipt images (spec R1–R4 plus S1–S5
edge-case bills: total mismatch, tip + delivery fee, CGST/SGST, complimentary
items, odd splits). Regenerate with `python samples/make_receipts.py`.

## Deliverables

| # | Deliverable | Where |
|---|------------|-------|
| 1 | Deployed API + minimal frontend | Railway (URL above); `frontend/index.html` served at `/` |
| 2 | Prompt log + model-vs-code arithmetic answer | `docs/prompt_log.md` |
| 3 | Edge-case doc (27 cases, each with input / handling / verified) | `docs/edge_cases.md` |
| 4 | "Where the AI was wrong" — 3 concrete caught-and-fixed errors | `docs/ai_errors.md` |

`DEVLOG.md` is the full build journal.
