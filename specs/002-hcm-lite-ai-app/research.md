# Phase 0 Research: HCM Lite with AI HR Assistant

**Feature**: `002-hcm-lite-ai-app` | **Date**: 2026-10-25 (revised for constitution v4.0.0)
**Sources**: PyPI (`pip index versions`, 2026-10-25); official docs fetched earlier this session
for openai-agents-python, Chainlit and qdrant-client; and the **installed-package introspection
results in "Verification results (T007)"** at the end of this file, which supersede any
earlier assumption.

---

## D-01 Interface (constitution Art. III.2, III.4)

- **Decision**: **Chainlit** is the chat and dashboard UI (Art. III.2 rule 5: there is no
  frontend, no brief, and the spec needs the assistant on the dashboard screen). **FastAPI** is
  the backend REST API (owner decision; contracts/api.md).
- **One auth system, two entry points**: Chainlit's `@cl.password_auth_callback` and FastAPI's
  `POST /api/v1/auth/token` both call `AuthService.authenticate` over the same `users` table, with
  the same lockout and audit (Art. XIII).
- **Dashboard** in `cl.ElementSidebar` (confirmed present, T007), refreshed by an action button.
- **Rejected**: mounting Chainlit inside FastAPI (offered, not chosen); a React frontend (Art. II
  basic level).
- **Reversible**: all logic lives in `services/` and `assistant/`; a future frontend uses the API.

## D-02 Database: SQLite via SQLAlchemy 2 async (Art. III.4, IX.1)

- **Decision**: SQLite file `data/hcm_lite.db`. SQLAlchemy 2.1 ORM (declarative models in
  `db/tables.py`) with `create_async_engine("sqlite+aiosqlite:///…")` and
  `async_sessionmaker(expire_on_commit=False)`. A sync `"connect"` listener sets
  `PRAGMA foreign_keys=ON`, `journal_mode=WAL` and `busy_timeout=5000` (verified, T007).
- **Startup check**: open the DB and compare `alembic current` with head; if not at head, stop
  with "Database schema is out of date — run `alembic upgrade head`".
- **Concurrency**: Chainlit and uvicorn are two processes on one file. WAL plus busy_timeout plus
  short transactions is sufficient for demo load; `DATABASE_URL` allows PostgreSQL later
  (asyncpg), with no repository changes beyond dialect-neutral SQL.
- **Rejected**: MongoDB (owner dropped it, no server reachable); sync SQLAlchemy in threads
  (blocks the event loop in Chainlit and FastAPI).

## D-03 Schema control and migrations (Art. IX.1.2–3)

- **Decision**: **Alembic** with the `async` env template. `hcm_lite/db/migrations/env.py` reads
  the URL from `get_settings()` (none in `alembic.ini`), and `target_metadata = Base.metadata`.
  Revision `0001_initial` creates every table with PK, FK, NOT NULL, UNIQUE and CHECK constraints
  per data-model.md. It is hand-reviewed after `alembic revision --autogenerate`, because CHECK
  constraints are kept explicit.
- `alembic check` in tests asserts the models and migrations don't drift.
- Application code never calls `Base.metadata.create_all()`. Tests also use `alembic upgrade
  head` on a temp DB, so the migrations themselves are tested.

## D-04 Repository and service layering (Art. V, VII, IX.1.4, X, XIV)

- `hcm_lite/db/repositories.py`: async repository classes (`UserRepo`, `EmployeeRepo`,
  `AttendanceRepo`, `LeaveRepo`, `PayrollRepo`, `HolidayRepo`, `AuditRepo`). All SQL lives here.
  Methods take explicit `employee_ids` filters and return Pydantic models; there is no
  authorization logic in them.
- `hcm_lite/services/*` holds authorization, scoping, validation and calculations.
- **Three consumers, one path**: Chainlit (`app.py`), FastAPI routes (`hcm_lite/api/routes`) and
  agent tools call **services only** (FR-012, FR-040).
- Calculations: `COUNT`, `SUM` and `GROUP BY` in SQL; rates and working days in Python
  (Art. IX.1.5).
