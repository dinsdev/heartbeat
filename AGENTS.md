# Heartbeat

A heartbeat classifier trained on the MIT-BIH Arrhythmia Database: a small 1D CNN against a logistic-regression baseline, evaluated on patients the model never saw, with a browser demo at `heartbeat.dins.dev` and a case study on dins.dev. Din's global working agreements (`~/.agents/AGENTS.md`) apply. This file adds what is specific to this project.

**Rigor leads.** The project exists to show an honest evaluation. When a rigor rule below conflicts with speed, polish or a better-looking number, the rule wins. If you can't keep a rule, stop and tell Din.

## Read first

- `docs/TASKS.md`: current phase and the next task. Check it at the start of every session; status is never recorded in this file.
- `docs/PLAN.md`: phases, exit criteria, the rule-to-test table (section 6), and the task-level plan for the current phase (section 8).
- `docs/PRD.md`: requirements with IDs (for example `EVAL-05`). Cite the ID when code implements one.
- `docs/WORK_LEDGER.md`: every decision with its reason, plus verification results. Search it before reopening a question.
- `docs/CONVENTIONS.md`: Python and TypeScript conventions (F4, not written yet).

Locked decisions stay locked. Changing one needs Din's go and a dated ledger entry. If the work and the docs disagree, say so; never quietly edit a requirement to match the code.

## Commands

Working today (Phase 4):

| What | Command |
| --- | --- |
| Install (Python) | `uv sync --frozen` |
| Install (web) | `pnpm -C web install --frozen-lockfile` |
| Playwright browsers, once per machine | `pnpm -C web exec playwright install chromium webkit` |
| Lint and unit tests, both toolchains, under 2 minutes (about 10 s warm); run before every commit | `scripts/check.sh` |
| Every Python test (includes the guard hook tests and the real-data tests, which need the download) | `uv run pytest` |
| One Python test | `uv run pytest tests/unit/test_wording.py::test_repo_is_clean` |
| Python lint, format, types | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |
| Wording lint (R44); `--root DIR` and paths check other files | `uv run python -m heartbeat.checks.wording` |
| Rule-to-test coverage, with pending rows | `uv run python -m heartbeat.checks.rule_coverage` |
| 14-day rule and action pins (R45, R46) | `uv run python -m heartbeat.checks.repo_config` |
| Download and checksum the 132 pinned MIT-BIH files (about 82 MB, about 70 s the first time; skips matching files after) | `uv run heartbeat download` |
| Prepare DS1 into `data/prepared/` with the floor-hit report (about 1.5 s) | `uv run heartbeat prepare` |
| Check `config/folds.json` against its pin and the manifests | `uv run heartbeat check-folds` |
| Rebuild the built stages (download, prepare, check-folds, cross-validate, cross-validate-cnn, select, exhibit, train-final), skipping unchanged ones, into the six `results/` files; run it in the background. Measured 108 minutes on 2026-10-30 when every training stage reran (cross-validate 5 s, cross-validate-cnn 74 min on MPS, select 1 s, exhibit 20 min, train-final 15 min on CPU); about 6 s when only the baseline reruns | `uv run heartbeat rebuild` |
| Rerun from one stage | `uv run heartbeat rebuild --from <stage>` |
| Baseline cross-validation into a new run folder under `runs/`, never `results/` (about 5 s) | `uv run heartbeat cross-validate --model baseline` |
| CNN cross-validation of one width and seed into a run folder (all five folds on MPS: about 5 min at width 0.5, 7 min at width 1, 13 min at width 2); `--fold N` trains one fold (width 1 measured 69 to 78 s on MPS, 19 min with `--device cpu`) | `uv run heartbeat cross-validate --model cnn --width 1 --seed 0 [--fold 0] [--device cpu]` |
| Select width and epoch count from the CV run folders into a new run folder (about 2 s; needs the `cross-validate-cnn` runs) | `uv run heartbeat select` |
| The leakage exhibit into run folders (about 20 min on MPS, measured as a rebuild stage) | `uv run heartbeat exhibit` |
| Three final models on CPU into run folders (about 5 min each at width 1 for 10 epochs, measured as a rebuild stage) | `uv run heartbeat train-final` |
| Real-data tests only (layer L2, needs the download) | `uv run pytest -m realdata` |
| Make the folds: done once by Din on 2026-10-29 and never run again (C1; F5 denies it to Claude) | `uv run heartbeat make-folds` |
| Subcommands of later phases (stubs that exit 2 and name their phase) | `uv run heartbeat --help` |
| Web lint, format (web files and every Markdown file), types, unit tests | `pnpm -C web run lint`, `pnpm -C web run format:check`, `pnpm -C web run check`, `pnpm -C web run test` |
| One Vitest file | `pnpm -C web exec vitest run <file>` |
| Web build | `pnpm -C web run build` |
| Browser tests on the built page, Chromium and WebKit | `pnpm -C web run e2e` |
| One Playwright file | `pnpm -C web exec playwright test <file>` |

Arriving in their phases (stubs today):

| What | Command | Phase |
| --- | --- | --- |
| Quick integrity check: manifests, checksums, frozen-model parity, results against the test log | `uv run heartbeat verify` | 5 |
| Rebuild every artifact, through `export` (cached stages, about 2 hours from scratch) | `uv run heartbeat rebuild` | 5 |
| Web build with demo data from the rebuild | `pnpm -C web run build` | 6 |

Python tools: ruff, mypy, pytest with hypothesis. Web tools: ESLint, Prettier, svelte-check, Vitest, Playwright (Chromium and WebKit). CI (`.github/workflows/ci.yml`) runs all of them on every push and pull request, in a `python` job (which caches and downloads the MIT-BIH files first) and a `web` job; `scripts/check.sh` skips the real-data tests, the build and Playwright.

