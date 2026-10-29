# Heartbeat: Plan

|  |  |
| --- | --- |
| **Status** | Locked by Din (F2, 2026-10-27). Phase task plans are added in section 8 as each phase starts. |
| **Date** | 2026-10-27 |
| **Implements** | `docs/PRD.md` (locked F1). Requirement IDs below (for example `EVAL-05`) refer to it. |
| **Related** | `docs/TASKS.md` (build tasks per phase), `docs/WORK_LEDGER.md` (decisions and verification results) |

This plan says in what order Heartbeat gets built, what each phase must prove before the next starts, and which test enforces each rigor rule. It does not repeat the requirements; the PRD holds those.

## 1. Approach

**Build the evidence before the show.** The order follows the trust chain: data and split first, then the evaluation harness on the cheap baseline, then the CNN, then export and parity, then the demo. Each layer is tested before the next depends on it, so a bug found late cannot quietly invalidate earlier numbers.

**DS2 stays sealed until one planned moment.** Everything up to Phase 6 uses DS1 only, including the demo, which runs on DS1 recordings (C1, E4). The sealed run is a single phase with a gate checklist (Phase 7). DS2 demo data, the model card and the case study come after it.

**Plan per phase, at the phase's start.** This document is phase-level. When a phase starts, Claude writes its task-level plan (files, interfaces, test-first steps, commits) as a section at the end of this file, Din reviews it, and the build tasks in `docs/TASKS.md` get updated. Reason: F4's conventions and earlier phases' interfaces shape the detail, so writing it all now would mean rewriting it.

**Tests come with the code.** Each phase's exit criteria include its rows of the rule-to-test table (section 6). A phase is done when those tests pass in CI, not when the code exists.

**Branches and pushes.** After the repo goes public (end of Phase 0), each phase works on a branch (`phase-N-<name>`) with local commits at every checkpoint. Pushing a branch and opening its pull request runs CI and, from Phase 6, a preview deploy. Every push waits on Din's go (E6), so pushes happen at checkpoints, not per commit. Phases merge to `main` after CI passes and Din agrees.

## 2. Global constraints

Every phase is bound by these (details in the PRD and ledger):

- Pins: newest stable release at least 14 days old, enforced by uv `exclude-newer = "14 days"` and pnpm `minimumReleaseAge: 20160`, both rolling; ONNX Runtime 1.30.0 in Python and the browser; Python 3.14; Node 24; TypeScript 6.0.3 (E1, E2).
- No result appears anywhere until a run produces it (PRD section 5).
- DS2 is read only by `evaluate-test` with a matching freeze record; demo data is DS1-only until the sealed run is logged (EVAL-04, EVAL-05, DEMO-17).
- Compute: Mac only; MPS for development numbers, CPU deterministic for frozen models (C7).
- Writing: no em or en dashes as separators, D7's avoid list, plain words (PUB-05).
- Din's go before: creating the repo, each push, the Cloudflare token and secret, the first production deploy, the sealed run, and each stretch item (E6, C8).

## 3. Phases

Estimates are Claude's guesses in focused working days, not measurements, except where a compute time is marked as measured (C7, E4). The dins.dev schedule is a best case, not a deadline.

### Phase 0: Planning (in progress)

**Remaining:** Din creates `dinsdev/heartbeat` and pushes `main` (F1 to F8 done).

**Exit:**

- Sections A to F decided and committed.
- `dinsdev/heartbeat` created as a public repo and `main` pushed by Din (E6; F5 denies both to Claude). This timestamps the pre-registered plan (A3, C4, C5, C8) before any code exists.

**Decided at the F2 lock:** the G items (publishing) are not planning and cannot finish in Phase 0, since G2 needs the demo and G3 needs the case study. They move into the build phases: G4 in Phase 6, G1 in Phase 7, G2 and G3 in Phase 8.

### Phase 1: Skeleton and CI (about 1 day)

**Builds:** `pyproject.toml` with the E2 pins and `exclude-newer`; `uv.lock`; the `heartbeat` CLI with empty subcommands; `web/` with pnpm, the E2 pins, `minimumReleaseAge` and `allowBuilds`; the GitHub Actions workflow (SHA-pinned actions, read-only permissions); `scripts/check.sh`; Renovate config; the wording lint; tool configs per `docs/CONVENTIONS.md`; the rule-coverage check (every non-manual row of section 6 at or below the current phase has a test carrying its ID; later rows listed as pending); `LICENSE`, `DATA_LICENSE.md`, README; `.gitignore` for `data/`, `runs/`, `web/public/data/`.

**Requirements:** OPS-05, OPS-08, OPS-09, PUB-05 (lint only), PUB-07.

**Depends on:** Phase 0 push.

**Exit:** CI green on the skeleton in under 10 minutes; `scripts/check.sh` under 2 minutes; the wording lint fails on a planted em dash and a planted "diagnose".

### Phase 2: Data and split (about 2 to 3 days)

