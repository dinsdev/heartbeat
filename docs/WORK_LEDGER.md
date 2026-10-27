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
