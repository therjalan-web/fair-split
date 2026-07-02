# Next steps (do these yourself — ~10 minutes)

## 1. Get your one-time Gemini key (2 min, never expires)
1. Open https://aistudio.google.com/apikey signed into a **personal Gmail**
   (your BITS .ac.in account is blocked by Google AI Studio).
2. Create API key → copy it.
3. Paste it into `.env` after `GEMINI_API_KEY=`.

That's it — this key is permanent. You never need a new one per run.
Your OpenRouter key stays in `.env` as automatic fallback (it was never being
read before — that's why you "kept needing new keys").

## 2. Test locally
```
pip install -r requirements.txt
python -m pytest tests/ -q          # should say: 19 passed
uvicorn main:app --reload
```
Open http://localhost:8000, upload `samples/receipt_R1.png`, paste the R1
description, check the split reconciles to ₹1147. Then try the S-series
receipts in `samples/` (S2 must show a ₹20-unexplained flag, S3 a tip flag).

## 3. Push to GitHub (redeploys Railway)
A stale git lock exists — remove it first:
```
del .git\index.lock
git add -A
git commit -m "fix: provider fallback layer (gemini-2.5-flash + openrouter), integration tests, docs, sample kit"
git push
```

## 4. Set the key on Railway
Railway dashboard → your project → **Variables** → add
`GEMINI_API_KEY = <your key>` (and optionally `OPENROUTER_API_KEY`).
Railway restarts automatically. Verify:
```
https://<your-app>.up.railway.app/health   →  {"status":"ok","providers":["gemini",...]}
```
Then run one real split through the live frontend before submitting.

## 5. Before submitting
- Put your live Railway URL into README.md (line 8).
- Delete this file and `b64.txt` (redundant — kept as samples/receipt_R2.jpg).