**Builds:** `manifests/` (`mitdb-1.0.0.sha256`, `subjects.toml`, `splits.toml`); the downloader (S3 mirror first, PhysioNet fallback, checksums); `prepare` (MLII by name, filter, int16 rounding, AAMI mapping, beat windows, RR features); the split-enforcing loader; `heartbeat make-folds` and the committed `config/folds.json`; the stage framework for `rebuild` (fingerprints, `--from`) with the stages built so far.

**Requirements:** DATA-01 to DATA-11, EVAL-01 to EVAL-04, OPS-01 (partial).

**Depends on:** Phase 1.

**Exit:** rule-to-test rows R1 to R15 and R51 pass in CI, including the real-data layer (download cached by the manifest). Per-record class counts match PhysioNet's table, and per-class totals are compared with de Chazal's Table II, each difference listed in the ledger. `folds.json` committed with a ledger entry (a rigor event).

### Phase 3: Evaluation harness and baseline (about 2 days)

**Builds:** metrics (per class, macro F1 over N, S, V and four-class, FPR, and the AAMI EC57 definitions for the de Chazal comparison); the paired patient bootstrap; the per-patient table; calibration (logit adjustment, temperature, equal-mass ECE, reliability data, log loss, Brier); run folders and the `results/` writer; the baseline with C selection on the folds.

**Requirements:** EVAL-07 to EVAL-12, MODEL-01, MODEL-07.

**Depends on:** Phase 2.

**Why the baseline first:** it is deterministic and trains in seconds, so the harness gets tested on a cheap model before the CNN depends on it.

**Exit:** rows R16 to R21 pass; baseline out-of-fold results in `results/` with the chosen C.

### Phase 4: CNN and the leakage exhibit (about 2 to 3 days, plus compute)

**Builds:** the C3 network, training loop, augmentation, derived seeds, deterministic CPU mode; cross-validation (3 widths, 5 folds, 3 seeds; measured about 1 hour on MPS); `select` (`results/selection.json`, epoch count from averaged curves); the exhibit's leaky side for CNN and baseline; `train-final` (3 seeds on CPU; measured about 30 minutes at width 1, about 2 hours at width 2).

**Requirements:** MODEL-02 to MODEL-06, EXHIBIT-01 to EXHIBIT-03.

**Depends on:** Phase 3.

**Exit:** rows R22 to R24 pass; selection and exhibit results committed with a ledger entry; three final models trained. Any exhibit number stays out of public text until the case study (it is real, but the page is written later).

### Phase 5: Export, parity and the rebuild (about 2 days)

**Builds:** single-file ONNX export, scaler and calibration JSON, `models/heartbeat-v1/` (pre-freeze contents, including `NOTICE`: MIT for the weights and the ODC-By 1.0 notice for the training data); parity fixtures from DS1; the Python half of the parity chain; `rebuild` end to end up to export, stopping before DS2; `heartbeat verify`; `heartbeat cards`, which renders the generated blocks of `docs/MODEL_CARD.md` and `docs/DATA_CARD.md` from `results/`, with its check in `verify` (F6); `evaluate-test` with its freeze and clean-tree checks and the append-only log writer, tested only for its refusals (it never reads DS2 before Phase 7).

**Requirements:** PARITY-01, PARITY-02, PARITY-03 (Python half), PARITY-04, OPS-01, OPS-02, OPS-04, EVAL-05, EVAL-06.

**Depends on:** Phase 4.

**Exit:** rows R25 to R28, R41, R42, R50 and R52 pass; `rebuild` from a clean clone reproduces `results/` within tolerance (default mode) and logs the result in the ledger.

### Phase 6: Demo on DS1 (about 5 to 7 days)

**Builds:** the Svelte app (full page and `?embed=page`); the canvas trace module; the Worker with ONNX Runtime Web; TypeScript preprocessing; chunked labeling; the parity counter and fallback; controls, legend, beat table, status line; reduced-motion paging; theme handling; brand tokens and drift check; `_headers` with the CSP; `build-demo-data` (DS1 recordings only); deploys (preview on pull requests; Din creates the Cloudflare token and secret); G4 handed to the dins.dev repo once the embed mode and headers exist.

**Requirements:** DEMO-01 to DEMO-17 (DS1 data), PARITY-03 (browser half), OPS-06, OPS-10, PUB-08, all of PRD section 9.

**Depends on:** Phase 5 for the real model. The app shell (trace, controls, accessibility) may start after Phase 2 with an untrained exported network as a stand-in, so Phases 3 to 5 and the shell can overlap.

**Exit:** rows R29 to R40 pass in Chromium and WebKit; the demo runs on a preview URL; timings reported in the ledger; G4 handoff note delivered. To check with the first preview deploy (task 6.6): whether turning off the production `workers.dev` route also turns off Worker Previews on `workers.dev`.

### Phase 7: Freeze and the sealed run (about 1 day, plus compute)

**Gate (all must hold before `evaluate-test`; Claude checks, Din confirms):**