- `LeaveRepo.insert_idempotent(record) -> (record, created)` catches `IntegrityError` on the
  `idempotency_key` UNIQUE constraint, then selects and returns the existing row. Other integrity
  errors map to `ValidationError`.

## D-05 Authentication (Art. VIII, FR-001–004, FR-039–041)

- **Passwords**: stdlib `hashlib.pbkdf2_hmac("sha256", …, 600_000)`, verified with
  `hmac.compare_digest`; a dummy hash for unknown usernames (timing parity).
- **Lockout**: the `login_failures` table. After `LOGIN_MAX_FAILURES` (5) failures within
  `LOGIN_LOCK_MINUTES` (15), set `users.locked_until`. The same rules apply on both channels, and
  the audit records the `channel`.
- **Chainlit session**: `[project] user_session_timeout = 3600` is an **absolute** lifetime
  (T007). The app-level idle check (`SESSION_IDLE_MINUTES`) in `on_message` and in the action
  callbacks is authoritative for FR-003. Logout is audited via `cl.on_logout` plus a cookie decode
  (T007; best-effort, never raises).
- **API tokens** (`services/tokens.py`): PyJWT HS256 with `API_JWT_SECRET`, which `config.py`
  requires to be ≥ 32 chars, since PyJWT only warns (T007). Claims are `sub, iat, exp, jti`, with
  no role; the lifetime is `API_TOKEN_MINUTES` (60). `algorithms=["HS256"]` is always pinned.
  Logout puts the `jti` on an in-memory deny-list until `exp` (one API process; noted in the
  README limitations). Each request reloads the user (`AuthService.load_user`), so deactivation and
  role changes apply immediately.

## D-06 Authorization and scoping (Art. VIII, FR-004–006)

`resolve_scope(user)`: employee → {self}; manager → {self} ∪ direct reports (queried per
request); hr_admin → all.

| Capability | Employee | Manager | HR Admin |
|------------|:-------:|:-------:|:-------:|
| own profile, own attendance, own leave requests, own balance | ✓ | ✓ | ✓ |
| leave draft + confirm submission (self) | ✓ | ✓ | ✓ |
| headcount / attendance / late comers / leave summary | – | team | all |
| employee search | – | team | all |
| pending leave list | – | team | all |
| payroll totals (department/month aggregates) | – | – | ✓ |
| documents: `all_employees` / `managers` / `hr_admin` | ✓ / – / – | ✓ / ✓ / – | ✓ / ✓ / ✓ |
| documents: `restricted` | – | – | – |

Every service method calls `authz.require` / `resolve_scope` before any repository call; a
denial raises `AccessDenied`, which is audited and maps to 403 in the API.

## D-07 Agent orchestration (Agents SDK)

One `Agent[AppContext]` with 10 tools decorated with **`agents.function_tool`** (T007), with
`RunContextWrapper` imported at module level. Runs use
`Runner.run_streamed(..., context=ctx, max_turns=8)`, with `ModelSettings(timeout=…)`. The app
package is `hcm_lite/`, with `assistant/`, never `agents/`. The same `run_turn` serves Chainlit
and `POST /assistant/conversations/{cid}/messages`.

## D-08 Smart leave confirmation (Art. XII, FR-028–032)

`prepare_leave_draft` stores the draft in a `DraftStore` (Chainlit `AppSession` or API
`ApiConversation`). Submission happens only through an explicit confirmation **outside the model**:
the Chainlit `confirm_leave` action, or the API confirm endpoint. Both call
`LeaveService.submit(user, store, draft_id)`, which re-validates, then
`insert_idempotent(idempotency_key=draft_id)`, and audits only on the first insert. There is no
submit tool, and no approve/reject anywhere.

## D-09 RAG

Embedded Qdrant (`QdrantClient(path=".qdrant")`), or server mode via `VECTOR_STORE_URL`;
`:memory:` in tests. Search uses **`query_points`** (`search` was removed in 1.20, T007).
`OPENAI_EMBEDDING_MODEL`. Formats `.md/.txt/.pdf`; front-matter metadata incl. optional
`department`; `access_scope` defaults to `restricted`. Chunks 800/120; SHA-256 change detection;
uuid5 ids. Scope filtering happens twice: a `MatchAny` filter (verified working in `:memory:`) and
a code re-check in `Retriever`. Threshold 0.35 (calibrated in a live test). Passages are wrapped
as `<<<UNTRUSTED_DOCUMENT n>>>`.

