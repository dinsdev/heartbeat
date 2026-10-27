# Heartbeat: Tasks

Status key: todo, doing, done, blocked.
Planning state key: open (not discussed), draft (proposed in the dins-projects PRD, not locked by Din), decided (Din locked it, reason in `WORK_LEDGER.md`), ongoing.

The schedule in `~/Develop/dins-projects/docs/PLAN.md` is a best-case recommendation, not a deadline (Din, 2026-10-22).

## Phase 0: Planning (no building)

Order of attack: A, then B and C, then D, then E, then F. F comes last so `AGENTS.md` and the conventions describe decisions already made.

### A. Foundations

| ID | Item | State | Status |
|---|---|---|---|
| A1 | Purpose and success: what a reader should come away believing, and what a win looks like | decided | done |
| A2 | Scope cut: core, stretch and out | decided | done |
| A3 | Results targets set before any test numbers exist, and what ships if the CNN loses to the baseline. Decided: a pre-registered evaluation plan instead of numeric targets | decided | done |

### B. Data

| ID | Item | State | Status |
|---|---|---|---|
| B1 | Records and exclusions: 44 records (four paced out), MLII picked by signal name, 202 dropped from DS2 to fix the 201/202 leak | decided | done |
| B2 | Beat locations: reference annotations in core, stated in the limits section and model card; the browser gets beat positions with the trace | decided | done |
| B3 | Preprocessing: 0.5 to 40 Hz zero-phase bandpass at 360 Hz, 256-sample window, int16 rounding at 200 units/mV (D4 amendment), per-window z-score, causal RR features plus post-RR | decided | done |
| B4 | Class mapping: AAMI symbols, strict; four scored classes N, S, V, F; Q out of training and scoring, kept for RR; F caveat; A3 addendum (S without 232, per-patient table) | decided | done |
| B5 | Download, caching, checksums, attribution and citations: 132 files from the PhysioNet S3 mirror first, PhysioNet as fallback (E2 amendment), pinned SHA256 manifest, gitignored cache. Still open: read the de Chazal full text (DS lists, RR features) | decided (paper check open) | doing |

### C. Modeling and evaluation

| ID | Item | State | Status |
|---|---|---|---|
| C1 | Split discipline: 201/202 leak fixed under B1 (DS1 22 subjects, DS2 21). 5-fold StratifiedGroupKFold by subject on DS1 with a committed fold file, pooled out-of-fold metrics, fixed epoch count, final retrain on all of DS1, DS2 sealed behind a freeze-checked command, demo uses DS2 only after the sealed run | decided | done |
| C2 | Baseline: multinomial logistic regression on the six B3 RR features (log ratios, standardized in fold), balanced class weights, C from five values on the C1 folds | decided | done |
| C3 | CNN design: beat window plus the six RR features, four conv blocks (about 52k parameters at width 1), width from 0.5/1/2 plus epoch count on the C1 folds, balanced weighted cross-entropy, fixed light augmentation, AdamW at a constant rate | decided | done |
| C4 | Metrics and calibration: headline macro F1 over N, S, V with four-class beside it, S and V FPR, paired 10,000-draw patient bootstrap, per-patient count rule, labels by argmax, probabilities by weight offset plus temperature, classwise ECE for S and V | decided | done |
| C5 | The honesty exhibit: inside DS1 only, patient-grouped (C1) against beat-level random 5-fold, same frozen config and seeds, CNN and baseline, accuracy shown only here, patient bootstrap on both | decided | done |
| C6 | Tracking, seeds, determinism: run folders plus committed `results/`, no tracking service; seeds 0, 1, 2 with seed 0 shipped and selection on the seed mean; all three in the sealed run; frozen models trained on CPU in deterministic mode; single-process loading | decided | done |
| C7 | Compute: Mac only (M5), MPS for development and CV numbers (within tolerance), CPU deterministic for frozen models, no rented GPU, CI smoke tests only | decided | done |
| C8 | Stretch, in order: INCART external test, saliency overlay, our own QRS detector (A2). Starts only after core is publishable; design note committed before any result; ships whole or not at all; INCART core rules pre-registered | decided | done |

### D. Browser demo

