# Contract: Chainlit UI Integration (`app.py`)

`app.py` contains only Chainlit wiring. Every decision is delegated to services or the runner.
Items marked VERIFY-AT-IMPL are confirmed in the first UI task.

| Hook | Behaviour |
|------|-----------|
| `@cl.password_auth_callback(username, password)` | `AuthService.authenticate`; on success it returns `cl.User(identifier=user_id, metadata={"username", "display_name"})`. The role is **not** trusted from metadata; it's reloaded via `AuthService.load_user` |
| `@cl.set_starters` | Role-specific starters (VERIFY-AT-IMPL: the `current_user` parameter). Employee: annual leave policy, my leave balance, prepare a leave request for next Monday and Tuesday, summarize my dashboard. Manager: + team attendance this month, who was late today. HR admin: + how many employees, payroll last month |
| `@cl.on_chat_start` | Load the user; create an `AppSession`; render the dashboard (`DashboardService.for_user`) in `cl.ElementSidebar` (VERIFY-AT-IMPL; fallback: a "Dashboard" message); show the welcome text with role and the **Demo data** label; add a "Refresh dashboard" action |
| `@cl.on_message` | Idle check (> `SESSION_IDLE_MINUTES` → audit `session_expired`, end the session, ask to sign in); `load_user` (inactive → sign out); `run_turn` with progress shown as `cl.Step`s; append a **Sources** list; if `ready_draft`, render the draft table labelled "DRAFT — not submitted" with actions `confirm_leave` / `cancel_leave` (payload `{"draft_id"}`) |
| `@cl.action_callback("confirm_leave")` | Idle and user checks → `LeaveService.submit(user, session, draft_id)` → post "Submitted for approval — reference LR-…, status pending" from the returned record, remove the actions, and append a system note to the session history so the model knows it was submitted. On `ValidationError`, show the reason |
| `@cl.action_callback("cancel_leave")` | Remove the draft from the session; post "Draft discarded — nothing was submitted" |
| `@cl.action_callback("refresh_dashboard")` | Re-render the dashboard |
| `@cl.on_chat_end` / logout | `AuthService.record_logout` (VERIFY-AT-IMPL hook availability) |

`.chainlit/config.toml`: `[UI] name = "HCM Lite"`; session timeout aligned with
`SESSION_IDLE_MINUTES` (VERIFY-AT-IMPL key name). `chainlit.md` welcome page: the product name,
a capabilities list and the "Demo data — fictional" banner.
