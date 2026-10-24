---
id: 007
title: Project Skills and Subagents
stage: misc
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: create project skills and subagents
labels: ["tooling", "skills", "subagents", "workflow"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - .claude/agents/hcm-implementer.md
 - .claude/agents/hcm-reviewer.md
 - .claude/agents/hcm-test-verifier.md
 - .claude/skills/hcm-implement/SKILL.md
 - .claude/skills/hcm-review/SKILL.md
 - .claude/skills/hcm-test/SKILL.md
 - CLAUDE.md
tests:
 - none (configuration files; not yet exercised)
---

## Prompt

now before implementing make three skills and make three subagents that will work only and help in the project development the skills will call the subagents automatically

## Response snapshot

Created three project-scoped subagents in .claude/agents/: hcm-implementer (test-first task
implementation under the constitution and conventions; marks tasks [x] only on passing tests),
hcm-reviewer (read-only constitution and security checklist with file:line findings and a
commit verdict), and hcm-test-verifier (runs offline/mongo/live suites, never prints secrets,
writes only demo-log.md). Each refuses work outside this repository. Created three skills in
.claude/skills/: hcm-implement (delegates to hcm-implementer, then automatically to
hcm-test-verifier and hcm-reviewer in parallel), hcm-review (→ hcm-reviewer, split by layer for
large diffs), and hcm-test (→ hcm-test-verifier; live tests only on explicit request).
Delegation uses explicit Agent-tool instructions in each skill body. Added a pointer section
to CLAUDE.md.

## Outcome

- ✅ Impact: Project-only development workflow ready for implementation.
- 🧪 Tests: none run; the skills and agents are not yet exercised
- 📁 Files: 3 agents, 3 skills, CLAUDE.md
- 🔁 Next prompts: /hcm-implement T001-T009
- 🧠 Reflection: Skills orchestrate; subagents do the work, keeping PHR creation in the main session.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): confirm the skills appear after a session reload
