# HANDOFF: where work stopped and how to continue

**Last updated**: 2026-10-25 by ZCode (GLM-5.3) after the AI-first continuation sprint
**Branch**: `002-hcm-lite-ai-app`
**Feature**: `specs/002-hcm-lite-ai-app/` (HCM Lite with AI HR Assistant)

---

## 1. State at handoff (supersedes the older notes below)

**Done, ticked, and live-verified** (see PHR-010 in `history/prompts/002-hcm-lite-ai-app/`):
- Phase 1, Phase 2 (T001–T045 except manual T045), US1 (T046–T054), US2 core (T063, T065–T074),
  US3/US4 tools (T079, T082), US5 core (T099–T103), US6 core (T105/T107/T108), US7 CLI
  (T112/T113), US8 (T088–T092).
- **Owner decision (deadline):** new-code test files were skipped in favour of implementation
  ("don't use testing"); every piece was smoke-checked and pre-existing suites stayed green
  (`pytest -q` → **394 passed**). The unticked test-writing tasks remain for later.
- The demo works end-to-end: seeded DB (`data/hcm_lite.db`), indexed documents (47 chunks in
  `.qdrant/`), live policy answers with citations, tools, draft→Confirm→pending, FastAPI on
  :8001 (`/docs`).
- Demo passwords were printed by the last `seed` run and are NOT stored anywhere; re-run
  `python -m hcm_lite.db seed --reset` to regenerate (drops demo rows only).
- Project subagents/skills now also live in `.zcode/` (`hcm-implementer`, `hcm-reviewer`,
  `hcm-test-verifier`; skills `hcm-implement`, `hcm-review`, `hcm-test`) alongside `.claude/`.

**Remaining** (in priority order): test files for tasks marked done without them; manual
checks T045/T055/T076/T080/T083/T093/T104/T109/T114; T075 threshold calibration; T110/T111
registry-based incremental ingest (current re-ingest is clean delete+upsert); T115–T121
polish (access-attempt suite, logging tests, README run-through from clean clone, acceptance
checklist).



## 1. Read these first (in order)

1. `.specify/memory/constitution.md`: **v4.0.0, binding.** SQLite + SQLAlchemy 2 async + Alembic,
   FastAPI backend API, Chainlit UI, OpenAI Agents SDK, RAG with embedded Qdrant. AI is the
   primary deliverable; auth, DB and dashboards stay at a basic level (Art. II).
2. `specs/002-hcm-lite-ai-app/tasks.md`: **the source of truth for progress.** `[x]` means done
   and tested. Do tasks in order, respecting the dependency table at the bottom.
3. `specs/002-hcm-lite-ai-app/research.md`: decisions D-01…D-14, plus the **"Verification
   results"** sections (T007, Phase 2 batch A, batch B). These record real API findings from the
   installed packages and override any assumption.
4. `contracts/`: `api.md`, `agent-tools.md`, `services.md`, `ui.md`, `cli.md`,
   `configuration.md`; and `data-model.md`.
5. `CLAUDE.md`: project rules (PHR after every prompt, ADR suggestions), active technologies.

## 2. State at handoff

**Done and tested** (ticked in tasks.md): T001–T015, T019–T031, T034.
- Phase 1 setup: venv `.venv` (Python 3.12.3), deps installed, smoke test of every
  library assumption.
- Batch A: `hcm_lite/errors.py`, `config.py`, `logging_config.py`, `models/{domain,results,requests}.py`,
  `services/{passwords,periods,tokens}.py`.
- Batch B: `hcm_lite/db/{engine,tables,repositories,seed,__main__}.py`, `alembic.ini`,
  `hcm_lite/db/migrations/` (revision `0001`), tests in `tests/unit/db/`.
- Last verified full run (batch B): **262 passed** (`.venv\Scripts\python -m pytest -q`).

