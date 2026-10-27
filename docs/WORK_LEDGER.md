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

## 2026-10-26: B4 decided, class mapping, and an A3 addendum

**Finding (PhysioNet beat table, entire records, DS2 without 202):**

| Class | DS1 | DS2 |
|---|---|---|
| N | 45866, spread across 22 records | 42198, spread across 21 records |
| S | 944; record 209 holds 41% | 1782; record 232 holds 78% |
| V | 3788; largest record (208) holds 26% | 3202; 233 and 200 hold 26% each |
| F | 415; record 208 holds 90% | 387; record 213 holds 94% |
| Q | 8 | 7 |

Pooled S recall on DS2 is mostly patient 232's recall, and F is one patient on each side.

**Decisions (Din):**
- Mapping (AAMI EC57): N = N, L, R, e, j; S = A, a, J, S; V = V, E; F = F; Q = /, f, Q. Any unrecognized annotation symbol makes the pipeline fail loudly; a test covers it. These symbols are the beats used for RR (B3). Not beats: flutter waves `!` (472, all in 207), non-conducted P waves `x`, and noise and rhythm markers.
- Four scored classes: N, S, V, F. Q beats are out of training and scoring (8 in DS1 cannot teach anything) but count for RR. The demo marks them grey as "not scored"; the data card gives the count (15).
- F stays a class but is never a headline. The limits section says F is one patient on each side. Dropping F would push those beats into wrong classes.

**A3 addendum (pre-registered now, before any DS2 run):**
1. Secondary line beside the headline: S recall and precision on DS2 with record 232 left out, with the same patient bootstrap.
2. Model card table: S and V recall per DS2 patient.
Reason: one patient carries the pooled S number. Added after results, this would read as an excuse; added before, it is what pre-registration is for. Final wording under C4.

## 2026-10-26: B5 decided, data download and attribution

**Decisions (Din):**
- Download only the 132 files the project uses (`.hea`, `.dat`, `.atr` for the 44 records) over HTTPS from `https://physionet.org/files/mitdb/1.0.0/`, with a small downloader of our own. wfdb only reads; it does not check file checksums.
- A pinned manifest of the 132 SHA256 values, copied once from PhysioNet's `SHA256SUMS.txt`, is committed. Every run checks the cache against it and stops on a mismatch.
- Cache in `data/raw/mitdb/1.0.0/`, gitignored. Downloads skip files whose checksums already match, so rebuilds work offline after the first run.
- Attribution under ODC-By 1.0: `DATA_LICENSE.md` in the repo; a short line on the demo (in the stage iframe if it fits, otherwise in its about text); a credits block in the case study and data card; an attribution note shipped beside the demo's data files, which are derived from the database.
- Citations: Moody GB, Mark RG, "The impact of the MIT-BIH Arrhythmia Database", IEEE Eng in Med and Biol 20(3):45-50 (2001); PhysioNet's standard citation, now Pollard et al. (2026), "PhysioNet as a global platform for biomedical research", Nature Health, https://doi.org/10.1038/s44360-026-00096-z; dataset DOI 10.13026/C2F305; de Chazal P, O'Dwyer M, Reilly RB, "Automatic classification of heartbeats using ECG morphology and heartbeat interval features", IEEE Trans Biomed Eng 51(7):1196-1206 (2004); AAMI EC57. Recheck PhysioNet's requested citation at G1, since it changed recently.

**Verified (2026-10-26):**
- PhysioNet page: version 1.0.0 (2005), ODC-By 1.0, 104.3 MB uncompressed, per-file SHA256 in `SHA256SUMS.txt`.
- de Chazal abstract (indexed by TARA and eDeposit Ireland): 44 non-paced records, two sets of 22 records and about 50,000 beats each; on the second set, S sensitivity 75.9% and positive predictivity 38.5%, V sensitivity 77.7% and positive predictivity 81.9%. This confirms the figures recalled in A3.
- New from the abstract: de Chazal's feature sets come from two ECG leads. Any context comparison on the page says their numbers come from a two-lead classifier tested on all 22 DS2 records; ours is one lead on 21.

