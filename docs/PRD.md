# Heartbeat: Product Requirements

| | |
|---|---|
| **Status** | Draft for Din's review (F1). Becomes the source of truth once Din locks it. |
| **Owner** | Din (decisions); Claude (drafting) |
| **Date** | 2026-10-27 |
| **Supersedes** | Section 7 of `~/Develop/dins-projects/docs/PRD.md` (the slate-level draft). Differences are listed in Appendix A. |
| **Related** | `docs/WORK_LEDGER.md` (every decision with its reason), `docs/TASKS.md` (planning items A1 to G4), `docs/PLAN.md` (phases and the rule-to-test table, F2), `~/Develop/dins-projects/docs/PRD.md` (shared requirements for all four projects), `~/Develop/dins.dev/docs/site/PRD.md` (site content model) |

**How to read this document.** Requirements carry an ID (for example `EVAL-04`), a priority and the planning item that decided them (for example `C1`). The ledger holds the reasoning; this document holds the requirement. If the two disagree, that is a bug: raise it, don't pick one.

**Priorities.**
- **P0:** core (A2). The project does not publish without it.
- **P1:** decided supporting work. It should ship with core, but a late P1 does not block publishing. (A2 defined only core, stretch and out; the P1 split is Claude's proposal, see open question Q1.)
- **P2:** stretch (C8). Starts only after core is publishable, in a fixed order.

---

## 1. Summary

Heartbeat is a small 1D convolutional network that labels heartbeats in ECG recordings as normal or one of three irregular kinds, tested on 21 patients it never saw during training. Its point is rigor, not raw performance: many published heartbeat classifiers report near-perfect accuracy because beats from the same patient land in both training and test sets. Heartbeat measures the honest number, shows the inflated one beside it, and ships the exact model to the browser so a visitor can watch it label a real recording live.

It is one of four portfolio projects on dins.dev, written for US master's admissions committees first (applications open mid-January 2027) and recruiters second. It succeeds when a skeptical reader can verify every claim: the split has no patient leak, the evaluation plan was public before the test set was opened, one command reproduces the numbers, and the model in the browser is provably the model that was tested.

## 2. Background

**Why this project exists.** dins.dev needs projects that prove Din can do machine learning, data science and data engineering through working demos (dins-projects PRD, section 1). Heartbeat is the deep learning entry and the first one built.

**The domain.** The MIT-BIH Arrhythmia Database (PhysioNet, ODC-By 1.0) holds 48 half-hour, two-lead ECG recordings from 47 subjects, with every beat annotated by cardiologists. It is the standard benchmark for heartbeat classification. AAMI EC57 groups the beat annotations into five classes: N (normal and bundle branch block beats), S (supraventricular ectopic), V (ventricular ectopic), F (fusion) and Q (paced or unclassifiable).

**The trap.** If beats from one patient appear in both training and test data, a model can recognize the patient's beat shapes instead of learning what makes a beat irregular. Results measured this way look excellent and do not carry over to new patients. de Chazal et al. (2004) proposed the inter-patient split (DS1 for training, DS2 for testing, 22 records each, different patients) to avoid this. On that split, their two-lead classifier reached 75.9% S sensitivity at 38.5% positive predictivity and 77.7% V sensitivity at 81.9% (abstract, verified 2026-10-26). Those are the realistic numbers in this field, and they are far below the "98% accuracy" figures common in projects that split by beat.

**A leak in the standard split itself.** PhysioNet states that records 201 and 202 come from the same subject. In de Chazal's split, 201 is in DS1 and 202 in DS2, so the standard split leaks one subject (B1). Heartbeat removes 202 from DS2.

**Why now.** The dins.dev content freeze is planned for 2026-12-01 and site launch for 2026-12-12, ahead of applications in mid-January 2027. Din treats that schedule as a best case, not a deadline (2026-10-22). Heartbeat is first in the build order.

## 3. Problem statement

Admissions readers and technical reviewers see many student ECG projects that report 95 to 99% accuracy on MIT-BIH. Most of those numbers come from splitting beats at random, so the same patients appear in training and testing; the realistic inter-patient numbers for the rare, clinically interesting classes are much lower (about 76% S recall at about 39% precision in the reference work). A reader skimming a portfolio cannot tell an honest result from an inflated one, and a modest honest number can look worse than an impressive leaky one.

The problem for this project is therefore credibility, not accuracy: **show, in a way a skeptical reader can check, that Din knows where medical ML results get inflated, measured this one honestly, and shipped a model that works on people it never saw.** A good outcome makes the honest number the more impressive one, because the reader can see exactly what the inflated number hides.

What makes this hard:
- The interesting classes are rare and concentrated in a few patients. In DS2 without 202, record 232 holds 78% of S beats, and record 213 holds 94% of F beats (B4). A pooled number can be one person's number.
- "Trust me" is not evidence. Every claim needs a test, a committed file or a reproducible command behind it.
- The demo must run in a browser on a portfolio page, within the site's performance and accessibility budgets.

## 4. Audience and stakeholders

| Audience | What they need | Time they give | Where they meet Heartbeat |
|---|---|---|---|
| **Admissions committees** (primary) | A real question, careful method, honest results and named limits | 2 to 5 minutes | Home stage video, then the case study |
| **Recruiters and hiring managers** | What it does, the stack, one real number | 30 seconds | Home stage video and the case study summary block |
| **Curious visitors** | Something to play with | About a minute | Case study iframe and the full demo |
| **Technical skeptics** (reviewers, engineers) | Proof: the split, the pre-registration, the parity test, a rebuild | As long as it takes | The public repo |

**Conflicting needs.** Recruiters want one striking number; the honest headline number is modest. Proposed resolution (follows from A1 and C5; final wording in G1): lead with the leakage exhibit (two numbers side by side), so the one number a fast reader takes away is the gap, not a bare score.

**Not for:**
- **Patients or clinicians.** Heartbeat is a research demo, never medical advice (D7). It accepts no uploads and no device input (A2).
- **ML researchers looking for state of the art.** Beating published numbers is a non-goal (A1).

**Stakeholders.**
- **Din:** owner; locks every decision; gives the go for repo creation, pushes, secrets and the first production deploy (E6).
- **dins.dev site repo:** hosts the stage video and case study, and must accept the integration changes in G4.
- **PhysioNet and the database authors:** license terms (ODC-By 1.0) and requested citations (B5).

## 5. Goals and success criteria

A3 rules out numeric results targets: a number to hit invites tuning toward it, which is the behavior this project calls out. Success is defined by checks that are true or false, not by scores.

| # | Goal (A1) | Done when | Checked by |
|---|---|---|---|
| G1 | **The 10-second read works** | The home stage video shows a real ECG scrolling with beats labeled, plus one plain line saying the model is tested on patients it never saw (amended by D1: video on the stage, live demo in the case study) | Din's review in a preview deploy |
| G2 | **The trap is shown, not described** | The case study shows the leakage exhibit (C5): same model, same 22 patients, patient-grouped number beside the beat-split number, both with intervals | Results file plus case study review |
| G3 | **Every claim is traceable** | One command reproduces the artifacts (E4); CI proves no subject appears on both sides of any split; the evaluation plan was pushed publicly before the sealed run (E6) | CI, `heartbeat verify`, git history on GitHub |
| G4 | **The browser model is provably the same model** | The parity chain passes in CI (E5), and the page shows a live counter of browser labels matching the Python results (D3) | CI and the on-page counter |
| G5 | **Failures are named** | A limits section and the model card say in plain words where the model fails (per-patient table, F caveat, annotation caveat) | Model card and case study review |
| G6 | **The comparison is reported straight** | CNN and baseline are compared on the same draws with intervals, and the page states the outcome whichever way it goes (A3) | Results file plus case study review |

**Guardrails (must never be violated):**
- No result appears anywhere (page, README, commit message, chat) until a run produces it (dins-projects shared requirement 5).
- DS2 is read only by `evaluate-test`, only with a matching freeze record, and every run is logged (C1, C6).
- The home page budget of the site is not touched: the stage uses a video, not a live iframe (D1).
- The demo's performance gates hold (D5, section 9).

## 6. Non-goals

Each of these could reasonably have been a goal. They are excluded on purpose.

| Non-goal | Why not |
|---|---|
| **State-of-the-art or published-number targets** | Rigor leads (A1). A target invites tuning toward it (A3). de Chazal's numbers appear only as context, labeled as two-lead and measured on all 22 DS2 records. |
| **Clinical use or clinical claims** | No clinical validation is possible here. The wording is controlled by D7's avoid list. |
| **Visitor uploads or live device input** | Needs privacy handling and different preprocessing, and changes the claim from "tested on unseen patients" to "runs on anything" (A2). |
| **Rhythm-level diagnosis or multi-lead models** | Beat classification on one lead fits a one-trace demo and the standard benchmark (A2, B1). |
| **Our own beat detector in core** | Core uses the expert beat annotations to isolate the classifier (B2). A detector is stretch 3, scored end to end. |
| **Large hyperparameter sweeps, ensembles, LLM explanations** | Tuning budget is fixed and equal for both models (C2, C3); explanations would invite clinical-sounding text (A2). |
| **Accuracy as a headline** | Accuracy is dominated by the N class. It appears only in the leakage exhibit, labeled as the number papers often lead with (C5). |
| **A live iframe on the dins.dev home stage** | Risks the home page's performance budget and needs a cross-origin pause protocol (D1). |
| **Rented GPUs or paid serving** | The model trains on a Mac in hours (C7); the demo runs on Cloudflare's free plan. |
| **An experiment tracking service** | About 20 development configurations do not justify one; run folders and committed results do the job (C6). |
| **DS1 patients in the final demo** | Training patients would look better than they deserve (D4). |

## 7. Use cases

**UC1: The 10-second read (recruiter or admissions reader on the home page).**
The dins.dev stage shows Heartbeat's window with a 16:10 video recorded from the real demo: patient 200 scrolling, beats labeled with letters and colors, irregular beats marked, and one plain line about unseen patients. The research-demo line sits in a corner. "View project" opens the case study.
Edge cases: reduced motion shows the site's calm version and poster frame; "Pause demos" pauses the video (site behavior, no Heartbeat work).

**UC2: The careful read (admissions reader, 2 to 5 minutes).**
The case study opens with the live demo in an iframe, labeling beats in the reader's browser. Below it: the summary block with real numbers, the leakage exhibit (two rows, one sentence of explanation), the DS2 headline with intervals, the CNN against baseline result stated plainly, the per-patient caveats, and the limits section.
Edge cases: the iframe fetches nothing heavy until it scrolls into view; the iframe follows the site's theme via `postMessage`; if WebAssembly is blocked, the demo plays precomputed labels with a visible note.

**UC3: Playing with the demo (curious visitor, full page at `heartbeat.dins.dev`).**
The demo autoplays patient 200 from its first irregular stretch. The visitor changes speed, scrubs, switches patients (each listed with its expert beat counts), and presses "Next irregular beat" or "Next disagreement" to jump to a model mistake. A table of visible beats shows time, model label, probability, expert label and match. The counter reads, for example, "Labels match the Python results: 2,134 of 2,134 beats".
Edge cases: patient 212 has no irregular beats ("Next irregular beat" says so instead of doing nothing; proposed here, D6 did not cover it); labels appear one beat late because of the post-RR feature (stated in the about text).

**UC4: Keyboard, screen reader or reduced-motion visitor.**
Every control is a native element reachable by keyboard. The canvas has a summary label updated on pause and seek; a polite status line summarizes each 10 seconds of playback; the beat table is readable at the visitor's pace when paused. Under reduced motion the trace pages every 10 seconds without scrolling and nothing autoplays.

**UC5: The skeptic verifies (engineer or reviewer).**
From the case study, the reader opens the public repo. They find the pre-registered plan committed and pushed before the sealed run, the freeze record, the append-only test log, the leakage tests in CI, and the parity tests. `uv run heartbeat verify` checks manifests, frozen-model parity and result consistency in minutes; `uv run heartbeat rebuild` reproduces everything in a few hours.
Edge cases: running `evaluate-test` without a matching freeze record or on a dirty tree refuses with a clear message; a reproduction after the sealed run is logged as a reproduction, never as a new test.

**UC6: Din runs the sealed test (maintainer, once).**
Development happens on DS1 only. When the configuration is chosen, Din commits and pushes the freeze record (commit, config, model checksum), runs `evaluate-test` once for the baseline and the CNN together, and pushes the log entry. The demo then switches to DS2 patients built from the frozen model's outputs.
Edge cases: a bug found after the sealed run is fixed and rerun; both runs stay in the log and the ledger (A3).

## 8. Functional requirements

### 8.1 Data (DATA)

- **DATA-01 (P0, B5, E2).** The downloader must fetch exactly the 132 files the project uses (`.hea`, `.dat`, `.atr` for the 44 non-paced records) from PhysioNet's S3 mirror first, falling back to `physionet.org`, into the gitignored cache `data/raw/mitdb/1.0.0/`.
- **DATA-02 (P0, B5).** Every run must check the cache against the committed manifest of 132 SHA256 values and stop on any mismatch. Files whose checksums match are not downloaded again, so rebuilds work offline after the first run.
- **DATA-03 (P0, B1).** The four paced records (102, 104, 107, 217) are excluded. The split lists, exclusions and their reasons live in a committed manifest, not in code.
- **DATA-04 (P0, B1).** The pipeline must select the MLII lead by signal name, never by channel index (record 114 has its signals reversed).
- **DATA-05 (P0, B3, D4).** The canonical signal is MLII in millivolts at 360 Hz, filtered once per record with a 0.5 to 40 Hz zero-phase Butterworth bandpass, then rounded to int16 at 200 units per mV. Training, evaluation and the browser all use this rounded signal.
- **DATA-06 (P0, B3).** Each beat window is 256 samples: 96 before the annotation and 160 after, with no realignment, z-scored per window.
- **DATA-07 (P0, B3).** Six RR features per beat: pre-RR, post-RR, local average RR (previous 10 beats), long average RR (previous 5 minutes), pre-RR over local average, post-RR over pre-RR. Only post-RR may look ahead, by one beat. RR is computed over every annotated beat, including unscored classes.
- **DATA-08 (P0, B3).** The first and last beat of each record are dropped. Noisy segments are not excluded.
- **DATA-09 (P0, B4).** Annotation symbols map to AAMI classes exactly: N = N, L, R, e, j; S = A, a, J, S; V = V, E; F = F; Q = /, f, Q. Non-beat symbols (`!`, `x`, noise and rhythm markers) are not beats. Any unrecognized symbol must make the pipeline fail loudly.
- **DATA-10 (P0, B4).** Four classes are scored (N, S, V, F). Q beats are excluded from training and scoring but count for RR.
- **DATA-11 (P0, B4, E5).** Per-record class counts must match PhysioNet's beat table.

### 8.2 Split and evaluation discipline (EVAL)

- **EVAL-01 (P0, B1).** DS1 is de Chazal's 22 training records. DS2 is de Chazal's test records without 202, 21 records from 21 subjects.
- **EVAL-02 (P0, B1, C1).** A committed subject map gives 201 and 202 one subject ID. Leakage tests run on subject IDs: no subject on both sides of DS1 and DS2, and none on both sides of any fold.
- **EVAL-03 (P0, C1).** Development uses 5-fold `StratifiedGroupKFold` on DS1, grouped by subject, with a fixed seed. The fold file is produced only by `heartbeat make-folds`, committed, and only checked (never regenerated) by `rebuild`.
- **EVAL-04 (P0, C1).** Training and cross-validation code must be unable to load DS2 records. Only `evaluate-test` reads DS2.
- **EVAL-05 (P0, C1, C6).** `evaluate-test` must refuse to run without a freeze record matching the commit hash, config and model checksum, or on a dirty working tree. It evaluates the baseline and the CNN in the same run.
- **EVAL-06 (P0, C6).** Every sealed run appends to the committed `results/test_runs.jsonl` and gets a ledger entry. Nothing in the log is overwritten.
- **EVAL-07 (P0, C1).** Development metrics are pooled out-of-fold predictions plus the spread across folds. No early stopping: one epoch count is chosen from averaged validation curves, and the final model retrains on all of DS1 for that many epochs.
- **EVAL-08 (P0, A3, C4).** The pre-registered report contains:
  1. Headline: S and V recall and precision on the 21 DS2 patients; macro F1 over N, S and V, with four-class macro F1 beside it.
  2. False positive rates for S and V.
  3. S recall and precision on DS2 without record 232, with intervals from a bootstrap over the remaining 20 patients.
  4. A per-patient table of S and V results with raw counts in every cell, and a percentage only when the patient has at least 10 beats of that class.
  5. A four-by-four confusion matrix, noting the 7 Q test beats as not scored; N and F recall and precision with the F caveat.
  6. Headline numbers from seed 0; one secondary line with the range across seeds 1 and 2.
- **EVAL-09 (P0, A3, C4).** Intervals come from a paired patient bootstrap: 21 DS2 patients resampled with replacement, 10,000 draws, fixed seed, percentile intervals, CNN and baseline scored on the same draws. A draw with no predicted S beats is skipped for S precision only, and the skip count is reported.
- **EVAL-10 (P0, A3).** "CNN better than baseline" may be stated only when the interval of the paired difference sits above zero; otherwise the page says there is no clear difference. If the baseline matches or beats the CNN, the CNN still ships and the page says so plainly.
- **EVAL-11 (P0, C4).** Calibration: labels are the argmax of the weighted model and calibration never changes a label. Probabilities subtract the log class weights from the logits, then apply one temperature fitted on DS1 out-of-fold predictions. Same procedure for both models.
- **EVAL-12 (P0, C4).** Calibration is reported as one-vs-rest calibration error for S and V with 10 equal-mass bins, reliability diagrams, log loss and Brier score.

### 8.3 Models (MODEL)

- **MODEL-01 (P0, C2).** Baseline: multinomial logistic regression (scikit-learn, `lbfgs`) on the six RR features only, with log ratio features and a scaler fitted inside each training fold, `class_weight="balanced"`, and C chosen from five log-spaced values (0.01 to 100) by pooled out-of-fold macro F1.
- **MODEL-02 (P0, C3).** CNN: the 256-sample window through four blocks of Conv1d (kernel 7), batch norm, ReLU and max-pool by 2 (channels 16, 32, 64, 64 at width 1), global average pooling, concatenated with the same six standardized RR features, a 64-unit layer with dropout 0.3, four outputs.
- **MODEL-03 (P0, C3).** CNN training: cross-entropy with the same balanced class weights as the baseline; fixed augmentation (time shift up to 5 samples each way, light Gaussian noise); AdamW at a constant 1e-3, weight decay 1e-4, batch 256.
- **MODEL-04 (P0, C3, C6).** CNN tuning: width 0.5, 1 or 2, plus epoch count, on the C1 folds with seeds 0, 1 and 2; selection on the seed mean of pooled out-of-fold macro F1. The baseline and CNN get the same folds, metric and reporting.
- **MODEL-05 (P0, C6).** Seed 0 is the shipped model. Each run derives every random seed from one master seed; the fold seed is independent.
- **MODEL-06 (P0, C6, C7).** Final models train on CPU in deterministic mode with single-process data loading. Same-seed CPU runs must produce identical weights on the same machine.
- **MODEL-07 (P0, C6).** Every run writes a run folder (config, commit and dirty flag, library versions, lockfile hash, device, thread count, metrics, out-of-fold predictions, checkpoint, log). Anything a page uses is copied to committed `results/` by the rebuild command, never by hand.

### 8.4 Leakage exhibit (EXHIBIT)

- **EXHIBIT-01 (P0, C5).** The exhibit runs inside DS1 only: the patient-grouped C1 folds against beat-level random 5-fold (`StratifiedKFold` on beats), same 22 patients, beats, code and seeds.
- **EXHIBIT-02 (P0, C5).** Both sides use the configuration chosen on the honest folds, with no retuning on the leaky side. Both the CNN and the baseline are shown.
- **EXHIBIT-03 (P0, C5).** Both sides report the headline metrics with patient-bootstrap intervals, plus accuracy, which appears only here and is labeled as the number papers often lead with.

### 8.5 Export and parity (PARITY)

- **PARITY-01 (P0, E2, E3).** The final model exports to a single-file ONNX model (opset 20, batch norm folded), with the scaler and calibration as JSON and a freeze record, committed under `models/heartbeat-v1/`.
- **PARITY-02 (P0, E5).** Export writes shared fixtures of about 50 real DS1 beats (never DS2) to `fixtures/parity/`.
- **PARITY-03 (P0, E5).** The parity chain must pass at a tolerance of 1e-5 on outputs and features with exact labels: PyTorch against Python ONNX Runtime; Python ONNX Runtime against ONNX Runtime Web in a real browser; TypeScript preprocessing (window, z-score, RR features, scaler, calibration) against Python step by step.
- **PARITY-04 (P0, E1).** Python and the browser use the same ONNX Runtime version (1.30.0 at the time of writing).

### 8.6 Demo (DEMO)

- **DEMO-01 (P0, D1).** The full demo is served at `https://heartbeat.dins.dev` by its own Cloudflare Worker with static assets, deployed from this repo. `?embed=page` serves the case study iframe mode: no page chrome, muted.
- **DEMO-02 (P0, D3).** Every label shown is computed in the visitor's browser by the shipped ONNX model in a Web Worker (single-threaded WebAssembly). The browser cuts and z-scores windows from the shipped trace, computes RR features from the shipped beat positions, applies the scaler, runs the model and applies calibration. Filtering stays in Python.
- **DEMO-03 (P0, D3).** The Worker labels beats in chunks about 10 seconds ahead of the playhead.
- **DEMO-04 (P0, D3, E5).** Each beat shows the model label and the expert label, with disagreements marked. A visible counter reports how many browser labels match the shipped Python labels, using the parity rule (labels exact, probabilities within 1e-5). A mismatch is shown, never hidden.
- **DEMO-05 (P0, D3).** If WebAssembly or the model fails to load, the demo plays the shipped Python labels with the visible note "Showing precomputed labels; in-browser model unavailable". This fallback is never silent.
- **DEMO-06 (P0, D5).** The trace and expert labels play as soon as the trace arrives; a "model loading" note shows until the Worker is ready.
- **DEMO-07 (P0, D4).** The final demo ships all 21 DS2 patients, each the full 30 minutes, loaded only when selected. Per patient: `NNN.trace.i16` (little-endian int16 at 200 units per mV) and `NNN.beats.json` (positions, expert labels, sealed-run seed-0 labels and probabilities).
- **DEMO-08 (P0, D4).** A `manifest.json` lists patients with expert class counts, a content hash per file, the model version and the attribution note. A test checks the manifest against the files.
- **DEMO-09 (P0, D4).** The default patient is record 200 (fixed by an expert-label-only rule before any test: most S plus V beats among records with at least 25 of each). Playback starts at the first 10-second span containing an S or V beat. The page says the patient was chosen before testing because it has many irregular beats.
- **DEMO-10 (P0, D6).** Controls: play and pause; speed 0.5x, 1x, 2x, 4x; patient picker with class counts; scrub slider with time as text and 5-second steps; "Next irregular beat"; "Next disagreement".
- **DEMO-11 (P0, D6).** Every beat shows its class as a letter (N, S, V, F) as well as color; disagreements have a distinct mark (outlined ring with the expert's letter beneath); Q beats show a grey "not scored" dash. A plain-language legend explains each mark in one line.
- **DEMO-12 (P0, D6).** An HTML table lists the beats in view (time, model label, probability, expert label, match). A polite status line summarizes every 10 seconds of playback.
- **DEMO-13 (P0, D6).** Theme follows the system setting by default. The demo accepts `{type: "theme", value}` messages only from the dins.dev origin.
- **DEMO-14 (P0, D6).** The full demo autoplays on load and the iframe when visible, silent, with a visible pause control. Under reduced motion: no scrolling and no autoplay; fixed 10-second pages with Previous and Next.
- **DEMO-15 (P0, D7).** The short line "Research demo, not medical advice. Recordings come from a public research database." is always visible under the full demo's controls and inside the iframe. The fuller note appears in the about text.
- **DEMO-16 (P0, B5).** The demo shows the dataset attribution (in the iframe if it fits, otherwise in the about text), and an attribution note ships beside the demo data files.
- **DEMO-17 (P0, C1).** Until the sealed run is logged, the demo uses DS1 recordings only. DS2 demo data is built only from the frozen model after the sealed run.

### 8.7 Content and publishing (PUB)

- **PUB-01 (P0, A1, A2).** The case study fills every field of the site's `projects` collection (title, kind, summary, role, stack, results with real numbers, demo, stage capture, repo link, status) and contains: the live demo iframe at the top, the leakage exhibit, the DS2 results with intervals, the CNN against baseline outcome, the 201/202 leak fix, the limits section and the credits block.
- **PUB-02 (P0, B2, B4, C4, D3).** The limits section states at least: beat locations come from expert annotations ("these numbers assume every beat has already been found"); F is one patient on each side; S results are dominated by record 232 (with the without-232 line); calibrated probabilities are fragile across patients; labels lag by one beat; the model is one lead tested on 21 patients.
- **PUB-03 (P0, B5).** Any comparison with de Chazal says their numbers come from a two-lead classifier tested on all 22 DS2 records.
- **PUB-04 (P0, A2, F6).** `docs/MODEL_CARD.md` and `docs/DATA_CARD.md` are filled with real numbers from committed results, including the per-patient table, confusion matrix, calibration figures and data counts (including 15 Q beats).
- **PUB-05 (P0, D7, E5).** All published text avoids D7's list ("diagnose", "diagnosis", "detects arrhythmia", "detects heart disease", "clinical-grade", "accurate" as a headline, "AI doctor") and never uses em or en dashes as separators. A wording lint enforces both on the built demo and the case study draft.
- **PUB-06 (P0, D1, D7, G2).** A 16:10 stage video recorded from the real demo (patient 200) with the short research-demo line burned in.
- **PUB-07 (P0, B5, E3).** `LICENSE` (MIT, code), `DATA_LICENSE.md` (ODC-By 1.0, data), and a README stating the code license does not cover the data. Citations as listed in B5, with PhysioNet's requested citation rechecked before publishing.
- **PUB-08 (P0, D1, G4).** The dins.dev changes are handed to that repo: `demo.src` accepts the Heartbeat origin from an allowlist; the case study renders the live demo as an iframe with `loading="lazy"` and a `title`; `frame-src` allows the origin; the site posts its theme to the iframe.
- **PUB-09 (P1, G3).** Sources for the case study's "Ask Ottie about this project" retrieval.

### 8.8 Reproducibility and operations (OPS)

- **OPS-01 (P0, E4).** `uv run heartbeat rebuild` runs every stage (download, prepare, check-folds, cross-validate, select, exhibit, train-final, export, reproduce-test after the freeze only, build-demo-data), skipping stages whose input fingerprint is unchanged; `--from <stage>` forces a rerun.
- **OPS-02 (P0, E4).** Before a freeze record exists, `rebuild` stops after export and builds DS1-only demo data.
- **OPS-03 (P0, E4).** After the sealed run, `rebuild` retrains and checks against the freeze record (default mode: metrics within tolerance; `--exact`: model checksum bit for bit), evaluates DS2 with the committed frozen model, and requires results equal to the logged ones. This is logged as a reproduction, a separate entry type. Mismatches fail loudly.
- **OPS-04 (P0, E4).** `heartbeat verify` checks manifests and checksums, frozen-model parity on the fixtures, and consistency of result files with the test log, in minutes, without training.
- **OPS-05 (P0, E6).** One GitHub Actions workflow runs on every push and pull request: ruff, mypy, Python unit and real-data tests, a smoke training run, the Python parity half, ESLint, Prettier, svelte-check, Vitest, the web build with size gates, Playwright in Chromium and WebKit, and the wording lint.
- **OPS-06 (P0, E6).** Deploys run from GitHub Actions with wrangler: production on `main` after checks pass, previews on pull requests. Deploys never train; demo data is built from the committed frozen model.
- **OPS-07 (P0, E6).** The repo `dinsdev/heartbeat` is public and pushed at the end of Phase 0, before the sealed run. The freeze record is pushed before `evaluate-test` runs and the test log right after.
- **OPS-08 (P1, E6).** `scripts/check.sh` runs lint and unit tests locally in under 2 minutes.
- **OPS-09 (P1, E6).** Renovate with a 14-day minimum release age, a monthly schedule, pull requests only, no automerge.
- **OPS-10 (P1, D2).** A check script flags drift between the vendored brand tokens and fonts and their source commit in the dins.dev repo.

### 8.9 Stretch (P2, C8)

Starts only when core is publishable (sealed run done and logged, model card filled, demo passing the launch criteria in section 12, case study drafted with real numbers, CI green), with Din's go per item, in this order. Each item has a design note committed before its first result and ships whole (tests, page text, a line in the limits section) or not at all.

- **STRETCH-01 (P2).** INCART external test (pre-registered in C8): the shipped seed-0 model as frozen, all 75 records, C4 metrics, bootstrap over the 32 patients, run once and logged. Resampling, lead choice and annotation offset are fixed in the design note before any INCART prediction.
- **STRETCH-02 (P2).** Saliency overlay, precomputed in Python or by occlusion in the browser, with a randomized-weights sanity check, worded as "where the output was most sensitive".
- **STRETCH-03 (P2).** Our own QRS detector, scored end to end against reference beats within 150 ms, counting misses and extra detections.

## 9. Non-functional requirements

**Performance (D5).**

| Measure | Requirement | Enforcement |
|---|---|---|
| Model file | Under 1 MB | CI gate |
| Demo JavaScript, excluding ONNX Runtime | Under 60 KB gzip | CI gate |
| Beats JSON per patient | Under 100 KB | CI gate |
| Main-thread tasks during playback | None over 50 ms | CI gate (Playwright) |
| First trace visible | Under 1.5 s desktop, 3 s phone | Measured and reported, not gated |
| First live label | Under 3 s desktop, 6 s phone | Measured and reported, not gated |
| Inference per beat in the Worker | Median under 2 ms | Measured and reported, not gated |
| Frame rate and memory | Steady 60 fps; under 100 MB | Measured and reported, not gated |

Reported timings use Playwright with 4x CPU slowdown, and fast 4G for the phone profile. The iframe fetches nothing heavy until visible. Files use hashed names and are served as immutable. A first visit is about 4 to 5 MB compressed, mostly ONNX Runtime's WebAssembly (2.4 MB Brotli); return visits load only the chosen patient's trace.

**Accessibility (D6).** WCAG 2.2 AA, matching the site. Native controls only and no custom single-key shortcuts; targets at least 24 by 24 CSS pixels; color never the only signal; class colors at least 3:1 against the background in light and dark (tested); the brand's focus ring. Axe at zero violations in Playwright for full and embed modes, light and dark, reduced motion on and off; a keyboard-only walk of every control; one manual VoiceOver pass before publishing.

**Reliability.** A static site with no server logic beyond headers. Failure modes are loading failures; DEMO-05 covers the model, and the trace either loads or shows an error. No uptime target beyond Cloudflare's.

**Security and supply chain (D1, E2, E6).**
- Response headers: `Content-Security-Policy` with `frame-ancestors` limited to `https://dins.dev` and the site's preview hostnames, and `'wasm-unsafe-eval'` in `script-src`. A test checks the built headers.
- Theme messages accepted only from the dins.dev origin.
- Dependencies pinned to the newest stable release at least 14 days old, enforced by uv `exclude-newer` and pnpm `minimumReleaseAge`, covering transitive packages. Install scripts allowed only for esbuild and workerd.
- Third-party GitHub Actions pinned to full commit hashes; read-only workflow permissions by default.
- No secrets in the repo. The Cloudflare token is a GitHub secret that Din creates; Claude never handles its value.

**Privacy.** The demo collects nothing from visitors: no uploads, accounts, cookies or analytics, and no visitor data leaves the browser (D7's "Nothing here uses your data", dins-projects non-goals). Cloudflare's own request handling is outside the project's control. See Q4 for whether this rules out usage metrics.

**Platform.** Current Chromium and WebKit browsers on desktop and phone, tested in CI. Requires WebAssembly and Web Workers for live labels; without them the labeled fallback runs. Firefox is not in the automated matrix (E5); see Q5.

**Reproducibility (C6, C7, E4).** Bit-for-bit retraining on the same machine and setup with `--exact`; within tolerance elsewhere. Inference with the shipped ONNX model reproduces the reported metrics exactly.

**Cost.** Zero recurring cost: Cloudflare Workers free plan with static assets; GitHub Actions on a public repo; training on Din's Mac.

**Internationalization.** English only, matching the site.

## 10. Constraints

| Constraint | Detail | Source |
|---|---|---|
| Compute | Apple M5 Mac with 16 GB only. MPS for development numbers, CPU deterministic for frozen models. No rented GPU. Measured: about 1 hour for the 45 development runs on MPS; about 30 minutes for the three final models on CPU at width 1, about 2 hours at width 2. | C7 |
| Hosting | Cloudflare Workers free plan with static assets on a subdomain of dins.dev. | D1, E6 |
| Site integration | The dins.dev home stage holds a video, and the site's home budget (100 KB first-party JavaScript, 60 fps, no task over 50 ms) must not be put at risk. | D1 |
| Data license | ODC-By 1.0: attribution required wherever derived data ships. | B5 |
| Pinned stack | Python 3.14, torch 2.14.1, onnxruntime 1.30.0, scikit-learn 1.9.1, wfdb 4.3.1; Node 24, Svelte 5.57.2, Vite 8.3.4, TypeScript 6.0.3 (7 breaks svelte-check), onnxruntime-web 1.30.0. Full list in the E2 ledger entry. | E1, E2 |
| People | Din, working with Claude. Din approves every decision, push, secret and first deploy. | E6 |
| Schedule | Best case: content freeze 2026-12-01, site launch 2026-12-12, applications from mid-January 2027. Not a deadline (Din, 2026-10-22). If Heartbeat is not ready, it stays a draft; the site never shows a half-built project. | dins-projects PLAN, site PRD |

## 11. Assumptions

Each is falsifiable. High-risk ones carry a check.

| # | Assumption | If wrong | Risk and check |
|---|---|---|---|
| AS1 | de Chazal's DS1 and DS2 record lists are as transcribed in secondary sources. | The split would differ from the reference work. | Low: our class totals match the totals usually quoted for the split. Check: read the full text (Q2). |
| AS2 | The B3 RR features loosely follow de Chazal's. | Only the page wording is affected. | Low. The page states only what the abstract supports until Q2 closes. |
| AS3 | MPS development numbers stay within tolerance of CPU. | Selection could differ between modes. | Medium. E4's reproduction check exposes it; the frozen models are CPU-only regardless. |
| AS4 | Cloudflare's free plan covers a custom domain on a subdomain in the same zone. | Hosting plan changes. | Low: dins.dev already runs on Workers in that zone. Confirmed at first deploy (Q3). |
| AS5 | Cloudflare compresses `application/wasm` automatically and not the int16 trace. | Download sizes differ from D5's estimates. | Low: documented. Measured at first deploy. |
| AS6 | The dins.dev repo accepts the G4 changes. | The case study cannot show the live iframe; it would fall back to a link. | Medium: the site plans currently reject outside `demo.src` URLs and frames. Hand over early (G4). |
| AS7 | ONNX Runtime Web gives the same labels in WebKit as in Chromium. | The parity counter would show mismatches on Safari. | Low: measured differences are about 1e-7 in Node. Check: Playwright parity in both engines. |
| AS8 | Readers value a visible, checkable rigor story over a higher headline number. | The project's framing would underperform. | Medium. This is the project's core bet (A1). Mitigated by the exhibit, which still produces a striking number. |

## 12. Launch criteria

Heartbeat is publishable (and stretch may start) when all of these hold (C8, dins-projects PRD section 9):

1. The sealed DS2 run is done and logged, with the freeze record and plan pushed before it.
2. Model card and data card are filled with real numbers from committed results.
3. The demo works in the case study iframe and full page, on a phone, in light and dark, with keyboard and reduced motion; axe passes in every mode; one VoiceOver pass is done.
4. The case study is drafted with real numbers and passes the wording lint.
5. `heartbeat rebuild` reproduces the artifacts; CI is green; all CI gates in section 9 hold.
6. Data licenses are cited (B5), with PhysioNet's citation rechecked.
7. The stage video exists, recorded from patient 200 with the research-demo line.
8. Din has reviewed it in a preview deploy.

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **The CNN does not beat the baseline.** RR intervals carry much of the S signal. | Medium | Medium | Pre-registered (A3): the CNN ships, the page says plainly that the baseline matched or beat it and why that is plausible. The rigor story does not depend on the CNN winning. |
| **One patient drives the S result.** Record 232 holds 78% of DS2's S beats. | High (by construction) | Medium | Pre-registered without-232 line and per-patient table (B4, C4). |
| **A bug is found after the sealed run.** | Low | High | Fix and rerun; both runs stay in the log and the ledger. No silent reruns (A3, EVAL-06). |
| **Overfitting to patient 208** (90% of DS1's F beats, each F beat weighted about 110 times a normal beat). | Medium | Low | Visible in the CV curves; F is never a headline (B4, C3). |
| **Schedule slips past the best-case freeze.** | Medium | Medium | Small core, stretch gated (C8); Heartbeat stays a draft rather than shipping half done. |
| **First-visit weight on phones** (about 4 to 5 MB, mostly the runtime). | Medium | Low | Trace plays before the model loads (DEMO-06); fallbacks noted in D5 (reduced-operator build or hand-written inference) if measured load times miss. |
| **We are wrong about the audience** (AS8): readers skim and see only a modest number. | Medium | High | Lead with the exhibit (the gap is the striking number); one plain line on the stage; recruiters get the stack and the gap in the summary block. |
| **dins.dev integration lags** (AS6). | Medium | Medium | Hand G4 over early; the full demo works standalone at `heartbeat.dins.dev`. |

## 14. Key decisions and alternatives considered

Full reasoning is in the ledger; these are the decisions a reviewer is most likely to question.

| Decision | Alternatives rejected | Why this one | What it costs |
|---|---|---|---|
| Drop 202 from DS2 (B1) | Drop 201 from DS1 | 201 holds 13.6% of DS1's S beats and 97 of its 100 aberrated APC beats | Test set is one record off the published DS2 |
| Pre-registered evaluation plan (A3) | Numeric results targets | A target invites tuning toward it | No number to declare victory against |
| 5-fold grouped CV on DS1 (C1) | Leave-one-subject-out | One-patient folds make the spread noise; 4 times the runs | Fewer, larger validation groups |
| Fixed epochs chosen from averaged CV curves (C1) | Early stopping per fold | Final retrain on all of DS1 needs one epoch count | Out-of-fold numbers slightly optimistic, stated |
| Exhibit inside DS1 (C5) | Pool all 43 records and split beats at random | Pooling breaks the DS2 seal and compares different patients | The exhibit uses 22 patients, not 43 |
| Expert beat locations in core (B2) | Our own detector in core | Isolates the classifier; detector is stretch 3 | Numbers assume every beat is found, stated |
| Filter in Python, ship the filtered trace (B3) | Filter in TypeScript | Parity stays simple; the demo shows the signal the model saw | Traces ship pre-filtered |
| Macro F1 over N, S, V as headline (C4) | Four-class macro F1 | DS2's F is 94% one patient; F stays visible beside it | Headline ignores F |
| Live inference in the browser (D3) | Precomputed labels only | Proves the shipped model is the tested model | ONNX Runtime's 2.4 MB download |
| Video on the home stage, live iframe in the case study (D1) | Live iframe on the stage | Home page budget and a cross-origin pause protocol | The stage is a recording, not live |
| Stock ONNX Runtime Web (D5) | Reduced-operator build; hand-written inference | No extra toolchain; parity rests on the tested runtime | Larger download; kept as fallbacks |
| All 21 DS2 patients, default by a label-only rule (D4) | A hand-picked showcase patient | No cherry-picking by construction | Some patients are uneventful |
| Logit adjustment plus temperature (C4) | Calibrate weighted outputs directly; no calibration | Undoes deliberate rare-class inflation without changing labels | Rare classes are flagged below 50% probability, explained on the page |

## 15. Edge cases

| Area | Case | Expected behavior | Source |
|---|---|---|---|
| Data | Record 114 has MLII as the second channel | Selected by name; unit test covers it | B1 |
| Data | Unknown annotation symbol | Pipeline fails loudly | B4 |
| Data | Flutter waves (`!`, 472 in record 207) and non-conducted P waves | Not beats; not used for RR | B4 |
| Data | Checksum mismatch in cache | Run stops | B5 |
| Data | First and last beat of a record | Dropped (no full window or RR) | B3 |
| Features | Beats near a record's start | RR averages use the available past, expanding | B3 |
| Features | Playback starts mid-recording | Whole-recording beat positions ship, so the 5-minute history exists | D3 |
| Metrics | Bootstrap draw with no predicted S beats | Skipped for S precision only; skip count reported | C4 |
| Metrics | Patient with fewer than 10 beats of a class | Counts only, with a footnote | C4 |
| Metrics | Q beats in DS2 (7) | Not scored; noted under the confusion matrix | B4 |
| Folds | Folds without 208 in training see almost no F | Reported, not engineered around | C1 |
| Sealed run | No matching freeze record, or dirty tree | `evaluate-test` refuses | C1, C6 |
| Sealed run | Rebuild after the sealed run | Logged as a reproduction; mismatches fail | E4 |
| Demo | Patient 212 has no irregular beats | Listed with its counts; "Next irregular beat" says there is none (proposed here) | D4, D6 |
| Demo | Model and expert disagree | Distinct mark; reachable by "Next disagreement" | D6 |
| Demo | WebAssembly blocked or model fails | Labeled fallback to shipped Python labels | D3 |
| Demo | Browser labels differ from Python | Counter shows the mismatch | D3 |
| Demo | Label timing | Labels appear one beat late (post-RR); stated | B3 |
| Demo | Theme message from another origin | Ignored | D6 |
| Demo | Reduced motion inside the iframe | Follows the viewer's setting | D1 |
| Demo | Iframe offscreen | No heavy fetch until visible | D5 |

## 16. Measurement plan

Because A3 rules out results targets, measurement here covers three things:

1. **Model results (pre-registered).** Section 8.2 fixes exactly what is computed and reported, before any DS2 run. Development signal: pooled out-of-fold metrics and fold spread on DS1. Final signal: the single sealed run. "Working" means the plan was followed and reported in full; "not working" means any deviation from it, which is logged and explained, never hidden.
2. **Demo quality.** CI gates and reported timings in section 9; the parity counter on the page.
3. **Reader outcome.** Not instrumented (see Q4). Proxy: Din's review against goals G1 to G6 in a preview deploy.

## 17. Release plan

Detailed phases belong to `docs/PLAN.md` (F2). The order the requirements impose:

1. **End of Phase 0.** Planning docs committed; repo created as public `dinsdev/heartbeat` and pushed (Din's go). This timestamps the pre-registered plan.
2. **Build on DS1.** Pipeline, baseline, CNN, exhibit, export, parity, and the demo running on DS1 recordings. Previews deploy on pull requests.
3. **Freeze.** Freeze record committed and pushed.
4. **Sealed run.** `evaluate-test` once; log pushed; ledger entry.
5. **DS2 demo and content.** Demo data rebuilt for the 21 DS2 patients; model card, data card and case study drafted with real numbers; stage video recorded.
6. **Review and launch.** Launch criteria (section 12); Din reviews in a preview deploy; first production deploy (Din's go); G4 handed to the dins.dev repo.
7. **Stretch,** if Din gives the go, in C8 order.

**Rollback (proposed here).** The demo is static: rolling back means redeploying the previous Worker version. Results are never rolled back; a correction is a new logged run with a ledger entry.

## 18. Open questions

| # | Question | Why it matters | Owner | Resolve by |
|---|---|---|---|---|
| Q1 | Is the P1 split right (Ask Ottie sources, `scripts/check.sh`, Renovate, brand drift check), or should all of them be P0? | Decides what can slip without blocking launch. | Din | F1 lock |
| Q2 | Does the de Chazal full text confirm the DS1 and DS2 lists and the RR features? TARA serves the PDF behind a Cloudflare bot check. | Page wording about the reference split and features (AS1, AS2). | Din (download the PDF), then Claude (read) | Before the case study draft |
| Q3 | Does the free plan cover the `heartbeat.dins.dev` custom domain? | Hosting (AS4). | Claude, at first deploy | First production deploy |
| Q4 | Should the demo or case study measure usage in any way, given "nothing here uses your data"? | Decides whether reader outcome can be measured at all. Current reading: no analytics. | Din | G1 |
| Q5 | Is Firefox worth adding to the Playwright matrix? | Firefox users are untested today. | Din | F2 |
| Q6 | What are the exact stage line and summary wording? | The 10-second read (G1). | Din | G1 and G2 |
| Q7 | Which dins.dev preview hostnames go in `frame-ancestors`? | The case study iframe in site previews. | Claude | Build time |
| Q8 | Do the INCART resampling, lead and annotation-offset choices hold up? | Stretch 1 only. | Claude drafts, Din locks | INCART design note |

## Appendix A: Changes from the dins-projects draft (section 7)

The dins-projects PRD drafted Heartbeat before planning. These are the places this PRD now differs. The dins-projects PRD should be updated to point here (that change belongs to the dins-projects repo).

| dins-projects draft said | This PRD says | Decided in |
|---|---|---|
| Visitors see a saliency overlay | Saliency is stretch 2; the core demo has no overlay | A2 |
| Beats grouped into the five AAMI classes | Four scored classes; Q kept for RR, not scored | B4 |
| The inter-patient split of de Chazal | The same split without record 202 (one subject leaked across it) | B1 |
| Measured by per-class metrics, macro F1, calibration error | Pre-registered plan: macro F1 over N, S, V as headline, paired patient bootstrap, without-232 line, per-patient table | A3, C4 |
| "A small 1D CNN on single beats with a little context" | The window plus six RR features (context as rhythm features) | C3 |
| Training may use a rented GPU if needed | Mac only | C7 |
| A stage capture: live demo or video; demo in a stage iframe | Video on the home stage; live iframe in the case study | D1 |
| Stack: TypeScript and canvas | Svelte 5 with Vite, a plain TypeScript canvas module, ONNX Runtime Web in a Web Worker | D2 |

## Appendix B: Glossary

- **AAMI classes:** N normal (and bundle branch block), S supraventricular ectopic, V ventricular ectopic, F fusion, Q paced or unclassifiable (AAMI EC57).
- **DS1, DS2:** the inter-patient training and test sets. Here DS1 is 22 records from 22 subjects and DS2 is 21 records from 21 subjects.
- **Freeze record:** a committed file holding the commit hash, config and model checksum that `evaluate-test` requires.
- **Leakage exhibit:** the C5 comparison of patient-grouped against beat-split evaluation inside DS1.
- **MLII:** modified limb lead II, the lead used here.
- **Parity:** the same inputs give the same outputs (within 1e-5, labels exact) in PyTorch, Python ONNX Runtime and the browser.
- **RR interval:** the time between consecutive beats.
- **Sealed run:** the single, logged evaluation on DS2.

## Appendix C: Data facts used in this document

From PhysioNet's beat table, entire records (B1, B4):

| Class | DS1 (22 records) | DS2 without 202 (21 records) |
|---|---|---|
| N | 45,866 | 42,198 |
| S | 944 (record 209: 41%) | 1,782 (record 232: 78%) |
| V | 3,788 (record 208: 26%) | 3,202 (records 233 and 200: 26% each) |
| F | 415 (record 208: 90%) | 387 (record 213: 94%) |
| Q | 8 | 7 |

## References

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Eng in Med and Biol 20(3):45-50 (2001).
- MIT-BIH Arrhythmia Database v1.0.0, PhysioNet. DOI 10.13026/C2F305. ODC-By 1.0.
- Pollard et al. (2026). PhysioNet as a global platform for biomedical research. Nature Health. https://doi.org/10.1038/s44360-026-00096-z
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat interval features. IEEE Trans Biomed Eng 51(7):1196-1206 (2004).
- AAMI EC57, testing and reporting performance results of cardiac rhythm and ST segment measurement algorithms.
