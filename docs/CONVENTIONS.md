# Heartbeat: Conventions

|  |  |
| --- | --- |
| **Status** | Locked by Din (F4, 2026-10-27). Changes need Din's go and a ledger entry. |
| **Applies to** | All code, tests and docs in this repo. `AGENTS.md` holds the rigor rules and approvals; this file holds how code is written. |
| **Enforced by** | The tools in section 1 wherever possible. The rest is checked in review. |

Rule of thumb: if a tool can enforce it, the tool's config is the rule and this file only names the tool. What stays here is what no linter can see.

## 1. What the tools enforce

Configured in Phase 1; the settings below are the target, checked against the pinned tool versions when Phase 1 installs them.

| Area | Tool and setting |
| --- | --- |
| Python format | `ruff format`, default style (88 columns, double quotes) |
| Python lint | `ruff check` with `E`, `W`, `F`, `I`, `B`, `UP`, `SIM`, `C4`, `N`, `NPY`, `PT`, `PTH`, `RUF`, `T20`, `ERA`, and `D` with the Google convention. `T20` (no `print`) is off for `cli.py`; `D` is off for tests. |
| Python types | `mypy --strict` over `src/` and `tests/` |
| TypeScript types | `tsconfig`: `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`, `erasableSyntaxOnly`; `svelte-check` with zero warnings |
| TypeScript lint | ESLint with typescript-eslint `recommendedTypeChecked` and `stylisticTypeChecked`, plus `switch-exhaustiveness-check`; `eslint-plugin-svelte` recommended |
| Web format | Prettier defaults with `prettier-plugin-svelte` |
| Markdown | Prettier with `proseWrap: "never"` over every `.md` file (wide tables print compact, so editing one cell changes one line) |
| Writing | The wording lint (R44): D7's avoid list and dash separators |

Don't silence a rule inline without a short comment saying why (`# noqa: B008, reason`). A rule that keeps getting silenced is a conventions change: raise it.

## 2. Python

**Layout and style**

- Functions over classes unless there is state to hold. Pure functions for anything numeric, so they can be tested without data.
- Settings come from `config/default.toml`, read with `tomllib` into frozen dataclasses. The resolved config is written into each run folder (C6). No new config library.
- Values fixed by a planning decision live in one module as named constants, with the decision ID in a comment. Never repeat the literal elsewhere.

```python
# B3: window of 256 samples, 96 before the annotation and 160 after
WINDOW_BEFORE_SAMPLES = 96
WINDOW_AFTER_SAMPLES = 160
```

- Paths come from one module that resolves them from the repo root, using `pathlib`. No absolute paths, no `os.chdir`.
- Use `logging` in library code. Only `cli.py` prints.

**Names carry units.** Signal code mixes samples, seconds and millivolts, so every numeric name that has a unit says it: `_samples`, `_s`, `_ms`, `_hz`, `_mv`, `_adu` (raw int16 units, 200 per mV).

```python
rr_pre_s = (beat_samples[i] - beat_samples[i - 1]) / FS_HZ   # good
rr = beats[i] - beats[i - 1]                                # bad: samples or seconds?
```

**Arrays**