**Not verified:** the full text. TARA serves the PDF behind a Cloudflare bot check, and Claude does not get past those; eDeposit Ireland exposes no direct file link. The DS1 and DS2 record lists still rest on secondary transcriptions plus our matching class totals, and the RR feature details on memory. Din can download the PDF in a browser and hand it over; until then the page states only what the abstract supports.

## 2026-10-26: C1 decided, folds and the sealed test set

**Decisions (Din):**
- Development uses 5-fold `StratifiedGroupKFold` on DS1, grouped by subject and balanced by class as far as groups allow, with a fixed seed. The fold assignment is a committed file. 22 subjects give 4 or 5 per fold. Leave-one-subject-out was not chosen: one-patient validation folds make the spread between folds noise, and it costs four times the training runs.
- Known limit: F cannot be balanced (208 holds 90% of DS1's F), so folds without 208 in training see almost no F. Reported, not engineered around.
- Development metrics come from pooled out-of-fold predictions (each beat predicted by the model that did not train on its patient), plus the spread across folds.
- No early stopping on validation folds. Folds train to a fixed maximum, one epoch count is chosen from the averaged validation curves, and the final model retrains on all of DS1 for that many epochs. Choosing the epoch on out-of-fold numbers makes them slightly optimistic; stated, not hidden. Calibration is fitted on out-of-fold predictions (details in C4).
- The data loader enforces the split: training and cross-validation code cannot load DS2 records, and a test checks it. Only the `evaluate-test` command reads DS2.
- `evaluate-test` refuses to run without a freeze record (A3) matching the commit hash, config and model checksum. The baseline and the CNN are frozen and tested in the same run. Every run is appended to a log, so the no-silent-rerun rule is enforced in code.
- Leakage tests work on subjects: none on both sides of DS1 and DS2, none on both sides of any fold. 201 and 202 share one subject ID.
- The demo is built and tuned on DS1 recordings. It switches to DS2 patients only after the sealed run, using the frozen model, because producing predictions on DS2 is a use of the test set. This ordering goes into `docs/PLAN.md` (F2).

## 2026-10-26: C2 decided, the baseline

**Rule:** the baseline gets the same data, folds, tuning budget and reporting as the CNN. An under-tuned baseline is the quiet way a CNN gets made to look good.

**Decisions (Din):**
- Inputs: the six RR features from B3, nothing else. With the C3 suggestion, the comparison reads "rhythm alone against rhythm plus learned beat shape".
- Model: multinomial logistic regression over N, S, V, F (scikit-learn, `lbfgs`).
- Features: log of the two ratio features (prematurity is multiplicative); all features standardized with a scaler fitted inside each training fold, in an sklearn pipeline.
- Imbalance: `class_weight="balanced"`. C3 should use the same weighting.
- Tuning: C from five log-spaced values, 0.01 to 100, on the C1 folds, by pooled out-of-fold macro F1.
- Prediction: argmax of the probabilities. Calibration and reporting (C4, the A3 bootstrap and addendum) are the same as for the CNN.
- Expected: reasonable on S (early beats), weak at separating V from S, near useless on F. That gap is what learned shape should fill; if the CNN cannot beat this, A3 covers it.
- Not doing: a second, hand-built morphology baseline (A2 sets one baseline; de Chazal's numbers already give that context). The baseline does not ship to the browser.

## 2026-10-26: C3 decided, the CNN

**Rule:** small enough to be boring in the browser; the same advantages as the baseline, no more.

**Decisions (Din):**
- Inputs: the 256-sample z-scored window (B3) and the same six RR features as the baseline, with log ratios, standardized with the training scaler. The scaler's 12 numbers ship with the model and are covered by the parity test.
- Architecture: four blocks of Conv1d (kernel 7), batch norm, ReLU and max-pool by 2, channels 16, 32, 64, 64; global average pooling; the six RR features concatenated; a 64-unit layer with dropout 0.3; four outputs. About 52k parameters (about 210 KB as float32) at width 1, about 800 KB at width 2. Batch norm is folded into the convolutions at export.
- Loss: cross-entropy with the same balanced class weights as the baseline. In DS1 these are about N 0.28, S 13, V 3.4, F 31, so each F beat weighs about 110 times a normal beat, and 90% of F is patient 208. Overfitting to 208 is a known risk, left visible in the CV curves and covered by the F caveat, not tuned around.
- Augmentation, fixed and untuned: random time shift of up to 5 samples each way, and light Gaussian noise. No amplitude scaling (the z-score cancels it).
- Optimizer: AdamW, learning rate 1e-3, weight decay 1e-4, batch 256, constant rate, since the epoch count is chosen after the folds (C1) and a schedule tied to total epochs would differ in the final retrain.
- Tuning: width multiplier 0.5, 1 or 2, plus the epoch count, on the C1 folds by pooled out-of-fold macro F1. 3 configurations times 5 folds, 15 runs. Seeds and repeats: C6.
- Not doing: a shape-only CNN. The "rhythm against rhythm plus shape" comparison carries the story.

## 2026-10-26: C4 decided, metrics and calibration (completes the pre-registration)

**Headline metrics:**
1. S and V recall and precision on the 21 DS2 patients (A3).
2. Macro F1 over N, S and V as the headline, with four-class macro F1 beside it. Reason: DS2's F is 94% one patient (213), so a four-class headline lets one person swing the average and the CNN-minus-baseline interval. F stays visible beside it. Decided before any result, so it is not a choice made after seeing numbers.
3. Secondary: false positive rate for S and V, for a like-for-like comparison with de Chazal.
4. A3 addendum, final wording: "S recall and precision on DS2 without record 232, with intervals from a bootstrap over the remaining 20 patients" and "Model card: a per-patient table of S and V results".
5. Per-patient table: every cell shows raw counts ("41 of 50"); a percentage appears only when the patient has at least 10 beats of that class, otherwise counts only with a footnote.

**Bootstrap:** resample the 21 DS2 patients with replacement, 10,000 draws, fixed seed, percentile intervals. Paired: CNN and baseline are scored on the same draws. If a draw has no predicted S beats, S precision is undefined for it; that draw is skipped for that metric only and the skip count is reported.

**Calibration:**
- Labels are the argmax of the weighted model's outputs (C2, C3). Calibration never changes a label.
- Probabilities: subtract the log class weights from the logits (logit adjustment, undoing the deliberate inflation of rare classes from balanced weighting), then apply one temperature fitted on DS1 out-of-fold predictions. Same procedure for both models. Consequence: the demo can say "flagged as S, estimated probability 30%", because rare classes are flagged below 50% on purpose.
- Metrics: one-vs-rest calibration error for S and V with 10 equal-mass bins (headline), reliability diagrams, and log loss and Brier score in the model card.
- Stated limit: calibration depends on class prevalence, which varies widely between patients, so calibrated probabilities are fragile across patients.

**Model card also has:** a four-by-four confusion matrix with the 7 Q test beats noted as not scored; N and F recall and precision with the F caveat.

## 2026-10-26: C5 decided, the honesty exhibit

**Rule:** a skeptical reader should find exactly one difference between the two numbers: whether a patient's beats can land on both sides.

**Rejected design:** pooling all 43 records and splitting beats at random. It trains on DS2 patients (breaking the seal) and compares different patient sets.

**Decisions (Din):**
- The exhibit runs inside DS1 only. Honest side: the C1 patient-grouped folds. Leaky side: beat-level random 5-fold (`StratifiedKFold` on beats). Same 22 patients, beats, code and seeds.
- Same configuration on both sides: the width and epoch count chosen on the honest folds, with no retuning on the leaky side. A real leaky project would also tune on leaky validation, so the gap shown is if anything conservative; the case study says so.
- Kept on purpose: neighboring beats' windows overlap in time, so random beat splits put overlapping signal on both sides. That is what random beat splitting does in the work being critiqued; the case study names it in one line.
- Both the CNN and the baseline get the exhibit (a small widening of A2's "the same CNN"). Expectation: leakage inflates the CNN far more, because it can memorize each patient's beat shapes.
- Metrics: the usual headline metrics with patient-bootstrap intervals on both sides, plus accuracy, shown only in the exhibit and labeled as the number papers often lead with.
- Timing: DS1 only, so it can run during development. Its design is pre-registered here.
- Case study wording sketch: "Same model, same 22 patients, same code. The only change: whether beats from one person can land in both training and testing." Then the two rows, then the DS2 headline as the real answer.

## 2026-10-26: C6 decided, tracking, seeds and determinism

**Decisions (Din):**
- No tracking service (about 20 development configurations do not justify one). Each run writes `runs/<time>-<short commit>-<name>/`: resolved config, commit hash with a dirty flag and diff hash, library versions, lockfile hash, device, metrics, out-of-fold predictions, checkpoint and log. `runs/` is gitignored. Anything the page uses is copied into committed `results/` (small JSON and figures) by the rebuild command, never by hand.
- Sealed-run log: committed, append-only `results/test_runs.jsonl`, plus a ledger entry per DS2 run. Development runs may start on a dirty tree (recorded); `evaluate-test` refuses one.
- Seeds: one master seed per run, with Python, NumPy, PyTorch, augmentation and shuffling seeds derived from it. The fold file has its own seed, independent of training seeds.
- Development runs seeds 0, 1 and 2 for every configuration; width is chosen on the seed mean (3 widths x 5 folds x 3 seeds = 45 CNN runs; the baseline is deterministic, one run).
- Seed 0 is the shipped model, fixed now. The single sealed run evaluates all three final models: headline numbers are seed 0, and one secondary line gives the range across seeds 1 and 2.
- Final and frozen models train on CPU with PyTorch deterministic mode; development may use MPS. Data loads in a single process (`num_workers=0`).
- Claims: retraining reproduces the frozen model bit for bit on the same machine and setup, and within a small tolerance elsewhere; inference with the shipped ONNX model reproduces the reported metrics exactly. E5 turns both into tests.

## 2026-10-27: C7 decided, compute

**Measured (2026-10-26, Apple M5, 16 GB, PyTorch 2.14.1, synthetic data the size of one training fold, about 41,000 beats, batch 256, 4 CPU threads by default):**

| Width | Parameters | MPS per epoch | CPU deterministic per epoch |
|---|---|---|---|
| 0.5 | 14,724 | 0.9 s | 8.9 s |
| 1 | 52,036 | 1.3 s | 17.9 s |
| 2 | 196,548 | 3.3 s | 59 s |

At a 40-epoch cap, the 45 development runs take about an hour on MPS. The three frozen final models (all of DS1, CPU) take about half an hour at width 1, about 2 hours at width 2. Caveat: synthetic tensors in memory skip data-loading cost; real data is also preloaded (C6), so timings should be close.

**Decisions (Din):**
- Mac only; no rented GPU.
- Development and cross-validation numbers, including the C5 exhibit and the out-of-fold metrics on the page, run on MPS and reproduce within tolerance.
- Frozen models train on CPU in deterministic mode (C6). The run folder records the PyTorch thread count, since it can change floating-point results.
- CI runs smoke tests only: a few training batches, the leakage tests, parity on fixed inputs (E5, E6).
- Noted for E4, not decided: a fast default rebuild (MPS, within tolerance) and an `--exact` mode (CPU, a few hours).

## 2026-10-27: C8 decided, stretch entry rules (section C complete)

**INCART facts (PhysioNet incartdb 1.0.0, checked 2026-10-27):** ODC-By 1.0; 794.5 MB; 75 records of 30 minutes from 32 patients (patient number in each header; several records per patient); 257 Hz; 12 standard leads (standard lead II, not MIT-BIH's modified lead II); no paced patients; beat annotations placed by an algorithm near the middle of the QRS using all 12 leads, then corrected, with locations not manually aligned; DOI 10.13026/C2V88N; PhysioNet asks for the Pollard et al. (2026) citation.

**Decisions (Din), all stretch items:**
1. Stretch starts only when core is publishable: sealed DS2 run done and logged, model card filled, demo passing the acceptance checks (stage, full width, phone, light and dark, keyboard, reduced motion), case study drafted with real numbers, CI green. Din gives the go per item; Claude gives a time estimate then.
2. Each item has a short design note committed before its first result.
3. Each item ships whole (tests, page text, a line in the limits section) or not at all.

**INCART (stretch 1), pre-registered now:**
- Test the shipped seed-0 model as frozen: no retraining, fine-tuning, threshold change or calibration refit.
- All 75 records; C4 metrics (S and V recall and precision, macro F1 over N, S, V with four-class beside it, calibration error); bootstrap over the 32 patients, not the records.
- Run once, logged in `results/test_runs.jsonl`. A drop is reported, never tuned away.
- Left to its design note, fixed before any INCART prediction: resampling 257 to 360 Hz, the lead, and the annotation offset (Claude's lean: snap each annotation to the nearest peak so both datasets follow one convention, decided blind and stated on the page).

**Saliency (stretch 2):** ONNX Runtime Web runs inference only (no gradients), so saliency is precomputed in Python and shipped, or computed by occlusion in the browser. The design note includes a randomized-weights sanity check, and the page says "where the output was most sensitive", never "what the model looked at".

**Own QRS detector (stretch 3):** scored end to end. Detections are matched to reference beats within 150 ms (AAMI); misses and extra detections are counted. Details in its design note.

## 2026-10-27: D1 amended, how the demo meets dins.dev

**Conflict found:** the dins.dev site plans (`~/Develop/dins.dev/docs/site/plans/`, read 2026-10-27) do not support an iframe on the home stage. M1's `ProjectWindow` and M4's stage hold the capture image or a `<video>`, and "Pause demos" only pauses videos. `demo.src` must be a site path (a test rejects outside URLs). M5's policy allows only Turnstile in `frame-src`. The case study already plans an "Open the live demo" button below its window.

**Decision (Din), replacing the stage part of the 2026-10-22 D1 decision:**
- Home stage: a 16:10 video recorded from the real demo (G2). The site already handles it, including the calm version, poster frame and "Pause demos". A1's 10-second read holds: a real ECG scrolling with beats labeled, plus the one plain line.
- Case study: the live demo in an iframe at the top, which matches the site PRD ("opens with the project's window and live demo") and settles the note left for G1.
- Full demo at `https://heartbeat.dins.dev`: its own Cloudflare Worker with static assets, deployed from this repo, so the demo stays independent of the site build and one pattern serves all four projects.
- Reason: the home page budget (100 KB first-party JavaScript, 60 fps, no task over 50 ms) is at real risk from three or four live iframes loading ONNX Runtime's WebAssembly on scroll, and pausing cross-origin iframes would need a postMessage protocol. The live claim is proven where readers look closely: the case study, the demo, the parity test.

**Heartbeat side:**
- `?embed=page` (case study iframe: no page chrome, muted) alongside the full page. `?embed=stage` is not needed for the home stage now; the stage capture is recorded from the full demo or the page embed.
- Response headers: `Content-Security-Policy` with `frame-ancestors https://dins.dev` plus the site's preview hostnames (exact names settled at build time), and `'wasm-unsafe-eval'` in `script-src` so ONNX Runtime Web can run.
- Reduced motion is respected inside the iframe (the media query reflects the viewer's setting).
- To confirm in E1: Workers custom domain on a subdomain, on the free plan.

**Changes for the dins.dev repo (logged here, not made; tracked as G4):**
1. `demo.src` in the `projects` schema accepts `https://heartbeat.dins.dev` (an allowlist of demo origins, not any URL).
2. The case study renders a `live` demo as an iframe in its window; the home stage keeps the capture or video.
3. The site's `frame-src` allows the demo origin.

## 2026-10-27: D2 decided, front-end stack

**Decisions (Din):**
- Svelte 5 with Vite as a single-page app, no SvelteKit: one page, two modes (full and `?embed=page`), no routing or server rendering needed. Reason: the demo has real interface (patient picker, speed, play and pause, a live accessible data table, labels and limits text), and Svelte's reactivity keeps that simple with a small runtime. It matches the site's islands.
- The ECG trace is a plain TypeScript canvas module outside Svelte: per-frame drawing, testable alone, mirroring the site's Ottie player.
- ONNX Runtime Web runs in a Web Worker, so model loading and inference stay off the main thread. The parity test (E5) exercises the same path.
- Tooling as on the site (Node 24 LTS, pnpm, TypeScript 6.0, Vitest 4.1, Playwright 1.64 with axe, Prettier, ESLint), re-checked in E1 and pinned for this repo in E2.
- Brand: `brand/tokens/tokens.css` and the font files are copied from `~/Develop/dins.dev/brand/` with the source commit recorded, so the case study iframe looks native without depending on the site's deploys. A small check script flags drift.
- Not chosen: React (heavier, differs from the site), Astro (content-first; this is one interactive canvas).

## 2026-10-27: D3 decided, live inference in the browser

**Rule:** A1 says the browser model is provably the same model; the page should show it, not only CI.

**Decisions (Din):**
- Live inference in the full demo and the case study iframe; every label shown is computed in the visitor's browser by the shipped ONNX model.
- The browser does the per-beat pipeline after filtering: cut and z-score the 256-sample window from the shipped filtered trace, compute the six RR features from the shipped beat positions (the whole recording's positions ship, so the 5-minute history exists when playback starts mid-recording), apply the shipped scaler, run the model, apply the C4 calibration for the displayed probability. Filtering stays in Python (B3).
- The Web Worker labels beats in chunks just ahead of the playhead (about the next 10 seconds). Labels still appear one beat late (post-RR, B3).
- ONNX Runtime Web's WebAssembly backend, single-threaded: a beat takes well under a millisecond, and multi-threaded WebAssembly would need COOP and COEP headers that make iframe embedding painful. No WebGPU.
- Shipped per patient: filtered trace, beat positions, the expert label per beat, and the seed-0 sealed-run label and probabilities from Python.
- Shown: model label and expert label per beat with disagreements marked, and a counter such as "Labels match the Python results: 2,134 of 2,134 beats" (labels exact, probabilities within a tolerance fixed in E5, about 1e-4). A mismatch is shown, not hidden; CI should catch it first.
- Fallback: if WebAssembly or the model fails to load, the demo plays the shipped Python labels with a visible note ("Showing precomputed labels; in-browser model unavailable"). Never silent.
- C1 ordering holds: DS1 recordings during development; DS2 patients and their sealed-run labels only after the sealed run.

## 2026-10-27: D4 decided, data shipped to the browser (and a B3 amendment)

**Rule:** no cherry-picking by construction.

**Decisions (Din):**
- All 21 DS2 patients ship, each the full 30 minutes with a scrub bar, loaded only when selected. No DS1 patients in the final demo (training patients would look better than they deserve); DS1 recordings appear only during development (C1).
- Default patient, fixed now by a rule on expert labels only: the DS2 record with the most S plus V beats among those with at least 25 of each. Qualifying: 200 (S 30, V 826) and 213 (S 28, V 220), so the default is record 200. Playback starts at the first 10-second span containing an S or V beat. The page says it was chosen before testing because it has many irregular beats. The stage video is recorded from it.
- The patient picker shows each patient's beat counts by class from the expert labels (including 212, with no irregular beats, and 232, the S-heavy one).
- Per patient: `NNN.trace.i16` (filtered trace as little-endian int16 at 200 units per mV, MIT-BIH's native resolution, about 1.3 MB) and `NNN.beats.json` (positions, expert labels, sealed-run seed-0 labels and probabilities; tens of KB).
- `manifest.json`: patients with class counts, a content hash per file (hashed filenames, cached indefinitely), the model version, and the B5 attribution note. A test checks the manifest against the files.
- Per visit: about 1.3 MB of trace, tens of KB of beats, about 210 KB of model, plus ONNX Runtime's WebAssembly (D5). Whether Cloudflare compresses the binary trace is checked in E1.

**B3 amendment (Din):** the canonical signal is "filtered, then rounded to int16 at 200 units per mV". Python trains and evaluates on this rounded trace too, so the browser and Python see identical inputs and the parity counter cannot fail for a rounding reason. The rounding (5 microvolt steps) is far below the signal's noise.

## 2026-10-27: D5 decided, performance budget

**Measured (2026-10-27, onnxruntime-web 1.31.1 from unpkg, compressed locally):** `ort-wasm-simd-threaded.wasm` 14.8 MB raw, 3.8 MB gzip, 2.4 MB Brotli; `ort.wasm.min.mjs` 54 KB raw, 17 KB gzip, 15 KB Brotli. The runtime is about ten times everything else in a visit. Version note for E1 and E2: 1.31.1 was released 2026-10-26; the previous stable, 1.30.0, on 2026-09-14, so the two-week rule likely pins 1.30.0.

**Decisions (Din):**
- Stock ONNX Runtime Web WebAssembly build. Kept as fallbacks if the measured load time misses budget: a reduced-operator custom build (needs the Emscripten toolchain), or hand-written TypeScript inference (no download, but parity would rest on our own code).
- The trace and expert labels play as soon as the trace arrives; a "model loading" note shows until the Worker is ready, then live labels start. This is loading, not the D3 failure fallback.
- The case study iframe loads nothing heavy until visible: the site marks it `loading="lazy"` (added to G4) and the demo waits for visibility before fetching the runtime.
- Hashed filenames, served as immutable.
- Gated in CI: model file under 1 MB; demo JavaScript under 60 KB gzip excluding ONNX Runtime; beats JSON under 100 KB per patient; no main-thread task over 50 ms during playback.
- Measured and reported in Playwright (4x CPU slowdown, fast 4G for the phone profile), not gated: first trace under 1.5 s desktop and 3 s phone; first live label under 3 s desktop and 6 s phone; median inference under 2 ms per beat in the Worker; steady 60 fps; memory under 100 MB.
- A first visit is about 4 to 5 MB compressed; return visits load only the chosen patient's trace.
- To confirm in E1: whether Cloudflare compresses `.wasm` and the int16 trace; if not, pre-compress at build time.

## 2026-10-27: D6 decided, interaction and accessibility

**Bar:** the site's own (WCAG 2.2 AA, full keyboard, a calm version under reduced motion, color never the only signal).

**Decisions (Din):**
- Native controls only (buttons, a `<select>` for the patient, a range input for scrubbing). No custom single-key shortcuts (WCAG 2.1.4, and they would fight the host page inside an iframe). The teal focus ring from the brand tokens.
- Controls: play and pause; speed 0.5x, 1x, 2x, 4x; patient picker with class counts (D4); scrub slider with the time as text, 5-second steps; "Next irregular beat"; "Next disagreement" (jumps to the next beat where model and experts differ, handing visitors the model's mistakes).
- Targets at least 24 by 24 CSS pixels (WCAG 2.5.8); on phones the controls stack under the canvas.
- Every beat shows its class as a letter (N, S, V, F) as well as color; disagreements get a distinct mark (outlined ring with the expert's letter beneath); Q beats a grey "not scored" dash.
- Class colors from the brand tokens, at least 3:1 against the background in light and dark (WCAG 1.4.11), enforced by a test.
- Plain-language legend: Normal, Supraventricular early beat, Ventricular early beat, Fusion beat, Not scored, one line each. Probabilities worded as in C4.
- The canvas has an image role and a summary label (patient, time span, beat count, flags), updated on pause and seek, not per frame.
- An HTML table of the beats in view (about 12 rows: time, model label, probability, expert label, match), not live-announced. A polite status line updates every 10 seconds of playback ("Last 10 seconds: 12 beats, 2 flagged, all agree with the experts"). Pausing lets screen-reader users read at their pace.
- Reduced motion: no scrolling and no autoplay; fixed 10-second pages with Previous and Next; play swaps pages every 10 seconds without animation.
- Otherwise the full demo autoplays on load and the case study iframe when visible, silent, with a visible pause (WCAG 2.2.2).
- Theme: the iframe follows the system setting by default; the site posts `{type: "theme", value}` and the demo accepts it only from the dins.dev origin. Added to G4, with an iframe `title`.
- Tests: axe at zero violations in Playwright for both modes, light and dark, with and without reduced motion; a keyboard-only walk of every control; one manual VoiceOver pass before publishing.

## 2026-10-27: D7 decided, research demo framing (section D complete)

**Decisions (Din):**
- Placement: a short line under the full demo's controls (always visible); the same line inside the case study iframe; burned into a corner of the home stage video (noted on G2); next to the case study's top window; the fuller note in the demo's about text and the case study's limits section.
- Short line: "Research demo, not medical advice. Recordings come from a public research database."
- Fuller note: "This is a research demo. The model has not been clinically validated and must not be used to make health decisions. The recordings come from the MIT-BIH Arrhythmia Database, collected in a hospital lab between 1975 and 1979. Nothing here uses your data, and you cannot upload your own. If you have concerns about your heart, talk to a doctor." The 1975 to 1979 dates are from Claude's memory; check against PhysioNet before use, or cut the clause.
- Avoid: "diagnose" or "diagnosis", "detects arrhythmia" or "detects heart disease", "clinical-grade", "accurate" as a headline, "AI doctor". Use: "labels heartbeats", "flags irregular beats", "on patients it never saw", "estimated probability". Checked in review.
