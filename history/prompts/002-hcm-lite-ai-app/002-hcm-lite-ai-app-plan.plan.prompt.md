---
id: 002
title: HCM Lite AI App Plan
stage: plan
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: /sp.plan
labels: ["plan", "mongodb", "chainlit", "rbac", "rag", "smart-leave"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/002-hcm-lite-ai-app/plan.md
 - specs/002-hcm-lite-ai-app/research.md
 - specs/002-hcm-lite-ai-app/data-model.md
 - specs/002-hcm-lite-ai-app/quickstart.md
 - specs/002-hcm-lite-ai-app/contracts/agent-tools.md
 - specs/002-hcm-lite-ai-app/contracts/services.md
 - specs/002-hcm-lite-ai-app/contracts/ui.md
 - specs/002-hcm-lite-ai-app/contracts/cli.md
 - specs/002-hcm-lite-ai-app/contracts/configuration.md
 - CLAUDE.md
tests:
 - none (planning only)
---

## Prompt

/sp.plan update

## Response snapshot

Planned feature 002 under constitution v3.1.0. Chainlit is the single app UI (Art. III.2 rule
5), with login delegated to a MongoDB-backed AuthService (PBKDF2, lockout 5/15, idle expiry 60).
A role dashboard is rendered in the sidebar. MongoDB is accessed through pymongo async, with
versioned migrations, $jsonSchema validators, unique indexes and a guarded demo seed.
Repositories sit behind services; dashboard and agent tools share the same MetricsService.
Scoping: Employee=self, Manager=direct reports, HR Admin=all. 10 tools, no submit tool; leave
submission goes through a UI Confirm action → idempotent LeaveService.submit (pending, audited).
RAG uses Qdrant embedded with dual scope filtering. Tests: fakes plus a repository contract
suite, plus -m mongo and -m live. Constitution Check PASS; one accepted risk (no hackathon
brief). No web docs were fetched (the user declined); unconfirmed APIs are marked VERIFY-AT-IMPL.
CLAUDE.md was updated manually (the agent-context script previously only added a BOM).

## Outcome

- ✅ Impact: Phase 0/1 artifacts complete for 002; ready for /sp.tasks.
- 🧪 Tests: none
- 📁 Files: plan, research, data-model, quickstart, 5 contracts, CLAUDE.md
- 🔁 Next prompts: /sp.tasks; /sp.adr for MongoDB+service-layer+single-auth decisions
- 🧠 Reflection: MongoDB server absent locally; offline fakes keep work unblocked.

## Evaluation notes (flywheel)

- Failure modes observed: no local MongoDB/Docker; doc verification deferred
- Graders run and results (PASS/FAIL): Constitution Check PASS (1 accepted risk)
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
