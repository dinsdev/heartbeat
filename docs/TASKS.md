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
| B3 | Preprocessing: 0.5 to 40 Hz zero-phase bandpass at 360 Hz, 256-sample window, per-window z-score, causal RR features plus post-RR | decided | done |
| B4 | Class mapping to AAMI, and what to do with the tiny Q class | draft | doing |
| B5 | Download, caching, checksums, ODC-By attribution and citations | draft | todo |

### C. Modeling and evaluation

| ID | Item | State | Status |
|---|---|---|---|
| C1 | Split discipline: DS1 and DS2, validation by patient groups within DS1, test set touched once. Leak confirmed (201 in DS1, 202 in DS2, same subject) and fixed under B1: 202 leaves DS2, so DS1 is 22 subjects and DS2 is 21. Still open: the patient-group folds and test-once mechanics | draft | todo |
| C2 | Baseline: RR-interval features with logistic regression | draft | todo |
| C3 | CNN design: inputs, size, class imbalance handling | draft | todo |
| C4 | Metrics and calibration: per-class precision and recall, macro F1, calibration error, calibration method | draft | todo |
| C5 | The honesty exhibit: also train on a patient-mixed split and show the inflated number. In core (A2); design details still open | decided (in core) | todo |
| C6 | Experiment tracking, seeds, determinism | open | todo |
| C7 | Compute: Mac (MPS) or rented GPU | open | todo |
| C8 | Stretch, in order: INCART external test, then saliency overlay, then our own QRS detector (A2) | decided (order) | todo |

### D. Browser demo

| ID | Item | State | Status |
|---|---|---|---|
| D1 | Integration with dins.dev: the demo is a standalone web app, shown in an iframe on the dins.dev stage; clicking it opens the case study, which links to the live demo. Still open: host and domain, embed mode, framing headers | decided (core), open (details) | todo |
| D2 | Front-end stack: Svelte 5 to match the site, or plain TypeScript and canvas | open | todo |
| D3 | Live inference or replayed labels, in the stage iframe and in the full demo | open | todo |
| D4 | Data shipped to the browser: which records, how long, file format, size budget | open | todo |
| D5 | Performance budget: model size, runtime size, load time, time per beat | open | todo |
| D6 | Interaction and accessibility: controls, reduced motion, keyboard, data table, color never the only signal | open | todo |
| D7 | Research demo, not medical advice, stated on the page | draft | todo |

### E. Stack and tooling

| ID | Item | State | Status |
|---|---|---|---|
| E1 | Research current stable versions: Python, uv, PyTorch, wfdb, onnx, ONNX Runtime and ONNX Runtime Web, Node, front-end tooling | open | todo |
| E2 | Lock the stack with pins and a reason for each | open | todo |
| E3 | Repo layout: Python package, front end, artifacts, docs | open | todo |
| E4 | One-command rebuild | open | todo |
| E5 | Test strategy: patient leakage test, metric tests, PyTorch and ONNX output match, Python and browser output match | open | todo |
| E6 | CI and remote: GitHub Actions needs a remote; the case study needs a public repo link | open | todo |

### F. Docs and agent rules

| ID | Item | State | Status |
|---|---|---|---|
| F1 | `docs/PRD.md`, promoted from the dins-projects PRD section 7 | open | todo |
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
| G2 | Stage capture: the 16:10 iframe view, and a video fallback if needed | open | todo |
| G3 | Ask Ottie sources for this project (the case study's project-scoped retrieval needs a corpus) | open | todo |

## Build phases

Added when `docs/PLAN.md` is written (F2).