**In progress when the session ended**: one `hcm-implementer` subagent run covering, in this
order:
1. hardening fixes M1–M3, L1, L2, L4, L6 (see §5);
2. Phase 2 remainder T016–T018, T032, T033, T035–T043, and T044 (live);
3. US1 T046–T054;
4. US2 T056–T075.

**Its outcome is unknown at the time of writing.** To find out where it got to:
- check which of those tasks are ticked in `tasks.md`;
- check whether the files exist (e.g. `hcm_lite/services/auth_service.py`,
  `hcm_lite/assistant/runner.py`, `app.py`, `hcm_lite/rag/ingest.py`);
- run `.venv\Scripts\python -m pytest -q`.

A task with code but no tick is **not done**: finish it, test it, then tick it.

**Not started**: US3 (T077–T080), US4 (T081–T083), US8 FastAPI (T084–T093), US5 smart leave
(T094–T104), US6 (T105–T109), US7 (T110–T114), Polish (T115–T121). Manual checks T045, T055 and
T076 are also not done.

## 3. Environment

- `.env` exists and is **git-ignored**. It holds a working `OPENAI_API_KEY`,
  `OPENAI_MODEL=gpt-5.4-mini`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`, and generated
  `CHAINLIT_AUTH_SECRET` / `API_JWT_SECRET`. **Never print or commit these values.** The user was
  advised to rotate the key (it was pasted into chat); if live calls fail with an auth error,
  ask the user for a new key and put it in `.env` yourself.
- The database is SQLite at `data/hcm_lite.db` (git-ignored). No server is needed. MongoDB was
  dropped; do not reintroduce it.
- Windows + PowerShell. Always use `.venv\Scripts\python`.

## 4. Commands

```powershell
.venv\Scripts\python -m pytest -q                # offline suite (default excludes live)
.venv\Scripts\python -m pytest -q -m live        # real OpenAI (costs money; run when needed)
.venv\Scripts\alembic upgrade head               # create/upgrade the schema
.venv\Scripts\python -m hcm_lite.db seed         # demo data; prints fresh demo passwords once
.venv\Scripts\python -m hcm_lite.db status
.venv\Scripts\python -m hcm_lite.rag.ingest      # (US2) index data/demo/documents
.venv\Scripts\python -m uvicorn hcm_lite.api.main:app --port 8001   # UI + API at http://localhost:8001
# UI is hcm_lite/api/static/ served at "/"; Chainlit/app.py were removed in v4.1.0.
# DB is now Supabase Postgres (v4.2.0) via DATABASE_URL in .env; migrations at revision 0002.
# No demo seed/logins. On first run the site shows "Create admin"; admin then adds HR + employees
#   (Users tab); everyone can change their own password (Profile tab). Login is by EMAIL.
# To wipe users and start over, the admin deletes them in the Users tab (no re-seed).
```

## 5. Known open review items

From the Phase 1 and batch A reviews; check whether the in-progress run fixed them:
- **M1**: `logging_config` must only accept event-name messages and must validate the values of
  allowed fields (no f-string/exception text leaks).
- **M2**: `UserRecord.password_hash` must be `Field(repr=False)`.
- **M3**: `YYYY-MM` year 1900–2099 with `[0-9]`; an invalid period → `hcm_lite.errors.ValidationError`.
- **L5 (for US8)**: the API must always return a generic 401 body. Never expose the
  `InvalidToken` reason ("expired"/"revoked").
- **L7**: `LeaveDraft.submitted_reference` is set if and only if `status == "submitted"`.
- **L10–L13**: the `ValidationError.message` consistency, an idempotent `configure_logging`,
  `.gitignore` tool caches, and narrowing the leftover Chainlit upload limits.
- **F6**: production `RunConfig(tracing_disabled=True)`; note in the README that no telemetry is
  exported.

## 6. Key gotchas (already learned; don't rediscover)

- **Never create a top-level `agents/` package**: it shadows the openai-agents SDK. App code is
  in `hcm_lite/assistant/`.
- **Tools**:
  - The tool decorator is `agents.function_tool`.
  - Import `RunContextWrapper` at module level when using `from __future__ import annotations`.
  - The test fake model is `ScriptedModel(agents.Model)` implementing `get_response` and
    `stream_response`.
- **Qdrant 1.20**: use `query_points` (`search` was removed).
- **Chainlit**:
  - `ElementSidebar`, `Action(name, payload, label)`, `action_callback`, `set_starters(current_user, …)`
    and `on_logout(request, response)` all exist.
  - `on_logout` gets no user; decode the cookie with `chainlit.auth.get_token_from_cookies` +
    `decode_jwt`, best-effort.
  - `user_session_timeout` is an **absolute** lifetime; the app's own idle check is
    authoritative.
- **SQLite + aiosqlite**:
  - PRAGMAs are set in a sync `"connect"` listener; `isolation_level=None` plus a `"begin"`
    listener emits `BEGIN`, which fixes SAVEPOINT semantics.
  - Always `await dispose(engine)`; tests fail on leaked threads.
- **Repositories** take a caller-owned `AsyncSession` (the caller commits); `employee_ids` is a
  required keyword (`None` = all). Only `hcm_lite/db/` may import sqlalchemy.
- **Services** (and nothing else) do authorization: `authz.require` / `resolve_scope` before any
  repository call.
- **JWT**: `TokenService` (class) in `services/tokens.py`; HS256 pinned; claims exactly
  `sub, iat, exp, jti`.
- **Leave**:
  - No submit/approve/reject tool.
  - Submission only via the UI Confirm action or the API confirm endpoint, then
    `LeaveService.submit` → `LeaveRepo.insert_idempotent`.
- **Periods**:
  - `this_*` = period to date and `last_*` = full period.
  - Exception: leave summaries use the **full calendar month** for `this_month`.
- **Seed**: demo passwords are random per seed run and printed once. The README must say
  "printed by `python -m hcm_lite.db seed`" (not list them).
- `.specify/scripts/powershell/create-new-feature.ps1` line 267 breaks on PowerShell 5.1
  (3-argument Join-Path). It's harmless; create `history/prompts/<feature>/` manually.

## 7. How to continue (recommended workflow)

1. Run `pytest -q` and reconcile `tasks.md` ticks with reality (§2).
2. Continue from the first unticked task in `tasks.md`. The project skills automate this:
   - `/hcm-implement <task ids>` → `hcm-implementer` builds test-first; `hcm-test-verifier` and
     `hcm-reviewer` check the result.
   - `/hcm-test`: run the suites and log the results to `specs/002-hcm-lite-ai-app/checklists/demo-log.md`.
   - `/hcm-review`: a read-only constitution and security review.
3. Suggested order: finish Phase 2 → US1 → US2 (MVP) → US3 → US4 → US8 (FastAPI) → US5 → US6 →
   US7 → Polish (README, access-attempt suite, clean-environment run, acceptance checklist).
4. After each user prompt, write a PHR under `history/prompts/002-hcm-lite-ai-app/` (next ID:
   **010**). **Redact any secrets.**
5. Commit when a phase is green. Suggested first commit:
   `feat: constitution v4.0.0 (SQLite+Alembic, FastAPI) and Phase 1–2 foundation for 002`.
   End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 8. Definition of done (from the constitution, Art. XX)

The project is ready when, using the demo personas `employee`, `manager` and `hr_admin`:
- sign-in works;
- each role sees its dashboard;
- policy answers are cited, or say "could not be verified";
- figures match across the dashboard, the assistant and the API;
- leave drafts are confirmed explicitly and stored once as pending;
- `pytest -q` passes;
- the README run-through works from a clean clone.

Track the evidence in `specs/002-hcm-lite-ai-app/checklists/acceptance.md` (T121).
