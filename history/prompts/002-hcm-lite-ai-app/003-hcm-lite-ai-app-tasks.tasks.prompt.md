---
id: 003
title: HCM Lite AI App Tasks
stage: tasks
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: /sp.tasks
labels: ["tasks", "tdd", "mongodb", "auth", "rag", "smart-leave"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/002-hcm-lite-ai-app/tasks.md
 - history/prompts/002-hcm-lite-ai-app/003-hcm-lite-ai-app-tasks.tasks.prompt.md
tests:
 - none run; format validation script 110/110 valid
---

## Prompt

/sp.tasks using constitution.md

## Response snapshot

Generated 110 tasks in 10 phases for feature 002 under constitution v3.1.0: Setup 9 (incl. the
VERIFY-AT-IMPL smoke test and the MongoDB availability check), Foundational 35 (config, errors,
models, Mongo client/migrations/repositories/fakes/seed/CLI, audit, authz, auth with lockout,
agent runner, Chainlit login), US1 dashboard 11, US2 policy RAG 21, US3 figures 4, US4 balance
3, US5 smart leave with Confirm-action submit 10, US6 AI summary + guardrails 5, US7 refresh 5,
Polish 7. Tests come first in every phase (Art. XVII), with offline/mongo/live markers and a
repository contract suite run against both fake and Mongo. 58 tasks are marked [P]. Includes a
dependency table/graph, parallel examples, MVP strategy and FR coverage map. Format validated:
0 malformed, sequential T001–T110.

## Outcome

- ✅ Impact: Executable task list; basic app = T001–T055, AI MVP = + T056–T076.
- 🧪 Tests: none executed
- 📁 Files: tasks.md, this PHR
- 🔁 Next prompts: install MongoDB (T009); /sp.analyze; /sp.implement from T001
- 🧠 Reflection: AI phases carry most tasks (US2–US6 = 43) consistent with Art. II priority.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): checklist-format regex PASS (110/110)
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
