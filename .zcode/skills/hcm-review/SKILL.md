---
name: hcm-review
description: Review HCM Lite code changes for constitution compliance and security (authorization, scoping, RAG injection, secrets, logging, leave-submission safety) — e.g. "review my changes", "check before commit", "security review T050". Delegates to the read-only hcm-reviewer subagent. HCM Lite repository only.
---

# HCM Lite: constitution and security review

Use this skill only inside the HCM Lite repository. When it is invoked, **do not review the code
yourself**. Delegate.

## 1. Determine scope

- Default: all uncommitted changes (`git status --short`).
- If the user named task IDs, files or a phase, pass those.
- If nothing has changed and no scope was given, say so and stop.

## 2. Delegate (automatic)

Call the **Agent** tool with `subagent_type: "hcm-reviewer"` (or, if that agent type is not
available in the current session, `general-purpose` with the full contents of
`.zcode/agents/hcm-reviewer.md` as binding instructions) and a prompt containing the scope
(file list or task IDs) and: "Apply your full checklist; cite file:line; severity per the
constitution; end with 'Ready to commit: yes/no'."

For a large change (more than 15 files), split it by layer (`hcm_lite/services` + `db`,
`hcm_lite/assistant` + `rag`, `app.py` + `ui` + `tests`) and send parallel reviewer calls in
one message, then merge the findings and drop duplicates.

## 3. Report to the user

- Present the reviewer's table with CRITICAL and HIGH first, and the "Ready to commit" verdict.
- If there are findings, offer to fix them via the **hcm-implement** skill (do not fix them
  automatically).
- Create the PHR required by `CLAUDE.md` (stage `misc`) under
  `history/prompts/002-hcm-lite-ai-app/`.
