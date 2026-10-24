# Quickstart: HCM Lite with AI HR Assistant

> Target flow from the design (constitution v4.0.0). These commands are verified only by
> implementation tasks; the README is the final, verified version (Art. XX).

## 0. Prerequisites

- Python 3.12 (`py -3.12`).
- An OpenAI API key.
- Nothing else: the database is a local SQLite file (`data/hcm_lite.db`) and the vector index is
  embedded Qdrant (`.qdrant/`).

## 1. Install

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## 2. Configure

```powershell
Copy-Item .env.example .env
chainlit create-secret                                              # → CHAINLIT_AUTH_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"        # → API_JWT_SECRET
# set OPENAI_API_KEY, OPENAI_MODEL, OPENAI_EMBEDDING_MODEL in .env
```

## 3. Database and documents

```powershell
alembic upgrade head                 # create the SQLite schema (constraints, indexes)
python -m hcm_lite.db seed           # labelled demo data + 3 demo accounts (prints credentials)
python -m hcm_lite.rag.ingest        # index demo HR policy documents
```

## 4. Run

```powershell
chainlit run app.py                                   # UI: http://localhost:8000
uvicorn hcm_lite.api.main:app --port 8001             # API: http://localhost:8001/docs
```

## 5. Demo script

| Who | Do | Expect |
|-----|----|--------|
| employee (UI) | look at the dashboard | own profile, attendance, balances, requests; "Demo data" label |
| employee (UI) | "What is the annual leave policy?" | cited answer `[1] Annual Leave Policy — …` |
| employee (UI) | "What is the pet insurance policy?" | "could not be verified from the available sources" |
| employee (UI) | "How many employees are there?" | access declined, no number |
| employee (UI) | "Prepare a leave request for next Monday and Tuesday." | follow-up questions → draft → **Confirm** → reference LR-…, pending |
| manager (UI) | dashboard | the same pending request in the team pending list |
| manager (UI) | "Who was late today?" / "Summarize my dashboard" | team-only names; figures equal the dashboard |
| manager (API) | `POST /api/v1/auth/token`, then `GET /api/v1/metrics/headcount` | same team headcount as the UI |
| manager (API) | `GET /api/v1/metrics/payroll` | 403 `access_denied` |
| hr_admin (API) | `GET /api/v1/metrics/payroll?period=2026-09` | department totals only |
| any | wrong password ×6 (UI or API) | locked for 15 minutes |

## 6. Tests

```powershell
pytest -q            # everything offline: real SQLite temp DB, in-memory Qdrant, scripted model, FastAPI TestClient
pytest -q -m live    # real OpenAI (costs money)
```