1. Every rule-to-test row through R40 passes in CI on `main`.
2. The pre-registered plan (A3, C4, C5, C8 in the ledger; PRD section 8.2) is unchanged since the Phase 0 push, or every change has a dated ledger entry made before this gate.
3. The freeze record (commit, config, model checksum) is committed and pushed (Din's go).
4. The working tree is clean.

**Then:** `evaluate-test` once for baseline and CNN, all three seeds; push `results/test_runs.jsonl` right after (Din's go); ledger entry with every headline number. Then `rebuild` builds DS2 demo data from the frozen model, and runs the reproduction check (default mode now; `--exact`, measured at about 15 hours, overnight when convenient). G1 (case study outline mapped to the site's `projects` fields) is written here, before the numbers are put into prose.

**Requirements:** EVAL-05, EVAL-06, EVAL-08, OPS-03, OPS-07, DEMO-07 to DEMO-09, DEMO-17.

**If a bug turns up after the run:** fix, rerun, log both runs in `test_runs.jsonl` and the ledger (A3). No silent reruns.

**Exit:** R43 passes and R41, R42 still pass; the demo switched to the 21 DS2 patients.

### Phase 8: Content and launch (about 3 to 4 days)

**Builds:** model card and data card: numbers rendered by `heartbeat cards` from committed results into the F6 templates, prose finished by hand; the case study (in the dins.dev repo, from G1); the stage video from patient 200 with the research-demo line (G2); Ask Ottie sources (G3); PhysioNet's citation rechecked; one VoiceOver pass; Din's review in a preview deploy; first production deploy (Din's go).

**Requirements:** PUB-01 to PUB-09, launch criteria (PRD section 12).

**Exit:** every launch criterion holds; the case study is published by the dins.dev repo's own process.

### Phase 9: Stretch (only with Din's go per item)

INCART, then saliency, then our own QRS detector (C8). Each starts with a committed design note, ships whole or not at all, and gets its own task-level plan.

### Rough total

About 18 to 23 focused days for Phases 1 to 8 (guess). Against the best-case 2026-12-01 content freeze, Heartbeat alone fits with little slack, and the dins-projects plan also expects the other three projects in that window. If time runs short, the cut order is: P1 items first, then reported (not gated) timings polish, never a P0 rigor rule. Heartbeat stays a draft rather than ship without its rigor rows passing.

## 4. Dependencies between phases

```
Phase 0 (push) -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> (9)
                       \
                        -> 6 shell (stand-in model) ---^
```

External dependencies: PhysioNet S3 mirror and PhysioNet (Phase 2); GitHub Actions (from Phase 1); Cloudflare token and custom domain (Phase 6); the dins.dev repo accepting G4 (Phase 6 to 8).

## 5. Verification layers

From E5. The rule-to-test table names a layer for every rule.

| Layer | What | Where it runs |
| --- | --- | --- |
| L1 | Python unit tests (pytest, hypothesis), no data | CI on every push; `scripts/check.sh` |
| L2 | Python tests on real MIT-BIH data (cached download) | CI on every push |
| L3 | Parity chain on shared DS1 fixtures (1e-5, labels exact) | CI (Python half and browser half) |
| L4 | Web unit tests (Vitest) | CI; `scripts/check.sh` |
| L5 | Web end to end (Playwright, Chromium and WebKit) | CI |
| TX | Wording lint on built demo text and the case study draft | CI |
| GATE | Size and performance gates in the web build and Playwright | CI |
| MAN | Manual check, recorded in the ledger | Before the named milestone |

## 6. Rule-to-test table

Each locked rigor rule and the test that enforces it. Test names are indicative; the phase plan fixes the real ones. R46 and R47 were added at F2; Din locked them with the plan. R50 was added, and R44 widened to the README and cards, at F6.

| # | Rule | Source | Enforced by | Layer | Phase |
| --- | --- | --- | --- | --- | --- |
| R1 | A checksum mismatch stops the run | B5 | download test with a corrupted file | L1 | 2 |
| R2 | The cache matches the pinned 132 checksums | B5 | every run's checksum step; `heartbeat verify` | L2 | 2 |
| R3 | Paced records excluded; DS1 and DS2 lists match the manifest | B1 | `splits.toml` schema and content test | L1 | 2 |
| R4 | MLII picked by name in any channel order | B1 | unit test with 114's layout; real-data test on 100 and 114 | L1, L2 | 2 |
| R5 | Bandpass is zero-phase, 0.5 to 40 Hz | B3 | phase and band test on synthetic sines | L1 | 2 |
| R6 | int16 rounding error at most 0.0025 mV | B3, D4 | property test | L1 | 2 |
| R7 | Window is 96 before, 160 after the annotation | B3 | index test | L1 | 2 |
| R8 | RR features are causal except post-RR, by one beat | B3 | hypothesis test changing beats further ahead | L1 | 2 |
| R9 | RR uses every annotated beat, including Q | B3, B4 | unit test with a Q beat between two N beats | L1 | 2 |
| R10 | Unknown annotation symbol fails loudly | B4 | unit test | L1 | 2 |
| R11 | Class counts match PhysioNet's table per record | B4 | real-data test over all 44 records | L2 | 2 |
| R12 | No subject on both sides of DS1 and DS2; 201 and 202 one subject | B1, C1 | leakage test on subject IDs | L2 | 2 |
| R13 | No subject on both sides of any fold | C1 | leakage test on `folds.json` | L2 | 2 |
| R14 | `rebuild` checks folds and never regenerates them | C1, E4 | test that a changed `folds.json` fails `check-folds` | L2 | 2 |
| R15 | Training and CV code cannot load DS2 | C1 | loader test | L2 | 2 |
| R16 | Metrics agree with scikit-learn | C4 | unit tests on known cases | L1 | 3 |
| R17 | Bootstrap resamples whole patients; CNN and baseline share draws | C4 | unit tests | L1 | 3 |
| R18 | Draws with no predicted S are skipped for S precision only, and counted | C4 | unit test | L1 | 3 |
| R19 | Per-patient cells show counts; percentage only at 10 or more beats | C4 | unit test | L1 | 3 |
| R20 | Calibration never changes a label; logit adjustment; equal-mass ECE | C4 | unit tests | L1 | 3 |
| R21 | Baseline and CNN use the same folds, class weights and selection metric | C2, C3 | test that both read one fold file and one weight function | L1 | 3 |
| R22 | Same seed on CPU gives identical weights | C6 | two short CPU runs compared | L1 | 4 |
| R23 | Training runs without crashing on real data | C7 | smoke run of a few CPU batches | L2 | 4 |
| R24 | The exhibit differs from the honest run only in the splitter | C5 | test comparing the two resolved configs | L1 | 4 |
| R25 | ONNX model is one file, under 1 MB | E2, D5 | export test and size gate | L3, GATE | 5 |
| R26 | PyTorch and Python ONNX Runtime agree within 1e-5, labels exact | E5 | parity test on fixtures | L3 | 5 |
| R27 | Parity fixtures come from DS1 only | E5 | test on fixture record IDs | L3 | 5 |
| R28 | `rebuild` stops before DS2 without a freeze record | E4 | test with no freeze record | L2 | 5 |
| R29 | Browser ONNX Runtime agrees with Python within 1e-5, labels exact, in Chromium and WebKit | E5 | Playwright parity test | L3, L5 | 6 |
| R30 | TypeScript preprocessing matches Python step by step | E5 | Vitest on fixtures (window, z-score with a synthetic flat window, RR, scaler, calibration) | L3, L4 | 6 |
| R31 | `manifest.json` matches the shipped files | D4 | build check | L4 | 6 |
| R32 | Demo data is DS1-only until the sealed run is logged | C1, E4 | `build-demo-data` test with no test log entry | L2 | 6 |
| R33 | Fallback is labeled when WebAssembly is blocked | D3 | Playwright with WebAssembly disabled | L5 | 6 |
| R34 | Class colors at least 3:1 in light and dark | D6 | contrast unit test | L4 | 6 |
| R35 | Axe at zero violations: full and embed, light and dark, reduced motion on and off | D6 | Playwright with axe | L5 | 6 |
| R36 | Every control reachable and usable by keyboard | D6 | Playwright keyboard walk | L5 | 6 |
| R37 | Theme messages accepted only from the dins.dev origin | D6 | unit test | L4 | 6 |
| R38 | No main-thread task over 50 ms during playback | D5 | Playwright long-task observer | GATE | 6 |
| R39 | Model under 1 MB, demo JS under 60 KB gzip, beats JSON under 100 KB per patient | D5 | build size gates | GATE | 6 |
| R40 | Headers carry `frame-ancestors` and `'wasm-unsafe-eval'` | D1 | test on built headers | L5 | 6 |
| R41 | `evaluate-test` refuses without a matching freeze record or on a dirty tree | C1, C6 | tests with a mismatched record and a dirty tree | L2 | 5 |
| R42 | Sealed runs append to `test_runs.jsonl`; nothing is rewritten; reproductions are a separate entry type | C6, E4 | test on the log writer; `heartbeat verify` checks results against the log | L2 | 5 |
| R43 | The default patient rule picks record 200 | D4 | test on the built DS2 manifest | L2 | 7 |
| R44 | Published text (built demo, case study draft, README, model and data cards) avoids D7's list and dash separators | D7, F6 | wording lint | TX | 1 onward |
| R45 | Dependencies respect the 14-day rule | E2 | uv and pnpm config; CI installs from frozen lockfiles | GATE | 1 |
| R46 | Third-party actions pinned to commit hashes | E6, F2 | a small workflow check that rejects tag references | TX | 1 |
| R47 | The freeze commit is on the public remote before the sealed run | E6, F2 | `evaluate-test` refuses unless the freeze commit is on `origin/main` | L2 | 7 |
| R48 | One VoiceOver pass | D6 | manual, recorded in the ledger | MAN | 8 |
| R49 | Pre-registered plan unchanged, or changes logged before the gate | A3 | Phase 7 gate checklist | MAN | 7 |
| R50 | Card numbers come from committed results: every generated block equals what `heartbeat cards` renders, and no test block is pending once the sealed run is logged | F6 | renderer unit tests; `heartbeat verify` check on the two cards | L1, L2 | 5 |
| R51 | The per-window z-score never divides by zero: a constant window gives zeros, any int16 window gives finite values | B3 | unit test plus hypothesis property test | L1 | 2 |
| R52 | The model ships with its license notice: `heartbeat export` writes `models/heartbeat-v1/NOTICE` (MIT weights, ODC-By 1.0 notice) and `verify` fails without it | B5, E3 | export unit test; `heartbeat verify` check | L1, L2 | 5 |

## 7. Review focus

Failure modes the requirements imply but no row above tests yet. Each gets a test in the named phase's task plan.

1. **An interrupted download** leaves a partial file in the cache. Expected: files are written to a temporary name and moved into place only after the checksum matches (Phase 2).
2. **MPS and CPU disagree enough to change selection.** Expected: the reproduction check reports it; Phase 4 records the MPS against CPU difference on one configuration in the ledger.
3. **Labeling falls behind playback at 4x speed** or on a slow phone. Expected: beats without a label yet show as pending, never as a wrong or missing class (Phase 6).
4. **Scrubbing to the very start or end** of a 30-minute recording. Expected: no out-of-range windows; the first and last beats are absent by design (B3) and the table says so (Phase 6).
5. **The iframe in a background tab** is throttled, then resumes. Expected: playback resumes at the right place and the counter stays correct (Phase 6).

## 8. Phase task plans

Added here when each phase starts (see section 1).

### Phase 1: Skeleton and CI (task plan, 2026-10-29)

**Goal:** a repo where every later phase can add code and tests that CI and `scripts/check.sh` already run, with the three Phase 1 rule rows (R44, R45, R46) and the rule-coverage check enforced from the first push.

**Approach:** Python checks (wording lint, rule coverage, dependency and workflow config) live in `src/heartbeat/checks/` as plain functions with a `python -m` entry point, and pytest runs them over the repo, so CI needs no extra steps for them. The web project is a placeholder Svelte page with the full toolchain wired. Test first throughout: each check's planted-failure tests are written and seen failing before the check exists.

**Settled for this phase (ledger, 2026-10-29, "Phase 1 settling" 1 to 4):** the coverage check is gated by `[tool.heartbeat] current-phase`; the wording lint has two tiers; uv's `exclude-newer = "14 days"` is rolling and Renovate covers PyPI, npm and Actions; this plan was written for Din's review before the build.

**Preconditions (Din):** pnpm 12.12.1 on the Mac (not installed today; Node 24.21.0 is); approval to install the locked dependencies with uv and pnpm and Playwright's Chromium and WebKit for the pinned `@playwright/test` 1.64.0; installing the Renovate GitHub app on `dinsdev/heartbeat` (an org setting, Din's); each push.

**Global constraints:** everything in section 2 above, plus: exact `==` pins (Python) and exact versions (web) for every direct dependency, copied from the E2 entry; no dependency outside E2 without a one-line reason in the commit; Conventional Commits (CONVENTIONS section 6); every file passes the wording lint's dash tier, including test files (write planted dashes as `"\u2014"` escapes, never literal characters).

#### File map

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Project metadata, E2 pins, dev group, `[tool.uv]` (`exclude-newer = "14 days"`, PyTorch CPU index for Linux only), `[tool.heartbeat] current-phase = 1`, ruff, mypy, pytest config |
| `uv.lock` | Written by `uv lock`; records `exclude-newer-span = "P14D"` |
| `.python-version`, `.node-version` | `3.14`; the newest Node 24 patch at least 14 days old |
| `src/heartbeat/__init__.py`, `paths.py` | Package; `REPO_ROOT` and other paths resolved from the repo root (CONVENTIONS section 2) |
| `src/heartbeat/cli.py` | `heartbeat` command with the E4 subcommands as stubs |
| `src/heartbeat/checks/wording.py` | R44: dash tier and published-text tier |
| `src/heartbeat/checks/rule_coverage.py` | Task 1.7: PLAN section 6 rows against rule IDs in tests |
| `src/heartbeat/checks/repo_config.py` | R45 (14-day enforcement in config and CI) and R46 (actions pinned to commit hashes) |
| `tests/conftest.py` | Hypothesis `ci` profile (`derandomize=True`, loaded when `CI` is set) |
| `tests/unit/test_cli.py`, `test_wording.py`, `test_rule_coverage.py`, `test_repo_config.py` | The tests below |
| `web/` | `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `tsconfig.json`, `vite.config.ts`, `svelte.config.js`, `eslint.config.js`, `.prettierrc.json`, `playwright.config.ts`, `index.html`, `src/main.ts`, `src/App.svelte`, `e2e/smoke.spec.ts` |
| `.github/workflows/ci.yml` | One workflow, two parallel jobs (`python`, `web`) |
| `scripts/check.sh` | Lint and unit tests, both toolchains, under 2 minutes |
| `renovate.json` | OPS-09 as amended |
| `LICENSE`, `DATA_LICENSE.md`, `README.md` | PUB-07 |
| `.gitignore` | Adds `data/`, `runs/`, `web/public/data/`, `.venv/`, `web/node_modules/`, `web/dist/`, tool caches, Playwright output, `.env*`, `.dev.vars*` |

#### Task 1: Python project and CLI stubs (TASKS 1.1, 1.6 Python half)

**Interfaces produced:** `heartbeat.paths.REPO_ROOT: Path`; `heartbeat.cli.main(argv: Sequence[str] | None = None) -> int`; `heartbeat.cli.SUBCOMMANDS: Mapping[str, int]` (name to the phase that builds it): download 2, prepare 2, make-folds 2, check-folds 2, rebuild 2, cross-validate 3, select 4, exhibit 4, train-final 4, export 5, evaluate-test 5, verify 5, cards 5, build-demo-data 6. `rebuild` accepts `--from <stage>` and `--exact`.

1. Write `pyproject.toml`: runtime pins torch 2.14.1, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1, pandas 3.0.6, wfdb 4.3.1, onnx 1.23.2, onnxscript 0.7.2, onnxruntime 1.30.0, matplotlib 3.11.2; dev group pytest 9.1.1, hypothesis 6.169.0, ruff 0.17.0, mypy 2.4.0. Torch on Linux comes from PyTorch's CPU wheel index through `[tool.uv.sources]` with a `sys_platform == 'linux'` marker and an `explicit = true` index, so CI does not pull CUDA wheels; macOS uses PyPI. Ruff: the CONVENTIONS section 1 rule set, Google docstrings, per-file ignores `D` for `tests/**` and `.claude/hooks/test_*.py`, `T20` for `src/heartbeat/cli.py`. mypy `strict = true` over `src` and `tests`. pytest: `testpaths = ["tests", ".claude/hooks"]`, `--strict-markers`, markers `rule(id)` and `realdata`, `filterwarnings = ["error"]`.
2. `uv lock`, then `uv sync --frozen`. Stop and ask Din if any E2 pin fails to resolve under the 14-day span, or if the CPU index cannot be used with `exclude-newer` (do not exempt torch from the span on your own).
3. Write `tests/unit/test_cli.py` first: every name in `SUBCOMMANDS` appears in `heartbeat --help`; each stub returns exit code 2 and writes `heartbeat <name>: not built yet (Phase N)` to stderr; an unknown subcommand exits non-zero; `rebuild --from prepare --exact` parses. Call `main([...])` in process (the shell forms of `evaluate-test` and `make-folds` are denied by F5). See it fail.
4. Write `paths.py` and `cli.py` (argparse, no new dependency) until the tests pass. Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run pytest`; the existing 96 guard tests must still pass under the new config.
5. Task 1.6 checks, recorded for the ledger: Hypothesis 6.169.0 has `settings(derandomize=True)`; ruff 0.17.0 accepts every selected rule code; a bare `uv run ruff check` now uses this config (the F5 entry's finding). Add `tests/conftest.py` with the `ci` profile.
6. Extend `.gitignore`; commit `feat(cli): Python project with E2 pins and CLI stubs`.

#### Task 2: Wording lint (TASKS 1.4, R44)

**Interfaces produced:** `Finding(path: Path, line: int, rule: str, excerpt: str)` (frozen dataclass); `check_dashes(path: Path, text: str) -> list[Finding]`; `check_published(path: Path, text: str) -> list[Finding]`; `scan(root: Path, paths: Sequence[Path] | None = None) -> list[Finding]` (default: tracked files from `git ls-files`); `PUBLISHED_PATHS = ("README.md", "docs/MODEL_CARD.md", "docs/DATA_CARD.md")`; `main(argv) -> int` for `python -m heartbeat.checks.wording [paths]`, exit 1 on any finding, one `path:line: rule: excerpt` line each.

1. Write `tests/unit/test_wording.py` first, each case one test, all `@pytest.mark.rule("R44")`:
   - Dash tier fails on: U+2014 anywhere (prose, code span, fenced block, `.py` comment); U+2013 anywhere; in Markdown prose (outside code spans and fences), a hyphen with a space on each side mid-line, a spaced double hyphen, and `&mdash;`, `&ndash;`, `&#8212;` or `&#8211;`; the same entities anywhere in `.html` and `.svelte`.
   - Dash tier passes: list markers (`- item`, `  - item`, `- [ ] task`), Prettier table separators (`| --- |`), front matter fences, hyphenated words, negative numbers, a spaced hyphen or an entity inside a Markdown code span or fenced block, the same characters in `uv.lock`, `web/pnpm-lock.yaml` and `web/vendor/brand/`, and `x - y` in a `.py` or `.ts` file (only Markdown prose gets the spaced-hyphen rule).
   - Published tier fails (case-insensitive, word-bounded) on: diagnose, diagnosis, diagnostic, diagnosed; "detects arrhythmia", "detect arrhythmias"; "detects heart disease"; "clinical-grade" and "clinical grade"; "AI doctor"; "accurate" in a Markdown heading, an HTML `h1` to `h6` and `<title>`; elevate, seamless, unleash, journey, tapestry; a negation ("not for diagnosis").
   - Published tier passes: "accurate" in body text, "accuracy" anywhere; the D7 words in files outside `PUBLISHED_PATHS` (for example a test file or `docs/PRD.md`).
   - Exit criterion cases: `main` returns 1 on a temporary README with a planted em dash, and 1 on one with a planted "diagnose".
   - Repo test: `scan(REPO_ROOT)` returns no findings.
2. See them fail; implement `wording.py` (stdlib `re` only, no Markdown library) until they pass; ruff, mypy, pytest clean. Commit `feat(checks): two-tier wording lint (R44)`.

#### Task 3: Rule-coverage check (TASKS 1.7)

**Interfaces produced:** `Row(rule_id: str, layers: tuple[str, ...], phase: int)`; `parse_rule_table(plan_md: str) -> list[Row]` (reads PLAN section 6; the phase is the first integer in the Phase column, so "1 onward" is 1); `collect_rule_ids(root: Path) -> set[str]` (Python: `pytest.mark.rule("Rn")` in `tests/**/*.py`; web: test titles starting `Rn:` in `web/**/*.test.ts` and `web/e2e/**/*.ts`); `current_phase(pyproject: Path) -> int`; `uncovered(rows, ids, phase) -> list[Row]` and `pending(rows, ids, phase) -> list[Row]` (both skip rows whose only layer is MAN); `main(argv) -> int`, exit 1 when anything is uncovered, pending rows printed with their phase.

1. Tests first in `tests/unit/test_rule_coverage.py`, on small synthetic tables and temporary trees: R4 is not covered by an R44 marker, and R1 not by R10; a row with layers `L1, L2` is covered by one test in either; MAN-only rows are never required; a row at phase 2 is pending when `current-phase` is 1 and uncovered when it is 2; "1 onward" parses as 1; a malformed table row (missing Phase cell) raises with the row text in the message; a Vitest title `"R29: parity"` and a Playwright title count; a marker inside a string in a non-test file does not.
2. Implement until green. The repo-level test (`uncovered(...)` on the real PLAN and tests is empty at phase 1) is written in Task 5, once R45 and R46 have tests. Commit `feat(checks): phase-gated rule-coverage check`.

#### Task 4: Web project (TASKS 1.2, 1.6 web half)

1. `web/package.json`: `private`, `"type": "module"`, `"packageManager": "pnpm@12.12.1"`, engines Node 24; exact versions from E2: svelte 5.57.2, vite 8.3.4, @sveltejs/vite-plugin-svelte 7.3.1, typescript 6.0.3, svelte-check 4.7.6, vitest 5.0.4, @playwright/test 1.64.0, @axe-core/playwright 4.13.0, eslint 10.12.0, typescript-eslint 8.71.2, eslint-plugin-svelte 3.23.1, prettier 3.9.10, prettier-plugin-svelte 4.1.1, onnxruntime-web 1.30.0. Wrangler 4.149.0 waits for the deploy workflow (task 6.6): only deploys use it. Scripts: `build`, `check` (`svelte-check --fail-on-warnings`), `lint`, `format:check`, `test` (`vitest run`), `e2e`.
2. `web/pnpm-workspace.yaml`: `minimumReleaseAge: 20160`; `allowBuilds` for esbuild and workerd only (check the pnpm 12 key names in its docs; E2 measured the behavior).
3. `tsconfig.json` with every CONVENTIONS section 1 option; ESLint flat config with `recommendedTypeChecked`, `stylisticTypeChecked`, `@typescript-eslint/switch-exhaustiveness-check` (confirm the rule name exists in 8.71.2: the third recalled setting) and `eslint-plugin-svelte` recommended; Prettier with `prettier-plugin-svelte`.
4. Placeholder page: heading "Heartbeat" and one line, "In development." (the D7 short line waits for Q6). Vitest gets `passWithNoTests: true` for Phase 1 only, with a comment that Phase 6 removes it once real tests exist; there is nothing to test yet and a fake test would be worse.
5. `e2e/smoke.spec.ts`: title starts `smoke:`; the built page (`vite preview`) shows the heading in Chromium and WebKit.
6. `pnpm -C web install`, then every script passes; svelte-check catches a planted type error (then remove it). Commit `feat(web): Svelte placeholder with the E2 toolchain`.

#### Task 5: Dependency and workflow checks, CI, Renovate, check script (TASKS 1.3, R45, R46)

**Interfaces produced:** `check_release_age(root: Path) -> list[str]` (R45; empty means pass) and `check_action_pins(root: Path) -> list[str]` (R46), with `main(argv) -> int` for `python -m heartbeat.checks.repo_config`.

1. Tests first in `tests/unit/test_repo_config.py`.
   - R45 (`@pytest.mark.rule("R45")`), each a failure when broken in a temporary copy: `pyproject.toml` lacks `exclude-newer = "14 days"`; `uv.lock` lacks `exclude-newer-span = "P14D"`; `web/pnpm-workspace.yaml` lacks `minimumReleaseAge: 20160` or allows builds for anything but esbuild and workerd; `renovate.json` lacks `minimumReleaseAge` of 14 days or sets automerge; a CI step runs `uv sync` without `--frozen` or `pnpm install` without `--frozen-lockfile`. Then the real repo passes.
   - R46 (`@pytest.mark.rule("R46")`): rejects `uses: actions/checkout@v5`, a quoted tag ref, a 7-character SHA, an uppercase SHA, `docker://image:tag`, and a reusable workflow `owner/repo/.github/workflows/x.yml@main`; accepts a 40-character lowercase SHA with a `# vX.Y.Z` comment, `./local-action`, and `docker://image@sha256:<64 hex>`. Then the real workflow passes.
   - Coverage (Task 3): `uncovered(...)` on the real PLAN and tests is empty at phase 1.
2. `.github/workflows/ci.yml`: on push and pull_request; top-level `permissions: contents: read`; concurrency cancels superseded runs; `timeout-minutes: 15` per job. Job `python`: checkout, `astral-sh/setup-uv` with uv 0.13.0 and its cache, `uv sync --frozen`, ruff check, ruff format check, mypy, pytest (this runs the wording lint, coverage and config checks). Job `web`: checkout, `pnpm/action-setup`, `actions/setup-node` with `.node-version` and the pnpm cache, `pnpm -C web install --frozen-lockfile`, lint, Prettier (web files and every Markdown file in the repo), svelte-check, Vitest, build, `playwright install --with-deps chromium webkit`, e2e. Each action pinned to the full commit hash of its newest release at least 14 days old, with the version in a comment. Resolve hashes with `git ls-remote` and release dates from the release pages; `gh api` is an ask rule and prompts Din.
3. `renovate.json`: `config:recommended`, `minimumReleaseAge: "14 days"` (with the internal checks setting that holds PRs until the age passes; confirm the name in Renovate's docs), monthly schedule, monthly `lockFileMaintenance`, no automerge, action digests pinned.
4. `scripts/check.sh` (`set -euo pipefail`): ruff check, ruff format check, mypy, `pytest -m "not realdata"`, web lint, Prettier (web and Markdown), svelte-check, Vitest. No Playwright, no build. Time three warm runs; all under 2 minutes.
5. Commit `ci: workflow, Renovate and check script with R45 and R46 checks`.

#### Task 6: Licenses and README (TASKS 1.5, PUB-07)

1. `LICENSE`: MIT, "Copyright (c) 2026 Dinesh Dawonauth", covering code and model weights.
2. `DATA_LICENSE.md`: the MIT-BIH Arrhythmia Database 1.0.0 (Moody and Mark, PhysioNet) is under ODC-By 1.0 (`https://opendatacommons.org/licenses/by/1-0/`, linked, not copied); what in this repo derives from it (demo traces and beats, parity fixtures, the model's `NOTICE`); the B5 citations, page ranges with plain hyphens.
3. `README.md`: what the project does in D7-safe words ("labels heartbeats", "on patients it never saw"); a research demo, not medical advice; status: in development, no results yet, and numbers appear only once a committed run produces them (rigor rule 2); the commands that work today; license split (the code license does not cover the data); citations.
4. `uv run pytest -k wording` passes now that the README exists. Commit `docs: licenses and README`.

#### Task 7: Verification and handoff

1. `scripts/check.sh` and full `uv run pytest` green; record warm timings.
2. Update `AGENTS.md` Commands: drop "Phase 0 is planning only", list the commands that exist now with single-test forms (`uv run pytest tests/unit/test_wording.py::<name>`, `pnpm -C web exec vitest run <file>`, `pnpm -C web exec playwright test <file>`), and mark the rest as arriving in their phases.
3. `docs/TASKS.md`: tasks 1.1 to 1.7 to Implemented, or Verified where a named check passed locally; the CI half waits for the push. Ledger entry: what was built, the three recalled settings checked, the CPU index result, timings, anything that deviated from this plan and why.
4. Commit, then give Din the push command for `phase-1-skeleton`. After Din pushes, read the run with `gh run list` and `gh run view` (read-only), record its wall-clock time in the ledger, fix anything red with a new commit, and ask for the next push. Phase 1 exits when CI is green under 10 minutes; Din then decides on the pull request and merge.

#### Review focus

Each line has its test in the named task.

1. Ways to dodge the dash rule (HTML entities, a spaced or double hyphen in prose): Task 2.
2. Lint false positives on ordinary Markdown (list markers, checkboxes, table separators, code spans and fences, hyphenated words): Task 2.
3. Rule ID prefix collisions (R4 and R44, R1 and R10): Task 3.
4. Workflow pins that look pinned but are not (quoted tags, short or uppercase SHAs, Docker tags, reusable workflows by branch): Task 5.
5. Local and CI toolchains drifting (a lock written by uv 0.12.11 installed by 0.13.0; torch's Linux wheels pulling CUDA): Task 1 step 2 and the first CI run, recorded in the ledger.
