---
id: 008
title: Switch to SQLite and FastAPI
stage: misc
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: /sp.implement (mid-run architecture change)
labels: ["architecture-change", "sqlite", "alembic", "fastapi", "constitution-v4", "phase-1"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - .specify/memory/constitution.md
 - specs/002-hcm-lite-ai-app/spec.md
 - specs/002-hcm-lite-ai-app/plan.md
 - specs/002-hcm-lite-ai-app/research.md
 - specs/002-hcm-lite-ai-app/data-model.md
 - specs/002-hcm-lite-ai-app/quickstart.md
 - specs/002-hcm-lite-ai-app/tasks.md
 - specs/002-hcm-lite-ai-app/contracts/api.md
 - specs/002-hcm-lite-ai-app/contracts/services.md
 - specs/002-hcm-lite-ai-app/contracts/cli.md
 - specs/002-hcm-lite-ai-app/contracts/configuration.md
 - .chainlit/config.toml
 - CLAUDE.md
 - .claude/agents/hcm-implementer.md
 - .claude/agents/hcm-reviewer.md
 - .claude/agents/hcm-test-verifier.md
 - .claude/skills/hcm-test/SKILL.md
 - (Phase 1 by hcm-implementer) requirements*.txt, .gitignore, .env.example, pytest.ini, chainlit.md, tests/unit/test_api_smoke.py, package skeleton
tests:
 - tests/unit/test_api_smoke.py: 22 passed (reported by hcm-implementer; independent verification running)
---

## Prompt

/sp.implement
mongodb://localhost:27017/ cant connect but the databse is there in mongodb compass
leave mongodb use fast-api
(answers) Storage: SQLite (Recommended); FastAPI role: Backend API + keep Chainlit UI (Recommended)
update all the contitution plan task plus others too
continue

## Response snapshot

Diagnosed MongoDB: no local mongod/service/port; the Compass connection is Atlas (srv). The owner
then dropped MongoDB for SQLite + FastAPI (backend API, Chainlit kept). Constitution 3.2.0 →
4.0.0 (MAJOR): III.4 now SQLite/SQLAlchemy 2 async/Alembic + FastAPI; IX.1 rewritten as SQLite
rules (constraints, Alembic-only schema, foreign_keys ON, real-DB tests); VIII adds a JWT entry
point (sub only); XV uses DATABASE_URL/API_JWT_SECRET. The spec adds US8 (programmatic
interface), FR-039–041 and SC-011. Plan, research (D-01…D-14, verification section kept),
data-model (SQL tables with CHECK/UNIQUE/FK), the new contracts/api.md, services/cli/config,
quickstart, CLAUDE.md and the subagents/skill were all updated. The running hcm-implementer was
redirected and finished Phase 1 (T001–T008) on the new stack (pymongo uninstalled; reported 22
smoke tests passing; all VERIFY-AT-IMPL items resolved, e.g. agents.function_tool,
Qdrant query_points, Chainlit sidebar/actions/on_logout). Chainlit file upload was disabled.
tasks.md was regenerated: 121 tasks, T001–T008 done, MongoDB T009 removed, a US8 API phase
added, all formats valid. Verifier and reviewer were launched on Phase 1.

## Outcome

- ✅ Impact: Architecture switched consistently across all artifacts; Phase 1 implemented.
- 🧪 Tests: 22 smoke tests reported passing; independent verification pending
- 📁 Files: see list
- 🔁 Next prompts: Phase 2 Foundational (T009–T045) via /hcm-implement
- 🧠 Reflection: Redirecting the running subagent avoided concurrent edits to shared files.

## Evaluation notes (flywheel)

- Failure modes observed: the requested database was unreachable; a mid-run stack change
- Graders run and results (PASS/FAIL): tasks format 121/121 PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