| ID | Item | State | Status |
|---|---|---|---|
| D1 | Integration with dins.dev (amended 2026-10-27): video capture on the home stage; live demo in an iframe at the top of the case study; full demo at `heartbeat.dins.dev` (own Worker, deployed from this repo) with `?embed` modes and `frame-ancestors` for dins.dev. Site changes listed under G4 | decided | done |
| D2 | Front-end stack: Svelte 5 with Vite (no SvelteKit), a plain TypeScript canvas module for the trace, ONNX Runtime Web in a Web Worker, the site's tooling, vendored brand tokens | decided | done |
| D3 | Live inference in both modes: browser computes windows and RR from shipped trace and beat positions, labels chunks just ahead of the playhead, single-thread wasm; expert labels and Python predictions shipped; visible match counter; labeled fallback | decided | done |
| D4 | Data shipped: all 21 DS2 patients, full 30 minutes, loaded per patient; default record 200 by a label-only rule; int16 trace at 200 units/mV (canonical in Python too, B3 amendment); beats JSON; hashed manifest | decided | done |
| D5 | Performance: stock ORT wasm build; trace first, model loads alongside; iframe fetches nothing heavy until visible; CI gates on model, JS, beats JSON size and long tasks; timings measured and reported | decided | done |
| D6 | Interaction and accessibility: native controls only (no single-key shortcuts), next-irregular and next-disagreement buttons, letters and shapes as well as color, visible-window table with a polite 10-second summary, reduced-motion paged view, theme via postMessage, axe in all modes plus a VoiceOver pass | decided | done |
| D7 | Research demo, not medical advice: a short line in the full demo, the iframe, the stage video and the case study; a fuller note in the about text and limits section; an avoid list for wording | decided | done |

### E. Stack and tooling

| ID | Item | State | Status |
|---|---|---|---|
| E1 | Research current stable versions: done 2026-10-27; policy adopted (newest stable at least 14 days old; ONNX Runtime 1.30.0 in Python and browser; Python 3.14; Node 24) | decided | done |
| E2 | Stack locked with pins and reasons (2026-10-27): compatibility checked hands-on; policy enforced by uv `exclude-newer` and pnpm `minimumReleaseAge`; TypeScript 6.0.3; single-file ONNX | decided | done |
| E3 | Repo layout: one repo, Python package at the root (`src/heartbeat`), front end in `web/`; `manifests/` for pinned inputs, `config/` for settings; frozen model and small results committed; data, runs and demo data gitignored; MIT for code, ODC-By for data | decided | done |
| E4 | One-command rebuild: `uv run heartbeat rebuild` with cached stages; folds only checked, never regenerated; stops before DS2 until a freeze exists; after the freeze, a reproduction check logged as such; default and `--exact` modes; `heartbeat verify` for quick checks; web build separate | decided | done |
| E5 | Test strategy: five layers (Python unit; Python on real data, downloaded and cached in CI; parity chain at 1e-5 with exact labels on DS1 fixtures; web unit; Playwright in Chromium and WebKit), wording lint, rule-to-test table in PLAN.md, no coverage percentage gate | decided | done |
| E6 | CI and remote: public `dinsdev/heartbeat`, pushed at the end of Phase 0 (before the sealed run, for an outside timestamp); one Actions workflow for checks; SHA-pinned actions, read-only permissions, Renovate with the 14-day rule; `scripts/check.sh`; deploys by Actions with wrangler (production on `main`, previews on PRs); each repo creation, push, secret and first deploy waits on Din | decided | done |

### F. Docs and agent rules

| ID | Item | State | Status |
|---|---|---|---|
| F1 | `docs/PRD.md`, promoted from the dins-projects PRD section 7: written from the A to E decisions, P0 core, P1 supporting work, P2 stretch, requirements traced to planning items | decided | done |
| F2 | `docs/PLAN.md`: nine phases, a Phase 7 gate before the sealed run, 49-row rule-to-test table (R46 and R47 added), task plans written per phase; build phases added to this file | decided | done |
| F3 | `AGENTS.md` (one root file, seven rigor rules, approvals, commands marked as Phase 1) and `CLAUDE.md` importing it; conventions go in `docs/CONVENTIONS.md` (F4) | decided | done |
| F4 | Coding conventions and rules in `docs/CONVENTIONS.md`: drafted 2026-10-27 (tool settings, Python, ML hygiene mapped to a leakage taxonomy, TypeScript and Svelte, tests, git and docs) | draft | doing |
| F5 | `.claude/settings.json`: permissions and hooks | open | todo |
| F6 | Model card and data card templates, filled with real numbers later | open | todo |
| F7 | `docs/WORK_LEDGER.md` kept current | ongoing | doing |

### G. Publishing

Scheduled into the build phases at the F2 lock (none can finish during planning): G4 in Phase 6, G1 in Phase 7, G2 and G3 in Phase 8. Phase 0 ends when F is done and the repo is pushed.

