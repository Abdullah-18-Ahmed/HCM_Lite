# Contract: Service Layer (internal API)

The service layer is the defined interface (constitution Art. III.3, XIV) used by **all three
consumers**: the Chainlit UI (dashboard + Confirm actions), the agent tools, and the FastAPI
routes (contracts/api.md). All methods are `async`, take `user: AuthenticatedUser` first, perform
authorization and scoping themselves, and raise only the errors listed.

Errors: `AccessDenied(capability)`, `ValidationError(field, message)`, `NotFound`,
`DatabaseError`, `RetrievalError`, `AccountLocked(until)`, `InvalidToken`.

`LeaveService.build_draft` / `submit` take a `session` argument, which is either the Chainlit
`AppSession` or the API's `ApiConversation`. Both implement the same `DraftStore` protocol
(`get_draft`, `put_draft`, `discard_draft`).

## AuthService (`hcm_lite/services/auth_service.py`)

| Method | Returns | Behaviour / errors |
|--------|---------|--------------------|
| `authenticate(username, password, channel)` | `AuthenticatedUser \| None` | Generic `None` on unknown user, bad password, inactive or locked; records `login_failures` rows / sets `locked_until`; audits `login_success` / `login_failed` / `account_locked` with `channel` (`chat`/`api`); constant-time compare plus a dummy hash for unknown users |
| `load_user(user_id)` | `AuthenticatedUser \| None` | Fresh role and active flag from the DB; None → force sign-out / 401 |
| `issue_token(user)` | `(jwt, expires_in)` | HS256 with `API_JWT_SECRET`; claims `sub, iat, exp, jti` only (no role) |
| `verify_token(jwt)` | `user_id` | Raises `InvalidToken` on a bad signature, expiry or a deny-listed `jti` |
| `revoke_token(jwt)` | None | Deny-lists the `jti` until `exp`; audit `logout` (channel api) |
| `record_logout(user, reason)` | None | Audit `logout` or `session_expired` (channel chat) |

## MetricsService (`hcm_lite/services/metrics_service.py`)

| Method | Capability | Returns |
|--------|-----------|---------|
| `my_profile(user)` | self | `ToolResult[ProfileResult]` |
| `headcount(user, department=None)` | team/all | `ToolResult[HeadcountResult]` |
| `attendance_summary(user, range, department=None)` | self/team/all | `ToolResult[AttendanceSummary]` |
| `late_comers(user, range, department=None)` | team/all | `ToolResult[LateComersResult]` |
| `leave_summary(user, range, status=None, department=None)` | self/team/all | `ToolResult[LeaveSummary]` |
| `payroll_summary(user, period, department=None)` | hr_admin | `ToolResult[PayrollSummary]` |
| `search_employees(user, filters)` | team/all | `ToolResult[EmployeeSearchResult]` |

The `department` filter is intersected with the scope (a manager cannot widen it). An empty
result for the period → `no_data`.

## LeaveService (`hcm_lite/services/leave_service.py`)

| Method | Returns | Notes |
|--------|---------|-------|
| `my_balance(user, leave_type=None)` | `ToolResult[LeaveBalanceResult]` | self only |
| `my_requests(user, limit=10)` | `ToolResult[LeaveRequestList]` | self only; newest first; limit 1–50 |
| `build_draft(user, session, request)` | `ToolResult[LeaveDraft]` | validates, checks overlap and balance, attaches policy citations via `PolicyService.search`; stores in `session.drafts`; never writes the DB |
| `submit(user, session, draft_id)` | `LeaveRequestRecord` | re-validates the stored draft; `ValidationError` if not `ready_for_review` or no longer valid; idempotent via `LeaveRepo.insert_idempotent(idempotency_key=draft_id)` (a duplicate returns the existing record, `created=False`); audits `leave_submitted` only on the first insert; marks the draft `submitted` |

## PolicyService (`hcm_lite/services/policy_service.py`)

`search(user, query, doc_type=None) -> ToolResult[PolicySearchResult]`. Scope-filtered
retrieval with threshold and untrusted wrapping; `RetrievalError` on index failure.

## DashboardService (`hcm_lite/services/dashboard_service.py`)

`for_user(user, today) -> DashboardData`, composed only of the methods above:

| Role | Sections |
|------|----------|
| employee | profile (`my_profile`), my attendance (this month), my balances, my leave requests (`my_requests`, latest 10) |
| manager | team headcount, team attendance (this month), team late today, team pending leave, + own balances |
| hr_admin | headcount by department, org attendance (this month), leave summary (this month), payroll last month |

Each section is fetched independently. A failure → the section name goes in `unavailable`; a
denial → `withheld`.