Long jobs: CNN cross-validation takes about 74 minutes on MPS, the exhibit about 20 minutes, `train-final` about 15 minutes on CPU at the selected width 1 and 10 epochs (all measured 2026-10-30), `rebuild --exact` about 15 hours (a guess). Run long jobs in the background and say how long they should take.

## Layout

- `src/heartbeat/`: the Python package (`data/`, `signal/`, `models/`, `train/`, `evaluate/`, `export/`, `cli.py`).
- `web/`: the Svelte demo. `web/vendor/brand/` is copied from dins.dev; change it there, not here.
- `manifests/`: pinned inputs (checksums, subjects, splits). Reviewed like code.
- `config/`: `default.toml` settings and `folds.json`.
- `models/heartbeat-v1/`: the frozen model, written only by `heartbeat export`.
- `results/`: committed metrics and figures, written only by `rebuild`. `results/test_runs.jsonl` is the sealed-run log.
- `fixtures/parity/`: shared Python and web parity fixtures, DS1 beats only.
- Gitignored, never commit: `data/`, `runs/`, `web/public/data/`.

## Rigor rules

Code enforces most of these (the rule-to-test table names each test). Don't look for ways around a check that blocks you; ask Din.

1. **DS2 is sealed.** DS2 is the test set: records 100, 103, 105, 111, 113, 117, 121, 123, 200, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234 (source of truth: `manifests/splits.toml`). Record 202 is excluded everywhere (201/202 leak), as are the paced records 102, 104, 107 and 217. Nothing you write or run may train, tune, select, calibrate, debug or plot on DS2 signals, labels or predictions. Allowed: downloading and checksumming DS2 files, and the tests that check class counts and subject leakage. Only `heartbeat evaluate-test` evaluates on DS2, and only Din starts it. Demo data is DS1 only until the sealed run is logged. If you see DS2 output by accident, stop and tell Din; it gets a ledger entry.
2. **No number without a run.** Every metric in docs, commit messages, UI text or the case study comes from a committed `results/` file or a named run folder, and you say which. Say whether a number is out-of-fold or test, MPS or CPU. Label estimates as guesses.
3. **Tests are the spec.** Never weaken, skip, delete or special-case a test, a tolerance (1e-5, labels exact), a size gate or a threshold to get to green, and never hard-code expected outputs into code. If a test looks wrong, stop and explain why; changing it is Din's call and gets a ledger entry.
4. **Folds, splits and checksums are rigor events.** `config/folds.json` is written only by `heartbeat make-folds`, and `rebuild` only checks it. Changes to `manifests/` or the folds need Din's go and a ledger entry. A learning-rate change is not a rigor event.
5. **Results come from code.** `results/` is written by `rebuild`, never by hand. `results/test_runs.jsonl` is append-only. No silent reruns: a rerun after a bug fix is logged next to the first run.
6. **The pre-registered plan holds.** A3, C4, C5 and C8 in the ledger (PRD section 8.2) change only with Din's go and a dated ledger entry made before the Phase 7 gate.
7. **Determinism.** Seeds derive from one master seed per run. Frozen models train on CPU in PyTorch deterministic mode with `num_workers=0`. Don't change a seed to make a result or a flaky test go away.

## Dependencies

- Pins follow the 14-day rule: newest stable release at least 14 days old, enforced by uv `exclude-newer = "14 days"` and pnpm `minimumReleaseAge`, both rolling. Never bypass either.
- ONNX Runtime is the same version in Python and the browser (1.30.0). TypeScript stays on 6.0.3 (7 breaks svelte-check). pnpm `allowBuilds` covers esbuild and workerd only.
- A new dependency needs a one-line reason in the commit. Upgrading a pin or changing the `exclude-newer` span needs Din's go and a ledger entry.

## Testing and done

- Work test first. For a row in the rule-to-test table, write the test before the code it checks.
- A phase is done when its rule-to-test rows pass in CI, not when the code exists.
- When you report work, give the command you ran and its result. Keep the states apart: implemented (code exists), verified (checks passed, say which), accepted (Din tried it; only Din sets this).

## Git and approvals

- Commit locally at each working checkpoint; no approval needed. After Phase 0, work on a branch per phase (`phase-N-<name>`). No attribution trailers such as `Co-Authored-By` in commits or pull requests.
- Stop and ask Din before:
  - creating the remote, any push, opening or merging a pull request, any deploy;
  - anything involving the Cloudflare token or a GitHub secret (Din handles the values, never you);
  - writing the freeze record or running `evaluate-test`;
  - `rebuild --exact` (about 15 hours of the Mac);
  - starting a stretch item (INCART, saliency, QRS detector);
  - changing a locked decision, the pre-registered plan, `manifests/` or the folds;
  - downloading anything other than the pinned MIT-BIH files;
  - adding a paid service, or deleting anything unrelated to the task.

## Writing

- In docs, UI text, comments and commit messages: no em dashes, no en dashes as separators, no AI-tell buzzwords (elevate, seamless, unleash, journey, tapestry, "not just X but Y"). Use periods, commas, colons or parentheses. Refer to Din by name.
- Public text (demo, case study, README, model and data cards) also avoids D7's list: "diagnose", "diagnosis", "detects arrhythmia", "detects heart disease", "clinical-grade", "accurate" as a headline, "AI doctor". Say "labels heartbeats", "flags irregular beats", "on patients it never saw". The wording lint checks both.
- Ledger entries are dated and say what was decided, why, and what was verified and how.
