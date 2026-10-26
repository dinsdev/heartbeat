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

## 2026-10-26: B1 decided (except the leak fix), records and lead

**Decisions (Din):**
- Exclude the four paced records (102, 104, 107, 217), as AAMI practice does. 44 records remain.
- Single lead, MLII, picked by signal name, never by channel index. Reason: one lead fits A2 (multi-lead is out) and a one-trace demo. PhysioNet's directory says 102 and 104 use V5 for the upper signal (both paced, so already out) and record 114 has its signals reversed, so MLII is the second channel there. A unit test covers 114.
- The leak fix is content: the case study says the standard split leaks one subject and that this project removed it.

**Verified (2026-10-26):**
- PhysioNet MIT-BIH directory (intro page): MLII upper signal in most records; V5 upper in 102 and 104; 114 reversed; paced records are 102, 104, 107, 217.
- de Chazal split, from secondary transcriptions (a 2025 systematic review, arXiv 2503.07276, and others; some papers print the lists with typos): DS1 = 101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230. DS2 = 100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234. So 201 (DS1) and 202 (DS2) do leak one subject. Check against the original paper under B5.
- AAMI class counts from PhysioNet's beat table (entire records; N = . L R e j, S = A a J S, V = V E, F = F, Q = / f Q). DS1: N 45866, S 944, V 3788, F 415, Q 8. DS2: N 44259, S 1837, V 3221, F 388, Q 7. These match the totals usually quoted for de Chazal's split, which also checks the mapping for B4.
- Record 201: N 1635, S 128, V 198, F 2. That is 13.6% of DS1's S beats and 5.2% of its V beats. Record 202: N 2061, S 55, V 19, F 1, which is 3.0% of DS2's S beats.

**Open (Din):** the proposed fix was to drop 201 from DS1, conditional on its beat counts. The counts show it costs 13.6% of the scarcest training class, so the choice went back to Din: drop 201 from DS1 (published test set kept exactly), or drop 202 from DS2 (training kept whole, test set one record off the published one).

## 2026-10-26: B1 leak fix and B2 decided

**Decision (Din), 201/202 leak:** drop 202 from DS2; 201 stays in DS1. Reason: 201 holds 13.6% of DS1's S beats and 97 of the 100 aberrated APC (`a`) beats in DS1, so dropping it would leave training almost blind to that S morphology. 202 is mostly normal beats (3.0% of DS2's S beats). The cost is a test set one record off the published DS2, which matters less since A3 made de Chazal context rather than a target.

**Resulting split:** DS1 has 22 records from 22 subjects; DS2 has 21 records from 21 subjects; no subject on both sides. The page may now say "tested on 21 patients it never saw". Published numbers quoted for context were measured on all 22 DS2 records, and the page says so.

**Implementation note for E5:** the leakage test works on subject IDs, not record IDs, with a subject map in which 201 and 202 share one subject. A record-level test would have missed this leak.

**Decision (Din), B2 beat locations:** core uses the database's expert beat annotations for training, evaluation and the demo. Reason: it isolates the classifier, matches common inter-patient practice, and A2 already places our own QRS detector at stretch 3.
- The limits section and model card say: "Beat locations come from the database's expert annotations, so these numbers assume every beat has already been found. A real device would also have to find them." The stage line stays short.
- The browser receives beat positions with the trace and only classifies.
- Annotations sit on the QRS's main peak, which is not always the R wave. Windows center on the annotation as given; B3 decides any realignment.
- No standalone detector score in core: it measures a different component and invites readers to multiply it into an end-to-end number that does not exist. Stretch 3 does the end-to-end version.

## 2026-10-26: B3 decided, preprocessing

**Rule:** anything the browser must repeat stays tiny, so the Python to browser parity test stays simple.

**Decisions (Din):**
- Signal: MLII in millivolts at the native 360 Hz, no resampling.
- Filter: 0.5 to 40 Hz Butterworth bandpass, zero-phase (forward and backward), applied once per record in Python. The browser receives the filtered trace, so the filter is never reimplemented in TypeScript and the demo shows the signal the model saw. The data card says the trace is filtered.
- Window: 256 samples per beat, 96 before the annotation (about 0.27 s) and 160 after (about 0.44 s). No R-peak realignment.
- Amplitude: per-window z-score (subtract the window mean, divide by its standard deviation). Tradeoff accepted: absolute amplitude is lost, but amplitude also varies between patients with electrode placement.
- RR features: pre-RR; post-RR; local average RR over the previous 10 beats; long average RR over the previous 5 minutes (both averages use only the past, expanding near a record's start); pre-RR divided by the local average; post-RR divided by pre-RR. Only post-RR looks ahead, by one beat.
- RR is computed over every annotated beat, including classes that are not scored, so a skipped beat never creates a false long interval. Which annotation symbols count as beats is set in B4.
- The first and last beat of each record are dropped (no full window or RR). No exclusion of noisy segments.

**Consequences:**
- Post-RR delays each label by one beat in the demo. The case study says so in one line.
- Suggestion carried to C3: the CNN takes the beat window plus the same RR features as the baseline, so the comparison reads "RR alone against RR plus learned beat shape".
- The feature set loosely follows de Chazal et al. (2004) from Claude's memory; verify under B5 before the page says so.
