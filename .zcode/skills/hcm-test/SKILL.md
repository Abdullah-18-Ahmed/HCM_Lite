---
name: hcm-test
description: Run and verify HCM Lite tests (offline incl. SQLite and API, live OpenAI) and record the real results — e.g. "run the tests", "verify T045", "are we green?", "run API tests". Delegates to the hcm-test-verifier subagent. HCM Lite repository only.
---

# HCM Lite: verify with tests

Use this skill only inside the HCM Lite repository. When it is invoked, **do not run pytest yourself**.
Delegate.

## 1. Determine what to run

- Default: the offline suite (`pytest -q`), which already includes the SQLite and FastAPI tests.
- Include `-m live` **only** if the user explicitly asks for live/OpenAI tests (they cost money).
- If task IDs are given, include the test files named in those tasks in
  `specs/002-hcm-lite-ai-app/tasks.md`.

## 2. Delegate (automatic)

Call the **Agent** tool with `subagent_type: "hcm-test-verifier"` (or, if that agent type is not
available in the current session, `general-purpose` with the full contents of
`.zcode/agents/hcm-test-verifier.md` as binding instructions) and a prompt listing the
suites and paths to run, plus: "Report passed/failed/skipped/not run per suite, map failures to
task IDs, append the run to checklists/demo-log.md, and never print secret values."

## 3. Report to the user

- The verifier's summary table and its verdict, exactly as reported.
- For failures, offer to fix them via the **hcm-implement** skill, naming the mapped task IDs.
- Never restate a suite as passing if the verifier marked it "not run".
- Create the PHR required by `CLAUDE.md` (stage `misc`) under
  `history/prompts/002-hcm-lite-ai-app/`.
