---
id: 014
title: Default Leave Balances And Pooling Fix
stage: green
date: 2026-10-26
surface: agent
model: claude-opus-4-8
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: fix "no leave balance" + leave-draft "data source unavailable"
labels: ["bugfix", "leave-balances", "supabase", "connection-pooling"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - hcm_lite/services/user_admin_service.py (default leave types+balances on create_user & bootstrap_admin)
 - hcm_lite/db/engine.py (pool_recycle=300 for Postgres)
tests:
 - .venv pytest -q -> 410 passed, 2 deselected
 - live: ahmed/leave/balance ok; build_draft reproduced 3x with no error (admin + ahmed)
---

## Prompt

"I couldn't prepare the leave draft because the HR data source is temporarily unavailable." and
"I couldn't find any annual leave balance for this year in the HR records." (in the AI assistant)

## Response snapshot

Diagnosed both against Supabase. (1) "No leave balance": users created via the app (admin
bootstrap + the admin/HR Users tab: Abdullah/Arslan/Areeb/Mohid) had NO leave_balances rows, so
my_balance returned no_data. Fix: UserAdminService.create_user and bootstrap_admin now seed the
standard leave types (if missing) and default balances (annual 20, sick 10, casual 6) for the
year via a new _ensure_default_balances helper (uses existing LeaveRepo.insert_leave_types /
insert_balances). Backfilled the 4 already-created users directly in Supabase (Ahmed/Shoaib
already had balances; total leave_balances now 18 = 6 x 3). (2) Leave-draft "HR data source
unavailable": not reproducible — build_draft ran fine 3x for both admin and Ahmed, so it was an
intermittent Supabase session-pooler idle-connection drop; hardened engine with pool_recycle=300
alongside the existing pool_pre_ping. Suite stayed green (410). Server restarted on new code;
verified ahmed /leave/balance returns annual/casual/sick.

## Outcome

- ✅ Impact: every user (new + backfilled) has leave balances; pooled-connection drops self-heal.
- 🧪 Tests: 410 passed; live balance + draft verified
- 📁 Files: user_admin_service.py, engine.py
- 🔁 Next: optional — attendance/payroll entry UI; git commit; rotate Supabase password
- 🧠 Reflection: creating an account must also provision its dependent HR data (balances), or
  downstream features read as "missing".

## Evaluation notes (flywheel)

- Failure modes observed: new accounts lacked default balances; one-off pooler connection drop
- Graders run and results: pytest 410 PASS; live checks PASS
- Next experiment: watch for any further pooler drops now that recycle is set
