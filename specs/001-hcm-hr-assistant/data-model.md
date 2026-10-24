# Data Model: HCM Lite AI HR Assistant

**Feature**: `001-hcm-hr-assistant` | **Date**: 2026-10-25
All models are Pydantic v2 (`hcm_lite/models/`). Dates are ISO `YYYY-MM-DD`; times are `HH:MM`
in the configured `APP_TIMEZONE`.

## 1. Identity and context

### Role (enum)
`employee` | `hr_manager` | `hr_admin`

### Permission (enum)
`own_leave_balance`, `leave_draft`, `employee_search_basic`, `headcount`, `attendance`,
`late_comers`, `leave_summary`, `payroll_summary`, `dashboard_summary`.

### AccessScope (enum)
`all_employees` | `hr` | `payroll` | `restricted`
- Allowed scopes: employee → {all_employees}; hr_manager → {all_employees, hr};
  hr_admin → {all_employees, hr, payroll}. `restricted` is never retrievable (fail-closed default).

### UserIdentity
| Field | Type | Rules |
|-------|------|-------|
| user_id | str | required; matches `employees.employee_id` |
| display_name | str | required |
| role | Role | required; only set by the auth callback |
| department | str \| None | |

### AppContext (per chat session; never sent to the model)
| Field | Type | Notes |
|-------|------|-------|
| user | UserIdentity | |
| session_id | str | UUID4 per Chainlit session |
| today | date | injected clock, for deterministic tests |
| data_provider | HRDataProvider | |
| retriever | Retriever | |
| demo_mode | bool | true when any demo source is active |

### DemoPersona (`data/demo/personas.json`)
`username`, `password_hash` (PBKDF2-SHA256, `salt$iterations$hash`), `user_id`, `role`.

## 2. Documents and retrieval

### HRDocument (ingestion registry)
| Field | Type | Rules |
|-------|------|-------|
| document_id | str | sha1(relative path); stable |
| title | str | front-matter `title`, else first heading, else file stem |
| source_path | str | relative to `DOCUMENTS_DIR` |
| doc_type | str | `policy` \| `handbook` \| `faq` \| `other` |
| access_scope | AccessScope | default `restricted` if absent |
| department | str \| None | |
| version | str | front-matter `version`, default `"1"` |
| last_updated | datetime | file mtime (UTC) |
| content_hash | str | SHA-256 of normalized text |
| status | IngestStatus | |
| is_demo | bool | front-matter `demo: true` |

**IngestStatus**: `loaded` | `updated` | `unchanged` | `rejected` | `deleted`.
State transitions per run: new → `loaded`; same hash → `unchanged`; new hash → `updated`;
file gone → `deleted`; failure → `rejected` (previous points remain only when the file still
exists and was previously valid — the old version keeps serving until a good version is loaded).

### DocumentChunk (Qdrant point payload)
| Field | Type | Rules |
|-------|------|-------|
| chunk_id | UUID | uuid5(`document_id:chunk_index`) — also the point id |
| document_id, title, source_path, doc_type, access_scope, department, version, last_updated, is_demo | from HRDocument | |
| section | str \| None | heading path (`Annual Leave > Carry-over`) or `page N` |
| page | int \| None | PDF only |
| chunk_index | int | ≥ 0 |
| text | str | 1..`RAG_CHUNK_SIZE`×1.2 chars |
| embedding_model | str | for mismatch detection |

### RetrievedChunk
`chunk: DocumentChunk`, `score: float` (cosine, 0..1). Only chunks with
`score ≥ RAG_SIMILARITY_THRESHOLD` and `access_scope ∈ allowed_scopes(role)` are ever constructed.

### Citation
`document_title`, `section | None`, `page | None`, `source_path`, `version`. It is rendered as
`[n] Title — Section (vX)`.

### IngestionReport
`run_at`, `documents: list[{source_path, status, reason | None, chunks: int}]`,
`totals: {loaded, updated, unchanged, rejected, deleted, chunks_written}`.
It is printed by the CLI and written to `.ingest/last_report.json`.

## 3. Structured HR records (demo exports in `HR_DATA_DIR`)

Each CSV's first line is `# DEMO DATA — fictional, for HCM Lite demonstration only`.

