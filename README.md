# HCM Lite — Human Capital Management with an AI HR Assistant

A lightweight HCM application with an **Agentic AI HR assistant** built on the OpenAI Agents
SDK: role dashboards, cited policy answers over RAG, exact HR figures from tools, smart leave
drafting with explicit confirmation, and a REST API — all sharing one service layer, one
authentication system and one SQLite database.

All data is **fictional demo data**, clearly labelled (`is_demo = 1`, "DEMO — fictional").

## Quickstart

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

copy .env.example .env
# Edit .env: set OPENAI_API_KEY. Generate the API secret (>= 32 chars):
#   python -c "import secrets; print(secrets.token_urlsafe(48))"   # API_JWT_SECRET

.venv\Scripts\alembic upgrade head                # create the SQLite schema (data/hcm_lite.db)
.venv\Scripts\python -m hcm_lite.db seed          # demo data; PRINTS demo passwords ONCE
.venv\Scripts\python -m hcm_lite.rag.ingest ingest  # index the demo HR documents (real embeddings)

# UI + API are one app. First startup takes ~10-15s (embedded Qdrant init).
.venv\Scripts\uvicorn hcm_lite.api.main:app --port 8001
# UI  → http://localhost:8001/
# API → http://localhost:8001/docs
```

Demo sign-in users (created by `seed`; passwords are random per seed run and **printed by
`python -m hcm_lite.db seed`** — they are not stored anywhere in the repo):

| Username | Role | Scope |
|----------|------|-------|
| `employee` | employee | own data only |
| `manager` | manager | own data + direct reports |
| `hr_admin` | hr_admin | whole organisation, payroll aggregates |

## What the assistant can do

- **Policy Q&A (RAG)**: answers grounded in the indexed HR documents with `[n] Title — Section`
  citations; when nothing verifies, it says the answer "could not be verified from the
  available sources". Document access scopes (`all_employees` / `managers` / `hr_admin`) are
  enforced in the vector query **and** re-checked in code — an employee can never be cited an
  HR-only document. Retrieved passages are wrapped as untrusted data, never instructions.
- **Exact figures** (never from the model): headcount, attendance summary, late comers, leave
  summary, payroll aggregates (HR only), employee search (manager/HR), own leave balance.
- **Smart leave**: drafts a leave request (dates → working days excluding weekends/holidays,
  overlap + balance checks, policy citations), then the user presses **Confirm** — the only
  submission path. There is deliberately **no submit/approve/reject tool**.
- **Dashboard summary**: summarizes the signed-in user's own dashboard figures.

## The 10 agent tools

`get_headcount`, `get_attendance_summary`, `get_late_comers`, `get_leave_summary`,
`get_my_leave_balance`, `get_payroll_summary`, `search_employees`, `search_hr_documents`,
`prepare_leave_draft`, `get_dashboard_summary`. No tool takes a user id, employee id or role —
identity comes only from the authenticated session (JWT carries only `sub`; the role is
reloaded from the database on every turn and every API request).

## REST API (`/api/v1`, OpenAPI at `/docs`)

`POST /auth/token` (OAuth2 password flow), `POST /auth/logout`, `GET /health` (no auth),
`GET /me`, `GET /me/profile`, `GET /dashboard`, `GET /metrics/{headcount|attendance|late-comers|leave|payroll}`,
`GET /employees`, `GET /leave/{balance|requests}`, `POST /policies/search`,
`POST /assistant/conversations`, `POST /assistant/conversations/{cid}/messages`,
`POST /assistant/conversations/{cid}/drafts/{draft_id}/confirm`,
`DELETE /assistant/conversations/{cid}/drafts/{draft_id}`.
Every route except `/health` and `/auth/token` requires a bearer JWT. No endpoint approves,
rejects or edits records.

## Tests

```powershell
.venv\Scripts\python -m pytest -q           # offline suite (real SQLite, mocked model)
.venv\Scripts\python -m pytest -q -m live   # real OpenAI calls (costs money)
```

## Architecture

```
SPA (hcm_lite/api/static)   FastAPI (hcm_lite/api :8001)   agent tools
        └──────────────────────┬──────────────────────────┘
                        hcm_lite/services  (authorization + business rules)
                               └────────── hcm_lite/db/repositories.py (SQLAlchemy async)
                                             └── SQLite (Alembic migrations)
hcm_lite/rag (loaders → chunking → embeddings → Qdrant vector store → retriever)
hcm_lite/assistant (instructions, tools, guardrails, runner, agent)
```

- Dashboard, API and tools call the **same service methods**, so figures always agree.
- Authorization (`hcm_lite/services/authz.py`) runs in the service layer before any query.
- Audit events (login, lockout, logout, access denials, leave submissions) never contain
  passwords, message text, document text or employee names. Tracing is disabled — no telemetry
  leaves the machine.

## Document library (US7)

```powershell
.venv\Scripts\python -m hcm_lite.rag.ingest ingest    # index new/changed documents
.venv\Scripts\python -m hcm_lite.rag.ingest rebuild   # drop + full re-index
.venv\Scripts\python -m hcm_lite.rag.ingest clear --force
.venv\Scripts\python -m hcm_lite.rag.ingest status [--json]
```

Documents live in `data/demo/documents/policies/` (Markdown with flat YAML front-matter
`title/version/doc_type/access_scope/demo`, plus PDF). Missing `access_scope` → `restricted`
(only HR admins ever see restricted documents; effectively hidden from answers).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| UI slow / blank on first load | first startup initializes embedded Qdrant (~10-15s); wait for `Application startup complete.` then reload |
| "Database schema is out of date" | `.venv\Scripts\alembic upgrade head` |
| `database is locked` | another process holds SQLite; close other app instances |
| Missing key error at startup | set `OPENAI_API_KEY` in `.env` |
| Model unavailable / auth error | check the key and `OPENAI_MODEL`; the app fails fast at startup |
| Empty policy answers | run `python -m hcm_lite.rag.ingest ingest` (see the welcome note) |
| Embedding dimension mismatch | `python -m hcm_lite.rag.ingest rebuild` after changing `OPENAI_EMBEDDING_MODEL` |
| Account locked | 5 wrong passwords lock for `LOGIN_LOCK_MINUTES` (default 15) |
| Port already in use | run uvicorn with a different `--port` |

## Limitations

No leave approval workflow (requests stay `pending`); basic auth only (no SSO/MFA/reset);
the JWT deny-list and API conversations are in-memory; SQLite is single-writer; English only;
no voice/brief support.
