# Implementation Plan: HCM Lite AI HR Assistant

**Branch**: `001-hcm-hr-assistant` | **Date**: 2026-10-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-hcm-hr-assistant/spec.md`

## Summary

A Chainlit chat app in which a single OpenAI Agents SDK agent answers HR questions for three demo
personas. Policy answers come from a real RAG pipeline (ingest `.md/.txt/.pdf` → chunk → OpenAI
embeddings → Qdrant, embedded locally) with role-scoped retrieval and citations. Exact metrics
come from ten typed tools over labelled demo CSV exports read through a replaceable
`HRDataProvider`, with numbers computed in Python. Authorization is enforced in trusted code
before any data reaches the model. Leave requests produce reviewable drafts only. See
[research.md](./research.md) for decisions R-01…R-15.

## Technical Context

**Language/Version**: Python 3.12 (3.13 supported), `>=3.12,<3.14`
**Primary Dependencies**: openai-agents 0.24, chainlit 2.12, qdrant-client 1.20, pydantic 2.14,
pydantic-settings 2.16, python-dotenv 1.2, pypdf 6.21
**Storage**: Qdrant embedded (`.qdrant/`) for chunks and vectors; demo CSV exports in
`data/demo/records/`; ingestion registry `.ingest/registry.json`; no conversation persistence
**Testing**: pytest 9 + pytest-asyncio; offline by default (fake embedder, Qdrant `:memory:`,
scripted model); `-m live` for real OpenAI
**Target Platform**: Local workstation (Windows/macOS/Linux) and browser UI on localhost:8000
**Project Type**: Single project (Python package + Chainlit entry point)
**Performance Goals**: first visible feedback ≤ 2 s; 90% of answers ≤ 15 s (SC-007); ingest of
the demo corpus (< 20 docs) ≤ 60 s
**Constraints**: offline-runnable vector store; max 8 agent turns per message; model timeout 30 s;
tool timeout 10 s; ≤ 2 OpenAI retries; no PII or message text in logs
**Scale/Scope**: demo: ~10 policy documents, ~60 employees, 3 months of attendance, 3 personas,
a few concurrent users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|:------:|----------|
| **Stack (Art. II)** | ✅ | Python, openai-agents, Chainlit, Pydantic, python-dotenv, pytest; one vector store (Qdrant) — R-02, R-06 |
| **Spec-first (Art. III)** | ✅ | spec.md with acceptance criteria; Q1/Q2 recorded under Clarifications; no invented sources |
| **RAG core (Art. IV, VII, X)** | ✅ | Full pipeline R-08/R-09; `search_hr_documents` with citations; `found=false` → "cannot verify" |
| **No hardcoded HR DB (Art. IV.3)** | ✅ | Data in external labelled exports via `HRDataProvider` (R-10); none in code; demo label on files + UI |
| **Exact metrics (Art. IV.4, IX)** | ✅ | Tools 1–6 compute in Python from structured rows; the LLM only explains |
| **Separation (Art. VI, XI)** | ✅ (adjusted) | `hcm_lite/{assistant,tools,rag,services,models}`; `app.py` thin; runner UI-independent. `agents/` renamed `assistant/` — see Complexity Tracking |
| **Security (Art. XII)** | ✅ | `authz.require` before data; dual scope filter (R-06); untrusted-content wrapping (R-12); no secrets in code; sanitized errors (R-13) |
| **Leave safety (Art. VIII)** | ✅ | `prepare_leave_draft` only; `submitted: Literal[False]`; no submit tool |
| **Limits (Art. XI)** | ✅ | R-14; error taxonomy R-13 distinguishes retrieval/model/business failures |
| **Testing (Art. XV)** | ✅ | R-15 covers agent, RAG, workflow and UI test lists; live tests gated |
| **Runnable (Art. XIV, XVII)** | ✅ | `chainlit run app.py`, `pytest -q`, ingest CLI; quickstart; README task per milestone |

**Result**: PASS (pre-research) — PASS (post-design re-check, no new violations).

## Project Structure

### Documentation (this feature)

```text
specs/001-hcm-hr-assistant/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── agent-tools.md   # tool + runner contracts
│   ├── ingestion-cli.md
│   └── configuration.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/sp.tasks — not created here)
```

### Source Code (repository root)

```text
app.py                         # Chainlit adapter only: auth callback, starters, on_chat_start, on_message
chainlit.md                    # welcome screen with DEMO MODE banner + capabilities
.chainlit/config.toml          # app name "HCM Lite AI Assistant"
hcm_lite/
├── __init__.py
├── config.py                  # Settings (pydantic-settings), startup model check
├── assistant/                 # (constitution "agents/", renamed — R-04)
│   ├── hr_agent.py            # build_agent(settings) -> Agent[AppContext]
│   ├── instructions.py        # dynamic instructions (today, role, demo)
│   ├── guardrails.py          # input size guardrail, payroll-leak output guardrail
│   └── runner.py              # run_turn(), error mapping, citations extraction
├── tools/
│   ├── _common.py             # tool alias/decorator, ToolResult helpers, period parsing
│   ├── employee_tools.py      # get_headcount, search_employees
│   ├── attendance_tools.py    # get_attendance_summary, get_late_comers
│   ├── leave_tools.py         # get_leave_summary, get_my_leave_balance, prepare_leave_draft
│   ├── payroll_tools.py       # get_payroll_summary
│   ├── policy_tools.py        # search_hr_documents
│   └── dashboard_tools.py     # get_dashboard_summary
├── rag/
│   ├── loaders.py             # md/txt/pdf loaders, front-matter, validation
│   ├── chunking.py            # heading/page-aware chunking with overlap
│   ├── embeddings.py          # Embedder protocol; OpenAIEmbedder; batching
│   ├── vector_store.py        # QdrantStore: ensure_collection, upsert, delete_by_doc, search(filter)
│   ├── retriever.py           # Retriever: scope filter + threshold + post-filter
│   ├── citations.py           # Citation building/formatting
│   └── ingest.py              # pipeline + CLI (__main__)
├── services/
│   ├── errors.py              # error taxonomy
│   ├── authz.py               # Role→Permission/Scope matrix, require()
│   ├── data_provider.py       # HRDataProvider protocol + CsvHRDataProvider
│   ├── periods.py             # period resolution, working days
│   ├── summary_service.py     # dashboard composition
│   ├── smart_leave_service.py # draft validation
│   ├── policy_service.py      # retrieval → PolicySearchResult (untrusted wrapping)
│   └── personas.py            # demo persona loading + PBKDF2 verify
└── models/
    ├── domain.py              # Role, Permission, AccessScope, records, UserIdentity, AppContext
    ├── requests.py            # tool input models
    └── responses.py           # ToolResult + payloads, LeaveDraft, Citation

