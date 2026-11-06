# Heartbeat

Heartbeat labels heartbeats in ECG recordings from the MIT-BIH Arrhythmia Database. A small 1D convolutional network is compared with a logistic-regression baseline, and both are scored on patients they never saw during training. The point of the project is the evaluation: the model was fixed before the test, the test ran once, and the result is reported the way the plan said it would be, whichever way it came out.

A browser demo runs the frozen model live at `https://heartbeat.dins.dev/`.

This is a research demo, not medical advice. The model has not been clinically validated and must not be used to make health decisions.

## Status

The model is frozen and the sealed test run is logged. The model card, the data card and the demo all report that run. What is left is the launch: the first production deploy of the demo, then the case study on dins.dev, which waits for that site to exist. `docs/TASKS.md` has the current state of every task.

This README quotes no test result, on purpose. The results live in one place each:

- [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md): the test report, calibration, development results and the leakage exhibit, in blocks generated from `results/`.
- [`docs/DATA_CARD.md`](docs/DATA_CARD.md): the records, the split, the counts and how beats are cut and labeled.
- [`results/test_runs.jsonl`](results/test_runs.jsonl): the append-only log of every run on the test set, and `results/test_runs/` for its reports.
- [`docs/case-study/`](docs/case-study/): the case study draft, whose numbers are filled in from those same files by a script.

## How it is evaluated

The records are split by patient into a training set (DS1) and a test set (DS2), following de Chazal et al. (2004), so no patient's beats appear on both sides. Record 202 is left out everywhere, because it comes from the same person as training record 201. Every model choice was made by cross-validation inside DS1, with folds grouped by patient. DS2 stayed sealed until one logged run, after a freeze record naming the commit, the config and the model checksums was committed and pushed.

The comparison rule was written before the test: the CNN is called better than the baseline only when the interval of the paired difference sits above zero. The full plan is in `docs/PRD.md` and `docs/PLAN.md`, and every decision and its reason is in `docs/WORK_LEDGER.md`.

## How to check the work

Needs Python 3.14 with uv, and Node 24 with pnpm 12.12.1.

```sh
uv sync --frozen                         # Python environment from uv.lock
pnpm -C web install --frozen-lockfile    # web toolchain from pnpm-lock.yaml
uv run heartbeat download                # the 132 pinned MIT-BIH files, by checksum
uv run heartbeat verify                  # manifests, folds, model files, parity, card blocks, the test log
uv run heartbeat check-folds             # the folds against their pin and the manifests
uv run pytest                            # every Python test, the real-data ones included
```

`heartbeat verify` takes seconds and trains nothing: it checks the committed model files and results against each other, and fails if a card block differs from what the results render.

To go further, `uv run heartbeat rebuild` reruns every stage from the raw files, retraining the models, and rewrites `results/`, `models/heartbeat-v1/` and the card blocks. It took about 104 minutes when measured on 2026-10-30, on a Mac with MPS for cross-validation.

From a fresh clone it takes longer, because the rebuild retrains twice and stops twice. On 2026-11-05 and 2026-11-06, on one Mac, the first pass took 121 minutes with other work running and stopped at `reproduce-test`, because that stage needs a clean tree and the pass had rewritten `results/`. After a commit, the second pass retrained everything (107 minutes) and stopped the same way, because the download stage's fingerprint changes once the raw files exist. After another commit, the third pass skipped training and ran the reproduction in 13 seconds. The results matched a second fresh clone apart from run names, commits, paths and wall times, the model files, fixtures and cards matched byte for byte, and the reproduction matched the sealed report. This has not been tried on another machine. The details are in `docs/WORK_LEDGER.md`.

## Running it

```sh
scripts/check.sh                                     # lint and unit tests, both toolchains
uv run heartbeat build-demo-data                     # the demo data into web/public/data
pnpm -C web run build                                # the demo, with its size gates
pnpm -C web exec playwright install chromium webkit  # once per machine
pnpm -C web run e2e                                  # browser tests
uv run heartbeat --help                              # every subcommand
```

`AGENTS.md` lists every command with how long it takes.

## License

The code and the model weights are MIT (`LICENSE`). The MIT-BIH Arrhythmia Database is under ODC-By 1.0, and the code license does not cover the data or anything derived from it. See `DATA_LICENSE.md` and `models/heartbeat-v1/NOTICE`.

## Citations

- Moody, G., & Mark, R. (2005). MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet. RRID:SCR_007345. https://doi.org/10.13026/C2F305
- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Eng in Med and Biol 20(3):45-50 (May-June 2001). PMID: 11446209.
- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. Nature Health. https://doi.org/10.1038/s44360-026-00096-z. Available from: https://pmc.ncbi.nlm.nih.gov/articles/PMC13641116/
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat interval features. IEEE Transactions on Biomedical Engineering 51(7):1196-1206 (2004).
- AAMI EC57, the standard that groups beat annotations into the classes used here.
