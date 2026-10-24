---
id: 002
title: HCM HR Assistant Implementation Plan
stage: plan
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 001-hcm-hr-assistant
branch: 001-hcm-hr-assistant
user: Abdullah-18-Ahmed
command: /sp.plan
labels: ["plan", "rag", "qdrant", "openai-agents-sdk", "chainlit", "authz"]
links:
  spec: specs/001-hcm-hr-assistant/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/001-hcm-hr-assistant/plan.md
 - specs/001-hcm-hr-assistant/research.md
 - specs/001-hcm-hr-assistant/data-model.md
 - specs/001-hcm-hr-assistant/quickstart.md
 - specs/001-hcm-hr-assistant/contracts/agent-tools.md
 - specs/001-hcm-hr-assistant/contracts/ingestion-cli.md
 - specs/001-hcm-hr-assistant/contracts/configuration.md
 - specs/001-hcm-hr-assistant/spec.md
 - specs/001-hcm-hr-assistant/checklists/requirements.md
 - CLAUDE.md
tests:
 - none (planning only)
---

## Prompt

/sp.plan

(empty arguments)

## Response snapshot

The open clarifications (Q1 roles, Q2 data source) were unanswered, so the recommended defaults
(A/A) were applied and recorded in the spec under Clarifications. Verified package versions
via pip index and SDK/Chainlit/Qdrant APIs via the official docs. Key decisions: a single
Agent[AppContext] with 10 tools; Qdrant embedded local mode with server mode via URL; OpenAI
embeddings; CSV demo exports behind an HRDataProvider; a role matrix enforced in code before
retrieval, plus dual scope filtering; deterministic guardrails; an error taxonomy and limits.
Found that the constitution's `agents/` folder shadows the SDK's `agents` module, so it was
renamed `hcm_lite/assistant/` (recorded in Complexity Tracking). Constitution Check PASS
before and after design. update-agent-context.ps1 only added a BOM to CLAUDE.md (no markers),
so that change was reverted and an Active Technologies section was added manually.

## Outcome

- ✅ Impact: Phase 0/1 artifacts complete; ready for /sp.tasks.
- 🧪 Tests: none
- 📁 Files: plan, research, data-model, quickstart, 3 contracts, spec/checklist updates, CLAUDE.md
- 🔁 Next prompts: /sp.adr for vector store + data source + authz; /sp.tasks
- 🧠 Reflection: Defaults applied without explicit user answers; flagged for user override.

## Evaluation notes (flywheel)

- Failure modes observed: update-agent-context.ps1 truncates multi-line plan fields and inserts a BOM
- Graders run and results (PASS/FAIL): Constitution Check PASS (pre and post design)
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): keep Technical Context values on single lines
