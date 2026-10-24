---
id: 005
title: Apply Analysis Remediation
stage: misc
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: remediation of /sp.analyze findings
labels: ["remediation", "constitution", "tasks", "contracts"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - .specify/memory/constitution.md
 - specs/002-hcm-lite-ai-app/spec.md
 - specs/002-hcm-lite-ai-app/plan.md
 - specs/002-hcm-lite-ai-app/tasks.md
 - specs/002-hcm-lite-ai-app/contracts/services.md
 - specs/002-hcm-lite-ai-app/data-model.md
tests:
 - task format validation 110/110 PASS
---

## Prompt

yes
A
B   (sent mid-turn, replacing A)

## Response snapshot

Applied the remediation. G1: T041 now builds role-specific `@cl.set_starters` (with a fallback).
U1: added `MetricsService.my_profile` and `LeaveService.my_requests` to contracts/services.md,
ProfileResult/LeaveRequestList to data-model §4, and covered them in T045/T046/T050/T051/T052.
G2: an instruction-confidentiality rule plus the `INSTRUCTIONS_CANARY` in T036, an
instruction-leak check in the T095/T097 output guardrail, and 4 prompt-extraction cases in T104.
C1 (option B): constitution 3.1.0 → 3.2.0 adds Art. I.1 (brief unavailable → the constitution
plus owner decisions are the requirements source); the plan Authority gate is now ✅; spec A-1
and Clarifications updated. Tasks still 110, format valid.

## Outcome

- ✅ Impact: All CRITICAL/HIGH analysis findings resolved; ready for /sp.implement.
- 🧪 Tests: format validation only
- 📁 Files: constitution, spec, plan, tasks, services contract, data model
- 🔁 Next prompts: optional fixes for MEDIUM items (I1, U3 first); /sp.implement
- 🧠 Reflection: The user switched from A to B mid-turn; applied B.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): tasks format PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
