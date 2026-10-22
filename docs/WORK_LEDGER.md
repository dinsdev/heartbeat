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

## 2026-10-22: A2 decided, scope cut

**Rule:** rigor leads (A1), so anything that proves honesty moves up and anything purely visual moves down.

**Core (the project does not publish without these):**
- MIT-BIH pipeline with the inter-patient split (corrected for 201/202 if C1 confirms the leak) and a CI leakage test.
- Baseline (RR features with logistic regression) and a small 1D CNN, on the same split.
- C5 honesty exhibit, promoted from open: the same CNN trained on a patient-mixed split, both numbers side by side. Reason: it is the project's punchline and costs only a second split through the same code.
- Model card: per-class precision and recall, confusion matrix, calibration, limits.
- ONNX export with parity tests from PyTorch to ONNX to the browser.
- Demo: scrolling ECG with live beat labels, patient switch, speed control, a stage mode for the iframe, a reduced-motion version.
- Case study, written last with real numbers.

**Stretch, in order:** (1) INCART external test, because a second hospital's data is a rigor claim; (2) saliency overlay; (3) our own QRS detector, if B2 uses reference annotations in core.

**Out:** visitor uploads and live device input; rhythm-level diagnosis and multi-lead models; large hyperparameter sweeps, ensembles, LLM explanations.

**PRD fix for F1:** the dins-projects PRD's "what visitors do" describes the saliency overlay, which is stretch. The Heartbeat PRD's visitor section describes the core demo only.

## 2026-10-22: A3 decided, pre-registration instead of targets

**Decision (Din):** no numeric results targets. Reason: a number to hit invites tuning toward it, which is the behavior this project calls out. Instead, a pre-registered evaluation plan is committed before any test-set run.

**Pre-registered plan (exact class set and calibration metric come from C4):**
1. Headline metrics: per-class recall and precision for S and V on unseen patients, and macro F1.
2. Uncertainty: 95% intervals from a bootstrap that resamples whole patients, not beats, because beats from one person are correlated and beat-level resampling gives falsely tight intervals.
3. Comparison: CNN minus baseline on each headline metric, with its own interval. "Better" means the interval sits above zero; otherwise the page reports no clear difference.
4. Context, not targets: de Chazal et al. (2004) results. Claude recalls about 76% S recall at about 38% precision and about 78% V recall; verify against the paper before any public use.

**Test discipline:**
- All iteration on DS1 with cross-validation by patient groups. DS2 stays sealed.
- Before the single DS2 run, a freeze record is committed: commit hash, config, model checksum.
- A bug found after the DS2 run is fixed and rerun, and both runs are logged here. No silent reruns.

**If the CNN loses or ties:** it ships as is and the demo still runs the CNN. The page says plainly that a simple baseline matched or beat it on unseen patients, and why that is plausible (RR intervals carry much of the S-class signal). DS2 is never used for tuning.
