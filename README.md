# Heartbeat

Heartbeat labels heartbeats in ECG recordings from the MIT-BIH Arrhythmia Database. A small 1D convolutional network is compared with a logistic-regression baseline, and both are scored on patients they never saw during training. A browser demo will run the model live at `heartbeat.dins.dev`.

This is a research demo, not medical advice.

## Status

In development: Phase 1 (skeleton and CI). There are no results yet. Numbers appear in this README, the demo and the model card only once a committed run produces them, from files in `results/`.

## How it is evaluated

The records are split by patient into a training set (DS1) and a test set (DS2), following de Chazal et al. (2004), so no patient's beats appear on both sides. DS2 stays sealed until one logged run near the end of the project. Every model choice is made by cross-validation inside DS1, with folds grouped by patient. The full plan is in `docs/PRD.md` and `docs/PLAN.md`.

## Running it

Needs Python 3.14 with uv, and Node 24 with pnpm 12.12.1.

```sh
uv sync --frozen                         # Python environment from uv.lock
pnpm -C web install --frozen-lockfile    # web toolchain from pnpm-lock.yaml
scripts/check.sh                         # lint and unit tests, both toolchains
```

Other commands that work today:

```sh
uv run pytest                                     # every Python test
uv run python -m heartbeat.checks.wording         # the wording lint
uv run python -m heartbeat.checks.rule_coverage   # rule-to-test coverage
uv run python -m heartbeat.checks.repo_config     # 14-day rule and action pins
uv run heartbeat --help                           # subcommands, stubs until built
pnpm -C web run build                             # the placeholder page
pnpm -C web exec playwright install chromium webkit
pnpm -C web run e2e                               # browser tests
```

## License

The code and the model weights are MIT (`LICENSE`). The MIT-BIH Arrhythmia Database is under ODC-By 1.0, and the code license does not cover the data or anything derived from it. See `DATA_LICENSE.md`.

## Citations

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Engineering in Medicine and Biology 20(3):45-50 (2001).
- Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005). https://doi.org/10.13026/C2F305
- Pollard T, et al. PhysioNet as a global platform for biomedical research. Nature Health (2026). https://doi.org/10.1038/s44360-026-00096-z
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat interval features. IEEE Transactions on Biomedical Engineering 51(7):1196-1206 (2004).
- AAMI EC57, the standard that groups beat annotations into the classes used here.