## D-10 Testing strategy (Art. XVII, IX.1.7)

- **Default `pytest -q` (offline)** includes:
  - real SQLite: a session-scoped temp DB migrated with `alembic upgrade head`, with each test in
    a transaction rolled back (or a fresh DB per module for migration tests);
  - FastAPI `TestClient`;
  - a hashing embedder plus Qdrant `:memory:`;
  - `ScriptedModel(agents.Model)` (verified to work with `run_streamed`, T007);
  - a frozen clock.
- There are no fake repositories: SQLite makes the real repositories cheap to test, which removes
  fake-vs-real drift.
- **`-m live`**: real OpenAI model and embeddings.
- **Parity tests**: tool output == dashboard section == API response for the same user (SC-003,
  SC-011).
- **Final demo**: the configured SQLite file plus real OpenAI and Qdrant.

## D-11 Error taxonomy, audit, logging

- Errors: `ConfigurationError`, `DatabaseError`, `RetrievalError`, `ModelServiceError`,
  `AccessDenied`, `ValidationError`, `NotFound`, `InvalidToken`, mapped to runner categories
  (contracts/agent-tools.md) and to HTTP statuses (contracts/api.md).
- `audit_events` table: `login_success`, `login_failed`, `account_locked`, `logout`,
  `session_expired`, `access_denied`, `leave_submitted`, plus `channel` and `correlation_id`.
  There is no message or document text.
- Logging: the stdlib with an allow-list filter. FastAPI middleware sets `X-Correlation-ID`.
  Chainlit's spontaneous file upload is **disabled** in `.chainlit/config.toml`, since no feature
  needs it (least privilege, Art. XVI).

## D-12 Dependencies (installed and verified, T007)

| Package | Version | Pin |
|---------|---------|-----|
| openai-agents | 0.24.0 | `>=0.24,<0.25` |
| chainlit | 2.12.0 | `>=2.12,<3` |
| fastapi | 0.162.0 | `>=0.162,<0.163` |
| uvicorn[standard] | 0.54.0 | `>=0.54,<0.55` |
| sqlalchemy[asyncio] | 2.1.6 | `>=2.1,<2.2` |
| aiosqlite | 0.22.1 | `>=0.22,<0.23` |
| alembic | 1.20.1 | `>=1.20,<1.21` |
| pyjwt | 2.15.1 | `>=2.15,<3` |
| qdrant-client | 1.20.0 | `>=1.20,<2` |
| pydantic / pydantic-settings | 2.14.1 / 2.16.1 | `>=2.14,<3` / `>=2.16,<3` |
| python-dotenv | 1.2.4 | `>=1.2,<2` |
| pypdf | 6.21.2 | `>=6.21,<7` |
| tzdata | 2026.5 (IANA 2026e) | `>=2026.5` (added in Phase 2 batch B: IANA database for `zoneinfo` on Windows, so `APP_TIMEZONE` accepts any IANA zone) |
| dev: pytest / pytest-asyncio / httpx | 9.1.1 / 1.4.0 / 0.28.1 | `>=9.1,<10` / `>=1.4,<2` / `>=0.28,<0.29` |

Python 3.12.3. pymongo is uninstalled and must not be imported.

## D-13 Demo data seed (FR-010, Art. IX.1.6)

`python -m hcm_lite.db seed` (requires the DB at head) uses a seeded RNG to produce:
- 6 departments and ~60 employees with a manager hierarchy;
- weekday attendance from 2026-08-01 **through today if today is a weekday, else the last working
  day** (fixes analysis U4);
- balances, mixed leave requests and payroll_totals for Aug–Oct 2026;
- holidays;
- 3 demo users (`employee`→E1001 managed by M1002, `manager`→M1002, `hr_admin`→H1003).