data/demo/
├── README.md                  # "DEMO DATA — fictional"
├── documents/policies/*.md    # ~8–10 labelled demo policies (+1 PDF), incl. an injection test doc
├── records/*.csv              # employees, attendance, leave_requests, leave_balances, payroll_summary
└── personas.json

tests/
├── conftest.py                # fake embedder, :memory: Qdrant, frozen clock, fixture data dir
├── fixtures/                  # small deterministic docs + CSVs
├── unit/                      # rag/, services/, tools/, config
├── integration/               # agent with scripted model, ingest→retrieve→tool, app handlers
└── live/                      # @pytest.mark.live

requirements.txt, requirements-dev.txt, pytest.ini, .env.example, .gitignore, README.md
```

**Structure Decision**: A single project with one importable package `hcm_lite` at the repository
root. The layers follow constitution Art. VI, with `agents/` → `assistant/` to avoid shadowing the
SDK's `agents` module. `reranker.py` is omitted until a measured need exists (Art. VII.3).

## Delivery Order (maps to constitution milestones; each leaves the app runnable)

1. **M1 Foundation** — config, personas/auth, Chainlit shell with demo banner and starters, agent
   with no tools, live smoke test of a real response.
2. **M2–M3 RAG + agentic RAG (US1, US6)** — loaders, chunking, embeddings, Qdrant store, ingest
   CLI, retriever with scope filtering, `search_hr_documents`, citations in the UI.
3. **M4 HR tools (US2, US3)** — data provider, authz, tools 1–7.
4. **M5 Workflows (US4, US5)** — leave draft service/tool, dashboard summary.
5. **M6 Security & reliability** — guardrails, injection fixtures, error mapping, limits,
   session isolation tests.
6. **M7 Demo** — README verified from a clean venv, full test run, limitations list.

## Risks (top 3)

1. **SDK API drift** (pre-1.0; the docs show both `tool` and `function_tool`). *Mitigation*: pin
   0.24.x; the first task is an import smoke test; a single alias in `tools/_common.py`.
2. **Retrieval threshold mis-calibration** causing false "cannot verify" or loose answers.
   *Mitigation*: a threshold-calibration test set (SC-004/005); the threshold is configurable.
3. **Model ignoring tool results or inventing numbers**. *Mitigation*: instructions plus the
   output guardrail; tests assert that numbers in final answers appear in tool outputs (live suite).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `agents/` folder renamed to `hcm_lite/assistant/` (Art. VI suggested layout) | The SDK is imported as top-level `agents`; a local `agents/` package shadows it | Keeping `agents/` breaks `from agents import Agent` depending on `sys.path` order |
| Three extra tools beyond the seven in Art. V (`search_hr_documents`, `prepare_leave_draft`, `get_dashboard_summary`) | Art. VIII/IX/X workflows need agent-callable entry points | Embedding policy search inside other tools would hide retrieval from the agent's decision (Milestone 3) |
