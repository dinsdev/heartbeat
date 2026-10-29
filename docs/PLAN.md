# Heartbeat: Plan

|                |                                                                                                     |
| -------------- | --------------------------------------------------------------------------------------------------- |
| **Status**     | Locked by Din (F2, 2026-10-27). Phase task plans are added in section 8 as each phase starts.       |
| **Date**       | 2026-10-27                                                                                          |
| **Implements** | `docs/PRD.md` (locked F1). Requirement IDs below (for example `EVAL-05`) refer to it.               |
| **Related**    | `docs/TASKS.md` (build tasks per phase), `docs/WORK_LEDGER.md` (decisions and verification results) |

This plan says in what order Heartbeat gets built, what each phase must prove before the next starts, and which test enforces each rigor rule. It does not repeat the requirements; the PRD holds those.

## 1. Approach

**Build the evidence before the show.** The order follows the trust chain: data and split first, then the evaluation harness on the cheap baseline, then the CNN, then export and parity, then the demo. Each layer is tested before the next depends on it, so a bug found late cannot quietly invalidate earlier numbers.

**DS2 stays sealed until one planned moment.** Everything up to Phase 6 uses DS1 only, including the demo, which runs on DS1 recordings (C1, E4). The sealed run is a single phase with a gate checklist (Phase 7). DS2 demo data, the model card and the case study come after it.

**Plan per phase, at the phase's start.** This document is phase-level. When a phase starts, Claude writes its task-level plan (files, interfaces, test-first steps, commits) as a section at the end of this file, Din reviews it, and the build tasks in `docs/TASKS.md` get updated. Reason: F4's conventions and earlier phases' interfaces shape the detail, so writing it all now would mean rewriting it.

**Tests come with the code.** Each phase's exit criteria include its rows of the rule-to-test table (section 6). A phase is done when those tests pass in CI, not when the code exists.

**Branches and pushes.** After the repo goes public (end of Phase 0), each phase works on a branch (`phase-N-<name>`) with local commits at every checkpoint. Pushing a branch and opening its pull request runs CI and, from Phase 6, a preview deploy. Every push waits on Din's go (E6), so pushes happen at checkpoints, not per commit. Phases merge to `main` after CI passes and Din agrees.

## 2. Global constraints

Every phase is bound by these (details in the PRD and ledger):

- Pins: newest stable release at least 14 days old, enforced by uv `exclude-newer` and pnpm `minimumReleaseAge: 20160`; ONNX Runtime 1.30.0 in Python and the browser; Python 3.14; Node 24; TypeScript 6.0.3 (E1, E2).
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

**Builds:** `pyproject.toml` with the E2 pins and `exclude-newer`; `uv.lock`; the `heartbeat` CLI with empty subcommands; `web/` with pnpm, the E2 pins, `minimumReleaseAge` and `allowBuilds`; the GitHub Actions workflow (SHA-pinned actions, read-only permissions); `scripts/check.sh`; Renovate config; the wording lint; tool configs per `docs/CONVENTIONS.md`; the rule-coverage check (every non-manual row of section 6 has a test carrying its ID); `LICENSE`, `DATA_LICENSE.md`, README; `.gitignore` for `data/`, `runs/`, `web/public/data/`.
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

**Builds:** single-file ONNX export, scaler and calibration JSON, `models/heartbeat-v1/` (pre-freeze contents); parity fixtures from DS1; the Python half of the parity chain; `rebuild` end to end up to export, stopping before DS2; `heartbeat verify`; `heartbeat cards`, which renders the generated blocks of `docs/MODEL_CARD.md` and `docs/DATA_CARD.md` from `results/`, with its check in `verify` (F6); `evaluate-test` with its freeze and clean-tree checks and the append-only log writer, tested only for its refusals (it never reads DS2 before Phase 7).
**Requirements:** PARITY-01, PARITY-02, PARITY-03 (Python half), PARITY-04, OPS-01, OPS-02, OPS-04, EVAL-05, EVAL-06.
**Depends on:** Phase 4.
**Exit:** rows R25 to R28, R41, R42 and R50 pass; `rebuild` from a clean clone reproduces `results/` within tolerance (default mode) and logs the result in the ledger.

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