All rows have `is_demo = 1`. Seeding refuses when non-demo rows exist unless `--force`;
`--reset` deletes demo rows only. The demo passwords are printed and listed in the README as
demo-only.

## D-14 FastAPI application (contracts/api.md)

- `hcm_lite/api/main.py`: the `FastAPI(title="HCM Lite API", version="1.0.0")` app, with a
  lifespan that builds services once and disposes the engine. Exception handlers map service
  errors to the status table, with 500s returning only `correlation_id`. There is correlation-id
  middleware, and CORS is off unless `API_CORS_ORIGINS` is set.
- `deps.py`: `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")` → `tokens.verify` →
  `AuthService.load_user` → `AuthenticatedUser`, with services from `app.state`.
- `conversations.py`: an in-memory `ApiConversation` store keyed by `(user_id, cid)`, with TTL
  `SESSION_IDLE_MINUTES`. Another user's cid → 404.
- Routes are thin: validate with the `models/requests.py` models, call one service, return its
  model; they don't import `sqlalchemy`.
- Tests: `TestClient(app)` with the temp DB and a scripted model injected through dependency
  overrides.

---

## Verification results (T007)

**Date**: 2026-10-25. **Method**: introspection of the packages installed in `.venv` (no web),
asserted by `tests/unit/test_api_smoke.py` (22 tests, all passing offline). Updated for the
constitution v4.0.0 switch to SQLite + FastAPI: pymongo was uninstalled and its MongoDB checks
removed.
**Resolved versions**: openai-agents 0.24.0, openai 3.37.0, chainlit 2.12.0, fastapi 0.162.0,
uvicorn 0.54.0, sqlalchemy 2.1.6, aiosqlite 0.22.1, alembic 1.20.1, pyjwt 2.15.1,
qdrant-client 1.20.0, pydantic 2.14.1, pydantic-settings 2.16.1, python-dotenv 1.2.4,
pypdf 6.21.2, pytest 9.1.1, pytest-asyncio 1.4.0, httpx 0.28.1 (full list in
`checklists/demo-log.md`).

