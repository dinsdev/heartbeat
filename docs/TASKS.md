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
| F2 | `docs/PLAN.md` phases, and build phases added to this file | open | todo |
| F3 | `AGENTS.md`, and `CLAUDE.md` starting with `@AGENTS.md` | open | todo |
| F4 | Coding conventions and rules: Python and TypeScript style, typing, naming, ML hygiene | open | todo |
| F5 | `.claude/settings.json`: permissions and hooks | open | todo |
| F6 | Model card and data card templates, filled with real numbers later | open | todo |
| F7 | `docs/WORK_LEDGER.md` kept current | ongoing | doing |

### G. Publishing

| ID | Item | State | Status |
|---|---|---|---|
| G1 | Case study outline mapped to the site's `projects` fields | open | todo |
| G2 | Stage capture: the 16:10 home stage video recorded from the demo (D1), default patient 200 (D4), with the D7 short line burned in | open | todo |
| G3 | Ask Ottie sources for this project (the case study's project-scoped retrieval needs a corpus) | open | todo |
| G4 | Hand the dins.dev changes (D1) to that repo: `demo.src` accepts the Heartbeat origin, case study renders a live demo as an iframe with `loading="lazy"`, `frame-src` allows the origin, the iframe has a `title`, the site posts its theme to the iframe | open | todo |

## Build phases

Added when `docs/PLAN.md` is written (F2).