| ID | Item | State | Status |
|---|---|---|---|
| G1 | Case study outline mapped to the site's `projects` fields | open | todo |
| G2 | Stage capture: the 16:10 home stage video recorded from the demo (D1), default patient 200 (D4), with the D7 short line burned in | open | todo |
| G3 | Ask Ottie sources for this project (the case study's project-scoped retrieval needs a corpus) | open | todo |
| G4 | Hand the dins.dev changes (D1) to that repo: `demo.src` accepts the Heartbeat origin, case study renders a live demo as an iframe with `loading="lazy"`, `frame-src` allows the origin, the iframe has a `title`, the site posts its theme to the iframe | open | todo |

## Build phases

From `docs/PLAN.md` (F2, locked 2026-10-27). Each phase gets a task-level plan at its start, which may split these rows further. Status is todo until then. The G items above are scheduled into these phases (G4 in 6, G1 in 7, G2 and G3 in 8).

### Phase 1: Skeleton and CI

| ID | Task | Status |
|---|---|---|
| 1.1 | Python project: `pyproject.toml` with E2 pins and `exclude-newer`, `uv.lock`, `heartbeat` CLI skeleton | todo |
| 1.2 | Web project in `web/`: pnpm, E2 pins, `minimumReleaseAge`, `allowBuilds` | todo |
| 1.3 | CI workflow (SHA-pinned actions, read-only permissions), `scripts/check.sh`, Renovate config | todo |
| 1.4 | Wording lint (D7 avoid list, dash separators) | todo |
| 1.5 | `LICENSE`, `DATA_LICENSE.md`, README, `.gitignore` | todo |

### Phase 2: Data and split

| ID | Task | Status |
|---|---|---|
| 2.1 | `manifests/`: checksums, subjects (201 and 202 one subject), splits with exclusions | todo |
| 2.2 | Downloader: S3 mirror first, PhysioNet fallback, checksum check, atomic writes | todo |
| 2.3 | `prepare`: MLII by name, filter, int16, AAMI mapping, windows, RR features | todo |
| 2.4 | Split-enforcing loader; leakage tests on subject IDs | todo |
| 2.5 | `make-folds` and committed `config/folds.json` (ledger entry) | todo |
| 2.6 | `rebuild` stage framework with fingerprints and `--from` | todo |

### Phase 3: Evaluation harness and baseline

| ID | Task | Status |
|---|---|---|
| 3.1 | Metrics, per-patient table, paired patient bootstrap | todo |
| 3.2 | Calibration: logit adjustment, temperature, equal-mass ECE, reliability, log loss, Brier | todo |
| 3.3 | Run folders and the `results/` writer | todo |
| 3.4 | Baseline with C selection on the folds; results committed | todo |

### Phase 4: CNN and the leakage exhibit

| ID | Task | Status |
|---|---|---|
| 4.1 | CNN, training loop, augmentation, derived seeds, deterministic CPU mode | todo |
| 4.2 | Cross-validation (3 widths x 5 folds x 3 seeds) and `select` | todo |
| 4.3 | Exhibit leaky side for CNN and baseline; results committed (ledger entry) | todo |
| 4.4 | `train-final`: three seeds on CPU | todo |

### Phase 5: Export, parity and the rebuild

| ID | Task | Status |
|---|---|---|
| 5.1 | Single-file ONNX export, scaler and calibration JSON, `models/heartbeat-v1/` | todo |
| 5.2 | DS1 parity fixtures and the Python half of the parity chain | todo |
| 5.3 | `evaluate-test` refusals and the append-only log writer | todo |
| 5.4 | `rebuild` end to end (stops before DS2) and `heartbeat verify`; clean-clone reproduction logged | todo |

### Phase 6: Demo on DS1

| ID | Task | Status |
|---|---|---|
| 6.1 | App shell: Svelte, full and embed modes, canvas trace, brand tokens and drift check | todo |
| 6.2 | Worker with ONNX Runtime Web, TypeScript preprocessing, chunked labeling, browser parity | todo |
| 6.3 | Parity counter, fallback, loading state | todo |
| 6.4 | Controls, legend, beat table, status line, reduced-motion paging, theme handling | todo |
| 6.5 | `build-demo-data` (DS1 only), manifest, size and performance gates, axe and keyboard tests | todo |
| 6.6 | Headers and CSP; deploy workflow with previews (Din: Cloudflare token and secret) | todo |
| 6.7 | G4 handoff note to the dins.dev repo | todo |

### Phase 7: Freeze and the sealed run

| ID | Task | Status |
|---|---|---|
| 7.1 | Gate checklist (PLAN.md section 3, Phase 7) | todo |
| 7.2 | Freeze record committed and pushed (Din's go) | todo |
| 7.3 | `evaluate-test` once; log pushed; ledger entry with every headline number | todo |
| 7.4 | DS2 demo data from the frozen model; reproduction check | todo |
| 7.5 | G1 case study outline | todo |

### Phase 8: Content and launch

| ID | Task | Status |
|---|---|---|
| 8.1 | Model card and data card filled from results | todo |
| 8.2 | Case study draft with real numbers (de Chazal full text read first, PRD Q2) | todo |
| 8.3 | G2 stage video; G3 Ask Ottie sources | todo |
| 8.4 | VoiceOver pass; PhysioNet citation recheck | todo |
| 8.5 | Din's preview review; first production deploy (Din's go) | todo |
