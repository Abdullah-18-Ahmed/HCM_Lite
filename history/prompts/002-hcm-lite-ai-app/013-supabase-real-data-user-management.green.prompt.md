---
id: 013
title: Supabase Real Data And User Management
stage: green
date: 2026-10-26
surface: agent
model: claude-opus-4-8
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: switch DB to Supabase + user management + de-demo UI
labels: ["supabase", "postgres", "user-management", "rbac", "ui", "constitution-v4.2"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - hcm_lite/db/engine.py (SSL connect_args for postgres)
 - hcm_lite/db/migrations/env.py (SSL), versions/0001_initial.py (portable NOCASE + boolean defaults)
 - hcm_lite/db/migrations/versions/0002_user_management.py (new; email, admin role, audit actions)
 - hcm_lite/models/domain.py, hcm_lite/db/tables.py, repositories.py, seed.py, __main__.py
 - hcm_lite/services/{auth_service,authz,user_admin_service}.py, assistant/context.py
 - hcm_lite/api/main.py, api/routes/{setup,users}.py (new)
 - hcm_lite/api/static/{index.html,app.js,styles.css} (setup/login-by-email/Users/Profile; demo badge removed)
 - requirements.txt (asyncpg), .env (DATABASE_URL -> Supabase pooler)
 - .specify/memory/constitution.md (v4.2.0), HANDOFF.md
tests:
 - .venv pytest -q -> 410 passed, 2 deselected (backend, SQLite)
 - Supabase verified: alembic_version 0002, GET /setup/status needs_admin=true, UI serves setup/email-login/Users+Profile, no demo badge
---

## Prompt

now i want to use supabase for the database ... create admin on first use ... admin creates HR and
employee (email, password, name, details) in a dashboard tab; deactivate/edit/delete; HR creates
employees; employees change their own password in a profile tab; remove demo-data labels; show
real per-role data; the AI assistant stays unchanged.

## Response snapshot

Phase 1 (DB swap): pointed DATABASE_URL at Supabase via the IPv4 session pooler (the direct host
is IPv6-only and did not resolve); added asyncpg + SSL (engine.py and alembic env.py); fixed two
SQLite-isms in migration 0001 (COLLATE NOCASE -> lower() on Postgres; BOOLEAN DEFAULT 0/1 ->
sa.false()/true()). Ran migrations on Supabase (0001, then 0002). SQLite suite stayed green (372).
Phase 2 (backend, via hcm-implementer, 410 passed): Alembic 0002 (users.email NOT NULL UNIQUE,
role CHECK + admin, audit-action CHECK), Role.ADMIN, email login, change_password, admin>=hr_admin
authz + can_manage_role, UserAdminService (list/create/update/set_active/delete/bootstrap_admin),
routes /setup/status,/setup/admin,/users CRUD,/me/password; seed+tests updated for email.
Phase 3 (UI, me): rewrote the SPA — first-run Create-admin screen, email login, Users tab
(admin creates HR+employee, HR creates employee, edit/deactivate/delete), Profile tab (change
password), removed the DEMO badge and demo labels. Verified live on Supabase (needs_admin=true;
UI markers present). The destructive end-to-end cleanup (TRUNCATE) was blocked by the safety
classifier and did not run, so no throwaway rows were written — the DB is empty for the user to
bootstrap. Constitution -> v4.2.0.

## Outcome

- ✅ Impact: Real Postgres data on Supabase; first-run admin + full user management; AI untouched.
- 🧪 Tests: 410 passed (SQLite); Supabase migration + read path verified live
- 📁 Files: see list
- 🔁 Next: user opens the site -> Create admin -> add HR/employees; optional: attendance/payroll
  have no entry UI so those dashboard cards stay empty until imported
- 🧠 Reflection: Supabase direct host is IPv6-only; the pooler (IPv4) is required. DB swap needed
  dialect-portable migrations, not just a URL change.

## Evaluation notes (flywheel)

- Failure modes observed: direct Supabase host unresolvable (IPv6-only); TRUNCATE blocked (good);
  port 8001 reuse on relaunch
- Graders run and results: pytest 410 PASS; live setup/status + UI markers PASS
- Next experiment: optional attendance/payroll import; ADR for datastore+auth change
