# Fair Split — Full Development Log

Complete record of every decision, iteration, error, fix, and workaround from the
entire build session. Written for reference, portfolio evidence, and future debugging.

---

## Table of Contents

1. [Assignment Spec (Source Material)](#1-assignment-spec-source-material)
2. [Architecture Decisions](#2-architecture-decisions)
3. [Build Order & What Was Built](#3-build-order--what-was-built)
4. [Errors & Fixes — Complete Chronological Log](#4-errors--fixes--complete-chronological-log)
5. [Prompt Iterations — Receipt Parser](#5-prompt-iterations--receipt-parser)
6. [Prompt Iterations — Description Parser](#6-prompt-iterations--description-parser)
7. [Split Engine Design](#7-split-engine-design)
8. [Testing Journey — 5 Tests → 15 Tests](#8-testing-journey--5-tests--15-tests)
9. [Deployment Journey — Railway & GitHub](#9-deployment-journey--railway--github)
10. [API Provider Journey — Gemini → OpenRouter → Groq](#10-api-provider-journey--gemini--openrouter--groq)
11. [Edge Case Coverage Expansion](#11-edge-case-coverage-expansion)
12. [Final File Structure](#12-final-file-structure)

---

## 1. Assignment Spec (Source Material)

### What Was Asked
Build a **deployed API + minimal frontend** that:
- Accepts a restaurant bill image (base64) + plain-English description of who had what
- Returns a per-person cost breakdown including tax/service/discount splits
- Includes settle-up logic, reconciliation check, assumptions, and flags

### API Contract (from spec)

```
POST /split
{
  "receipt_base64": "<base64 string>",
  "description": "Aman had the pasta. Priya had the salad. Karan paid."
}
```

Response shape:
```json
{
  "per_person": [
    {
      "name": "Aman",
      "items": ["Pasta"],
      "subtotal": 320,
      "tax_share": 16,
      "service_share": 16,
      "discount_share": 0,
      "total": 352
    }
  ],
  "grand_total": 1147,
  "reconciliation": {
    "sum_of_person_totals": 1147,
    "matches_bill": true
  },
  "paid_by": "Karan",
  "settle_up": [
    { "from": "Aman", "to": "Karan", "amount": 352 }
  ],
  "assumptions": ["Aman absorbs +₹1 rounding adjustment (fractional remainder: ₹0.6667)"],
  "flags": []
}
```

### 5 Fairness Rules (from spec)

1. Each person pays for items they consumed
2. Shared items split equally among those who had them
3. Tax + service charge allocated **proportionally** to each person's subtotal
4. Discount allocated **proportionally** to each person's subtotal (as negative)
5. Round to whole rupees; absorb paise residual in the person with the largest fractional remainder; state this in assumptions

### 4 Sample Receipts (from spec)

| Receipt | Restaurant | Grand Total | Key Complexity |
|---------|-----------|-------------|----------------|
| R1 | Brew & Bite Café | ₹1147 | Round-off +₹0.40, 5% GST |
| R2 | Tamarind Kitchen | ₹1345 | Partial share (Gulab Jamun for 2 of 4), Round-off −₹0.05 |
| R3 | The Daily Grind | ₹1720 | 3-way fractional split (₹380 ÷ 3), partial beer share |
| R4 | Spice Route | ₹1436 | 15% WELCOME15 coupon discount |

### Deliverables Required (from spec)

1. **Deployed API + minimal frontend** — upload image, paste description, see result table
2. **Prompt log** — what changed between versions and why; did model do arithmetic or code?
3. **Edge-case doc** — every case considered, how handled, whether verified
4. **"Where the AI was wrong" note** — 3 concrete examples from testing

### Stack Preferences (from spec/conversation)

- FastAPI (Python), Gemini vision + text via `google-genai` SDK
- Model: `gemini-2.0-flash`
- Deploy on Railway (free tier)
- Frontend served by FastAPI itself (no separate hosting)

### Execution Order Specified

3 (split engine) → 1 (receipt parser) → 2 (description parser) → 4 (API) → 6 (deployment config) → 5 (frontend) → 7 (docs) → 8 (tests) → 9 (deploy)

---

## 2. Architecture Decisions

### Decision 1: Model extracts, Python computes

**Question:** Should the model do the arithmetic (proportional splits, rounding) or just extract data?

**Decision:** Model does **zero arithmetic**. It only reads numbers off the image and maps text to item names. All computation happens in `split_engine.py`.

**Why:** Models make arithmetic errors silently — no exception, confident-looking wrong output. Code is deterministic and throws exceptions on failure. The reconciliation check (`sum_of_person_totals == grand_total`) validates every run. A model error becomes a caught, flagged discrepancy instead of a silent wrong answer.

### Decision 2: Reconciliation on every response

Every API response includes:
```json
"reconciliation": {
  "sum_of_person_totals": 1147,
  "matches_bill": true
}
```
This means a model OCR error (wrong tax value, hallucinated item) immediately surfaces as a numeric discrepancy rather than being silently absorbed.

### Decision 3: Paise absorption by fractional remainder

When `floor(person_total)` values don't sum to `grand_total`, the residual ±N rupees is distributed to the N people with the largest fractional remainders. Named in `assumptions`. This is deterministic and fair — the person who "rounds up" most is the one who gets the rounding adjustment.

### Decision 4: Assumptions vs Flags separation

- **assumptions** = interpretive decisions the parser made (e.g., "rest of us" interpreted as X)
- **flags** = unresolvable issues (e.g., item in description not on receipt)

Evaluator specifically tests for surfacing ambiguity rather than guessing silently.

### Decision 5: No payer → flagged, settle_up empty

If description doesn't name who paid, `paid_by: null`, `settle_up: []`, and a flag fires. We never assume or guess the payer.

### Decision 6: Grand total is authoritative

When extracted line items don't sum to printed grand total, the split still uses the printed grand total as the target. The discrepancy is flagged but not used to override the bill. "The printed total is what you actually owe the restaurant."

---

## 3. Build Order & What Was Built

### Phase 1: Split Engine (`split_engine.py`)

Built first — pure Python, no model involved, fully testable offline.

Core function: `compute_split(bill, assignments, paid_by, all_people, extra_assumptions, extra_flags) → dict`

Steps inside:
1. Per-person item subtotals (equal splits for shared items)
2. Proportional tax/service/discount allocation
3. Floor + fractional-sort rupee rounding
4. Build per-person result rows (tax_r absorbs integer arithmetic residual)
5. Reconciliation check
6. Settle-up graph

Verified against R1 (₹1147), R2 (₹1345), R3 (₹1720), R4 (₹1436) — all reconcile exactly.

### Phase 2: Parsers (`receipt_parser.py`, `description_parser.py`, `prompts.py`)

- `receipt_parser.py` — calls vision model with receipt image, returns normalized dict
- `description_parser.py` — calls text model with description + receipt items context, returns assignments
- `prompts.py` — versioned prompt constants (v1–v4 for both parsers)

### Phase 3: API (`main.py`)

FastAPI app:
- `POST /split` — main endpoint
- `GET /` — serves frontend HTML
- `GET /health` — health check for Railway

CORS allow_origins=["*"] for Railway deployment.

### Phase 4: Frontend (`frontend/index.html`)

Single HTML file, dark theme, served by FastAPI. Sections:
- Receipt image upload (drag-and-drop + click)
- Description textarea
- Split the Bill button
- Results table (per-person breakdown)
- Settle-up section
- Assumptions + Flags sections

### Phase 5: Deployment Config

- `requirements.txt` — dependencies
- `Procfile` — `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
- `railway.toml` — Railway build config
- `.gitignore` — `.env`, `venv/`, `__pycache__/`, `*.pyc`
- `.env.example` — template for API keys

### Phase 6: Docs

- `docs/prompt_log.md` — prompt iteration history
- `docs/edge_cases.md` — 25 edge cases documented
- `docs/ai_errors.md` — 3 concrete AI errors caught during testing

---

## 4. Errors & Fixes — Complete Chronological Log

### Error 1: robocopy "cannot find path"

**What happened:** User tried to copy files using `robocopy` from a path that didn't exist on their Windows filesystem.

**Root cause:** Files were created in the Cowork sandbox (Linux), not the Windows filesystem. The sandbox path (`/sessions/...`) isn't accessible via Windows tools.

**Fix:** Created a zip of all files via bash `zip -r fair-split.zip fair-split/`, presented for download via `present_files` tool. User extracted to their Desktop.

---

### Error 2: UTF-8 BOM / null bytes syntax error

**What happened:** After copying files, Python showed `SyntaxError: source code string cannot contain null bytes` and UTF-8 BOM markers.

**Root cause:** Files were corrupted during the copy process — BOM characters were injected, or the encoding was mishandled.

**Fix:** Regenerated all Python files cleanly via bash heredocs:
```bash
cat > split_engine.py << 'PYEOF'
...content...
PYEOF
```
Verified with `file split_engine.py` → "Python script, ASCII text". All null bytes eliminated.

---

### Error 3: pydantic-core build failure (Rust required)

**What happened:**
```
error: can't find Rust compiler
Building wheel for pydantic-core (PEP 517) ... error
```

**Root cause:** User was on Python 3.14. `pydantic-core` v2 requires Rust to build from source. Python 3.14 wheels weren't available on PyPI yet for pydantic v2.

**Fix (attempted first):** Pin `pydantic==1.10.21` (pure Python, no Rust). This worked for the engine but caused FastAPI compatibility issues.

**Final fix:** Unpinned all versions in `requirements.txt` (just `fastapi`, `uvicorn[standard]`, etc.) — let pip resolve compatible versions for the user's Python version. This worked.

---

### Error 4: uvicorn not found after pip install

**What happened:**
```
uvicorn : The term 'uvicorn' is not recognized
```

**Root cause:** Venv wasn't activated. `pip install` went to system Python, but shell was looking elsewhere.

**Fix:**
```powershell
.\venv\Scripts\Activate.ps1
```
If execution policy blocked it:
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Error 5: FutureWarning — google.generativeai deprecated

**What happened:**
```
FutureWarning: google.generativeai is deprecated. Please use `google-genai` instead.
```
Followed by 404 for `gemini-1.5-flash`.

**Root cause:** Code was using the old `google-generativeai` SDK and the model `gemini-1.5-flash` which wasn't in the user's available models.

**Fix:** Switched to new `google-genai` SDK (`from google import genai`), switched model to `gemini-2.0-flash` (confirmed in user's model list).

Code change:
```python
# Before (deprecated)
import google.generativeai as genai
genai.configure(api_key=...)
model = genai.GenerativeModel("gemini-1.5-flash")

# After (new SDK)
from google import genai
from google.genai import types
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
resp = client.models.generate_content(model="gemini-2.0-flash", contents=[image_part, prompt], ...)
```

---

### Error 6: 429 RESOURCE_EXHAUSTED — quota limit: 0

**What happened:**
```
Error 429: Quota exceeded for metric: generate_content_free_tier_requests, limit: 0
```

**Root cause:** The Google Cloud project associated with the API key had quota set to **0** — not just exhausted, but hard-disabled at the project level. This affected ALL models. Likely caused by using an `.ac.in` educational Google Workspace account where Gemini API quotas are restricted by the organization.

**Attempted workaround:** Create new API keys from new projects → same result because all projects inherit the billing account's quota policy.

**Final fix:** Switch to alternative provider (OpenRouter, then Groq — see Section 10).

---

### Error 7: GitHub push protection (GH013) — API key in committed file

**What happened:**
```
remote: error: GH013: Repository rule violations found for refs/heads/main
remote: - GITHUB PUSH PROTECTION: Secrets detected in commits
```

**Root cause:** Real `GEMINI_API_KEY` was committed inside `.env.example` during an early iteration. GitHub's secret scanning blocked the push.

**Fix:**
1. Revoke the exposed key at aistudio.google.com
2. Fix `.env.example` to use placeholder only: `GEMINI_API_KEY=your_gemini_api_key_here`
3. `git commit --amend` to rewrite the last commit (replacing the bad `.env.example`)
4. `git push --force` to overwrite the remote history

**Second instance:** Same thing happened later with an OpenRouter key (`sk-or-v1-86afec...`) accidentally pasted into `.env.example`. Same fix — revoke key, fix file, commit, force push.

**Prevention added:** Explicit comment at top of `.env.example`: `# NEVER commit .env to git`

---

### Error 8: Railway crash — ImportError: cannot import name 'genai' from 'google'

**What happened:** Railway build succeeded but app crashed on startup:
```
ImportError: cannot import name 'genai' from 'google'
```

**Root cause:** `requirements.txt` still had `google-generativeai` (old SDK) instead of `google-genai` (new SDK). Railway installed the old package, which doesn't have the `genai` submodule.

**Fix:** Updated `requirements.txt`:
```
# Before
google-generativeai

# After
google-genai
```

---

### Error 9: git push — "fatal: unable to resolve host: github.com"

**What happened:**
```
fatal: unable to access 'https://github.com/...': Could not resolve host: github.com
```

**Root cause:** DNS resolution failure — likely VPN or network issue on user's machine.

**Fix options given:**
1. Disconnect VPN
2. `ipconfig /flushdns` then retry
3. Switch to phone hotspot

---

### Error 10: git commit — "index.lock: File exists"

**What happened:**
```
fatal: Unable to create '.git/index.lock': File exists
```

**Root cause:** Previous git process (likely the failed commit from the terminal) left a lock file behind.

**Fix:**
```powershell
Remove-Item ".git\index.lock" -Force
```

---

### Error 11: OpenRouter — "No endpoints found for google/gemini-2.0-flash-exp:free"

**What happened:** After switching from Gemini to OpenRouter, got 404 for `google/gemini-2.0-flash-exp:free`.

**Root cause:** This model was removed or renamed on OpenRouter.

**Attempted:** `qwen/qwen-2.5-vl-7b-instruct:free` → same 404.
**Attempted:** `meta-llama/llama-3.2-11b-vision-instruct:free` → not confirmed working.

**Final fix:** Switched to **Groq** — more reliable free tier with confirmed vision model (`llama-3.2-11b-vision-preview`). See Section 10.

---

### Error 12: "No module named 'openai'"

**What happened:** After adding OpenRouter/Groq support, server threw `ModuleNotFoundError: No module named 'openai'`.

**Root cause:** `openai` package wasn't installed in the venv.

**Fix:**
```powershell
pip install openai
```

---

## 5. Prompt Iterations — Receipt Parser

### v1 — Baseline (wrong)

```
"Extract all line items, subtotal, taxes, grand total from this receipt image. Return JSON."
```

**Problem:** Model computed GST instead of reading it. R1 printed `GST ₹54.60`. Model returned `"tax": 54` or `55` (it recalculated `5% × subtotal` and rounded). When combined with the round-off (₹0.40), this caused a ₹1 reconciliation failure.

**Caught by:** Reconciliation check. `sum_of_person_totals = 1146` but `grand_total = 1147`.

---

### v2 — Added "DO NOT compute"

Added: `"DO NOT compute anything — only READ printed values."` + `extraction_notes` field.

**Problem:** Model still returned discount as negative sometimes (e.g., `"discount": -228` on R4). Inconsistent across runs. Also still occasionally hallucinated items at non-zero temperature.

---

### v3 — Full schema + temperature 0

Added:
- Explicit field-by-field JSON schema with inline comments
- Rule: `discount.amount is ALWAYS a positive number even if printed with a minus sign`
- `temperature: 0` for determinism

**Result:** Eliminated hallucinated items. Discount consistently positive. GST read correctly.

---

### v4 — Real-world bill variants

Added rules for:

**CGST/SGST:** Indian bills often show two lines:
```
CGST 2.5% ₹27.30
SGST 2.5% ₹27.30
```
Instruction: sum them into `tax.amount` (54.60), set `tax.label` to "CGST+SGST".

**Tip/Gratuity:** A "Tip" or "Staff Tip" line is a LINE ITEM, not `service_charge`. Include in `items[]` with printed amount.

**Complimentary items:** Items marked "FOC", "Complimentary", or "On the house" → include in `items[]` with `total: 0`. Do NOT skip them.

**Delivery charge:** "Delivery Fee", "Packing Charge", "Platform Fee" → goes in new `delivery_charge.amount` field, NOT `service_charge`.

**Loyalty deductions:** "Points Redeemed", "Wallet Balance" → treat as `discount.amount` (positive), note in `discount.code`.

---

## 6. Prompt Iterations — Description Parser

### v1 — Baseline (wrong)

```
"Parse this description: who ate what, who paid. Return JSON."
```
No receipt context provided.

**Problem:** Model invented item names. Description said "pasta", model returned `"item": "Pasta"` instead of `"item": "Penne Arrabiata"`. The normalizer did an exact-match lookup, found no match, dropped the assignment. ₹240 of Butter Naan went unaccounted. Reconciliation failed with a ₹266 gap.

---

### v2 — Added receipt context

Injected receipt item list as JSON into the prompt. Added: `"Use EXACT item names from the receipt list."`

**Problem:** Ambiguous phrases ("rest of us", "I", "we") were silently guessed at or dropped. No way to distinguish interpretive decisions from unresolvable problems.

---

### v3 — Explicit ambiguity rules + assumptions/flags split

Added rules:
- `"rest of us"` → flag it AND best-guess from context, state guess in `assumptions`
- `"I"/"me"` → flag as ambiguous unless clearly resolvable
- Items in description not on receipt → `flags`, not assignments
- Receipt items not in description → `flags`
- Split output into `assumptions` (interpretive decisions) vs `flags` (unresolvable)

---

### v4 — Delivery, tip, and more ambiguity patterns

Added rules:
- Delivery/packing charge → default `shared_by` to ALL people, note in assumptions
- Tip → if not explicitly assigned, `shared_by: []` (flagged as unassigned)
- `"between the two of us"` → flag which two, state in assumptions
- `"we split X"` without naming who → all identified people, note in assumptions

---

## 7. Split Engine Design

### Key Arithmetic — Proportional Allocation

For each person `p`:
```python
ratio = person_subtotals[p] / total_subtotal

tax_share   = tax_total   * ratio
service_share = service_total * ratio
discount_share = -discount_total * ratio  # negative
delivery_share = delivery_total * ratio   # rolled into service_share in output

person_total_raw = subtotal + tax_share + service_share + discount_share
```

### Rupee Rounding — Floor + Fractional Sort

```python
floored = {p: math.floor(raw[p]["total"]) for p in all_people}
fracs = {p: raw[p]["total"] - floored[p] for p in all_people}
residual = grand_total - sum(floored.values())

# Distribute residual rupees to people with largest fractional remainders
absorbers = sorted(all_people, key=lambda p: fracs[p], reverse=True)
for i in range(residual):
    floored[absorbers[i % len(absorbers)]] += 1
```

Example — R3, Margherita Pizza ₹380 ÷ 3 people:
- Each person's raw share: ₹126.6667
- Floored: ₹126 each → sum = ₹378
- Residual = ₹380 - ₹378 = ₹2
- Top 2 fractional remainders get +₹1 each
- Result: 2 people pay ₹127, 1 pays ₹126

### Component Reconciliation in Output

The `tax_r` field in each person's row absorbs any integer arithmetic residual:
```python
subtotal_r = round(raw[p]["subtotal"])
service_r  = round(raw[p]["service"])
discount_r = round(raw[p]["discount"])
tax_r = total_r - subtotal_r - service_r - discount_r  # absorbs rounding
```

This guarantees `subtotal + tax_share + service_share + discount_share == total` for every person, every time.

### New Bill Types Added (v2 of split engine)

**Tips:** Detected by checking item name against `_TIP_TOKENS = {"tip", "gratuity", "staff tip", "optional gratuity"}`. If unassigned → specific flag. If assigned → note in flags but still split.

**Delivery charge:** New `delivery_charge_amount` field in bill dict. Added proportionally to `service_share` in output.

**Complimentary items:** `amount == 0` → skip cost allocation, add to person's `items` list with "(complimentary)" suffix.

**CGST/SGST:** No engine change needed — parser sums them before passing to engine.

---

## 8. Testing Journey — 5 Tests → 15 Tests

### Original 7 Tests

| Test | What it verifies |
|------|-----------------|
| `test_r1_basic` | R1 reconciles ₹1147; Ravi + Neha owe Sameer |
| `test_r2_partial_share` | Gulab Jamun only for Priya+Karan; subtotals correct |
| `test_r3_fractional_splits` | ₹380÷3 rounding; Ishaan==Rohit>Meera |
| `test_r4_with_discount` | Discount shares ≤0; Dev==Nikhil symmetric |
| `test_no_payer_flagged` | paid_by=null → settle_up=[] → flag fires |
| `test_no_service_charge` | service_share=0 for all; reconciles |
| `test_unassigned_item_flagged` | Empty shared_by → item excluded + flagged |

### 8 New Tests Added

| Test | What it verifies |
|------|-----------------|
| `test_tip_flagged` | Tip item with no assignees → specific tip flag fires |
| `test_delivery_charge` | delivery_charge_amount allocated proportionally; note in assumptions |
| `test_cgst_sgst_combined` | Combined tax identical to single-GST math |
| `test_large_group_6_people` | ₹1000÷6: exactly 4 people pay ₹167, 2 pay ₹166 |
| `test_complimentary_item` | ₹0 item noted in assumptions; doesn't affect totals |
| `test_one_person_all_items` | Solo diner: Bob=₹0, Alice=full bill; settle-up correct |
| `test_new_person_from_description` | Charlie not in all_people → auto-added + flagged |
| `test_bill_total_mismatch_flagged` | Items+charges≠grand_total → "unexplained" flag fires |

**Final result: 15/15 passing**

---

## 9. Deployment Journey — Railway & GitHub

### GitHub Setup

```bash
git init
git add -A
git commit -m "initial: fair split"
git remote add origin https://github.com/therjalan-web/fair-split.git
git push -u origin main
```

### GitHub Push Protection Block (GH013)

First attempt failed: real `GEMINI_API_KEY` was in `.env.example`.

Fix sequence:
```bash
# 1. Revoke exposed key at aistudio.google.com
# 2. Fix .env.example to use placeholder
# 3. Amend the commit to rewrite history
git add .env.example
git commit --amend --no-edit
# 4. Force push to overwrite remote
git push --force
```

### Railway Setup

1. New project → Deploy from GitHub repo
2. Railway auto-detected Python + `Procfile`
3. `Procfile`: `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment variable: `GEMINI_API_KEY` (or `GROQ_API_KEY`) set in Variables tab

### Railway Crash — ImportError

First successful build crashed on startup because `requirements.txt` had `google-generativeai` but code imported `from google import genai` (new SDK).

Fix: updated `requirements.txt` to `google-genai`.

### DNS Failure on git push

```
fatal: unable to resolve host: github.com
```

This was a local network/DNS issue, not a git problem. Workaround: use phone hotspot, or:
```powershell
ipconfig /flushdns
```

### git index.lock

```
fatal: Unable to create '.git/index.lock': File exists
```

Fix:
```powershell
Remove-Item ".git\index.lock" -Force
```

---

## 10. API Provider Journey — Gemini → OpenRouter → Groq

### Phase 1: google-generativeai (deprecated SDK)

Initial code used `google.generativeai`. Got `FutureWarning` + 404 on `gemini-1.5-flash`.

Switch to: `google-genai` SDK + `gemini-2.0-flash`.

### Phase 2: Gemini quota limit: 0

```
429 RESOURCE_EXHAUSTED
Quota exceeded for metric: generate_content_free_tier_requests, limit: 0
```

This was a **project-level quota** issue. All projects on the billing account inherited limit: 0. Retried with new keys from new projects — same result each time. The `.ac.in` account likely has Gemini API disabled at the Workspace level.

### Phase 3: OpenRouter

Switched to OpenRouter (openai-compatible API). Updated both parsers to auto-detect provider:

```python
def _get_provider() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    raise RuntimeError("No API key found.")
```

Tried models:
- `google/gemini-2.0-flash-exp:free` → 404 "No endpoints found"
- `qwen/qwen-2.5-vl-7b-instruct:free` → 404 "No endpoints found"
- `meta-llama/llama-3.2-11b-vision-instruct:free` → uncertain availability

OpenRouter's `:free` tier models have unreliable endpoint availability — they appear and disappear.

### Phase 4: Groq (current)

Switched to [Groq](https://console.groq.com) — free tier, no credit card, instant key, 1000 req/day.

Models used:
- **Receipt parser (vision):** `llama-3.2-11b-vision-preview`
- **Description parser (text):** `llama-3.3-70b-versatile`

API is OpenAI-compatible, same code structure, just different `base_url`:
```python
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)
```

### Provider Auto-Detection Logic

Both parsers check env vars in order:
1. `GEMINI_API_KEY` set → use google-genai SDK → `gemini-2.0-flash`
2. `GROQ_API_KEY` set → use Groq via openai SDK → llama vision / llama text
3. Neither set → RuntimeError with instructions

Zero changes needed in `main.py` — provider selection is internal to parsers.

---

## 11. Edge Case Coverage Expansion

### Original 18 cases (spec-driven)

Covered the dimensions listed in the assignment: no service charge, total mismatch, item not on receipt, "rest of us", partial sharing, uneven quantities, tip, multiple payers, no payer, discount, negative discount sign, round-off, partial sharing, unreadable image, duplicate items, new person, negative net settle-up.

### 7 New Cases Added (real-world testing)

Added to handle bill types the spec sample receipts didn't cover:

| # | Case | How Handled |
|---|------|-------------|
| 19 | Tip/gratuity line | Flagged as outside fairness rules; excluded from split unless explicitly assigned |
| 20 | Delivery/packing charge | Proportional allocation like service charge; noted in assumptions |
| 21 | CGST+SGST separate lines | Receipt parser sums them; engine unchanged |
| 22 | Complimentary/FOC item | ₹0 cost, item listed, noted in assumptions |
| 23 | Loyalty/points deduction | Treated as discount via prompt instruction |
| 24 | Large group (6+) rounding | 4 of 6 pay ₹167, 2 pay ₹166 for ₹1000 bill |
| 25 | Solo diner in group | One person's total = grand_total; others = ₹0 |

---

## 12. Final File Structure

```
fair-split/
├── main.py                    # FastAPI app — POST /split, GET /, GET /health
├── split_engine.py            # All arithmetic — zero model involvement
├── receipt_parser.py          # Vision model call → normalized receipt dict
├── description_parser.py      # Text model call → assignment map
├── prompts.py                 # Versioned prompt constants (v4 for both parsers)
├── requirements.txt           # fastapi, uvicorn, google-genai, openai, python-dotenv
├── Procfile                   # Railway: uvicorn main:app --host 0.0.0.0 --port $PORT
├── railway.toml               # Railway build config
├── .env                       # NOT committed — GROQ_API_KEY or GEMINI_API_KEY
├── .env.example               # Template with instructions
├── .gitignore                 # .env, venv/, __pycache__/, *.pyc
├── frontend/
│   └── index.html             # Single-page UI served by FastAPI
├── tests/
│   └── test_split_engine.py   # 15 tests — 15/15 passing
└── docs/
    ├── prompt_log.md          # v1→v4 iterations for both parsers + arithmetic decision
    ├── edge_cases.md          # 25 edge cases, input/handling/verified for each
    ├── ai_errors.md           # 3 concrete AI errors caught during R1-R3 testing
    └── DEVLOG.md              # This file
```

### Key Numbers

| Metric | Value |
|--------|-------|
| Tests passing | 15/15 |
| Edge cases documented | 25 |
| Prompt versions | v4 (receipt), v4 (description) |
| AI errors documented | 3 |
| Sample receipts verified | R1 ✓ R2 ✓ R3 ✓ R4 ✓ |
| Providers supported | Gemini (primary), Groq (free fallback) |
| Deployment | Railway (auto-deploy from GitHub) |

---

*Generated from full build session — Fair Split, epifi internship assignment, July 2026.*
