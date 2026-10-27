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
- Verified 2026-10-27: PhysioNet says the recordings were "obtained by the Beth Israel Hospital Arrhythmia Laboratory between 1975 and 1979", so the fuller note stands as worded.

## 2026-10-27: E1 decided, versions researched and a pinning policy

**Correction:** in the D5 entry and in chat, Claude called "stable and at least 14 days old" Din's rule. Din's rule is "prefer stable releases over prereleases". The 14-day wait was proposed here as a supply-chain policy and adopted below.

**Policy (Din):**
- Pin the newest stable release that is at least 14 days old (a compromised release is usually caught within days).
- The same ONNX Runtime version in Python and the browser: 1.30.0. Python's onnxruntime has 1.31.0 (2026-10-09), but onnxruntime-web skipped it and published 1.31.1 on 2026-10-26, so 1.30.0 is the newest version both have that meets the policy.
- Python 3.14: 3.15 is out (3.15.2), but torch 2.14.1 ships macOS arm64 wheels for cp310 to cp314 only.
- Node 24 LTS, matching the site. Node 26 becomes LTS on 2026-10-28; upgrade with the site later.

**Candidates as of 2026-10-27 (cutoff 2026-10-13), confirmed in E2:**
- Python: torch 2.14.1, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1, wfdb 4.3.1, pandas 3.0.6, onnx 1.23.2, onnxscript 0.7.2, onnxruntime 1.30.0, pytest 9.1.1, hypothesis 6.169.0, ruff 0.17.0, mypy 2.4.0, matplotlib 3.11.2, uv 0.13.0.
- Front end: svelte 5.57.2, vite 8.3.4, @sveltejs/vite-plugin-svelte 7.3.1, typescript 6.0.3 or 7.0.2, vitest 5.0.4, @playwright/test 1.64.0, @axe-core/playwright 4.13.0, eslint 10.12.0, typescript-eslint 8.71.2, eslint-plugin-svelte 3.23.1, prettier 3.9.10, prettier-plugin-svelte 4.1.1, svelte-check 4.7.6, wrangler 4.150.0, pnpm 12.13.0, onnxruntime-web 1.30.0.

**Findings:**
- The site's Vitest 4.1 hold exists for Cloudflare's Workers test plugin, which the demo does not use, so Vitest 5 is fine here. The site's TypeScript 6.0 hold exists for `@astrojs/check`; whether `svelte-check` supports TypeScript 7 is unknown, so 6.0.3 is the default unless E2 shows 7 works.
- To test in E2: wfdb 4.3.1 (February 2026, needs pandas 2.2.3 or later) with pandas 3; torch's ONNX exporter with onnxscript 0.7.2; `svelte-check` with TypeScript 7.
- Cloudflare: `application/wasm` is on the automatic compression list, so visitors download the 2.4 MB Brotli runtime from D5. `application/octet-stream` is not, so the int16 trace ships raw (about 1.3 MB per patient), which D4 accepted. Requests to Workers static assets are "free and unlimited". Custom domains on a subdomain are documented; the pricing page does not say whether the free plan includes them, but dins.dev already runs on Workers in the same zone. Confirm at deploy (E6).

## 2026-10-27: E2 decided, the stack (and a B5 amendment)

