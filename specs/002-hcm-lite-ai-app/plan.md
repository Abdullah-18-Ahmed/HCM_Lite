# Implementation Plan: HCM Lite with AI HR Assistant

**Branch**: `002-hcm-lite-ai-app` | **Date**: 2026-10-25 (revised for constitution v4.0.0) | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-hcm-lite-ai-app/spec.md`

## Summary

A Chainlit UI with basic sign-in, a basic per-role dashboard and an OpenAI Agents SDK assistant
on the same screen. Alongside it runs a FastAPI REST API exposing the same capabilities to other
clients. Users, HR records and audit events live in **SQLite** through SQLAlchemy 2 (async,
aiosqlite) with **Alembic** migrations, CHECK/UNIQUE/FK constraints, and a labelled demo seed. A
single service layer enforces Employee / Manager (team) / HR Admin scoping and is the only data
path for the dashboard, the API routes and the agent's 10 tools, so the figures are identical
everywhere. Policy answers use RAG (embedded Qdrant + OpenAI embeddings) with role-filtered
retrieval and citations. Leave drafts are submitted only through an explicit confirmation outside
the model (Chainlit Confirm button or the API confirm endpoint), stored once as *pending*. Effort
is weighted to the AI subsystem (constitution Art. II). Decisions: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.12 (>=3.12,<3.14)
**Primary Dependencies**: openai-agents 0.24, chainlit 2.12, fastapi 0.162, uvicorn 0.54, sqlalchemy 2.1 (asyncio), aiosqlite 0.22, alembic 1.20, pyjwt 2.15, qdrant-client 1.20, pydantic 2.14, pydantic-settings 2.16, python-dotenv 1.2, pypdf 6.21
**Storage**: SQLite file `data/hcm_lite.db` (HR data, users, audit; Alembic-managed); embedded Qdrant `.qdrant/` (document vectors); chat sessions and API conversations in process memory
**Testing**: pytest 9 + pytest-asyncio + httpx (FastAPI TestClient); everything offline by default against real temporary SQLite DBs; `-m live` for real OpenAI
**Target Platform**: Local workstation (Windows/macOS/Linux); UI on localhost:8000, API on localhost:8001
**Project Type**: Single project (Python package + Chainlit entry point + FastAPI app)
**Performance Goals**: dashboard ≤ 3 s after sign-in; API data endpoints ≤ 500 ms p95 on demo data; first assistant feedback ≤ 2 s; 90% of answers ≤ 15 s
**Constraints**: max 8 agent turns per message; model timeout 30 s; tool timeout 10 s; ≤ 2 OpenAI retries; no PII or conversation text in logs; SQLite single-writer (WAL mode, short transactions)
**Scale/Scope**: demo: ~60 employees, 6 departments, ~3 months of attendance, ~10 policy documents, 3 demo accounts, a few concurrent users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (v4.0.0)

| Gate | Pre | Post | Evidence |
|------|:---:|:----:|----------|
| Authority (Art. I, I.1) | ✅ | ✅ | No brief exists; Art. I.1 applies; owner decisions recorded in spec Clarifications and Art. III.4 |
| Technology (Art. III.1, III.4) | ✅ | ✅ | SQLite + SQLAlchemy + Alembic, FastAPI, Chainlit, Agents SDK, RAG, pytest, exactly as adopted |
| UI decision (Art. III.2–3, XIII) | ✅ | ✅ | Rule 5 → Chainlit UI; FastAPI API; both call the same services and the same `AuthService` over one `users` table (one auth system, two entry points) |
| Spec-first (Art. IV) | ✅ | ✅ | spec.md incl. FR-039–041 for the API; one combined spec (Complexity Tracking) |
| Architecture (Art. V, XIV) | ✅ | ✅ | UI / API routes / tools → services → repositories → SQLite; API contract in contracts/api.md with schemas, errors and status codes |
| Agent & tools (Art. VI, VII) | ✅ | ✅ | 10 tools → one service call each; no submit tool; success only after a DB-confirmed insert |
| Auth & RBAC (Art. VIII) | ✅ | ✅ | PBKDF2; lockout 5/15 min in `login_failures`; chat idle expiry 60 min; JWT with only `sub`, 60 min, revocable; role reloaded per request |
| Persistence (Art. IX, IX.1) | ✅ | ✅ | Alembic `0001_initial` with PK/FK/UNIQUE/CHECK; `foreign_keys=ON`; no `create_all()` outside tests; guarded seed; repositories only |
| Dashboards (Art. X) | ✅ | ✅ | DashboardService composes the same MetricsService used by tools and API |
| RAG (Art. XI) | ✅ | ✅ | Metadata (incl. department) + access classification; dual scope filtering; threshold → "not found"; citations |
| Leave (Art. XII) | ✅ | ✅ | Draft → explicit confirm (UI action or API confirm endpoint) → `LeaveService.submit` (idempotent, audited, pending); no approve/reject anywhere |
| Secrets (Art. XV) | ✅ | ✅ | `DATABASE_URL`, `API_JWT_SECRET`, `CHAINLIT_AUTH_SECRET` via env; fail-fast with masked values |
| Security (Art. XVI) | ✅ | ✅ | Least privilege; audit with channel; sanitized errors; untrusted-content wrapping; payroll and instructions-leak guardrails |
| Testing (Art. XVII) | ✅ | ✅ | Real-SQLite repository and migration tests; API TestClient tests; offline agent tests; live tests; final real demo |
| Done (Art. XX) | ✅ | ✅ | Quickstart demo (UI + API); README; demo log |

**Result**: PASS (constitution v4.0.0). No unjustified violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-hcm-lite-ai-app/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/ (api.md, agent-tools.md, services.md, ui.md, cli.md, configuration.md)
├── checklists/ (requirements.md, demo-log.md)
└── tasks.md
```

