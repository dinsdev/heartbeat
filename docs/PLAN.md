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

### Phase 2: Data and split (task plan, 2026-10-29)

**Goal:** the 132 pinned files downloaded and checked, DS1 prepared into the canonical int16 trace with beats, AAMI classes and RR features, a loader that cannot hand out DS2, folds made once by Din and protected by a pinned hash, and `rebuild` running its first three stages, with R1 to R15 and R51 passing in CI on real data.

**Approach:** pure functions for every numeric step (`signal/`), thin I/O around them (`data/`), and one stage framework (`stages.py`) that later phases extend. Test first throughout: each module's tests are written and seen failing before the module exists. Real-data tests (L2) read the cache through session fixtures and never skip; a missing cache fails with the command that fills it.

**Settled for this phase (ledger, 2026-10-29, "Phase 2 settling" 1 to 6, and the manifests entry):** manifests written in planning and read-only to the goal agent; filter order 4 with `sosfiltfilt`; exact RR averages; `prepare` builds DS1 only before the freeze; folds by one seeded run with a pinned hash; two goal runs around `make-folds`. Design calls approved in the same session: the window-range check reads DS1 only; more than 5 DS1 floor hits stops the run; stage fingerprints hash the code of the package folders a stage declares, not the whole package.

**Preconditions:** `manifests/` (four files) and `config/default.toml` committed (done, `7534e21`); network access to the S3 mirror; Din at the keyboard for Goal B.

**Global constraints:** section 2 above and the Phase 1 constraints (exact pins, Conventional Commits, the dash tier in every file). No new Python dependency: downloads use `urllib.request` and `hashlib`; reading uses the pinned wfdb; filtering scipy; folds scikit-learn. One new CI action, `actions/cache`, pinned to the full hash of its newest release at least 14 days old (R46), found the way Phase 1 found its pins. DS2: download, checksum (R2) and annotation counts (R11) only. No DS2 signal is read in this phase; the R4 real-data test reads record 100's header only (`wfdb.rdheader`), never its signal.

**The current-phase bump:** the first commit sets `[tool.heartbeat] current-phase = 2`. From then until every Phase 2 row has a test, the repo-level coverage test is red; it is the only red allowed in `scripts/check.sh` before a commit, and each commit message that leaves it red says which rows remain.

#### File map

| Path | Responsibility |
| --- | --- |
| `src/heartbeat/constants.py` | Planning values with decision IDs: `FS_HZ = 360`, `ADU_PER_MV = 200`, band 0.5 and 40 Hz, `BANDPASS_ORDER = 4`, `WINDOW_BEFORE_SAMPLES = 96`, `WINDOW_AFTER_SAMPLES = 160`, `ZSCORE_STD_FLOOR_ADU = 2.0`, `RR_LOCAL_INTERVALS = 10`, `RR_LONG_WINDOW_SAMPLES = 108000`, `AAMI_CLASS`, `NON_BEAT_SYMBOLS`, `SCORED_CLASSES = ("N", "S", "V", "F")`, `RR_FEATURE_NAMES`, `N_FOLDS = 5`, `FLOOR_HIT_LIMIT = 5` |
| `src/heartbeat/paths.py` | Adds `CONFIG_DIR`, `DEFAULT_CONFIG`, `MANIFESTS_DIR` and one constant per manifest, `FOLDS_JSON`, `FOLDS_PIN`, `UV_LOCK`, `STAGES_DIR` (`data/stages`) |
| `src/heartbeat/config.py` | `load_settings(path) -> Settings` (frozen dataclasses: data folders, sources, fold seed) |
| `src/heartbeat/data/manifests.py` | Parse and validate the four manifests |
| `src/heartbeat/data/download.py` | Cache check and download (DATA-01, DATA-02) |
| `src/heartbeat/data/records.py` | wfdb read, MLII by name (DATA-04) |
| `src/heartbeat/data/aami.py` | Strict symbol mapping (DATA-09, DATA-10) |
| `src/heartbeat/signal/filter.py` | Bandpass and int16 rounding (DATA-05) |
| `src/heartbeat/signal/rr.py` | The six RR features (DATA-07) |
| `src/heartbeat/signal/windows.py` | Window cutting and the floored z-score (DATA-06, R51) |
| `src/heartbeat/data/prepare.py` | Per-record pipeline; DS1 writer and floor-hit report (DATA-08) |
| `src/heartbeat/data/loader.py` | `load_ds1`; DS2 and excluded IDs raise (EVAL-04) |
| `src/heartbeat/data/folds.py` | `make_folds`, `write_folds`, `check_folds` (EVAL-02, EVAL-03) |
| `src/heartbeat/stages.py` | Stage framework, fingerprints, `run_pipeline` (OPS-01, partial) |
| `src/heartbeat/cli.py` | `download`, `prepare`, `make-folds`, `check-folds`, `rebuild` become real |
| `tests/unit/` | `test_manifests.py`, `test_download.py`, `test_records.py`, `test_aami.py`, `test_filter.py`, `test_windows.py`, `test_rr.py`, `test_prepare.py`, `test_loader.py`, `test_folds.py`, `test_stages.py`, `test_cli.py` (updated) |
| `tests/data/` | `conftest.py` (session fixtures: settings, cache present, DS1 prepared into a temp folder), `test_cache.py`, `test_records_real.py`, `test_counts.py`, `test_windows_real.py`, `test_loader_real.py`; Goal B adds `test_folds_committed.py` |
| `.github/workflows/ci.yml` | `python` job: cache step and `uv run heartbeat download` before pytest |
| `config/folds.json`, `manifests/folds.sha256` | Goal B only: written by Din's `make-folds` run and the pin edit Din approves |

