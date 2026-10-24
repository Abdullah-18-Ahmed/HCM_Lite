# Quickstart: HCM Lite AI HR Assistant

> **Status**: this is the target flow from the design. These commands become verified only when
> implementation tasks complete (Art. XIV). The README is the final verified version.

## 1. Environment (Windows PowerShell shown; bash equivalents in README)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## 2. Configure

```powershell
Copy-Item .env.example .env
chainlit create-secret        # paste the value into CHAINLIT_AUTH_SECRET in .env
# set OPENAI_API_KEY, OPENAI_MODEL, OPENAI_EMBEDDING_MODEL in .env
```

No vector-store service is needed: Qdrant runs embedded and stores data in `.qdrant/`. To use a
Qdrant server instead, set `VECTOR_STORE_URL` (and `VECTOR_STORE_API_KEY` if secured).

## 3. Build the knowledge index (demo documents)

```powershell
python -m hcm_lite.rag.ingest            # incremental ingest of data/demo/documents
python -m hcm_lite.rag.ingest status     # shows point count and last report
```

## 4. Run

```powershell
chainlit run app.py
```

Open http://localhost:8000 and sign in with a demo persona (demo-only credentials, listed in the
README): `employee` / `hr_manager` / `hr_admin`.

## 5. Demo script (validates acceptance criteria)

| Persona | Prompt | Expect |
|---------|--------|--------|
| employee | What is the annual leave policy? | Answer with a `[1] Annual Leave Policy — …` source |
| employee | What is the pet insurance policy? | "could not be verified from the available sources" |
| employee | What is my remaining annual leave balance? | Exact balance, source `demo-export:leave_balances.csv` |
| employee | How many employees are in the organization? | Access-denied explanation, no number |
| employee | Prepare a leave request for next Monday and Tuesday. | Follow-up asking for leave type and reason, then a draft with dates; not submitted |
| hr_manager | Summarize attendance for this month. | Exact figures + period |
| hr_manager | Summarize the current HR dashboard. | Summary with "payroll withheld" |
| hr_admin | What is the payroll summary for last month? | Aggregates only |

## 6. Tests

```powershell
pytest -q                 # offline unit + integration tests (no API key needed)
pytest -q -m live         # optional: real OpenAI + embeddings (needs .env)
```

## 7. Index maintenance

- Edit or add files in `data/demo/documents/`, then run `python -m hcm_lite.rag.ingest`.
- Full rebuild: `python -m hcm_lite.rag.ingest rebuild`.
- Reset dev index: `python -m hcm_lite.rag.ingest clear --yes`.
- Ingestion errors: see `.ingest/last_report.json`.
