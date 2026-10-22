# Heartbeat: Work ledger

## 2026-10-22: Planning kickoff

**Context:** Heartbeat is one of the four dins.dev portfolio projects. Cross-project requirements live in `~/Develop/dins-projects/docs/PRD.md` (section 7 is Heartbeat). This session plans the project fully; nothing gets built.

**Decisions (Din):**
- Planning ledger accepted as drafted. It lives in `docs/TASKS.md` as Phase 0; each item is closed here with its reason.
- D1, integration with dins.dev: the demo is a standalone web app shown in an iframe on the dins.dev stage. Clicking it opens the case study, which links to the live demo. Reason: keeps the demo independent of the site build and lets one pattern serve all four projects.
- The schedule in the dins-projects plan is a best-case recommendation, not a deadline.

**Work done:** `git init` in `~/Develop/heartbeat`; `docs/TASKS.md` and this ledger written.

**Notes to reconcile:**
- The site PRD (`~/Develop/dins.dev/docs/site/PRD.md`, `/work/<project>`) says the case study "opens with the project's window and live demo". D1 has the case study link to the live demo. Settle which (the iframe at the top, a link, or both) under G1.
- The dins-projects ledger says the MIT-BIH citations were recorded in the heartbeat README. That README went with the removed scaffold, so the citations get rewritten under B5.
- The dins-projects plan still reads "Order of work (to the December 1 content freeze)". Din now treats that schedule as best case; the dins-projects session can update the wording.

**Handoff:** A1 (purpose and success) in progress.