| Entity | File | Fields | Validation |
|--------|------|--------|------------|
| EmployeeRecord | employees.csv | employee_id, full_name, department, job_title, employment_status (`active`/`inactive`), hire_date, manager_id? | unique id; status enum |
| AttendanceRecord | attendance.csv | employee_id, date, status (`present`/`absent`/`leave`/`remote`), check_in? (HH:MM), scheduled_start (HH:MM) | id exists; check_in required if present/remote |
| LeaveRecord | leave_requests.csv | leave_id, employee_id, leave_type, start_date, end_date, days, status (`pending`/`approved`/`rejected`/`cancelled`) | end ≥ start; days > 0 |
| LeaveBalance | leave_balances.csv | employee_id, leave_type, entitled, used, remaining, as_of | remaining = entitled − used (checked) |
| PayrollAggregate | payroll_summary.csv | period (YYYY-MM), department, headcount_paid, gross_total, net_total, currency | non-negative; no per-employee rows |

**LeaveType (enum)**: `annual`, `sick`, `casual`, `unpaid`, `other`. Leave-policy rules
(notice, maximums) come from policy documents via RAG and are shown as guidance; balance checks
use `LeaveBalance` only.

**Lateness rule**: a person is late when `status ∈ {present, remote}` and
`check_in > scheduled_start + LATE_GRACE_MINUTES` (default 0; configurable).

## 4. Tool result models (`hcm_lite/models/responses.py`)

Every tool returns a `ToolResult[T]` envelope:

| Field | Type | Notes |
|-------|------|-------|
| ok | bool | |
| data | T \| None | present when ok |
| error | ToolError \| None | `{code, message}`; codes: `access_denied`, `not_found`, `no_data`, `invalid_input`, `source_unavailable` |
| source | str | e.g. `demo-export:attendance.csv` |
| period | str \| None | e.g. `2026-10-01..2026-10-31` |
| is_demo | bool | |
| complete | bool | false if invalid rows were skipped |

Payloads (`T`):
- **HeadcountResult**: `total_active`, `by_department: dict[str,int]`, `as_of`.
- **AttendanceSummary**: `period`, `working_days`, `records`, `present`, `remote`, `absent`, `on_leave`, `late`, `attendance_rate` (present+remote / (records − on_leave)), `by_department`.
- **LateComersResult**: `period`, `count`, `entries: list[{employee_id, full_name, department, date, check_in, minutes_late}]` (max 50, `truncated` flag).
- **LeaveSummary**: `period`, `by_status: dict`, `by_type: dict`, `total_days_approved`.
- **LeaveBalanceResult**: `employee_id`, `as_of`, `balances: list[{leave_type, entitled, used, remaining}]`.
- **PayrollSummary**: `period`, `currency`, `gross_total`, `net_total`, `headcount_paid`, `by_department`.
- **EmployeeSearchResult**: `count`, `employees: list[{employee_id, full_name, department, job_title, employment_status}]` (max 25).
- **PolicySearchResult**: `found: bool`, `chunks: list[{n, text, citation}]`, `note` (untrusted-content label).
- **LeaveDraft**: see §5.
- **DashboardSummary**: `sections: dict[str, ToolResult]`, `withheld: list[str]`, `unavailable: list[str]`.

Monetary values are `Decimal`, serialized as strings with 2 decimals; rates are rounded to
1 decimal percent in code, not by the model.

## 5. Leave draft

### LeaveDraftRequest (tool input)
| Field | Type | Rules |
|-------|------|-------|
| leave_type | LeaveType \| None | |
| start_date | date \| None | ISO date; the model resolves relative phrases using `today` supplied in instructions, and the service re-validates |
| end_date | date \| None | defaults to start_date if only one day is given |
| reason | str \| None | ≤ 500 chars |

### LeaveDraft (tool output)
| Field | Type |
|-------|------|
| status | `incomplete` \| `ready_for_review` |
| leave_type, start_date, end_date, reason | as above |
| working_days | int \| None (Mon–Fri, minus supplied holidays) |
| missing_fields | list[str] |
| validation_errors | list[str] — end before start, start in past, > 60 days span |
| warnings | list[str] — exceeds remaining balance, policy guidance |
| balance_remaining | Decimal \| None |
| policy_citations | list[Citation] |
| submitted | `Literal[False]` — always false; there is no submit path |

Transitions: `incomplete` → (user supplies fields) → `ready_for_review` → (user edits) →
`ready_for_review`. There is no `submitted` state in this version (FR-020).
