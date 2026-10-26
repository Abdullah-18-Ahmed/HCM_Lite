---
id: 011
title: UI Polish And Chat Isolation Fix
stage: green
date: 2026-10-26
surface: agent
model: claude-opus-4-8
feature: 002-hcm-lite-ai-app
branch: 002-hcm-lite-ai-app
user: Abdullah-18-Ahmed
command: fix UI, fix chat history leak, remove launcher
labels: ["ui", "bugfix", "session-isolation", "frontend"]
links:
  spec: specs/002-hcm-lite-ai-app/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - hcm_lite/api/static/app.js (resetAppState on login+logout; GET-body login fix retained)
 - hcm_lite/api/static/styles.css (anti-clipping + polish overrides)
 - deleted run-hcm-lite.bat
tests:
 - verified server (health 200) serves updated app.js/styles.css
 - confirmed server-side conversation store is keyed by (user_id, cid): no cross-user leak
---

## Prompt

fix the UI and make it look better in some places the text is cutting also the AI assistant is
showing previous history in all logins hr can see employee history fix that too after completing
give credentials and site link and also remove the hcm batch lite system i want it working
without it normally

## Response snapshot

Investigated the "HR sees employee history" report: the server (conversations.py) keys
conversations by (user_id, cid) and get() only returns the owner's — no backend leak. The cause
was client-side: logout()/login did not clear the chat DOM, suggested chips, or the cid, so the
previous user's bubbles stayed visible in the same browser tab. Added resetAppState() and call it
in both enterApp() and logout(), wiping chat log, suggested, cid, dashboard and leave grids, and
the input. Text-clipping: grid/flex children defaulted to min-width:auto and overflowed the
cards' overflow:hidden; added min-width:0 to grid children and .stat, overflow-wrap:anywhere on
titles/values/messages, a flexible bar-row label column, wrapping profile/draft values, and
general spacing polish. Removed run-hcm-lite.bat per request. Server already running on :8001 and
confirmed serving the updated files; static changes need only a browser hard refresh.

## Outcome

- ✅ Impact: No stale chat across logins; clipping fixed; launcher removed.
- 🧪 Tests: static-only change; server serves updated files; conversation isolation verified by code read
- 📁 Files: app.js, styles.css; deleted run-hcm-lite.bat
- 🔁 Next prompts: optional public deployment; polish T115–T121; update stale Chainlit text in specs/README
- 🧠 Reflection: The reported "leak" was a UI state bug, not a data breach — always confirm the server boundary before alarming.

## Evaluation notes (flywheel)

- Failure modes observed: SPA did not reset per-user UI state on logout
- Graders run and results: manual served-file check PASS
- Prompt variant: none
- Next experiment: add a Playwright/browser test for logout clearing chat