| Item (source) | Finding | Consequence |
|---------------|---------|-------------|
| Tool decorator (D-07) | `agents.function_tool` exists. `agents.decorators.tool` is the **same object**. Top-level `agents.tool` is a **module**, not a decorator. Signature includes `timeout`, `timeout_behavior` (default `"error_as_result"`), `failure_error_function`, `strict_mode` | T037 `hr_tool` wraps `agents.function_tool` |
| Tool annotations (D-07) | With `from __future__ import annotations`, the SDK resolves tool parameter annotations through the defining module's globals; a `RunContextWrapper` imported inside a function raises `NameError` at decoration time. The context parameter is excluded from `params_json_schema` | `tools.py` imports `RunContextWrapper` at module level |
| Other SDK names (D-07, D-11) | Importable: `Agent, Runner, RunContextWrapper, MaxTurnsExceeded, ModelSettings, input_guardrail, output_guardrail, GuardrailFunctionOutput, ModelTimeoutError, ToolTimeoutError, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered, ModelBehaviorError, UserError, RunConfig, RunResultStreaming`. `ModelSettings` has a `timeout` field. `Runner.run_streamed(starting_agent, input, context=None, max_turns=10, hooks, run_config, ...)`; `RunResultStreaming.to_input_list()` exists | T038 sets `ModelSettings(timeout=MODEL_TIMEOUT_SECONDS)`; T039 as planned |
| Scripted model (D-10) | `agents.Model` abstract methods are exactly `get_response` and `stream_response`. A subclass passed as `Agent(model=...)` works with `Runner.run` (return `ModelResponse(output=[ResponseOutputMessage], usage=Usage(), response_id=None)`) and with `Runner.run_streamed` (yield one `ResponseCompletedEvent` carrying a `Response`). Use `RunConfig(tracing_disabled=True)` in tests | T040 `ScriptedModel` subclasses `agents.Model`; the `Runner.run_streamed` patch fallback is **not needed** |
| pymongo (former D-02) | Was present in 4.19.0 and confirmed working, then **uninstalled** with its orphaned dependency dnspython after MongoDB was dropped. The smoke test asserts `pymongo` is not importable | Nothing may import pymongo |
| SQLAlchemy async + aiosqlite | `sqlalchemy.ext.asyncio.create_async_engine("sqlite+aiosqlite:///<path>")`, `async_sessionmaker(engine, expire_on_commit=False)` → `AsyncSession` work. PRAGMAs set in a **sync** `"connect"` listener on `engine.sync_engine` (`foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`) are in effect on the connection (`PRAGMA foreign_keys` → 1, `journal_mode` → `wal`, `busy_timeout` → 5000); `SELECT 1` → 1 | `db/engine.py` uses that listener pattern; call `await engine.dispose()` on shutdown and in tests |
| Alembic | `alembic.command.upgrade/downgrade/current/revision/check` exist. `alembic.config.Config()` can be built in code with `set_main_option("script_location", ...)`, so no URL has to live in `alembic.ini`. Bundled templates: `async`, `generic`, `multidb`, `pyproject`, `pyproject_async` | `migrations/env.py` follows the `async` template and reads the URL from `get_settings()` |
| FastAPI + TestClient | `FastAPI`, `Depends` and `fastapi.testclient.TestClient` (via httpx 0.28.1) work: an async dependency injected into an async route returns 200 with the expected JSON | API tests use `TestClient` (or `httpx.AsyncClient` + `ASGITransport` if async fixtures are needed) |
| PyJWT (HS256) | `jwt.encode(payload, key, algorithm="HS256")` returns `str`; `jwt.decode(token, key, algorithms=["HS256"])` round-trips. A wrong key raises `InvalidSignatureError`; a past `exp` raises `ExpiredSignatureError` (a subclass of `InvalidTokenError`). A key shorter than 32 bytes only emits `InsecureKeyLengthWarning` and does **not** fail | `services/tokens.py` always passes `algorithms=["HS256"]` and catches `InvalidTokenError`; the ≥32-char rule for `API_JWT_SECRET` must be enforced in `config.py`, since PyJWT won't enforce it |
| `cl.ElementSidebar` (D-01) | Present; `set_elements(elements, key=None)`, `set_title(title)` | T054 uses the sidebar (no fallback) |
| `cl.Action` / `cl.action_callback` (D-08) | `Action(name, payload: dict, label='', tooltip='', icon=None, forId=None, id=...)`; `action_callback(name)` | T092 as planned |
| `cl.set_starters` + `current_user` (contracts/ui.md) | Chainlit calls `set_starters(current_user, language)`; `wrap_user_function` binds the positional args to the user function's parameter **names in order**, so `async def starters(current_user, language=None)` receives the `cl.User` | T041 uses role-specific starters (no fallback). The role still comes from `AuthService.load_user(current_user.identifier)` |
| Logout hook (D-05) | `cl.on_logout(func)` exists; `func(request: starlette Request, response: Response)` gets **no user**. It runs after `clear_auth_cookie` modifies the response, but `request.cookies` still holds the token: `chainlit.auth.get_token_from_cookies(request.cookies)` + `chainlit.auth.decode_jwt(token)` returns the `cl.User` (internal helpers, not top-level exports). `cl.on_chat_end` also exists | T041 audits `logout` via `on_logout` + cookie decode; on any failure there, skip the audit (never raise). Session-expiry audit is unchanged |
| Session timeout key (D-05) | `[project] user_session_timeout` (seconds) sets both the JWT `exp` and the auth cookie `max_age`; it is an **absolute** lifetime from sign-in, not an idle timer. `[project] session_timeout` (seconds) is only the websocket reconnect window | T008 sets `user_session_timeout = 3600` (= `SESSION_IDLE_MINUTES` default × 60); the app-level idle check stays authoritative for FR-003. TOML is static, so a non-default `SESSION_IDLE_MINUTES` needs the config value edited to match (README) |
| Chainlit import side effect | Importing `chainlit` creates `.chainlit/config.toml` (default), `.chainlit/translations/` and `.files/` under the current directory (or `CHAINLIT_APP_ROOT`). `.files/` and translations are git-ignored | Tests run from the repo root; nothing else |
| `qdrant_client.QdrantClient` (D-09) | Present in 1.20.0. **`QdrantClient.search` no longer exists**; use `query_points(collection, query=vector, query_filter=..., limit=..., score_threshold=...)` → `.points`. In `:memory:` mode a `FieldCondition(key="access_scope", match=MatchAny(any=[...]))` filter is honoured, and `delete(points_selector=FilterSelector(filter=...))` removes by payload. `get_collection(name).config.params.vectors.size` returns the dimension | T068 uses `query_points`; the Qdrant filter plus the Retriever re-check both stay (FR-021) |