#### Task 1: Phase bump, constants, config, manifests reader (TASKS 2.1)

**Interfaces produced:** `Settings`, `DataSettings(raw_dir: Path, prepared_dir: Path, sources: tuple[str, ...])`, `FoldSettings(seed: int)`; `Splits(ds1: tuple[str, ...], ds2: tuple[str, ...], excluded: Mapping[str, str], lead: str)`; `load_splits(path) -> Splits`, `load_subjects(path) -> Mapping[str, str]`, `load_checksums(path) -> Mapping[str, str]` (file name to hex), `load_beat_counts(path) -> Mapping[str, Mapping[str, int]]`, `downloaded_records(checksums) -> tuple[str, ...]`; `ManifestError`.

1. Commit `chore: start Phase 2 (current-phase = 2)`.
2. Tests first, `tests/unit/test_manifests.py`: R3 (`ds1` and `ds2` equal de Chazal's lists written out in the test, 202 excluded, the four paced records excluded, none in either set, 22 and 21 records); R12 (no subject ID on both sides of DS1 and DS2; 201 and 202 one ID; 48 records, 47 subjects); the checksum manifest names exactly the `.hea`, `.dat` and `.atr` of the 44 non-paced records; a malformed checksum line, a duplicate record, a record in both sets, or an unknown key raises `ManifestError` naming the file and line. Settings, in the same file: the fold seed reads 20261026; an unknown key in `config/default.toml` raises.
3. Implement `constants.py`, `paths.py` additions, `config.py`, `data/manifests.py` until green. Commit `feat(data): constants, settings and manifest readers`.

#### Task 2: Signal functions (TASKS 2.3, numeric half)

**Interfaces produced:** `bandpass_mv(x_mv: NDArray[np.float64]) -> NDArray[np.float64]`; `to_adu(x_mv) -> NDArray[np.int16]` (`np.rint`, `TraceRangeError` outside int16); `rr_features(beat_sample: NDArray[np.int64]) -> NDArray[np.float64]` of shape `(n_beats - 2, 6)` for beats 1 to n-2 in `RR_FEATURE_NAMES` order, `ValueError` for fewer than 3 beats or non-increasing samples; `window_bounds(sample: int) -> tuple[int, int]`; `extract_windows(trace_adu, beat_sample) -> NDArray[np.int16]` `(n, 256)`, `WindowRangeError` naming the beat; `zscore_windows(windows_adu) -> NDArray[np.float64]`; `window_std_adu(windows_adu) -> NDArray[np.float64]`.

1. Tests first, each one case:
   - R5 (`test_filter.py`): on 60 s synthetic sines at 360 Hz, measured away from the edges, gain within 0.2 dB of 0 from 2 to 25 Hz; within 0.2 dB of -6 dB at 0.5 and 40 Hz; at most -30 dB at 60 Hz; at most -40 dB at 0.1 Hz (measured on the settled filter in planning: worst -0.14 dB in 2 to 25 Hz, -6.02 dB at both edges, -32.8 dB at 60 Hz, -112.6 dB at 0.1 Hz); zero phase: a 10 Hz sine's output has its cross-correlation peak at lag 0 and a phase difference under 1e-3 rad.
   - R6: hypothesis over float64 arrays within plus or minus 150 mV, `abs(to_adu(x) / 200 - x) <= 0.0025`; values beyond the int16 range raise `TraceRangeError`; round half to even on exact halves.
   - R7 (`test_windows.py`): `window_bounds(1000) == (904, 1160)`; `extract_windows` puts `trace[s]` at index 96; a beat at sample 95 or within 159 samples of the end raises `WindowRangeError`.
   - R51: a constant window gives all zeros; hypothesis over any int16 window gives finite values; a window with standard deviation above 2 equals `(x - mean) / std` with population standard deviation.
   - R8 (`test_rr.py`): hypothesis over increasing beat samples, moving any beat at index i+2 or later never changes row i; moving beat i+1 changes only post-RR and post-over-pre of row i.
   - R9: a Q beat between two N beats is an RR endpoint (beats at 0, 300, 600 give pre-RR 300/360 s for the last N).
   - The settled definitions on a hand-checked example: the local average uses `RR_(i-9)` to `RR_i` (fewer at the start); the long average includes every interval whose ending beat lies at most 108,000 samples before beat i (one at exactly 108,000 is in, one at 108,001 out); the first kept beat's averages equal its pre-RR.
2. Implement until green. Commit `feat(signal): bandpass, int16 rounding, windows, z-score and RR features`.

#### Task 3: AAMI mapping and record reading (TASKS 2.3, labels half)

**Interfaces produced:** `NON_BEAT_SYMBOLS = frozenset("+~|!x[]\"")`; `classify_symbols(record_id: str, symbols: Sequence[str]) -> tuple[NDArray[np.bool_], NDArray[np.str_]]` (is-beat mask, class per beat); `UnknownSymbolError` naming record, index and symbol; `select_lead(sig_names: Sequence[str], lead: str) -> int` (`LeadNotFoundError`); `RawRecord(record_id, mlii_mv, ann_sample, ann_symbol)`; `read_record(raw_dir, record_id) -> RawRecord` (asserts 360 Hz, beat samples strictly increasing); `read_annotations(raw_dir, record_id)` (annotations only, for R11).

1. Tests first: R10 (`test_aami.py`): an unknown symbol raises with record and index; every symbol in DATA-09 maps to its class; `!` and `x` are not beats; the mapping covers exactly the symbols DATA-09 lists. R4 (`test_records.py`): `select_lead(["V5", "MLII"], "MLII") == 1`, `["MLII", "V1"]` gives 0, a missing lead raises.
2. Implement. Real-data tests (`tests/data/test_records_real.py`, `realdata`): R4 on 114 (full record: MLII is channel 1, 360 Hz) and 100 (header only via `wfdb.rdheader`: MLII is channel 0).
3. Commit `feat(data): strict AAMI mapping and MLII by name`.

#### Task 4: Downloader (TASKS 2.2)

**Interfaces produced:** `sha256_file(path) -> str`; `check_cache(raw_dir, checksums) -> CacheStatus(ok, missing)`, raising `ChecksumMismatchError` on a present file with the wrong hash (DATA-02: stop, never re-download over it; the message says to delete the file); `download(raw_dir, checksums, sources, fetch=fetch_url) -> DownloadReport(fetched, skipped, source_used)`. `fetch: Callable[[str], bytes]` is injected so L1 tests need no network; `fetch_url` uses `urllib.request` with a 60 s timeout.

1. Tests first (`test_download.py`, fake `fetch`, temporary folders): R1, a fetched file with the wrong hash from every source raises `ChecksumMismatchError` and leaves no file under its name; a wrong hash from the first source falls back to the second and succeeds; a network error on the first source falls back; matching cached files are skipped and `fetch` is never called; a cached file with the wrong hash stops the run; review focus 1: an exception while writing leaves no file under the final name, and stale temporary files from an earlier interrupted run are removed at the start; writes go to a temporary name in the same folder and `os.replace` after the hash matches.
2. Implement. CLI `heartbeat download` (prints counts, exit 0; exit 1 with the file name on a mismatch). Real-data test R2 (`tests/data/test_cache.py`): `check_cache` over all 132 files is ok.
3. Run `uv run heartbeat download` locally (about 100 MB; measured 1.9 MB/s from the mirror in E2, so about a minute; a guess for today). Commit `feat(data): checksum-pinned downloader with mirror fallback`.

#### Task 5: Prepare and the loader (TASKS 2.3, 2.4)

**Interfaces produced:** `PreparedRecord(record_id, subject_id, trace_adu int16, beat_sample int64, beat_symbol, beat_class, kept bool, rr_s float64 (n_kept, 6))` with `save_prepared(record, path)` (atomic `.npz`, `allow_pickle=False`) and `load_prepared(path)`; `prepare_record(raw: RawRecord, subject_id: str) -> PreparedRecord` (pure; the same function will prepare DS2 in memory inside `evaluate-test`); `prepare_ds1(settings, splits, subjects) -> PrepareReport` writing `<prepared_dir>/<record>.npz` and `<prepared_dir>/floor_hits.json` (per DS1 record: hits and smallest window standard deviation in int16 units); `SealedRecordError`; `require_ds1(record_ids, splits)`; `BeatTable(record_id, subject_id, sample, beat_class, window_adu (n, 256) int16, rr_s (n, 6))`; `load_ds1(prepared_dir, splits, subjects, records=None, include_q=False) -> BeatTable`.

1. Tests first: `test_prepare.py` on a synthetic `RawRecord` (a few beats, one Q, one `+` marker): first and last beat not kept; Q kept for RR but its class is Q; non-beats excluded from RR; RR rows line up with kept beats; a round trip through `save_prepared` and `load_prepared` is exact; `prepare_ds1` refuses a DS2 or excluded ID before reading anything. R15 (`test_loader.py`): `load_ds1` and `require_ds1` raise `SealedRecordError` for every DS2 ID, 202, the paced IDs and an unknown ID, even when a matching `.npz` exists in a temporary folder; an import-graph test (AST over `src/heartbeat`) finds `read_record` imported only by `data/prepare.py`.
2. Implement. CLI `heartbeat prepare` writes DS1 and prints the floor-hit total.
3. Real-data tests: R11 (`test_counts.py`) for each of the 44 records, symbol counts from `read_annotations` equal `mitdb-beat-counts.toml` exactly, and AAMI class counts per record follow from them; DS1 window range (`test_windows_real.py`): every kept DS1 beat has a full window; R15 L2 (`test_loader_real.py`): `load_ds1` on the prepared DS1 returns 22 records, classes only N, S, V, F, dtypes and shapes as documented, and refuses `"100"`.
4. Run `uv run heartbeat prepare`. Record in the ledger: floor hits per DS1 record and the smallest standard deviation (B3 amendment); our per-class totals from the annotations against de Chazal's Table II (DS1: N 45868, S 942, V 3787, F 415, Q 8; DS2 with 202, as the paper counts it: N 44258, S 1837, V 3221, F 388, Q 7), once for all beats and once with each record's first and last beat dropped, listing every difference (annotation counts only; no DS2 signal). Commit `feat(data): DS1 prepare, floor-hit report and split-enforcing loader`.

#### Task 6: Folds code (TASKS 2.5, code half)

**Interfaces produced:** `Folds(seed, sklearn_version, manifest_sha256: Mapping[str, str], subject_fold: Mapping[str, int], class_counts: Mapping[str, Mapping[str, int]])`; `make_folds(beats: BeatTable, seed: int) -> Folds` (`StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)` on scored DS1 beats, label the class, group the subject); `write_folds(folds, path)` (canonical JSON: sorted keys, two-space indent, trailing newline; atomic; refuses to overwrite); `read_folds(path)`; `check_folds(folds_path, pin_path, splits, subjects) -> Folds` raising `FoldCheckError` with the reason. The pin file uses `sha256sum` format (`<hex>  config/folds.json`).

1. Tests first (`test_folds.py`, synthetic `BeatTable`s, temporary paths): `make_folds` is deterministic for one seed; every subject in exactly one fold; R13, a planted fold file with one subject in two folds, a DS2 subject, a missing DS1 subject, or 201 and 202 split apart fails `check_folds`; R14, flipping one byte of a valid copy fails on the pinned hash, a missing pin fails, and `check_folds` never imports or calls the splitter (patched to raise); `write_folds` refuses an existing file; `heartbeat make-folds --out <tmp>` and `heartbeat check-folds` called as `main([...])` in process (the shell form of `make-folds` is denied by F5).
2. Implement. CLI `make-folds [--out PATH]` (default `config/folds.json`, reads the prepared DS1 and the seed from settings) and `check-folds`. Commit `feat(data): make-folds and check-folds with a pinned hash`.

#### Task 7: Stage framework and `rebuild` (TASKS 2.6)

**Interfaces produced:** `Stage(name, settings_keys, upstream, code, inputs, run, outputs, always_run=False)`; `fingerprint(stage, context, upstream_fingerprints) -> str` (SHA256 over canonical JSON of: name, the named settings values, upstream fingerprints, the hash of every `.py` file under the stage's declared package folders, the hashes of its input files, the `uv.lock` hash); `run_pipeline(stages, context, from_stage=None) -> list[StageResult]`; state in `data/stages/<name>.json`; `PIPELINE` (download, prepare, check-folds built; cross-validate, select, exhibit, train-final, export, reproduce-test, build-demo-data named with their phases).

1. Tests first (`test_stages.py`, stages with counting `run` functions in temporary folders): a second run skips every stage; a changed setting, input file, code file or upstream fingerprint reruns that stage and everything after it; deleting an output reruns its stage; `--from prepare` reruns prepare and check-folds but not download; `check-folds` (`always_run`) runs every time; an unknown `--from` exits non-zero; a stage that fails leaves its old state untouched; `rebuild` stops after the last built stage, exits 0 and names the next stage and its phase; `--exact` parses.
2. Implement and wire `rebuild`. Update `test_cli.py`: the stub test now covers only subcommands whose phase is above 2; the five built ones have their own tests. Commit `feat(cli): rebuild stages with fingerprints and --from`.

#### Task 8: CI real-data step, docs, and the hand-off to Din (Goal A ends here)

1. `.github/workflows/ci.yml`, `python` job, before pytest: `actions/cache` (hash-pinned, with the version comment) on `data/raw/mitdb/1.0.0` keyed on `hashFiles('manifests/mitdb-1.0.0.sha256')`, then `uv run heartbeat download`. R45 and R46 tests pass on the new workflow. Commit `ci: cache and download MIT-BIH for the real-data tests`.
2. `scripts/check.sh`, `uv run pytest` (with the real-data layer), `rule_coverage`, `repo_config` and the wording lint all green; R13's real-file test is not written yet, since the planted-leak test already covers the row. `AGENTS.md` Commands: `download`, `prepare`, `check-folds`, `rebuild` move to "Working today" and `make-folds` is listed as Din's. `docs/TASKS.md`: 2.1 to 2.4 and 2.6 Implemented or Verified as checks allow, 2.5 In progress. Ledger: what was built, deviations and why, timings, the floor hits and Table II comparison from Task 5. Commit `docs: Phase 2 Goal A verification and hand-off`.
3. Stop and give Din: `uv run heartbeat make-folds`.

#### Task 9: The committed folds (Goal B)

1. Din has run `make-folds`; `config/folds.json` exists and is untracked. Read it (DS1 only) and compute its SHA256.
2. Write `manifests/folds.sha256` (Din approves the prompt). Tests first, `tests/data/test_folds_committed.py`: R13 on the committed file (every DS1 subject once, no DS2 or excluded subject, 201's fold valid, its manifest hashes equal today's manifests); `check_folds` on the committed file and pin passes.
3. `uv run heartbeat check-folds` exit 0; `uv run heartbeat rebuild` twice: the first runs, the second skips download and prepare (timings recorded).
4. Ledger entry (rigor event, rule 4): seed, scikit-learn version, subjects per fold, per-fold class counts, where 208 and its F beats landed, the hash, and that this was the only run. Commit `feat(data): committed folds and their pinned hash` with `config/folds.json`, `manifests/folds.sha256` and the test.
5. Full verification as in Task 8, `docs/TASKS.md` 2.1 to 2.6 Verified where checks passed, `AGENTS.md` if anything changed. Commit, then give Din the push command for `phase-2-data`. After the push, read the run with `gh run list` and `gh run view`, record its wall-clock time and the download time in the ledger, and fix anything red in a new commit. Phase 2 exits when R1 to R15 and R51 pass in CI.

#### Stop and ask Din (both goals)

Never edit a manifest, a test's expected value or a tolerance to get past one of these:

1. Any record's `.atr` counts differ from `mitdb-beat-counts.toml` (R11).
2. An annotation symbol outside DATA-09's beats and `NON_BEAT_SYMBOLS` in any record.
3. A kept DS1 beat whose window leaves the record, or MLII missing, or a rate other than 360 Hz.
4. More than 5 DS1 windows hit the z-score floor.
5. Both download sources fail, or a downloaded file's hash never matches.
6. Anything that would need a new dependency, a pin change, or an edit to `manifests/` (Goal A) or `.claude/`.
7. Any DS2 signal, feature or prediction seen by accident (rule 1).
8. Din's fold file fails `check_folds` or holds other than 22 DS1 subjects (a bug to fix in code; never a reason to rerun `make-folds` for different folds).

#### Review focus

1. A cached file corrupted after download, and a download interrupted mid-write: Task 4.
2. The edge cases of the settled RR definitions (first kept beat, the exact 5-minute boundary, Q beats as endpoints): Task 2.
3. DS2 reaching `prepare` or the loader by any path, including a stray `.npz` in the prepared folder: Task 5.
4. A fold file that is valid but different from the pinned one: Task 6.
5. A stage skipped although its code changed, because the code sits outside the folders the stage declares: Task 7 declares download as `data/`, prepare as `data/` and `signal/`, check-folds as `data/`, each plus `constants.py`, `config.py` and `paths.py`; Din's review of this plan is the check that the lists are complete.

### Phase 3: Evaluation harness and baseline (task plan, 2026-10-29)

**Goal:** every metric, interval and calibration number the pre-registered report needs exists as tested code; run folders and a `results/` writer exist; the baseline is cross-validated on the committed folds with C chosen by pooled out-of-fold macro F1 over N, S and V; `rebuild` runs a `cross-validate` stage that writes `results/cv_baseline.json`; R16 to R21 pass locally and, after Din's push, in CI.

**Approach:** metrics are pure functions of a 4 by 4 confusion matrix (rows the expert label, columns the model label, order `SCORED_CLASSES`), so pooled, per-fold, per-patient and bootstrap numbers all come from one code path. The bootstrap sums per-patient confusion matrices with draw counts, so 10,000 draws are one matrix product. One model-agnostic cross-validation driver owns the folds, the class weights, the selection metric and calibration; a model supplies only `fit` and `logits`. The baseline is its first model and the CNN plugs into the same driver in Phase 4, which is what makes R21 structural. Test first throughout, as in Phase 2.

**Settled for this phase (ledger, 2026-10-29, "Phase 3 settling" 1 to 5):** selection on macro F1 over N, S and V, including Phase 4's epoch curves; the zero-denominator rule (skip per metric and count, F1 = 2TP / (2TP + FP + FN), "undefined" never 0); per-patient percentages gated on each cell's own denominator; DS1 calibration with the in-sample temperature, labeled, plus one throwaway cross-fit check; 95% percentile intervals. Table V's EC57 counts are written out in settling 5.

**Design calls for Din's review (made by Claude while planning, approved with this plan):**

1. Bootstrap seed `BOOTSTRAP_SEED = 20261029` (today, distinct from the fold seed), a constant in `constants.py`, since no run varies it. Patients are ordered by sorted subject ID; draws depend only on the seed and the number of patients, so every model scored on one patient set shares one draw matrix. The without-232 line draws again with the same seed over its 20 patients.
2. The RR scaler is the shared `fit_rr_scaler` and `apply_rr_scaler` (CONVENTIONS section 3), not scikit-learn's `StandardScaler` inside a `Pipeline` as the C2 entry words it. Same math (population standard deviation); one implementation that the CNN and the TypeScript parity code will also use. A test checks it equals `StandardScaler` on random data.
3. Balanced class weights come from one function, `n_beats / (4 * count_c)` over the training part of the fold, passed to scikit-learn as an explicit dict (same math as `class_weight="balanced"`, checked against `compute_class_weight`).
4. The baseline runs in float64 (it never ships; CONVENTIONS' float32 rule is for the model path).
5. lbfgs gets `max_iter=10_000`; a `ConvergenceWarning` is an error (pytest already sets `filterwarnings = ["error"]`; the CLI escalates it too). Any non-convergence stops the run (stop condition 1). A C tie keeps the smaller C.
6. `results/` holds summaries only (`cv_baseline.json`); out-of-fold predictions stay in the run folder. No figures in Phase 3: reliability data is written as numbers, and figures come with the pages that use them.
7. The `cross-validate` CLI writes a run folder only; `results/` is written only by the `rebuild` stage (rule 5). A committed results file must record `"dirty": false` and a commit that is an ancestor of `HEAD`, checked by a test.

**Preconditions:** Phase 2 merged (`5643163`); the MIT-BIH cache downloaded and DS1 prepared (`uv run heartbeat rebuild`); settling 1 to 5 committed on `main`.

**Global constraints:** section 2 and the Phase 1 and 2 constraints. No new dependency (numpy, scipy and scikit-learn cover everything; torch is not imported in Phase 3). DS1 only: no code path in this phase touches DS2, and the bootstrap and per-patient code are tested on synthetic patients. Numbers quoted in the ledger name `results/cv_baseline.json` or the run folder and say "DS1 out-of-fold, CPU".

**The current-phase bump:** the first commit on branch `phase-3-harness` sets `current-phase = 3`; the coverage test is red until R16 to R21 each have a test, and each commit that leaves it red names the rows remaining.

#### File map

| Path | Responsibility |
| --- | --- |
| `src/heartbeat/constants.py` | Adds `HEADLINE_CLASSES = ("N", "S", "V")`, `BASELINE_C_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)` (C2), `BASELINE_MAX_ITER = 10_000`, `BOOTSTRAP_DRAWS = 10_000`, `BOOTSTRAP_SEED = 20261029`, `INTERVAL_PERCENTILES = (2.5, 97.5)` (settling 5), `ECE_BINS = 10`, `PER_PATIENT_MIN_BEATS = 10` (C4), `TEMPERATURE_BOUNDS = (0.05, 20.0)` |
| `src/heartbeat/evaluate/metrics.py` | Confusion matrix, one-vs-rest and EC57 metrics, macro F1, `selection_score` (EVAL-08, R16) |
| `src/heartbeat/evaluate/bootstrap.py` | Draws, per-patient confusions, batched metrics, intervals, skip counts, paired differences (EVAL-09, R17, R18) |
| `src/heartbeat/evaluate/per_patient.py` | The per-patient S and V table with the count rule (EVAL-08 item 4, R19) |
| `src/heartbeat/evaluate/calibration.py` | Labels, logit adjustment, temperature, ECE, reliability data, log loss, Brier (EVAL-11, EVAL-12, R20) |
| `src/heartbeat/models/inputs.py` | `rr_model_inputs` (log of the two ratios), `fit_rr_scaler`, `apply_rr_scaler` (C2, C3) |
| `src/heartbeat/models/baseline.py` | Multinomial logistic regression as a `ModelSpec` (MODEL-01) |
| `src/heartbeat/train/weights.py` | `balanced_class_weights` (C2, C3) |
| `src/heartbeat/train/cv.py` | Fold indices from `Folds`, the CV driver, C selection, calibration of the chosen model, the summary payload (EVAL-07, R21) |
| `src/heartbeat/runs.py` | Run folders and provenance (MODEL-07, C6) |
| `src/heartbeat/results.py` | Canonical, atomic `results/` writer (rule 5) |
| `src/heartbeat/stages.py`, `cli.py` | `cross-validate` stage and subcommand |
| `tests/unit/` | `test_metrics.py`, `test_bootstrap.py`, `test_per_patient.py`, `test_calibration.py`, `test_inputs.py`, `test_weights.py`, `test_baseline.py`, `test_cv.py`, `test_runs.py`, `test_results.py`, `test_results_committed.py`; `test_stages.py` and `test_cli.py` updated |
| `tests/data/` | `test_cv_baseline_real.py` |

#### Task 1: Phase bump, constants, metrics (TASKS 3.1)

**Interfaces produced:** `confusion_matrix(y_true, y_pred) -> NDArray[np.int64]` `(4, 4)`, labels as class strings, anything outside `SCORED_CLASSES` raises; `class_metrics(cm) -> dict[str, ClassMetrics]` with `recall`, `precision`, `f1`, `fpr` per class (`float`, NaN when undefined; F1 = 2TP / (2TP + FP + FN)); `macro_f1(cm, classes) -> float` (mean over the classes; NaN only if one of them is undefined); `ec57_metrics(cm) -> dict[str, EC57Metrics]` for S and V with `se`, `ppv`, `fpr` from the Table V counts in the settling 5 entry; `selection_score(cm) = macro_f1(cm, HEADLINE_CLASSES)`; `summarize(cm) -> dict` (everything above, NaN written as `None`). Batched variants take `(..., 4, 4)` arrays so the bootstrap reuses them.

1. Commit `chore: start Phase 3 (current-phase = 3)` on `phase-3-harness`.
2. Tests first, `test_metrics.py`, R16: recall, precision and F1 per class equal scikit-learn's `precision_recall_fscore_support(labels=SCORED_CLASSES, zero_division=np.nan)` and `f1_score`, on hand cases and a hypothesis property over random label pairs (compare with `equal_nan`); macro F1 over all four equals `f1_score(average="macro")` when every class is defined; a hand 4 by 4 case for EC57 where Fv is non-zero and is excluded from V's FP and TN, and Qs-style cells do not exist; FPR on a hand case; no predicted S gives S precision NaN and S F1 0; a class absent from labels and predictions gives F1 NaN; batched equals looped.
3. Implement until green. Commit `feat(evaluate): confusion-matrix metrics with EC57 definitions`.

#### Task 2: Paired patient bootstrap (TASKS 3.1)

**Interfaces produced:** `patient_confusions(y_true, y_pred, subject_id, patients) -> NDArray[np.int64]` `(n_patients, 4, 4)`; `draw_counts(n_patients, n_draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED) -> NDArray[np.int64]` `(n_draws, n_patients)` (`np.random.default_rng(np.random.SeedSequence(seed))`, patients drawn with replacement, counts per row sum to `n_patients`); `bootstrap(confusions_by_model: Mapping[str, NDArray], counts) -> BootstrapResult` with, per model and metric, the point estimate on the full set, the 95% interval (`np.percentile` over defined draws, default linear method) and the skip count; `paired_difference(result, a, b, metric)` with its own skip count. Draws with no defined value at all give a `None` interval, never an error.

1. Tests first, `test_bootstrap.py`. R17: every draw is a multiset of whole patients (a planted patient with a unique label pattern contributes all or none of its beats per copy); the same seed gives the same counts; two models scored in one call use one counts matrix (a spy on `draw_counts` sees one call); the draw-sum equals recomputing the confusion matrix from the resampled beats on a small case. R18: a draw where no patient has predicted S is skipped for S precision only, S recall and macro F1 still use it, and the skip count equals the number of such draws (constructed exactly); a paired difference skips draws where either side is undefined. Interval percentiles on a known vector.
2. Implement. Commit `feat(evaluate): paired patient bootstrap with skip counts`.

#### Task 3: Per-patient table (TASKS 3.1)

**Interfaces produced:** `per_patient_table(confusions, patients) -> list[PatientRow]` with, for S and V, `recall_cell` and `precision_cell`, each `Cell(numerator, denominator, percent: float | None, note: str | None)`; `percent` only when the cell's own denominator is at least `PER_PATIENT_MIN_BEATS`; zero flagged beats gives `note="none flagged"`; zero true beats gives `note="none present"`.

1. Tests first, `test_per_patient.py`, R19: 9 true S beats gives counts and no percent; 10 gives a percent; precision with 50 true S and 2 flagged gives no percent (the settling 3 case); 12 flagged gives a percent; 0 flagged gives "none flagged"; counts always present.
2. Implement. Commit `feat(evaluate): per-patient table with the count rule`.

#### Task 4: Calibration (TASKS 3.2)

**Interfaces produced:** `predict_labels(logits) -> NDArray[np.str_]` (argmax of the raw weighted-model logits; takes nothing else, so calibration cannot reach it); `adjust_logits(logits, class_weights) -> NDArray` (subtract `log w_c`, per row's own fold weights when given an array); `fit_temperature(adjusted, y_true) -> float` (minimize mean log loss over `log T` with `scipy.optimize.minimize_scalar(method="bounded")` inside `TEMPERATURE_BOUNDS`; raises if the optimum is within 1% of a bound); `calibrated_probs(adjusted, temperature)`; `ece_equal_mass(prob_k, is_k, n_bins=ECE_BINS) -> float` (stable sort by probability, `np.array_split` into 10 bins, sum of `n_b / N * |mean p_b - mean y_b|`); `reliability_data(...)` (per bin: count, mean probability, observed rate, lowest and highest probability); `log_loss_from_logits(adjusted, temperature, y_true)` via `scipy.special.log_softmax`; `brier(probs, y_true)` (mean over beats of the squared distance to the one-hot label summed over the four classes).

1. Tests first, `test_calibration.py`, R20: labels from `predict_labels` are identical before and after adjustment and any temperature (property test), and calibrated probabilities' argmax may differ, which is allowed and documented; logit adjustment on a hand case equals `logits - log(w)`; a model whose logits are a known multiple of true log-odds recovers that temperature within 1e-3; equal-mass bins differ in size by at most one beat and ECE matches a hand case; ties in probability split by original order deterministically; log loss equals scikit-learn's `log_loss(labels=...)` on the calibrated probabilities; Brier on a hand case and against scikit-learn's `brier_score_loss(labels=..., scale_by_half=False)` (checked while planning: scikit-learn 1.9.1 accepts multiclass probabilities there).
2. Implement. Commit `feat(evaluate): logit adjustment, temperature and calibration metrics`.

#### Task 5: Run folders and the results writer (TASKS 3.3)

**Interfaces produced:** `create_run(name, settings, extra_config, root=RUNS_DIR) -> RunFolder` making `runs/<UTC %Y%m%dT%H%M%SZ>-<short commit>-<name>/` with `config.json` (resolved settings plus `extra_config`), `provenance.json` (commit, dirty flag, SHA256 of `git diff HEAD`, Python version, versions of numpy, scipy, scikit-learn and wfdb from `importlib.metadata`, `uv.lock` and `config/folds.json` SHA256, device `"cpu"`, `os.cpu_count()` and any `*_NUM_THREADS` variables) and `log.txt` (a logging file handler); `RunFolder.write_json(name, payload)`, `RunFolder.write_arrays(name, **arrays)` (`.npz`, `allow_pickle=False`); `write_result(name, payload, run, results_dir=RESULTS_DIR)` writing `results/<name>.json` as canonical JSON (sorted keys, two-space indent, trailing newline, `allow_nan=False`, so NaN must already be `None`), atomic, with `run`, `commit` and `dirty` copied from the run's provenance. `RUNS_DIR` and `RESULTS_DIR` join `paths.py`.

1. Tests first, `test_runs.py` and `test_results.py` (temporary git repos and folders): provenance fields present and the dirty flag true after an uncommitted edit; a NaN in a payload raises; output is byte-stable for one payload; a failed write leaves the old file; an import-graph test (AST over `src/heartbeat`) finds `write_result` imported only by `stages.py`. `test_results_committed.py`: every committed `results/*.json` other than `test_runs.jsonl` has `"dirty": false` and a commit that is an ancestor of `HEAD` (passes vacuously until Task 7 commits one).
2. Implement. Commit `feat(cli): run folders and the results writer`.

#### Task 6: Inputs, weights, the CV driver and the baseline (TASKS 3.4)

**Interfaces produced:** `rr_model_inputs(rr_s) -> NDArray[np.float64]` `(n, 6)`, with `log` of `pre_over_local` and `post_over_pre` (a non-positive ratio raises); `RRScaler(mean, std)`, `fit_rr_scaler(x_train)`, `apply_rr_scaler(scaler, x)` (population std; a zero std raises); `balanced_class_weights(y_train) -> dict[str, float]`; `fold_indices(beats: BeatTable, folds: Folds) -> list[tuple[NDArray, NDArray]]` (validation fold k is the beats whose subject is in fold k; raises on a subject missing from the folds); `ModelSpec(name, fit(x_train, y_train, class_weight, params) -> fitted, logits(fitted, x) -> (n, 4))`; `BASELINE: ModelSpec` (`LogisticRegression(solver="lbfgs", C=params["C"], class_weight=dict, max_iter=BASELINE_MAX_ITER)` on scaled `rr_model_inputs`; logits are `decision_function` reordered from scikit-learn's sorted `classes_` (F, N, S, V, checked while planning) to `SCORED_CLASSES` order); `cross_validate(spec, beats, folds, params) -> CVResult` (out-of-fold raw logits, fold per beat, each fold's class weights and scaler); `select_baseline_c(beats, folds, grid=BASELINE_C_GRID) -> BaselineCV` (one `CVResult` per C, pooled `selection_score` per C, chosen C with ties to the smaller, then for the chosen C: labels, adjusted logits with each fold's own weights, temperature, calibrated probabilities); `cv_summary(result, subject_id) -> dict` (the payload below).

The payload: model and chosen C; per C, pooled macro F1 over N, S and V and four-class beside it; for the chosen C, the pooled confusion matrix and `summarize`, EC57 S and V, per-fold `summarize` with min and max across folds for each headline metric (EVAL-07's spread), bootstrap intervals over the 22 DS1 subjects with skip counts, and calibration (temperature, S and V ECE, reliability data, log loss, Brier) under a key that carries the label `"temperature fitted on these predictions"` (settling 4); patient order and draw settings; the folds SHA256.

1. Tests first: `test_inputs.py` (log columns, scaler equals `StandardScaler` on random data, scaler fitted on train never sees validation rows: a validation-only outlier leaves it unchanged); `test_weights.py` (equals scikit-learn's `compute_class_weight("balanced")`); `test_baseline.py` (fit and logits shapes on a synthetic separable set; column k of the logits belongs to `SCORED_CLASSES[k]`, shown by a set where only S is separable; a `ConvergenceWarning` raises); `test_cv.py`: R21, `cross_validate` gets its folds only through `fold_indices`, its weights only through `balanced_class_weights` and its selection metric only through `selection_score` (spies, and an AST check that `models/` never imports `data.folds` or computes weights), and the baseline is run through `cross_validate`, so Phase 4 extends this test with the CNN spec; every beat gets exactly one out-of-fold prediction and its fold matches its subject; C tie keeps the smaller; the summary has no NaN.
2. Implement. CLI `heartbeat cross-validate --model baseline` (reads the prepared DS1 and the checked folds, writes a run folder with `metrics.json`, `oof.npz` (record, subject, sample, true class, fold, raw logits and calibrated probabilities for the chosen C) and `model.npz` (each fold's coefficients, intercepts and scaler), prints the chosen C and the run folder; never writes `results/`). Commit `feat(train): CV driver and the logistic regression baseline`.

#### Task 7: The `cross-validate` stage, the real run, and its checks (TASKS 3.3, 3.4)

1. Tests first: `test_stages.py`, the `cross-validate` stage (upstream prepare and check-folds; code folders `data`, `signal`, `models`, `train`, `evaluate` plus `runs.py`, `results.py` and the shared files; inputs the folds, its pin and the two manifests; output `results/cv_baseline.json`) reruns when any of those change and is skipped otherwise; `rebuild` now stops after it and names `select` (Phase 4). `tests/data/test_cv_baseline_real.py` (`realdata`): baseline CV on real DS1 at one C gives one prediction per scored beat, only N, S, V, F, folds equal `config/folds.json`, and no record outside DS1.
2. Implement the stage. Update `test_cli.py`: `cross-validate` leaves the stub list.
3. Commit the code, then on that clean tree run `uv run heartbeat rebuild` (all stages up to cross-validate; record the wall-clock time) and commit `results/cv_baseline.json` alone as `feat(train): baseline out-of-fold results`. Run `rebuild --from cross-validate` once more: the metrics in the new file must equal the committed ones exactly (determinism on CPU); restore nothing by hand, just confirm `git diff` shows only `run`, `commit` or `dirty` changes, or none.
4. Settling 4's check, in a throwaway script in Claude's scratchpad that reads the run folder's `oof.npz`: fit a temperature per fold on the other four folds' adjusted logits, apply it to that fold, and compare log loss and S and V ECE with the in-sample numbers. Record both in the ledger. Stop and ask Din if log loss differs by more than 1e-3 nats per beat or either ECE by more than 0.01. Delete the script.

#### Task 8: Docs and the hand-off to Din

1. `scripts/check.sh`, `uv run pytest` (real-data layer included), `rule_coverage` (R16 to R21 covered), `repo_config` and the wording lint all green.
2. `AGENTS.md` Commands: `cross-validate` and the `rebuild` stage move to "Working today". `docs/TASKS.md` 3.1 to 3.4 Verified (locally) with commands. Ledger entry: what was built, commits, deviations and why, timings, the chosen C, the pooled DS1 out-of-fold headline numbers with their intervals and the temperature, each naming `results/cv_baseline.json` and the run folder, labeled "DS1 out-of-fold, CPU", and settling 4's comparison. Commit `docs: Phase 3 verification and hand-off`.
3. Give Din the push command for `phase-3-harness`. After the push, read the run with `gh run list` and `gh run view`, record its wall-clock time, and fix anything red in a new commit. Phase 3 exits when R16 to R21 pass in CI and `results/cv_baseline.json` is committed.

#### Stop and ask Din

Never change a test's expected value, a tolerance, the C grid or a seed to get past one of these:

1. lbfgs fails to converge at any C, even at `max_iter=10_000`.
2. A metric disagrees with scikit-learn on a case where both are defined.
3. Two `rebuild --from cross-validate` runs give different metrics on the same commit.
4. Settling 4's cross-fit check exceeds its threshold.
5. A fitted temperature lands within 1% of a bound.
6. Anything needs a new dependency, a pin change, or an edit to `manifests/`, `config/folds.json` or `.claude/`.
7. Any DS2 signal, label or prediction seen by accident (rule 1).
8. The chosen C is 0.01 or 100 (the edge of the locked grid): not a stop, but say so in the ledger and the hand-off, since widening the grid is Din's call.

#### Review focus

1. Undefined metrics turning into 0 anywhere (scikit-learn defaults, `np.nanmean` over a NaN that should propagate, JSON writing): Tasks 1, 2 and 5.
2. Calibration leaking into labels: Task 4's property test, and the CV driver taking labels from raw logits only.
3. Out-of-fold logits adjusted with the wrong fold's weights: Task 6 tests a case where folds have different weights.
4. The scaler or weights fitted on validation rows: Task 6.
5. A results file written from a dirty tree or by hand: Task 5's committed-results test and the guard hook.