**Checked hands-on (2026-10-27, throwaway environments in Claude's scratchpad, nothing in the repo):**
- Python stack resolved with uv under the cutoff (86 packages, CPython 3.14.7).
- wfdb 4.3.1 with pandas 3.0.6 and numpy 2.5.4 read records 100 and 114 (checksums verified). AAMI counts match PhysioNet's table exactly (100: N 2239, S 33, V 1; 114: N 1820, S 12, V 43, F 4). MLII found by name: index 0 in 100, index 1 in 114.
- Filter then int16 rounding: maximum rounding error 0.0025 mV, as designed.
- The C3 network exported with torch 2.14.1 and onnxscript 0.7.2 (`dynamo=True`): opset 20, batch norm folded by the exporter, nine basic operator types (Concat, Conv, Gemm, MaxPool, ReduceMean, Relu, Reshape, Squeeze, Unsqueeze).
- PyTorch against onnxruntime 1.30.0 (Python): maximum difference 1.0e-7, identical argmax. onnxruntime-web 1.30.0 (WebAssembly, one thread, run in Node) against Python: maximum difference 8.9e-8, identical argmax. The in-browser check is E5's Playwright test.
- Front-end stack resolved with pnpm under `minimumReleaseAge`; svelte-check and vite build pass on TypeScript 6.0.3 and catch a planted type error. svelte-check 4.7.6 crashes at startup on TypeScript 7.0.2.

**Findings:**
- pnpm's minute-level check rejected wrangler 4.150.0 and pnpm 12.13.0 (published hours inside the window), and it covers transitive packages; so does uv's `exclude-newer`. Both now enforce the policy.
- pnpm 12 blocks install scripts by default: allow esbuild and workerd (they fetch their binaries), keep protobufjs blocked (its script only checks versions).
- The dynamo exporter writes weights to a separate `.data` file by default; save as one file (238 KB at width 1).
- PhysioNet's main server ran at about 10 KB/s at times; PhysioNet's open S3 mirror (`https://physionet-open.s3.amazonaws.com/mitdb/1.0.0/`) ran at 1.9 MB/s with identical checksums.

**Decisions (Din):**
- Runtimes: Python 3.14 (newest torch supports); Node 24 LTS (matches the site); uv 0.13.0; pnpm 12.12.1 (12.13.0 too new).
- Python: torch 2.14.1; onnx 1.23.2; onnxscript 0.7.2 (exporter); onnxruntime 1.30.0 (same as the browser); numpy 2.5.4; scipy 1.18.1 (filter); scikit-learn 1.9.1 (baseline, folds); pandas 3.0.6 (wfdb dependency, tested); wfdb 4.3.1 (tested); matplotlib 3.11.2 (model card figures). Dev: pytest 9.1.1, hypothesis 6.169.0, ruff 0.17.0, mypy 2.4.0.
- Front end: svelte 5.57.2; vite 8.3.4; @sveltejs/vite-plugin-svelte 7.3.1; typescript 6.0.3 (7 breaks svelte-check); svelte-check 4.7.6; vitest 5.0.4 (the site's 4.1 hold does not apply); @playwright/test 1.64.0; @axe-core/playwright 4.13.0; eslint 10.12.0; typescript-eslint 8.71.2; eslint-plugin-svelte 3.23.1; prettier 3.9.10 with prettier-plugin-svelte 4.1.1; onnxruntime-web 1.30.0; wrangler 4.149.0 (deploy only).
- Enforcement: `[tool.uv] exclude-newer` (a fixed date, moved forward deliberately on upgrade) and pnpm `minimumReleaseAge: 20160` (rolling 14 days), with `allowBuilds` for esbuild and workerd only.
- ONNX export saved as a single file.

**B5 amendment (Din):** the downloader fetches from PhysioNet's S3 mirror first and falls back to `physionet.org`. The pinned checksums make the source irrelevant to trust.

## 2026-10-27: E3 decided, repo layout and licenses

**Decisions (Din):**
- One repo, two toolchains. Python at the root as a src-layout package, `src/heartbeat/` with `data/`, `signal/`, `models/`, `train/`, `evaluate/`, `export/` and `cli.py` (one `heartbeat` command; subcommands in E4). The Svelte app in `web/`, with copied brand files in `web/vendor/brand/`.
- `manifests/` holds pinned inputs reviewed like code: `mitdb-1.0.0.sha256` (132 checksums), `subjects.toml` (record to subject; 201 and 202 share one), `splits.toml` (DS1, DS2 and exclusions with reasons). `config/` holds settings: `default.toml` and the committed `folds.json`. A split or checksum change is a rigor event; a learning-rate change is not.
- Committed outputs: `models/heartbeat-v1/` (the frozen `model.onnx`, scaler and calibration JSON, freeze record; about 240 KB), so CI's parity tests have the exact model and "this exact model" can be checked in git; `results/` (metrics JSON, SVG figures, `test_runs.jsonl`); `fixtures/parity/` shared by Python and web tests.
- Gitignored: `data/` (raw cache, intermediate arrays), `runs/` (C6), `web/public/data/` (built demo data, about 27 MB, regenerated by the rebuild; E6 decides whether deploys rebuild or upload it).
- Docs in `docs/`: PRD, PLAN, TASKS, WORK_LEDGER, MODEL_CARD, DATA_CARD. CI in `.github/workflows/`, Claude settings in `.claude/settings.json`.
- Licenses: MIT for the code (`LICENSE`); the MIT-BIH data stays under ODC-By 1.0 (`DATA_LICENSE.md`), and the README says the code license does not cover the data.

## 2026-10-27: E4 decided, the one-command rebuild

**Decisions (Din):**
- `uv run heartbeat rebuild` runs: download (S3 mirror, checksums), prepare (filter, int16, MLII by name, beats, AAMI, RR), check-folds, cross-validate (baseline C values; CNN widths x 3 seeds x 5 folds), select (`results/selection.json`), exhibit (C5 leaky side), train-final (3 seeds, CPU deterministic), export (single-file ONNX, scaler, calibration, fixture parity), reproduce-test (after the freeze only), build-demo-data.
- Every stage records a fingerprint of its inputs (settings, upstream outputs, code) and is skipped when up to date; `--from <stage>` forces a rerun.
- Folds are made only by `heartbeat make-folds` and committed; `rebuild` only checks them.
- Before a freeze record exists, `rebuild` stops after export and builds DS1-only demo data; DS2 is never read.
- After the sealed run is logged, `rebuild` retrains and checks against the freeze record (exact mode: model checksum bit for bit; default mode: metrics within tolerance), then evaluates DS2 with the committed frozen model and requires results equal to the logged ones. This is appended to `test_runs.jsonl` as a reproduction, a separate entry type. Mismatches fail loudly; nothing is overwritten.
- Modes: default (about 2 to 3.5 hours; cross-validation and exhibit on MPS, within tolerance) and `--exact` (about 15 hours; everything on CPU, bit for bit on the same machine). Final models train on CPU in both (C6).
- The web build stays separate (`pnpm -C web build`, reading the rebuilt demo data); "one command" covers the artifacts.
- `heartbeat verify` runs in minutes without training: manifests and checksums, frozen-model parity on the fixtures, result files consistent with the test log. CI runs what it can of it.

## 2026-10-27: E5 decided, test strategy

**Decisions (Din):**
1. Python unit tests (pytest, hypothesis; no data; CI on every push): zero-phase filter, int16 rounding within 0.0025 mV, window indices; RR features causal except post-RR (property test changing beats further ahead); unknown annotation symbol fails (B4); MLII picked by name in any channel order (114's layout); checksum mismatch stops the download (B5); metrics against scikit-learn on known cases; bootstrap draws contain whole patients, CNN and baseline share draws, undefined precision draws skipped and counted, per-patient counts-only rule below 10 beats, logit adjustment and equal-mass ECE (C4); same-seed CPU runs give identical weights (C6).
2. Python tests on real data: CI downloads the 132 files from the S3 mirror (about a minute) with a cache keyed by the checksum manifest. Subject leakage (DS1 against DS2, every fold, 201 and 202 one ID); the loader refuses DS2 outside `evaluate-test`; `evaluate-test` refuses without a matching freeze record or on a dirty tree; `rebuild` stops before DS2 without a freeze (E4); class counts match PhysioNet's table per record; a smoke training run of a few CPU batches (C7).
3. Parity chain on shared fixtures of about 50 real DS1 beats (never DS2) written by `heartbeat export`: PyTorch against Python ONNX Runtime; Python ONNX Runtime against ONNX Runtime Web in a real browser (closing E2's Node-only gap); TypeScript preprocessing (window, z-score, RR features, scaler, calibration) against Python step by step. Tolerance 1e-5 on outputs and features, labels exact. This replaces D3's "about 1e-4"; measured differences were about 1e-7. The on-page counter uses the same rule.
4. Web unit tests (Vitest): drawing math, chunk scheduling, manifest parsing, class colors at 3:1 contrast in light and dark (D6).
5. Web end-to-end (Playwright, Chromium and WebKit): axe at zero violations in every mode (full and embed, light and dark, reduced motion on and off); keyboard-only walk; labeled fallback when WebAssembly is blocked (D3); no main-thread task over 50 ms; size gates (model under 1 MB, demo JavaScript under 60 KB gzip, beats JSON under 100 KB; D5); built headers carry `frame-ancestors` and `'wasm-unsafe-eval'` (D1); timings reported, not gated.
- A wording lint scans the built demo text and the case study draft for D7's avoid list and for em or en dashes used as separators (Din's writing rule).
- `docs/PLAN.md` (F2) gets a table mapping each locked rigor rule to the test that enforces it.
- No code-coverage percentage gate.

## 2026-10-27: E6 decided, CI, remote and deploys (section E complete)

**Checked:** dins.dev's remote is `dinsdev/dins.dev` (`dinsdev` is a GitHub organization); `dinsdev/heartbeat` does not exist yet; the GitHub CLI is signed in as `dinesh-git17`. dins.dev has no workflows yet. Din's rule (dins.dev ledger): pushing needs permission.

**Decisions (Din):**
- Remote: `dinsdev/heartbeat`, public (MIT, E3), linked from the case study.
- Public at the end of Phase 0, before the sealed run: the push gives the pre-registered plan (A3, C4, C5, C8) an outside timestamp that local commit dates cannot. Evidence, not cryptographic proof. The freeze record is pushed before `evaluate-test` runs, and the test log right after.
- CI: one GitHub Actions workflow on every push and pull request, aiming under about 10 minutes. Python: ruff, mypy, unit tests, real-data tests (download cached by the checksum manifest), smoke training, the Python half of the parity chain. Web: frozen-lockfile install, ESLint, Prettier, svelte-check, Vitest, build and size gates, Playwright in Chromium and WebKit. Text: the wording lint.
- Supply chain: third-party actions pinned to full commit hashes; read-only workflow permissions by default; Renovate with a 14-day minimum release age, a monthly schedule, pull requests only, no automerge.
- `scripts/check.sh` runs lint and unit tests locally in under 2 minutes, as on the site.
- Deploys: GitHub Actions with wrangler, not Workers Builds, because building demo data needs Python, uv and the data download. No training in deploys; demo data is built from the committed frozen model (DS1 only before the freeze, per E4). Production on `main` after checks pass; preview versions on pull requests. `heartbeat.dins.dev` set as a custom domain in wrangler's config; free-plan coverage confirmed on the first deploy.
- Din's go needed for: creating the repo and making it public, each push, creating a Workers-scoped Cloudflare API token and adding it as a GitHub secret (Claude never handles its value), and the first production deploy.

**Handoff (2026-10-27, end of session):** sections A to E are decided. Next is section F (F1 PRD, F2 PLAN with build phases and the rule-to-test table, F3 AGENTS.md and CLAUDE.md, F4 conventions, F5 `.claude/settings.json`, F6 card templates), then G. Open items carried: the de Chazal full text (B5; TARA is behind a Cloudflare bot check, so Din downloads it); G4, the dins.dev changes to hand over; and confirming Workers custom-domain coverage at the first deploy.

## 2026-10-27: F1 drafted, the PRD

**Research (2026-10-27), how large tech companies structure requirement docs:**
- Google design docs (Malte Ubl, "Design Docs at Google", industrialempathy.com): context and scope, goals and non-goals, design, alternatives considered (called one of the most important sections), cross-cutting concerns such as security and privacy. A non-goal is something that could reasonably be a goal but is deliberately excluded, not a negated goal. About 10 to 20 pages for a larger project.
- Amazon PR/FAQ (workingbackwards.com): start from the customer and work backwards; the internal FAQ names dependencies, the assumptions that must hold and the top reasons the product could fail.
- Common pattern across published PRD templates (Lenny's Newsletter template roundup, third-party guides): problem before solution, testable requirements with priorities, explicit non-goals, open questions with owners. No internal template from Google, Amazon or Meta is public; these are the closest primary sources.

**Work done:** `docs/PRD.md` written. Structure: summary; background; problem; audience; goals as true-or-false checks (A3 rules out numeric targets); non-goals with reasons; six use cases; 70-odd functional requirements with IDs, priorities and the planning item that decided each; non-functional requirements; constraints; falsifiable assumptions; launch criteria; risks; decisions with rejected alternatives; edge cases; measurement plan; release order; open questions with owners; an appendix of changes from the dins-projects draft.

**Choices made in drafting (for Din's review):**
- Priorities: P0 is A2's core, P2 is C8's stretch. P1 (Ask Ottie sources, `scripts/check.sh`, Renovate, brand drift check) is Claude's proposal; A2 had no middle tier (open question Q1).
- Three behaviors not covered by a decision are marked "proposed here": "Next irregular beat" on a patient with none (212), the rollback procedure, and leading with the exhibit's gap to resolve the recruiter conflict.
- Privacy reads D7 ("Nothing here uses your data") as no analytics in the demo, so reader outcome is not instrumented (Q4).
- New open questions: Q1 P1 split, Q4 analytics, Q5 Firefox in the Playwright matrix, Q6 stage line wording, Q7 preview hostnames. Carried: de Chazal full text (Q2), custom domain on the free plan (Q3), INCART design choices (Q8).

**Found:** the dins-projects PRD section 7 differs from the decisions in eight places (saliency, five classes, the 202 fix, metrics, CNN inputs, GPU, stage, stack). Listed in the PRD's Appendix A; updating the dins-projects PRD belongs to that repo.

**Verified:** no em or en dashes, no avoid-list words, ASCII only (grep). Every number in the PRD traced to a ledger entry. Not verified: anything new; the PRD adds no new facts beyond the research summary above.

## 2026-10-27: F1 decided, the PRD

**Decision (Din):** lock `docs/PRD.md` as drafted, with the P1 split accepted (Ask Ottie sources, `scripts/check.sh`, Renovate, brand drift check: they should ship with core but do not block publishing). Q1 is closed and removed from the PRD's open questions; the other question numbers stay as they were so references hold.

**Also:** Din ran Prettier over the PRD (table padding, blank lines before lists). Checked: formatting only, no content change. Kept; F4 should say whether Markdown docs are Prettier-formatted.

**From now on:** the PRD is the source of truth for requirements. A change to a requirement gets a ledger entry, like any decision.

## 2026-10-27: F2 drafted, the plan

**Work done:** `docs/PLAN.md` written and build phases added to `docs/TASKS.md` (Phases 1 to 8, 36 tasks).

**Proposed (for Din's lock):**
- Order follows the trust chain: skeleton and CI; data and split; evaluation harness on the baseline; CNN and exhibit; export, parity and rebuild; demo on DS1; freeze and sealed run; content and launch; stretch. The demo shell may start after Phase 2 with an untrained network as a stand-in.
- PLAN.md stays phase-level. Each phase gets a task-level plan (files, interfaces, test-first steps) appended to PLAN.md when it starts, reviewed by Din. Noted conflict: the superpowers writing-plans skill wants a code-level plan up front; F4's conventions and earlier phases' interfaces would change it, so it waits.
- Phase 7 gate checklist before `evaluate-test`: all rows through R40 green on `main`, pre-registration unchanged or changes logged, freeze record pushed, clean tree.
- The G items move from Phase 0 into build phases (G4 in 6, G1 in 7, G2 and G3 in 8), since none can finish during planning.
- Branch per phase (`phase-N-<name>`), pushes at checkpoints with Din's go, merge after CI.
- Rule-to-test table: 49 rows. Two are new checks no planning item decided: R46 (a workflow check that rejects action tags instead of commit hashes) and R47 (`evaluate-test` refuses unless the freeze commit is on `origin/main`).
- Review focus, five untested failure modes assigned to phases: interrupted downloads (atomic writes), MPS against CPU selection drift, labeling falling behind at 4x, scrubbing to the ends, background-tab throttling.

**Estimates (Claude's guesses, not measured):** about 18 to 23 focused days for Phases 1 to 8. Compute times are the measured C7 and E4 figures. Against the best-case 2026-12-01 freeze, Heartbeat fits with little slack, before the other three projects. Cut order if short: P1 items, then timing polish, never a P0 rigor rule.

**Not verified:** whether Workers preview URLs need a production deploy first (checked when the token is set up, Phase 6).

## 2026-10-27: F2 decided, the plan

**Decision (Din):** lock `docs/PLAN.md` as drafted, including:
- R46: a CI check that rejects third-party actions referenced by tag instead of commit hash (Phase 1).
- R47: `evaluate-test` refuses unless the freeze commit is on `origin/main`, so "pushed before the sealed run" is enforced in code, not only promised (built with the other refusals, checked at Phase 7).
- The G items move out of Phase 0 into the build phases: G4 in Phase 6, G1 in Phase 7, G2 and G3 in Phase 8. Phase 0 ends when section F is done and the repo is pushed public.

Also locked with the plan: the phase order, the Phase 7 gate checklist, phase-level PLAN.md with a task-level plan appended per phase at its start, a branch per phase with pushes at checkpoints (Din's go), the five review-focus failure modes, and the cut order if time runs short (P1 items, then timing polish, never a P0 rigor rule).

**Handoff (2026-10-27, end of session):** F1 and F2 are decided. Next is F3 (`AGENTS.md`, and `CLAUDE.md` starting with `@AGENTS.md`) in a new conversation, then F4 (conventions, including whether Markdown docs are Prettier-formatted, since Din ran Prettier on the PRD), F5 (`.claude/settings.json`), F6 (model and data card templates). After F: create `dinsdev/heartbeat` as a public repo and push (Din's go), which closes Phase 0 and timestamps the pre-registration. Open items carried: the de Chazal full text (PRD Q2; Din downloads the PDF); Workers custom-domain coverage on the free plan (Q3, at first deploy); whether Workers preview URLs need a production deploy first (Phase 6); the dins-projects PRD section 7 should point to this PRD (listed in the PRD's Appendix A; that change belongs to the dins-projects repo).

## 2026-10-27: F3 drafted, AGENTS.md and CLAUDE.md

**Research (2026-10-27, primary sources):**
- agents.md (the format's site): plain Markdown, no required fields; common sections are overview, build and test commands, code style, testing, security. Nested files: the closest one to the edited file wins; the user's chat prompt overrides all. No size guidance.
- Codex docs (learn.chatgpt.com, agent configuration): walks from the Git root down to the working directory, one file per directory, `AGENTS.override.md` before `AGENTS.md`, concatenated root first; stops at `project_doc_max_bytes`, default 32 KiB.
- Claude Code docs (memory, best practices): target under 200 lines; write only what Claude can't find by reading the repo (exact check commands, misleading spots, decisions not in the code, anything corrected twice); concrete, checkable instructions; no IMPORTANT or capitals (current models over-apply them); contradictions get resolved arbitrarily; a rule with no exceptions belongs in a hook or deny rule, since CLAUDE.md is guidance Claude may decide doesn't apply. Claude Code reads `AGENTS.md` natively from v2.1.277, and a `CLAUDE.md` with `@AGENTS.md` never loads it twice.
- Checked locally: the installed CLI is 2.1.266, so the `@AGENTS.md` import is still what makes Claude load it (Din's global note holds).
- Gloaguen et al., "Evaluating AGENTS.md" (ETH Zurich, arXiv 2602.11988 v3, 2026-09-29): context files did not generally improve task success and raised inference cost by over 20%; repository overviews didn't help; agents do follow the instructions, so the files are useful for non-standard practices. Read from the abstract page, not the full text.
- GitHub blog, lessons from over 2,500 agents.md files: commands early with flags, real examples over prose, explicit boundaries in always, ask first and never tiers; "never commit secrets" was the most common useful line.
- METR, "Recent frontier models are reward hacking" (2025-06-05, from search excerpts, page not opened): models modified tests or scoring code to raise scores. The reason the test rule below is explicit.

**Proposed (for Din's lock):**
- One root `AGENTS.md`, 87 lines and 7.8 KB (under 200 lines and Codex's 32 KiB). No nested `web/AGENTS.md` yet; revisit in Phase 1 if web commands crowd the root file. A nested file would need its own `web/CLAUDE.md` import while the CLI is older than 2.1.277.
- Content follows the research: a short purpose line, pointers to the four docs instead of copying them, commands, a layout map marking who writes what, seven rigor rules, dependency rules, test and done rules, approvals, writing rules. No architecture overview, no status (TASKS.md holds it).
- The rigor rules are the core: DS2 sealed (with the 21 record IDs, 202 and the paced records excluded, what is allowed: download, checksums, count and leakage tests); no number without a run; tests are the spec (no weakening, skipping or special-casing to get green); folds, splits and checksums as rigor events; results written by code, test log append-only; the pre-registered plan; determinism.
- Commands are listed from E4 and E6 with a note that none exist until Phase 1, when the section gets exact single-test commands.
- Approvals gathered from the global agreements, E6, C8 and PLAN.md in one list. Two are new and need Din's call: ask before `rebuild --exact` (about 15 hours), and downloads other than the pinned MIT-BIH files need a go while the pinned download (part of `rebuild`) does not.
- Reporting states for work: implemented, verified, accepted (only Din sets accepted), per the global agreements. TASKS.md's build-phase status key (todo, doing, done) does not separate these yet; F4 or the Phase 1 plan can change the key if Din wants it there too.
- No attribution trailers, carried over from dins.dev (this repo has none so far).
- Conventions get their own file, `docs/CONVENTIONS.md` (F4), linked from `AGENTS.md`, since `.claude/rules/` would hide them from Codex. That adds a sixth file to E3's docs list.
- `CLAUDE.md`: the import plus three Claude-only notes (Superpowers overrides with plans in PLAN.md section 8, scratchpad checks, hooks from F5 not to be worked around).
- Enforcement split for F5: rules with no exceptions (no push, no `evaluate-test`, no edits to `results/test_runs.jsonl`, `manifests/` or `config/folds.json`) get deny rules or hooks there; the code checks from the rule-to-test table stay the real guard, since Codex doesn't run Claude hooks.

**Verified:** no em or en dashes, no avoid-list words, ASCII only (grep); DS2 list has 21 records and matches the B1 entry minus 202.

## 2026-10-27: F3 decided, AGENTS.md and CLAUDE.md

**Decision (Din):** lock `AGENTS.md` and `CLAUDE.md` as drafted:
- One root `AGENTS.md`; no nested `web/AGENTS.md` until Phase 1 shows a need.
- The seven rigor rules as written (DS2 sealed, no number without a run, tests are the spec, folds and splits as rigor events, results from code, the pre-registered plan, determinism).
- The approvals list, including the two new stops: `rebuild --exact` (about 15 hours), and any download other than the pinned MIT-BIH files. The pinned download inside `rebuild` needs no go.
- Conventions live in `docs/CONVENTIONS.md` (F4), linked from `AGENTS.md`. This adds a sixth file to E3's docs list.
- `CLAUDE.md` imports `AGENTS.md` and adds three Claude-only notes.

**Carried to F4 and F5:** whether Markdown docs are Prettier-formatted, and whether TASKS.md's build status key separates implemented, verified and accepted (F4); deny rules or hooks for the no-exception rules (F5).

## 2026-10-27: F4 drafted, conventions

**Checked locally:** dins.dev has no tooling config yet (no `package.json`, Prettier or ESLint config), so "the site's tooling" (D2) means its locked workflow rules in `~/Develop/dins.dev/docs/PLAN.md`: Conventional Commits, `type/short-description` branches, a PR for every change, squash merge only, one `check.sh`. That plan also says shared conventions live once in the `handbook` repo; `dins-handbook` has no conventions file and is private, so a public repo can't point to it. `docs/CONVENTIONS.md` stands (F3). Prettier, ruff and mypy are not installed on the Mac, so no tool setting below was run; Phase 1 checks them against the pinned versions. Existing docs: only the PRD is Prettier-formatted (padded tables); PLAN, TASKS and the ledger are not.

**Research (2026-10-27, primary sources):**
- scikit-learn "Common pitfalls": split before any preprocessing, never `fit` on test data, use pipelines; pass an integer `random_state` to CV splitters for comparable folds; avoid `np.random.seed`.
- NumPy "Parallel random number generation": derive streams with `SeedSequence.spawn` or `default_rng`; `seed + i` is marked unsafe because nearby root seeds give overlapping worker seeds across runs.
- PyTorch 2.14 reproducibility notes: no guarantee across releases, platforms, or CPU against GPU; `torch.use_deterministic_algorithms`; seed the `DataLoader` with a `generator`.
- Ruff rules: `NPY002` flags legacy `np.random` functions and recommends a `Generator`; `ERA001` flags commented-out code; `T201` flags `print`.
- typescript-eslint configs: start from `recommended(TypeChecked)` plus `stylistic(TypeChecked)`; `strict` configs are for teams highly proficient in TypeScript and are not semver-stable (rules can change in minor releases).
- TypeScript tsconfig reference: `strict` does not include `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride` or `noFallthroughCasesInSwitch`.
- Svelte best practices: `$derived` not `$effect` for computed values, effects as an escape hatch, classes with `$state` instead of stores, keyed each blocks not keyed by index.
- Kapoor and Narayanan, "Leakage and the reproducibility crisis in machine-learning-based science" (Patterns 2023): leakage found in at least 294 papers across 17 fields; the taxonomy (L1.1 to L1.4, L2, L3.1 to L3.3) is mapped to this repo in CONVENTIONS section 3.
- From Claude's memory, not checked: Hypothesis's `derandomize` setting for a fixed-seed CI profile; the rule name `@typescript-eslint/switch-exhaustiveness-check`; Prettier printing tables wider than the print width compactly (which would keep TASKS and ledger diffs small). Phase 1 checks all three.

**Proposed (for Din's lock):**
- Tools enforce whatever they can; `docs/CONVENTIONS.md` (120 lines) names the tool settings and keeps only what a linter can't see. Ruff with a wider rule set than the default, including `NPY` (bans global NumPy random state) and `ERA`; `mypy --strict`; strict TypeScript plus four extra flags and `erasableSyntaxOnly` (no enums, matching Node's type stripping); typescript-eslint's recommended and stylistic type-checked sets rather than strict (stable across minor upgrades, which matters with Renovate).
- Python: names carry units (`_samples`, `_s`, `_hz`, `_mv`, `_adu`); decided values as named constants with the decision ID; arrays typed with shapes in docstrings and asserts at boundaries (no jaxtyping, to avoid two dependencies); `ddof=0` everywhere so TypeScript matches; errors fail loudly; atomic writes.
- ML hygiene: the leakage taxonomy table; a separate fit step and apply step for anything learned; no global random state, streams spawned from one master seed with `SeedSequence`; figures made by code; no notebooks in the repo.
- TypeScript and Svelte: runes only, plain TypeScript for the trace, preprocessing and Worker protocol, string unions, validated message unions, parity code mirrors Python name for name.
- Tests: three Python test folders by layer with a `realdata` marker; rule IDs on tests (`@pytest.mark.rule("R12")`, `R29:` title prefixes) plus a small CI check that every non-manual row in PLAN section 6 has a test. New: no planning item decided this check.
- Git: Conventional Commits from Phase 1 (as on dins.dev). Merge commits, never squash or rebase: run folders, the freeze record and R47 refer to commit hashes, and a squash would leave the freeze commit off `main`. This differs from dins.dev's squash-only rule on purpose.
- Task status for the build phases uses dins.dev's words (Planned, In progress, Implemented, Verified, Accepted by Din only, Blocked), closing the gap noted at F3. The build-phase rows in TASKS.md switch from todo to Planned at the lock.
- Markdown: Prettier formats every `.md` file (`proseWrap: "preserve"`). Proposed timing: one formatting-only pass with the pinned Prettier 3.9.10 just before the Phase 0 push (needs Din's go for the download), so the pushed pre-registration is already formatted and the Phase 7 gate never sees a reformat as a change.

**Gap found (for the Phase 2 plan, not decided here):** B3's per-window z-score does not say what happens when a window's standard deviation is zero or near zero (a flat or lead-off segment). Python and TypeScript must handle it the same way.

**Verified:** no em or en dashes, no avoid-list words, ASCII only (grep).

## 2026-10-27: F4 decided, conventions

**Decision (Din):** lock `docs/CONVENTIONS.md` as drafted:
- Tools enforce whatever they can (ruff, mypy strict, strict TypeScript, typescript-eslint recommended and stylistic type-checked, Prettier); the doc keeps only what a linter can't see.
- Names carry units; decided values are named constants with their decision ID.
- The leakage table (Kapoor and Narayanan's taxonomy) and a separate fit step and apply step for anything learned.
- No global random state; streams spawned from one master seed with `SeedSequence`.
- Rule IDs on tests, with a CI check that every non-manual row in PLAN.md section 6 has a test.
- Conventional Commits from Phase 1.
- Merge commits, never squash or rebase, so commit hashes in run folders, the freeze record and R47 stay on `main`.
- dins.dev's status words for build tasks.
- Prettier formats every Markdown file, with one formatting-only pass before the Phase 0 push.

**Applied:**
- `docs/TASKS.md`: a second status key for the build phases; all 40 build tasks switched from todo to Planned; new tasks 1.6 (tool configs, checked against the pinned versions, including the three settings recalled from memory in the F4 draft entry) and 1.7 (the rule-coverage check); new Phase 0 item F8 (the Prettier pass before the push, Din's go for the download).
- `docs/PLAN.md`: Phase 0 remaining now lists F5, F6 and F8; Phase 1 builds the tool configs and the rule-coverage check.

**Still open:** the zero standard deviation case in B3's z-score, for the Phase 2 plan.

## 2026-10-27: F5 drafted, `.claude/settings.json` and the guard hook

**Research (2026-10-27, primary sources: code.claude.com permissions, permission-modes and hooks pages):**
- Rules are evaluated deny, then ask, then allow; a deny at any settings level wins. Bash rules split compound commands and strip a fixed wrapper list (`timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, bare `xargs`); deny and ask rules match past any leading variable assignment. They don't match other spellings of the same program (`git -C . push`, `/usr/bin/git push`, `sh -c '...'`); the docs say a Bash rule "isn't a security boundary" and point to PreToolUse hooks or the sandbox.
- Read and Edit rules use gitignore patterns; `/path` anchors at the project root in project settings; Edit rules cover every built-in edit tool and `Write(path)` rules never match. Read and Edit denies also apply to Bash commands Claude Code recognizes (`cat`, `sed`, `tee`) and to redirect targets, not to a script that opens files itself.
- Modes: the docs say deny rules block in every mode, explicit ask rules still prompt in bypass mode, and allow rules have no effect there. Project allow rules apply only after the workspace trust dialog; deny and ask rules always apply.
- Hooks: PreToolUse runs before the permission check; exit 2 blocks with stderr as the reason; any other non-zero exit is a non-blocking error, so a crashing hook lets the call through. `onFailure: "block"` fixes that but needs v2.1.295, and the installed CLI is 2.1.266, so the guard fails closed in its own code instead. Hooks also run inside subagents. Settings edits are picked up mid-session.

**Measured (this session, desktop app Code tab, bypass mode):**
- Deny rules hold: a Write into `web/vendor/brand/` was refused by `Edit(/web/vendor/brand/**)`, and a scratchpad setup command writing `> results/test_runs.jsonl` after a `cd` was refused by `Edit(/results/**)` (the redirect check resolved the relative path against the repo root, not the `cd` target).
- The hook holds: it blocked `git push --dry-run`, an `rm` inside `.claude/hooks/`, and, before a fix, two read-only commands (false positives, fixed and added to the tests).
- Ask rules did not prompt: `curl --version` ran with `Bash(curl *)` in ask, and Edits to `.claude/hooks/guard.py` ran with `Edit(/.claude/**)` in ask. A hook answering `permissionDecision: "ask"` also ran without a prompt (temporary probe, removed). This contradicts the docs for bypass mode; it may be the desktop app or rules added mid-session. Not checked in Manual mode.
- A headless end-to-end run (`claude -p` in a scratch repo with a local bare remote) could not run: the terminal CLI is not logged in, and signing in is Din's. The scratch repo was deleted.

**Proposed (for Din's lock):**
1. Deny first. Every step AGENTS.md reserves for Din and every outward-facing step is a deny rule plus a hook block, since only those held in bypass mode: `git push`, `git remote add` and `set-url`, `gh repo create`, `gh pr create` and `merge`, `gh release`, `gh workflow run`, secrets (`gh secret`, `gh variable`, `gh auth token`, `wrangler secret`, `wrangler login`), deploys (`wrangler deploy`, `wrangler versions`, `pnpm ... deploy`), `heartbeat evaluate-test`, `heartbeat make-folds`, `heartbeat rebuild --exact`. Claude stops and gives Din the exact command; Din runs it. Tradeoff: Claude can't push even after Din's go. These steps are few (the Phase 0 push, the freeze push, PR merges, deploys), and the pushes are the timestamps the case study leans on, so Din running them is a plus.
2. Commands that discard uncommitted work are denied (`git clean`, `git reset --hard`, `git checkout -- path`, `git restore path` without `--staged`, `git stash drop` and `clear`), per the global agreements.
3. File denies: `results/**` (written only by `rebuild`, rule 5), `models/heartbeat-v1/**` (written by `export`; it also holds the freeze record), `config/folds.json` (`make-folds`, rule 4), `web/vendor/brand/**` (changed in dins.dev), and reads of `.env*` and `.dev.vars*` (secrets).
4. Ask rules where a prompt is right and a silent run in bypass mode does no lasting harm: `manifests/**` edits (Phase 2.1 writes them with Din's go), `.claude/**` edits, `gh api`, `curl`, `wget`. Per the docs they prompt in Manual mode (not measured). Once Phase 2 locks the manifests, `Edit(/manifests/**)` moves to deny.
5. `.claude/hooks/guard.py` (stdlib Python, runs on 3.9 and 3.14) covers what deny rules miss: other spellings of the Din-only commands (options before the subcommand, full paths, `sh -c`, `eval`, `$(...)`, `uv run`, `pnpm exec`, `npx`, `python -m heartbeat`), shell writes to the protected paths and `.claude/` (redirects, `tee`, `rm`, `mv`, `cp` destinations, `sed -i`, `find -delete`, path-writing git subcommands, interpreters whose script writes), and adding skip, xfail, only or todo markers to test files (rule 3; the reward-hacking pattern from the F3 research). It follows `cd` within a command, ignores heredoc bodies, and blocks on its own errors. Tests: 50 blocked and 27 allowed commands plus file-tool and fail-closed cases in `.claude/hooks/test_guard.py`.
6. Allow rules for routine local commands (git add, commit, switch, branch, merge, stash; uv sync, lock and run of pytest, ruff, mypy, heartbeat; `scripts/check.sh`; pnpm in `web/`). They matter only outside bypass mode and after the trust dialog.
7. Not proposed: the sandbox (OS-level write denial would also block `rebuild`, `export` and `make-folds`, which write the same paths, and it changes how every command runs, including network for uv and pnpm); a SessionStart hook printing TASKS status (AGENTS.md already says to read it, and the F3 research found context files cost tokens); format-on-edit hooks (no tools until Phase 1; task 1.6 can add them).
8. `.gitignore` gains `.claude/settings.local.json`, `.claude/worktrees/` and `__pycache__/`.
9. `CLAUDE.md`: the F5 note gains one sentence saying only deny rules and the guard hold in bypass mode, so Claude hands Din the command.

**Carried:** Phase 1 task 1.3 runs the hook tests in `scripts/check.sh` and CI. Phase 2 adds Read denies for DS2 record files once the cache layout is set (rule 1) and moves `manifests/` to deny. Whether ask rules prompt in Manual mode in the desktop app, checked when convenient.

**Limits:** none of this binds Codex, a subprocess that opens files itself, or a git alias. The code checks in PLAN.md section 6 stay the real guard.

**Verified:** `python3 -m unittest discover -s .claude/hooks`: 11 tests OK on Python 3.14.7 and on macOS `/usr/bin/python3` 3.9.6; `settings.json` parses as JSON; live checks above. No em or en dashes, no avoid-list words (grep).

## 2026-10-27: F5 decided, `.claude/settings.json` and the guard hook

**Decision (Din):** lock F5 as drafted: deny rules plus the fail-closed guard hook for every step only Din runs and for commands that discard uncommitted work; file denies for `results/`, `models/heartbeat-v1/`, `config/folds.json`, `web/vendor/brand/` and secrets; ask rules only for `manifests/` and `.claude/` edits, `gh api`, `curl` and `wget`; allow rules for routine local commands.

**Verified end to end (after Din logged the CLI in):** Claude Code CLI 2.1.266, `claude -p --model haiku --permission-mode bypassPermissions` in a scratchpad copy of `.claude/` with a local bare remote as `origin`.
- Run 1, eleven calls: the hook blocked `git push origin main`, `uv run heartbeat evaluate-test`, `echo extra >> results/test_runs.jsonl` and a new test file with a skip marker; deny rules refused Writes to `results/new.json` and `web/vendor/brand/x.css` and a Read of `.env`; the ask rules turned into refusals for the `manifests/splits.toml` Edit and `curl --version` (headless runs can't prompt); `git status --short` ran. The model skipped `git -C . push` on its own, so run 2 covered it.
- Run 2: the hook blocked `git -C . push origin main`, `sh -c 'git push origin main'`, `/usr/bin/git push origin main` and `uv run python -m heartbeat evaluate-test`.
- After both runs the bare remote had no `main`, and `results/test_runs.jsonl` and `manifests/splits.toml` were unchanged.
- Correction to the draft entry: in a fresh process the ask rules were enforced in bypass mode, as the docs say. The earlier "ask rules did not prompt" result is limited to this desktop session, where the rules were added mid-session. Deny-first still stands, since it holds either way. Din's check in a new desktop session settles the desktop case.
- Setting up the scratch repo, the guard blocked my own `git remote add` (it applies to any repo, by design); the scratch remote was set by cloning the empty bare repo instead. The scratch folder was deleted after the runs.

**Carried:** unchanged from the draft entry (hook tests in `scripts/check.sh` and CI at task 1.3; DS2 Read denies and `manifests/` to deny in Phase 2; the desktop ask-rule check).

## 2026-10-27: F5 follow-up, the hook code made ruff-clean

**Why:** Din found ruff errors in the hook code; leaving them would mean an ignore in the before-push check.

**Checked:** pinned ruff 0.17.0 (E2, run with `uvx`) with the CONVENTIONS section 1 rule set and Google docstrings found 87 findings and 2 unformatted files: long lines (34), unittest-style asserts (13), missing docstrings (25), `os.path` and `os.getcwd` (6), `print` (2), two duplicate `if` arms, mutable class defaults, the exception name, an unused `noqa`.

**Done (no behaviour change):**
- `guard.py`: Google docstrings, pathlib in place of `os.path.basename`, `expanduser` and `getcwd`, `sys.stderr.write` in place of `print` (no `T20` ignore needed), `Blocked` renamed `BlockedError`, the write-target branches folded into `write_targets()`, formatted with `ruff format`.
- `test_guard.py`: moved from unittest to pytest with parametrized cases (pytest is the project's runner; `D` is off for tests per CONVENTIONS), so Phase 1's `uv run pytest` can run it with no special case. Same cases as before, now 90 test items. Run: `uv run pytest .claude/hooks` (until Phase 1: `uvx --python 3.14 pytest@9.1.1 .claude/hooks`).
- `settings.json`: the allow rule for the old unittest command removed; `Bash(uv run pytest *)` covers the new one.

**Verified:** `ruff check` passes with `target-version` py39 and py314; `ruff format --check` passes; pytest 9.1.1: 90 passed with the guard run by Python 3.14.7, and 90 passed with `GUARD_PYTHON=/usr/bin/python3` (3.9.6).

**Carried to task 1.6:** the root ruff config targets py314 and the hook files must keep running on 3.9, so if a future rule needs 3.10 syntax the hook directory gets a nested config with `extend` and `target-version = "py39"`. Today both targets pass, so no nested config was added. Task 1.3 runs `.claude/hooks` in `scripts/check.sh` (carried from the F5 draft).

**Handoff (2026-10-27, end of session):** F5 is decided and closed, including the ruff follow-up. Phase 0 remaining: F6 (model and data card templates), then F8 (the formatting-only Prettier 3.9.10 pass, Din's go for the download), then Din creates `dinsdev/heartbeat` and pushes `main` (F5 denies repo creation and pushes to Claude, so Claude prepares the exact commands). Tools before Phase 1: `uvx ruff@0.17.0` and `uvx --python 3.14 pytest@9.1.1 .claude/hooks`; the terminal CLI is now logged in, so `claude -p` runs in a scratchpad repo work for end-to-end hook checks. Open items carried: Din's check that ask rules prompt in a new desktop session; the de Chazal full text (PRD Q2); the zero standard deviation case in B3's z-score (Phase 2 plan); Workers custom-domain coverage and preview URLs (Phase 6); the dins-projects PRD pointer (that repo).