### Source Code (repository root)

```text
app.py                          # Chainlit wiring only (contracts/ui.md)
chainlit.md, .chainlit/config.toml
alembic.ini                     # no URL inside; env.py reads get_settings()
hcm_lite/
├── config.py                   # Settings, startup checks (models, DB at head)
├── errors.py, logging_config.py
├── models/  (domain.py, results.py, requests.py)
├── db/
│   ├── engine.py               # async engine + session factory, PRAGMA foreign_keys/WAL
│   ├── tables.py               # SQLAlchemy ORM models (declarative)
│   ├── repositories.py         # repository classes (SQL here only)
│   ├── migrations/             # Alembic env.py + versions/0001_initial.py
│   ├── seed.py
│   └── __main__.py             # CLI: status | seed | create-user
├── services/  (authz, passwords, auth_service, tokens, periods, metrics_service,
│               leave_service, policy_service, dashboard_service, audit)
├── rag/  (loaders, chunking, embeddings, vector_store, retriever, citations, ingest)
├── assistant/                  # NOT "agents/" (SDK name collision)
│   ├── context.py              # AppContext, AppSession, DraftStore protocol
│   ├── instructions.py, guardrails.py, hr_agent.py, tools.py, runner.py
├── api/
│   ├── main.py                 # FastAPI app, exception handlers, correlation-id middleware
│   ├── deps.py                 # current_user (JWT → AuthService.load_user), services
│   ├── conversations.py        # ApiConversation store (in-memory, TTL)
│   └── routes/  (auth.py, dashboard.py, metrics.py, leave.py, policies.py, assistant.py, health.py)
└── ui/render.py                # dashboard / draft / sources → markdown

data/demo/documents/policies/   # labelled demo policies
tests/
├── conftest.py                 # temp SQLite (alembic upgrade), frozen clock, contexts, scripted model, hashing embedder, API client
├── unit/  (services/, rag/, assistant/, db/, ui/, api/)
├── integration/                # agent + services + RAG; app handlers; API end-to-end
└── live/                       # -m live
requirements.txt, requirements-dev.txt, pytest.ini, .env.example, .gitignore, README.md
```

**Structure Decision**: One package `hcm_lite` with three thin entry points (`app.py` for
Chainlit, `hcm_lite/api/main.py` for FastAPI, and the CLIs). They share one service layer. Art. V
layers map to `app.py` + `ui/` + `api/` (presentation/API), `services/auth_service.py` +
`services/tokens.py` (auth), `services/` (business), `db/` (database), `rag/`, `assistant/`,
`services/authz.py` (tool and route authorization), and `services/audit.py` + `logging_config.py`
(audit/observability).

## Delivery Order (constitution Art. XVIII; each stage stays runnable)

1. **Foundation**: config, errors, engine, ORM tables, Alembic `0001`, repositories, seed, auth
   service, authz, Chainlit login, an agent with no tools (real reply).
2. **Basic dashboards (US1)**: metrics, leave (balance/requests) and dashboard services; sidebar.
3. **AI core (US2)**: RAG pipeline + `search_hr_documents` + citations (MVP).
4. **AI figures (US3, US4)**: tools 1–7.
5. **API (US8)**: FastAPI app, token auth, data routes, `/policies/search`, assistant
   conversations, error mapping, parity tests.
6. **Smart leave (US5)**: draft tool, Confirm/Cancel (UI) and confirm endpoint (API), idempotent
   submit.
7. **AI summary (US6) + refresh (US7)**.
8. **Hardening + demo**: guardrails, access-attempt suite (UI + API), logging review, README,
   clean-environment run.

## Risks

1. **Unverified API details** (Chainlit sidebar/actions/logout hooks, the SDK tool decorator
   name). *Mitigation*: T007 smoke test with fallbacks.
2. **SQLite concurrency** (Chainlit and uvicorn are two processes writing one file).
   *Mitigation*: WAL mode, `busy_timeout=5000`, short transactions, a unique idempotency key;
   PostgreSQL via `DATABASE_URL` if needed later.
3. **Model invents or leaks numbers**. *Mitigation*: tools are the only data path; instructions;
   output guardrails; parity tests between tools, dashboard and API (SC-003, SC-011).

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| One combined spec instead of Art. IV's 14 spec files | Owner wants basic auth/DB/dashboard with AI focus; one spec keeps them consistent | 14 files for a basic-level app would be mostly duplication; Art. IV says "where applicable" |
| Package `hcm_lite/assistant/` instead of `agents/` | A local `agents/` shadows the SDK module `agents` | Keeping `agents/` breaks SDK imports |
| Two processes (Chainlit :8000, FastAPI :8001) | Chainlit owns its server; FastAPI is the requested backend API | Mounting Chainlit inside FastAPI was offered and not chosen by the owner |
| Leave drafts and API conversations in process memory | Drafts are unconfirmed, per-conversation proposals | Persisting them adds cleanup logic with no requirement for it |
