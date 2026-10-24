# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/sp.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [single/web/mobile - determines source structure]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates from `.specify/memory/constitution.md` (v3.0.0). Each MUST be checked or justified in
Complexity Tracking:

- [ ] **Authority (Art. I)**: Hackathon brief and existing repository inspected; mandatory features
      and team-owned interfaces identified; conflicts resolved in favour of the brief.
- [ ] **Technology (Art. III.1)**: Uses technologies required by the brief/repo; any new choice is
      documented; no existing technology replaced without justification.
- [ ] **UI decision (Art. III.2–3, XIII)**: Assistant interface chosen by the Art. III.2 rule order
      and documented; Chainlit (if used) is a presentation layer on the app's real identity; agent,
      tools, RAG and business logic are reusable independently of the UI.
- [ ] **Spec-first (Art. IV)**: Spec exists with permissions, interfaces, errors and test cases;
      out-of-brief modules not added.
- [ ] **Architecture (Art. V, XIV)**: Logical layers separated; existing services/endpoints reused;
      new endpoints defined in contracts with validated schemas and server-side authorization.
- [ ] **Agent & tools (Art. VI, VII)**: Tools validate input, verify identity/permissions, apply
      employee/team/department scope, use authoritative services; no success claimed without
      service confirmation.
- [ ] **Auth & RBAC (Art. VIII)**: Existing auth integrated (or justified new auth); Employee /
      Manager / HR Admin enforced in the backend; role/ID in chat or client never trusted.
- [ ] **Persistence (Art. IX)**: Persistent DB with migrations; labelled demo seed; any mock is
      clearly identified and replaceable; no hardcoded/in-memory data as the database.
- [ ] **Dashboards (Art. X)**: Required dashboards integrated; figures from backend queries only;
      RAG never used for live counts or balances.
- [ ] **RAG (Art. XI)**: Retrieval with metadata, access restrictions and citations; "not found"
      stated; no fabricated policy or citation.
- [ ] **Leave (Art. XII)**: No self-approval; submission only through the authorized workflow after
      confirmation, recorded and confirmed by the backend.
- [ ] **Secrets (Art. XV)**: Env-based config; `.env.example` placeholders; clear failure on missing
      essential config.
- [ ] **Security (Art. XVI)**: Least privilege, audit logging, safe errors; documents and user text
      treated as data, not instructions.
- [ ] **Testing (Art. XVII)**: Tests planned for auth, RBAC, persistence, dashboards, tools, RAG,
      agent failure paths, leave, UI-to-backend and end-to-end workflows.
- [ ] **Done (Art. XX)**: Demonstrable in the intended application, with setup docs.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/sp.plan command output)
├── research.md          # Phase 0 output (/sp.plan command)
├── data-model.md        # Phase 1 output (/sp.plan command)
├── quickstart.md        # Phase 1 output (/sp.plan command)
├── contracts/           # Phase 1 output (/sp.plan command)
└── tasks.md             # Phase 2 output (/sp.tasks command - NOT created by /sp.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
