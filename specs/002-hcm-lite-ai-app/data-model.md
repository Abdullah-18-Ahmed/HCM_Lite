# Data Model: HCM Lite with AI HR Assistant

**Feature**: `002-hcm-lite-ai-app` | **Date**: 2026-10-25 (revised for constitution v4.0.0)
Storage is SQLite (`DATABASE_URL`, default `sqlite+aiosqlite:///./data/hcm_lite.db`) through
SQLAlchemy 2 ORM models in `hcm_lite/db/tables.py`. The schema is created **only** by Alembic
revision `0001_initial` (constitution Art. IX.1.3). `PRAGMA foreign_keys=ON` is set on every
connection. Dates are `DATE`, timestamps are UTC `DATETIME`, money is `NUMERIC(12,2)`
(`Decimal` in Python). Enum columns are `VARCHAR` with a `CHECK (col IN (...))`. Every demo row
has `is_demo = 1`. Pydantic v2 models in `hcm_lite/models/` mirror these tables for service
results.

## 1. Tables

### users
| Column | Type | Constraints |
|--------|------|-------------|
| id | VARCHAR(10) | PK, e.g. `U0001` |
| username | VARCHAR(40) | NOT NULL, **UNIQUE**, CHECK length 3–40 |
| password_hash | VARCHAR(200) | NOT NULL (`pbkdf2_sha256$<iter>$<salt>$<hash>`) |
| role | VARCHAR(10) | NOT NULL, CHECK IN (`employee`,`manager`,`hr_admin`) |
| employee_id | VARCHAR(10) | NOT NULL, **UNIQUE**, FK → employees.id |
| active | BOOLEAN | NOT NULL DEFAULT 1 |
| locked_until | DATETIME | NULL |
| is_demo | BOOLEAN | NOT NULL DEFAULT 0 |
| created_at | DATETIME | NOT NULL |

### login_failures
`id` PK, `user_id` FK → users.id NOT NULL, `at` DATETIME NOT NULL. Index `(user_id, at)`.
Rows older than `LOGIN_LOCK_MINUTES` are deleted on each successful login.

### departments
`name` VARCHAR(60) PK, `is_demo`.

### employees
| Column | Type | Constraints |
|--------|------|-------------|
| id | VARCHAR(10) | PK, e.g. `E1001`, `M1002`, `H1003` |
| full_name | VARCHAR(120) | NOT NULL |
| department | VARCHAR(60) | NOT NULL, FK → departments.name |
| job_title | VARCHAR(80) | NOT NULL |
| employment_status | VARCHAR(10) | NOT NULL, CHECK IN (`active`,`inactive`) |
| hire_date | DATE | NOT NULL |
| manager_id | VARCHAR(10) | NULL, FK → employees.id; **index** (team lookup) |
| is_demo | BOOLEAN | NOT NULL |

Indexes: `(department, employment_status)`, `(manager_id)`, `(full_name COLLATE NOCASE)`.

### attendance
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK autoincrement |
| employee_id | VARCHAR(10) | NOT NULL, FK |
| date | DATE | NOT NULL |
| status | VARCHAR(10) | NOT NULL, CHECK IN (`present`,`remote`,`absent`,`leave`) |
| check_in | VARCHAR(5) | NULL; CHECK `status NOT IN ('present','remote') OR check_in IS NOT NULL` |
| scheduled_start | VARCHAR(5) | NOT NULL (`HH:MM`) |
| is_demo | BOOLEAN | NOT NULL |

**UNIQUE** `(employee_id, date)`; index `(date)`.
Derived: `late = status IN (present, remote) AND check_in > scheduled_start + LATE_GRACE_MINUTES`.

### leave_types
`id` VARCHAR(10) PK CHECK IN (`annual`,`sick`,`casual`,`unpaid`,`other`), `label`, `is_demo`.

### leave_balances
`id` PK; `employee_id` FK NOT NULL; `leave_type` FK → leave_types.id NOT NULL; `year` INTEGER
NOT NULL; `entitled`, `used` NUMERIC(6,2) NOT NULL CHECK ≥ 0; `as_of` DATE NOT NULL; `is_demo`.
**UNIQUE** `(employee_id, leave_type, year)`. `remaining` (= entitled − used − pending days) is
computed, never stored.

### leave_requests
| Column | Type | Constraints |
|--------|------|-------------|
| id | VARCHAR(20) | PK, reference `LR-YYYYMMDD-XXXX` |
| employee_id | VARCHAR(10) | NOT NULL, FK |
| leave_type | VARCHAR(10) | NOT NULL, FK |
| start_date, end_date | DATE | NOT NULL, **CHECK `end_date >= start_date`** |
| working_days | INTEGER | NOT NULL, CHECK ≥ 1 |
| reason | VARCHAR(500) | NOT NULL |
| status | VARCHAR(10) | NOT NULL, CHECK IN (`pending`,`approved`,`rejected`,`cancelled`) |
| source | VARCHAR(10) | NOT NULL, CHECK IN (`assistant`,`api`,`seed`) |
| idempotency_key | VARCHAR(36) | NULL, **UNIQUE** (SQLite allows multiple NULLs) |
| created_by | VARCHAR(10) | NOT NULL, FK → users.id |
| created_at | DATETIME | NOT NULL |
| is_demo | BOOLEAN | NOT NULL |

Indexes `(employee_id, start_date)`, `(status)`. **State transitions in this feature**:
`(none) → pending` only. No transition out of `pending` is implemented (FR-032).

