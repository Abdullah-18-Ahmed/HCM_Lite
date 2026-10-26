---
id: 012
title: Supabase And User Management Plan
stage: plan
date: 2026-10-26
surface: agent
model: claude-opus-4-8
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: plan Supabase + real-data user management
labels: ["supabase", "postgres", "auth", "user-management", "planning"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - history/prompts/002-hcm-lite-ai-app/012-supabase-and-user-management-plan.plan.prompt.md
tests:
 - none (planning)
---

## Prompt

now i want to use supabase for the database so i can use real data without the demo data on first
usage it will allow to create admin by asking from us after creating admin only admin can create
HR and employee after login their email and password and name all details inside a tab in
dashboard and can also deactivate or edit or delete any hr or employee login hr can create employee
login inside tab with the details username and all details employee after login can edit their
password for better use from profile tab. then in the UI remove the places it shows written demo
data or related to it. and the respected leave and another data will be shown from their
perspective database like number of employees everything. but the AI assistant data will not
change it will remain as it is its in good shape no change needed there.

## Response snapshot

Scoped the request. Verified current code is mostly Postgres-ready (engine.py guards SQLite
listeners by dialect) but has two blockers for Supabase/Postgres: (1) migration 0001 uses a
`full_name COLLATE NOCASE` index (SQLite-only) — must become a `lower(full_name)` functional index
on Postgres; (2) `asyncpg` is not installed. Chose approach: use Supabase purely as the Postgres
DATABASE (postgresql+asyncpg + SSL), keep our own JWT AuthService (no Supabase Auth/RLS rework),
keep the AI/RAG unchanged. New work: add `admin` role + `email` login, first-run admin bootstrap,
a Users management tab (admin creates HR+employee; HR creates employee; edit/deactivate/delete), a
Profile tab (change own password), drop the demo seed + "DEMO" badge. Flagged that no
attendance/payroll data-entry UI exists, so those dashboard sections will be empty on real data
unless imported. Blocked on the Supabase connection string (secret) and 4 schema-shaping
decisions; asked the user before implementing.

## Outcome

- ✅ Impact: Plan + blockers identified; awaiting connection string + decisions.
- 🧪 Tests: none
- 📁 Files: this PHR
- 🔁 Next prompts: user provides Supabase URI + confirms roles/login/delete/attendance decisions
- 🧠 Reflection: DB swap is not just a URL change (NOCASE index, asyncpg, SSL); user mgmt is a new RBAC surface.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run: none
- Next experiment: once creds arrive, build in phases (DB swap → bootstrap → user CRUD → profile → de-demo)
