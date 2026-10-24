---
id: 006
title: Fix Idempotency and Request Models
stage: misc
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: remediation of /sp.analyze findings I1, U3
labels: ["remediation", "idempotency", "models", "tasks"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/002-hcm-lite-ai-app/tasks.md
 - specs/002-hcm-lite-ai-app/contracts/services.md
tests:
 - task format validation 110/110 PASS
---

## Prompt

yes

## Response snapshot

I1: defined `LeaveRepo.insert_idempotent(record) -> (record, created)` in T015/T027; a
duplicate idempotency_key returns the existing record instead of raising, while other unique
indexes still map to ValidationError. T089 and contracts/services.md audit `leave_submitted`
only when created=True. U3: folded `hcm_lite/models/requests.py` into T023 (PeriodArgs,
DepartmentFilter, EmployeeSearchFilters, PolicyQuery, LeaveDraftRequest with extra="forbid")
plus a unit test file; T089 now types its input as LeaveDraftRequest. Task IDs unchanged (110).

## Outcome

- ✅ Impact: Foundational contradictions resolved; remaining open items are MEDIUM U2, G3, U4, I2.
- 🧪 Tests: format validation only
- 📁 Files: tasks.md, contracts/services.md
- 🔁 Next prompts: /sp.implement from T001
- 🧠 Reflection: Folding into T023 avoided renumbering 87 tasks.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): tasks format PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