### payroll_totals
`id` PK; `period` VARCHAR(7) NOT NULL (`YYYY-MM`); `department` FK NOT NULL; `headcount_paid`
INTEGER CHECK ≥ 0; `gross_total`, `net_total` NUMERIC(12,2) CHECK ≥ 0; `currency` VARCHAR(3);
`is_demo`. **UNIQUE** `(period, department)`. There are no per-employee pay columns anywhere.

### holidays
`date` DATE PK, `name` VARCHAR(80) NOT NULL, `is_demo`.

### audit_events
`id` PK; `at` DATETIME NOT NULL; `actor_user_id` NULL; `action` VARCHAR(20) NOT NULL CHECK IN
(`login_success`,`login_failed`,`account_locked`,`logout`,`session_expired`,`access_denied`,
`leave_submitted`); `channel` CHECK IN (`chat`,`api`); `target` NULL; `outcome` CHECK IN
(`ok`,`denied`,`error`); `correlation_id` VARCHAR(36). Index `(at)`. There are no message or
document text columns (FR-034).

### alembic_version
Managed by Alembic (applied revision).

## 2. Application (non-persisted) models

- **AuthenticatedUser**: `user_id`, `username`, `role`, `employee_id`, `display_name`,
  `department`. It is reloaded from the DB on every chat turn and every API request, so role
  changes and deactivation take effect immediately.
- **Scope**: `kind` (`self` | `team` | `all`), `employee_ids: frozenset[str] | None` (None = all).
- **AppSession** (Chainlit `cl.user_session`): `session_id`, `user`, `history`,
  `drafts: dict[draft_id, LeaveDraft]` (max 5), `last_activity`.
- **ApiToken** (JWT claims): `sub` (user id), `iat`, `exp` (= `API_TOKEN_MINUTES`), `jti`. There is
  no role claim.
- **AppContext** (agent run context): `user`, `session`, `today`, `services`, `demo_mode`.

## 3. Documents (vector store, not SQL)

**DocumentChunk payload** (Qdrant): `chunk_id` (uuid5), `document_id`, `title`, `source_path`,
`doc_type`, `access_scope` (`all_employees` | `managers` | `hr_admin` | `restricted`),
`department` (optional), `version`, `last_updated`, `section`, `page`, `chunk_index`, `text`,
`embedding_model`, `is_demo`. Registry `.ingest/registry.json`. Allowed scopes: employee
{all_employees}; manager {+managers}; hr_admin {+hr_admin}.

## 4. Service result models (`hcm_lite/models/results.py`)

`ToolResult[T]` envelope: `ok`, `data`, `error {code, message}` (codes `access_denied`,
`not_found`, `no_data`, `invalid_input`, `source_unavailable`), `source`
(e.g. `hr-db:attendance`), `period`, `scope` (`self`/`team`/`all`), `is_demo`. The same
envelope is the JSON body of the FastAPI data endpoints (contracts/api.md).

| Payload | Fields |
|---------|--------|
| ProfileResult | employee_id, full_name, department, job_title, manager_name, hire_date |
| LeaveRequestList | count, requests[{reference, leave_type, start_date, end_date, working_days, status, created_at}] (newest first) |
| HeadcountResult | scope, total_active, by_department, as_of |
| AttendanceSummary | period, working_days, records, present, remote, absent, on_leave, late, attendance_rate (%, 1 dp), by_department |
| LateComersResult | period, count, entries[{employee_id, full_name, department, date, check_in, minutes_late}] (≤50, truncated flag) |
| LeaveSummary | period, by_status, by_type, total_days_approved, pending[{reference, employee, start_date, end_date, days}] (team/all only, ≤25) |
| LeaveBalanceResult | employee_id, year, as_of, balances[{leave_type, entitled, used, pending, remaining}] |
| PayrollSummary | period, currency, gross_total, net_total, headcount_paid, by_department |
| EmployeeSearchResult | count, employees[{employee_id, full_name, department, job_title, employment_status}] (≤25) |
| PolicySearchResult | found, chunks[{n, text(wrapped), citation}] |
| DashboardData | role, sections{name → ToolResult}, withheld[], unavailable[] |

## 5. Leave draft (session only)

| Field | Type |
|-------|------|
| draft_id | uuid4 string (also the idempotency key) |
| status | `incomplete` \| `invalid` \| `ready_for_review` \| `submitted` |
| leave_type, start_date, end_date, reason | optional until complete |
| working_days | int \| None |
| missing_fields | list[str] |
| validation_errors | list[str]: end<start, start in past, span>60 days, overlap with pending/approved |
| warnings | list[str]: exceeds remaining balance, policy guidance unavailable |
| balance_remaining | Decimal \| None |
| policy_citations | list[Citation] |
| submitted_reference | str \| None (set only after `LeaveService.submit` confirms the insert) |

Transitions: `incomplete → ready_for_review`; `→ invalid` (fixable by edit);
`ready_for_review → submitted` **only** via an explicit user confirmation outside the model:
the Chainlit Confirm action callback, or the API call
`POST /api/v1/assistant/conversations/{cid}/drafts/{draft_id}/confirm`. A `submitted` draft
returns its existing reference if confirmed again.

API conversations (contracts/api.md) keep an **ApiConversation** in server memory, keyed by
`(user_id, conversation_id)`, with the same fields as AppSession. It expires after
`SESSION_IDLE_MINUTES` without use.