### Verification results (Phase 2 batch A: T020, T025, T034)

**Date**: 2026-10-25. **Method**: introspection and tests against the installed `.venv` packages.

| Item | Finding | Consequence |
|------|---------|-------------|
| `zoneinfo` on Windows | `tzdata` is **not installed**; `zoneinfo.ZoneInfo("UTC")` raises `ZoneInfoNotFoundError` (no system IANA database on Windows) | `config.py` maps `APP_TIMEZONE=UTC` to `datetime.UTC`; any other zone fails validation as `APP_TIMEZONE` unless `tzdata` is added to `requirements.txt` (owner decision). **Superseded in batch B**: `tzdata` added; the UTC special case is removed |
| pydantic-settings 2.16 | `env_ignore_empty=True` makes `VAR=` (as in `.env.example`) count as unset, so a blank required value is reported as missing; `extra="ignore"` is needed because `.env` extras are otherwise forbidden; `ValidationError.errors(include_input=False)` omits the offending values | `ConfigurationError` names variables from `loc`, never values |
| PyJWT 2.15 claims | `jwt.decode(..., algorithms=["HS256"], options={"require": [...], "verify_exp": False})` enforces presence of claims; `jwt.encode(payload, None, algorithm="none")` produces an unsigned token, which the pinned decode rejects; an HS512 token signed with the same secret is rejected | `TokenService` checks `exp` itself against an injectable clock, requires the exact claim set `{sub, iat, exp, jti}`, and keeps HS256 pinned |
| Period semantics | contracts do not define where `this_*` ends | `this_week`/`this_month`/`this_quarter` end on `today` (period to date); `last_*` and `YYYY-MM` are full periods; weeks start Monday |

### Verification results (Phase 2 batch B: T013–T015, T026–T031)

**Date**: 2026-10-25. **Method**: experiments and tests against the installed `.venv` packages
(SQLAlchemy 2.1.6, aiosqlite 0.22.1, Alembic 1.20.1, tzdata 2026.5) on Windows 11, Python 3.12.3.

