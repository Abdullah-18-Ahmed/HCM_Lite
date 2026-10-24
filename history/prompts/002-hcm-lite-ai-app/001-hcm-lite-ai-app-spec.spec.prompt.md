---
id: 001
title: HCM Lite AI App Spec
stage: spec
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: /sp.specify
labels: ["spec", "constitution-v3.1", "auth", "dashboard", "rag", "smart-leave"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/002-hcm-lite-ai-app/spec.md
 - specs/002-hcm-lite-ai-app/checklists/requirements.md
 - specs/001-hcm-hr-assistant/spec.md
 - history/prompts/002-hcm-lite-ai-app/001-hcm-lite-ai-app-spec.spec.prompt.md
tests:
 - none (specification only)
---

## Prompt

/sp.specify accorgint to the updated constitution

## Response snapshot

Created branch `002-hcm-lite-ai-app` and a new spec under constitution v3.1.0, superseding
001 (status line updated there). 7 user stories: P1 sign-in plus role dashboard (basic), P1
cited policy Q&A; P2 exact role-scoped figures, own leave balance; P3 smart leave with
explicit-confirm submission (pending only, no approval), AI dashboard summary, document refresh.
12 edge cases, 38 FRs (basic auth with lockout and expiry, persistent validated data with
versioned setup, Employee/Manager/HR Admin scoping, dashboard = assistant figures, RAG access
filtering before reasoning, audit, demo labels), 12 entities, 10 success criteria. Checklist
passes with 0 clarification markers. create-new-feature.ps1 again failed at the 3-argument
Join-Path (PS 5.1), so the prompts folder was created manually.

## Outcome

- ✅ Impact: Constitution-compliant spec ready for /sp.plan.
- 🧪 Tests: none
- 📁 Files: spec.md, checklists/requirements.md, 001 spec status line, this PHR
- 🔁 Next prompts: /sp.plan (MongoDB, Chainlit-as-UI decision, single auth)
- 🧠 Reflection: Confirm-button submission keeps the consequential action outside the model.

## Evaluation notes (flywheel)

- Failure modes observed: create-new-feature.ps1 Join-Path PS 5.1 bug (recurring)
- Graders run and results (PASS/FAIL): spec quality checklist PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): fix line 267 with nested Join-Path