**Builds:** model card and data card: numbers rendered by `heartbeat cards` from committed results into the F6 templates, prose finished by hand, the model weights license decided; the case study (in the dins.dev repo, from G1); the stage video from patient 200 with the research-demo line (G2); Ask Ottie sources (G3); PhysioNet's citation rechecked; one VoiceOver pass; Din's review in a preview deploy; first production deploy (Din's go).
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

| Layer | What                                                       | Where it runs                        |
| ----- | ---------------------------------------------------------- | ------------------------------------ |
| L1    | Python unit tests (pytest, hypothesis), no data            | CI on every push; `scripts/check.sh` |
| L2    | Python tests on real MIT-BIH data (cached download)        | CI on every push                     |
| L3    | Parity chain on shared DS1 fixtures (1e-5, labels exact)   | CI (Python half and browser half)    |
| L4    | Web unit tests (Vitest)                                    | CI; `scripts/check.sh`               |
| L5    | Web end to end (Playwright, Chromium and WebKit)           | CI                                   |
| TX    | Wording lint on built demo text and the case study draft   | CI                                   |
| GATE  | Size and performance gates in the web build and Playwright | CI                                   |
| MAN   | Manual check, recorded in the ledger                       | Before the named milestone           |

## 6. Rule-to-test table

Each locked rigor rule and the test that enforces it. Test names are indicative; the phase plan fixes the real ones. R46 and R47 were added at F2; Din locked them with the plan. R50 was added, and R44 widened to the README and cards, at F6.

| #   | Rule                                                                                                                                                              | Source | Enforced by                                                                                | Layer    | Phase    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------ | -------- | -------- |
| R1  | A checksum mismatch stops the run                                                                                                                                 | B5     | download test with a corrupted file                                                        | L1       | 2        |
| R2  | The cache matches the pinned 132 checksums                                                                                                                        | B5     | every run's checksum step; `heartbeat verify`                                              | L2       | 2        |
| R3  | Paced records excluded; DS1 and DS2 lists match the manifest                                                                                                      | B1     | `splits.toml` schema and content test                                                      | L1       | 2        |
| R4  | MLII picked by name in any channel order                                                                                                                          | B1     | unit test with 114's layout; real-data test on 100 and 114                                 | L1, L2   | 2        |
| R5  | Bandpass is zero-phase, 0.5 to 40 Hz                                                                                                                              | B3     | phase and band test on synthetic sines                                                     | L1       | 2        |
| R6  | int16 rounding error at most 0.0025 mV                                                                                                                            | B3, D4 | property test                                                                              | L1       | 2        |
| R7  | Window is 96 before, 160 after the annotation                                                                                                                     | B3     | index test                                                                                 | L1       | 2        |
| R8  | RR features are causal except post-RR, by one beat                                                                                                                | B3     | hypothesis test changing beats further ahead                                               | L1       | 2        |
| R9  | RR uses every annotated beat, including Q                                                                                                                         | B3, B4 | unit test with a Q beat between two N beats                                                | L1       | 2        |
| R10 | Unknown annotation symbol fails loudly                                                                                                                            | B4     | unit test                                                                                  | L1       | 2        |
| R11 | Class counts match PhysioNet's table per record                                                                                                                   | B4     | real-data test over all 44 records                                                         | L2       | 2        |
| R12 | No subject on both sides of DS1 and DS2; 201 and 202 one subject                                                                                                  | B1, C1 | leakage test on subject IDs                                                                | L2       | 2        |
| R13 | No subject on both sides of any fold                                                                                                                              | C1     | leakage test on `folds.json`                                                               | L2       | 2        |
| R14 | `rebuild` checks folds and never regenerates them                                                                                                                 | C1, E4 | test that a changed `folds.json` fails `check-folds`                                       | L2       | 2        |
| R15 | Training and CV code cannot load DS2                                                                                                                              | C1     | loader test                                                                                | L2       | 2        |
| R16 | Metrics agree with scikit-learn                                                                                                                                   | C4     | unit tests on known cases                                                                  | L1       | 3        |
| R17 | Bootstrap resamples whole patients; CNN and baseline share draws                                                                                                  | C4     | unit tests                                                                                 | L1       | 3        |
| R18 | Draws with no predicted S are skipped for S precision only, and counted                                                                                           | C4     | unit test                                                                                  | L1       | 3        |
| R19 | Per-patient cells show counts; percentage only at 10 or more beats                                                                                                | C4     | unit test                                                                                  | L1       | 3        |
| R20 | Calibration never changes a label; logit adjustment; equal-mass ECE                                                                                               | C4     | unit tests                                                                                 | L1       | 3        |
| R21 | Baseline and CNN use the same folds, class weights and selection metric                                                                                           | C2, C3 | test that both read one fold file and one weight function                                  | L1       | 3        |
| R22 | Same seed on CPU gives identical weights                                                                                                                          | C6     | two short CPU runs compared                                                                | L1       | 4        |
| R23 | Training runs without crashing on real data                                                                                                                       | C7     | smoke run of a few CPU batches                                                             | L2       | 4        |
| R24 | The exhibit differs from the honest run only in the splitter                                                                                                      | C5     | test comparing the two resolved configs                                                    | L1       | 4        |
| R25 | ONNX model is one file, under 1 MB                                                                                                                                | E2, D5 | export test and size gate                                                                  | L3, GATE | 5        |
| R26 | PyTorch and Python ONNX Runtime agree within 1e-5, labels exact                                                                                                   | E5     | parity test on fixtures                                                                    | L3       | 5        |
| R27 | Parity fixtures come from DS1 only                                                                                                                                | E5     | test on fixture record IDs                                                                 | L3       | 5        |
| R28 | `rebuild` stops before DS2 without a freeze record                                                                                                                | E4     | test with no freeze record                                                                 | L2       | 5        |
| R29 | Browser ONNX Runtime agrees with Python within 1e-5, labels exact, in Chromium and WebKit                                                                         | E5     | Playwright parity test                                                                     | L3, L5   | 6        |
| R30 | TypeScript preprocessing matches Python step by step                                                                                                              | E5     | Vitest on fixtures (window, z-score with a synthetic flat window, RR, scaler, calibration) | L3, L4   | 6        |
| R31 | `manifest.json` matches the shipped files                                                                                                                         | D4     | build check                                                                                | L4       | 6        |
| R32 | Demo data is DS1-only until the sealed run is logged                                                                                                              | C1, E4 | `build-demo-data` test with no test log entry                                              | L2       | 6        |
| R33 | Fallback is labeled when WebAssembly is blocked                                                                                                                   | D3     | Playwright with WebAssembly disabled                                                       | L5       | 6        |
| R34 | Class colors at least 3:1 in light and dark                                                                                                                       | D6     | contrast unit test                                                                         | L4       | 6        |
| R35 | Axe at zero violations: full and embed, light and dark, reduced motion on and off                                                                                 | D6     | Playwright with axe                                                                        | L5       | 6        |
| R36 | Every control reachable and usable by keyboard                                                                                                                    | D6     | Playwright keyboard walk                                                                   | L5       | 6        |
| R37 | Theme messages accepted only from the dins.dev origin                                                                                                             | D6     | unit test                                                                                  | L4       | 6        |
| R38 | No main-thread task over 50 ms during playback                                                                                                                    | D5     | Playwright long-task observer                                                              | GATE     | 6        |
| R39 | Model under 1 MB, demo JS under 60 KB gzip, beats JSON under 100 KB per patient                                                                                   | D5     | build size gates                                                                           | GATE     | 6        |
| R40 | Headers carry `frame-ancestors` and `'wasm-unsafe-eval'`                                                                                                          | D1     | test on built headers                                                                      | L5       | 6        |
| R41 | `evaluate-test` refuses without a matching freeze record or on a dirty tree                                                                                       | C1, C6 | tests with a mismatched record and a dirty tree                                            | L2       | 5        |
| R42 | Sealed runs append to `test_runs.jsonl`; nothing is rewritten; reproductions are a separate entry type                                                            | C6, E4 | test on the log writer; `heartbeat verify` checks results against the log                  | L2       | 5        |
| R43 | The default patient rule picks record 200                                                                                                                         | D4     | test on the built DS2 manifest                                                             | L2       | 7        |
| R44 | Published text (built demo, case study draft, README, model and data cards) avoids D7's list and dash separators                                                  | D7, F6 | wording lint                                                                               | TX       | 1 onward |
| R45 | Dependencies respect the 14-day rule                                                                                                                              | E2     | uv and pnpm config; CI installs from frozen lockfiles                                      | GATE     | 1        |
| R46 | Third-party actions pinned to commit hashes                                                                                                                       | E6, F2 | a small workflow check that rejects tag references                                         | TX       | 1        |
| R47 | The freeze commit is on the public remote before the sealed run                                                                                                   | E6, F2 | `evaluate-test` refuses unless the freeze commit is on `origin/main`                       | L2       | 7        |
| R48 | One VoiceOver pass                                                                                                                                                | D6     | manual, recorded in the ledger                                                             | MAN      | 8        |
| R49 | Pre-registered plan unchanged, or changes logged before the gate                                                                                                  | A3     | Phase 7 gate checklist                                                                     | MAN      | 7        |
| R50 | Card numbers come from committed results: every generated block equals what `heartbeat cards` renders, and no test block is pending once the sealed run is logged | F6     | renderer unit tests; `heartbeat verify` check on the two cards                             | L1, L2   | 5        |
| R51 | The per-window z-score never divides by zero: a constant window gives zeros, any int16 window gives finite values                                                 | B3     | unit test plus hypothesis property test                                                    | L1       | 2        |

## 7. Review focus

Failure modes the requirements imply but no row above tests yet. Each gets a test in the named phase's task plan.

1. **An interrupted download** leaves a partial file in the cache. Expected: files are written to a temporary name and moved into place only after the checksum matches (Phase 2).
2. **MPS and CPU disagree enough to change selection.** Expected: the reproduction check reports it; Phase 4 records the MPS against CPU difference on one configuration in the ledger.
3. **Labeling falls behind playback at 4x speed** or on a slow phone. Expected: beats without a label yet show as pending, never as a wrong or missing class (Phase 6).
4. **Scrubbing to the very start or end** of a 30-minute recording. Expected: no out-of-range windows; the first and last beats are absent by design (B3) and the table says so (Phase 6).
5. **The iframe in a background tab** is throttled, then resumes. Expected: playback resumes at the right place and the counter stays correct (Phase 6).

## 8. Phase task plans

Added here when each phase starts (see section 1).
