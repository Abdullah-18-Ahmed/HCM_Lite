---
name: hcm-implement
description: Implement HCM Lite tasks from specs/002-hcm-lite-ai-app/tasks.md (e.g. "implement T023", "build phase 2", "do the next task"). Delegates the work to the hcm-implementer subagent, then automatically runs hcm-test-verifier and hcm-reviewer on the result. HCM Lite repository only.
---

# HCM Lite: implement tasks

Use this skill only inside the HCM Lite repository. When it is invoked, **do not write the code
yourself**. Orchestrate the project subagents as follows.

## 1. Select the tasks

- If the user gave task IDs or a range (e.g. `T019-T025`, "phase 2"), use those.
- If they said "next", pick the first unchecked tasks in `specs/002-hcm-lite-ai-app/tasks.md`
  whose dependencies are all checked. Group up to 5 tasks that share a phase.
- Confirm the selection in one line before delegating (no question unless the selection is
  ambiguous).

## 2. Delegate implementation (automatic)

Call the **Agent** tool with `subagent_type: "hcm-implementer"` (or, if that agent type is not
available in the current session, `general-purpose` with the full contents of
`.zcode/agents/hcm-implementer.md` as binding instructions) and a prompt containing:
- the exact task IDs and their full task text copied from `tasks.md`,
- "Follow `.specify/memory/constitution.md` and the Conventions section of tasks.md; tests first;
  mark tasks [x] only if their tests pass; report files changed and exact test results."

Independent `[P]` tasks touching different files may be sent as parallel calls in one message.
Dependent tasks go sequentially.

## 3. Verify (automatic, after the implementer returns)

Call the **Agent** tool with `subagent_type: "hcm-test-verifier"` (or `general-purpose` with
`.zcode/agents/hcm-test-verifier.md` as binding instructions), asking it to run the offline
suite plus the test files named in those tasks, and to log the results.

## 4. Review (automatic, in parallel with step 3)

Call the **Agent** tool with `subagent_type: "hcm-reviewer"` (or `general-purpose` with
`.zcode/agents/hcm-reviewer.md` as binding instructions) on the files the implementer changed.

## 5. Report to the user

- Tasks completed / not completed, with reasons.
- Test results exactly as the verifier reported them (passed / failed / skipped / not run).
- Reviewer findings at CRITICAL or HIGH severity. If any exist, say the tasks are **not done** and
  offer to send the findings back to hcm-implementer.
- Then create the PHR required by `CLAUDE.md` (stage `green`, or `red` if tests were only written
  and are failing) under `history/prompts/002-hcm-lite-ai-app/`.

Never report a task as complete unless the verifier's results show its tests passing.
