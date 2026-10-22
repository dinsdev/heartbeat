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

## 2026-10-22: A1 decided, purpose and success

**Decision (Din):** rigor leads, with the shipped browser model as the supporting proof. Reason: admissions readers have seen many "98% on MIT-BIH" projects; knowing where those numbers come from is what sets this one apart. Leading with raw performance would lead with the weakest numbers, since inter-patient recall on the rare classes is modest by nature.

**What a reader should come away believing:** Din knows where medical ML results get inflated, measured this one honestly, and shipped the model so you can watch it work.

**Success criteria (none depend on beating published numbers):**
1. 10-second read: in the stage iframe, a real ECG scrolls with beats labeled live, and one plain line says it is tested on patients it never saw.
2. The trap is shown, not just described: the case study makes patient leakage concrete (candidate: the C5 exhibit, honest number beside the inflated one).
3. Every claim is traceable: one command reproduces the numbers; a CI test proves no patient appears on both sides of the split.
4. The browser model is provably the same model: a parity test checks browser outputs against Python on fixed inputs, and the page says so.
5. Failures are named: a limits section says in plain words where the model fails.
6. The CNN and baseline comparison is reported straight, whichever way it goes (A3 decides what ships if the CNN loses).

**Not goals:** state-of-the-art numbers, clinical usefulness, more than one dataset in core.

**Finding:** PhysioNet's MIT-BIH page states the database has 48 records from 47 subjects and that "Records 201 and 202 originate from the same subject" (checked 2026-10-22). Claude recalls that de Chazal et al. (2004) put 201 in DS1 and 202 in DS2, which would leak one subject across the standard inter-patient split. Not yet verified against the paper; tracked under C1. Until C1 settles it, no page or doc states a count of unseen patients.
