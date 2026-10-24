---
id: 004
title: Cross-Artifact Consistency Analysis
stage: misc
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: /sp.analyze
labels: ["analyze", "consistency", "coverage", "constitution"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - history/prompts/002-hcm-lite-ai-app/004-cross-artifact-consistency-analysis.misc.prompt.md
tests:
 - none (read-only analysis)
---

## Prompt

/sp.analyze

(empty arguments)

## Response snapshot

Read-only analysis of spec/plan/tasks for 002 against constitution v3.1.0. 14 findings:
1 CRITICAL (C1: Art. I step 2 requires reading the hackathon brief before code; the brief is
absent and the plan only "accepts the risk"); 3 HIGH (G1: no implementation task for
role-specific starters (FR-014, only test T106); U1: no service method for the employee
profile and own-request list required by the US1 dashboard; G2: no prompt-extraction test
(Art. XIII/XVI)); 6 MEDIUM (I1 repo duplicate-key behaviour contradictory T015 vs T027; U2
DB-down at sign-in indistinguishable from bad password; G3 SC-009 performance unmeasured; U3
plan's models/requests.py has no task; U4 manager "late today" empty on weekends with seed
ending today−1; I2 chunk metadata lacks department vs Art. XI); 4 LOW. FR coverage 37/38
implementation (97%); 38/38 incl. tests. No files modified.

## Outcome

- ✅ Impact: Issues identified before /sp.implement; 1 critical blocker.
- 🧪 Tests: none
- 📁 Files: this PHR only
- 🔁 Next prompts: supply the brief or amend Art. I; apply remediation edits to spec/tasks
- 🧠 Reflection: Plan marked missing-brief as an accepted risk, but a MUST cannot be waived in planning.

## Evaluation notes (flywheel)

- Failure modes observed: test-only coverage masking a missing implementation task (starters)
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): add an "impl task exists" check to the coverage map