| Item | Finding | Consequence |
|------|---------|-------------|
| `tzdata` / `zoneinfo` | With `tzdata` 2026.5 installed, `ZoneInfo("Asia/Karachi")` and `ZoneInfo("UTC")` resolve. `ZoneInfo("Mars/Base")` raises `ZoneInfoNotFoundError`, `ZoneInfo("Asia")` (a folder) raises `PermissionError` (an `OSError`), and `ZoneInfo("../x")` raises `ValueError` | `config.py` resolves every zone with `ZoneInfo` and maps `ZoneInfoNotFoundError`, `ValueError` and `OSError` to a `ConfigurationError` naming `APP_TIMEZONE` |
| SAVEPOINTs with aiosqlite | In the driver's default (legacy) transaction mode, a transaction whose first statement is a SAVEPOINT (`session.begin_nested()` before any DML) is **committed even when the outer transaction is rolled back** (experiment: 1 row left after rollback). With the SQLAlchemy-documented workaround, `dbapi_connection.isolation_level = None` in the sync `"connect"` listener plus a `"begin"` listener that emits `BEGIN`, the same experiment leaves 0 rows. The aiosqlite adapter has a working `isolation_level` setter | `db/engine.py` installs both listeners (with the PRAGMAs). Repository writes run in a SAVEPOINT, so a rejected row (`IntegrityError` → `ValidationError`) leaves the caller's transaction usable; `LeaveRepo.insert_idempotent` depends on this |
| SQLite error texts | `IntegrityError.orig` messages: `UNIQUE constraint failed: t.col[, t.col2]`, `CHECK constraint failed: <constraint name>`, `NOT NULL constraint failed: t.col`, `FOREIGN KEY constraint failed` (no column given) | Constraints are named through a `MetaData(naming_convention=...)` (`ck_<table>_<name>`, `uq_<table>_<cols>`, `fk_…`, `ix_…`); repositories map messages to `ValidationError(field, …)` without row values. `insert_idempotent` treats only `UNIQUE … leave_requests.idempotency_key` as "already submitted" |
| Driver errors | A file that is not a database fails in the connect listener with `sqlite3.DatabaseError` (wrapped as `sqlalchemy.exc.DatabaseError`, not `OperationalError`); a missing table is `OperationalError` | Repositories map every non-integrity `DBAPIError` (incl. `OperationalError`) to `DatabaseError`; `python -m hcm_lite.db status` exits 1 for an unreadable DB |
| Expression index | Autogenerate skips `Index(..., text("full_name COLLATE NOCASE"))` with a warning; once created, SQLite reflects it as a plain `full_name` index, so `alembic check` reports false drift. `PRAGMA index_info` lists the column `full_name` | `0001_initial` creates `ix_employees_full_name_nocase` by hand; `tables.HAND_MANAGED_INDEXES` + `include_object` in `env.py` exclude it from comparisons; the test checks its SQL contains `COLLATE NOCASE` |
| `alembic check` scope | Detects added/removed columns, indexes and type changes (a column added to the metadata at runtime → `AutogenerateDiffsDetected`), but **does not compare CHECK constraints** | `tests/unit/db/test_migrations.py` asserts every CHECK constraint by name in the `CREATE TABLE` SQL, plus NOT NULL on every column except the documented nullable ones |
| Alembic in-code Config | `Config()` + `set_main_option("script_location", …)` + `config.attributes["database_url"]` works for `upgrade`, `downgrade`, `current` and `check`, so tests need no ini file, no URL in a file and no full `Settings`. The async `env.py` calls `asyncio.run`, so tests run Alembic commands in a worker thread | `engine.alembic_config(url)`; `env.py` falls back to `get_settings().database_url` for the CLI (`alembic.ini` has `script_location = %(here)s/hcm_lite/db/migrations` and no URL) |
| Timestamps | SQLite `DATETIME` drops time zone information | `tables.UTCDateTime` stores naive UTC and returns aware UTC datetimes; the migration uses plain `sa.DateTime()` |
| NOT NULL beyond data-model.md | data-model.md leaves NOT NULL implicit for several short-form columns (e.g. `audit_events.channel/outcome/correlation_id`, `payroll_totals.currency`, `leave_types.label`, every `is_demo`) | Every column is NOT NULL except `users.locked_until`, `employees.manager_id`, `attendance.check_in`, `leave_requests.idempotency_key`, `audit_events.actor_user_id` and `audit_events.target` (Art. IX.1.2). `audit_events.actor_user_id` has no FK, so audit history survives `seed --reset` |
| Thread and file cleanup | An engine that is not disposed leaves an aiosqlite `_connection_worker_thread` running (and the DB file open on Windows) | DB-test fixtures dispose every engine; an autouse fixture in `tests/unit/db/conftest.py` fails any test that leaves a thread running |
| Demo credentials (D-13) | Fixed passwords in code or README would be committed secrets | `seed` generates each demo password with `secrets.token_urlsafe(12)` on every run, stores only the PBKDF2 hash and prints the passwords once. The README should therefore say "printed by `python -m hcm_lite.db seed`" instead of listing them. Usernames: `employee`, `manager`, `hr_admin` |
| Seed calendar (D-13) | The attendance window is defined relative to the injected `today`: from the first day of the month two months earlier (2026-08-01 for 2026-10-25) through the last working day <= `today` (weekends and demo holidays excluded) | Leave requests include pending ones in the current month and at least one later in the month (next month only if `today` is the month's last working day); approved days appear as `leave` attendance and in `leave_balances.used` |