- Annotate with `numpy.typing.NDArray[np.float32]` (or the right dtype) and give the shape in the docstring, for example `(n_beats, 256)`. Check shapes and dtypes with explicit asserts where data crosses a module boundary.
- Dtypes are explicit: the trace is int16 at 200 units per mV (B3, D4), model inputs are float32. No silent upcasts to float64 on the model path.
- Standard deviation is the population one (`ddof=0`, NumPy's default) everywhere, because TypeScript must compute the same number (parity).

**Errors fail loudly.** Raise a specific exception with the record and beat in the message. No bare `except`, no `except Exception: pass`, no fallback value that hides missing data. An unknown annotation symbol is an error (B4).

**Writes are atomic.** Write to a temporary file in the same folder, then rename. A checksum check, where one exists, happens before the rename (review focus 1 in `docs/PLAN.md`).

**Comments** explain why, and cite the decision or requirement (`# C4: calibration never changes a label`). No commented-out code (`ERA`).

## 3. ML hygiene

The leakage types follow Kapoor and Narayanan's taxonomy (Patterns, 2023). Each line says how this repo blocks it.

| Leakage type | Here |
| --- | --- |
| No separate test set (L1.1) | DS2 sealed; only `evaluate-test` reads it (`AGENTS.md`, R15) |
| Preprocessing fitted on train and test (L1.2) | Anything fitted (RR feature scaler, class weights, temperature, logit adjustment) is fitted on the training part of each fold only. The filter and z-score are per record and per window, so they fit nothing. |
| Feature selection on all data (L1.3) | The features are fixed by B3 and C3; none is chosen from data |
| Train and test not independent (L3.2) | Splits and folds by subject; 201 and 202 are one subject (R12, R13) |
| Illegitimate features (L2) | Features use beat positions only, never a beat's label or a neighbour's label. Post-RR looks one beat ahead by design (B3) and is stated. |
| Temporal leakage (L3.1) | RR averages use only past beats (R8) |

**Fitted things have a fit step and an apply step.** A function that learns from data takes the training data explicitly and returns a fitted object; applying it is a separate call. Nothing fits on data passed in for evaluation.

```python
scaler = fit_rr_scaler(train_features)        # good: fitted on the fold's training part
x_val = apply_rr_scaler(scaler, val_features)

x_all = standardize(all_features)            # bad: statistics include validation beats
```

**Randomness**

- No global random state: no `np.random.seed`, no `np.random.<function>` (`NPY002`), no unseeded `random`.
- One master seed per run. Every stream (NumPy, PyTorch, augmentation, shuffling) is derived from it with `np.random.SeedSequence(master).spawn(...)`, and each `Generator` or `torch.Generator` is passed in as an argument. Never derive seeds as `seed + i`: NumPy's docs show it makes runs with nearby master seeds share streams.
- The fold file has its own seed (C1). scikit-learn splitters get an integer `random_state`, as its docs advise for comparable folds.
- Frozen models: `torch.use_deterministic_algorithms(True)`, CPU, `num_workers=0`, a seeded `generator` on the `DataLoader` (C6). MPS results are not expected to match CPU bit for bit (PyTorch's reproducibility notes); compare them within the stated tolerance.

**Runs and results**

- Every run writes its own folder under `runs/` (C6). Code reads results from run folders or `results/`, never from numbers typed into code.
- Figures are made by code from result files (matplotlib, SVG) and never edited by hand.
- No notebooks in the repo. Exploration happens in throwaway scripts on DS1; anything worth keeping becomes tested code.

## 4. TypeScript and Svelte

- Svelte 5 runes only: `$state` for reactive values, `$derived` for anything computed from them (never `$effect` to sync state), `$props`, `onclick` attributes. Shared state lives in classes with `$state` fields, not stores. Keyed `each` blocks with a real ID, never the index. These follow Svelte's own best-practices page.
- The trace renderer, preprocessing and the Worker protocol are plain TypeScript modules with no Svelte imports (D2), so Vitest covers them alone.
- No enums or namespaces (`erasableSyntaxOnly`): use string unions, for example `type BeatClass = "N" | "S" | "V" | "F"`, and switch on them exhaustively.
- Messages between the page, the Worker and the parent site are discriminated unions with a `type` field, validated where they arrive. Theme messages are accepted only from the dins.dev origin (R37).
- Names: files in kebab-case (`trace-renderer.ts`), Svelte components in PascalCase (`BeatTable.svelte`), variables in camelCase with units as in Python (`offsetSamples`, `durationMs`).
- Model inputs are `Float32Array`.

**Parity code mirrors Python.** Each preprocessing step in TypeScript has the same name as its Python twin (in camelCase), the same order of operations, and a parity test on the shared fixtures (R30). When the two disagree, fix the code; the 1e-5 tolerance does not move (`AGENTS.md`, rule 3).

## 5. Tests

- Layout: `tests/unit/` (L1, no data), `tests/data/` (L2, real data, pytest marker `realdata`), `tests/parity/` (L3). Web tests sit next to the code (`*.test.ts`); Playwright tests in `web/e2e/`.
- A test that enforces a row of the rule-to-test table carries its ID: `@pytest.mark.rule("R12")` in Python, and the title starts with `R29:` in Vitest and Playwright. A small check fails CI when a row in `docs/PLAN.md` section 6 (other than MAN rows) whose phase is at or below the current build phase has no test carrying its ID; later rows are listed as pending. The current phase is `[tool.heartbeat] current-phase` in `pyproject.toml`, bumped as the first commit of each phase. One test in any layer covers a row.
- Names say the behavior: `test_unknown_symbol_raises`, not `test_mapping_2`.
- Hypothesis runs with a fixed seed in CI (a settings profile), so a failure there is reproducible; locally it explores freely.
- Fixtures come from DS1 only (R27).

## 6. Git and docs

- Commit messages follow Conventional Commits, as on dins.dev: `type(scope): what changed`, with types `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`. Scopes are the package areas (`data`, `signal`, `models`, `train`, `evaluate`, `export`, `cli`), `web`, `ci` and `docs`. From Phase 1 on; planning commits stay as they are.
- Branches: `phase-N-<name>` (F2).
- Pull requests merge with a merge commit, never squash or rebase. Reason: run folders, the freeze record and R47 refer to commit hashes, and squashing or rebasing rewrites them, so the freeze commit would not be on `main`. This differs from dins.dev's squash-only rule on purpose.
- Task status in the build phases of `docs/TASKS.md` uses dins.dev's words: Planned, In progress, Implemented, Verified (checks passed), Accepted (Din tried it; only Din sets it), Blocked. Phase 0 rows keep their planning keys.
- Docs are Markdown formatted by Prettier. Requirement IDs, rule IDs (R1 to R52) and decision IDs (A1 to G4) are how docs and code point at each other; never renumber one.
