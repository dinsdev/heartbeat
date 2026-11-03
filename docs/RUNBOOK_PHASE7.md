# Phase 7 runbook: the freeze and the sealed run

For Din. Settling 6's five steps with exact commands and the output to expect, run in the main checkout (`~/Develop/heartbeat`) on `main`. Claude cannot run steps 2, 3 or the pushes (the guard denies them), so every step here is Din's. Nothing else lands on `main` from step 2 to step 5: no merge, no doc fix, no other push. If any output differs from what is written here, stop and bring it to a Claude session before going on.

## Step 0: before you start

Goal A's pull request is merged, and CI on the merge commit is green (Phase 7 gate, item 1):

```bash
gh run list --branch main --limit 1
```

Expected: the newest row is `CI` for the merge commit, `completed`, `success`.

## Step 1: a clean, checked tree

```bash
git switch main
```

```bash
git pull
```

```bash
git status --short
```

Expected: no output (gate item 4).

```bash
uv run heartbeat verify
```

Expected, last line: `heartbeat verify: 6 of 6 checks passed`.

```bash
uv run heartbeat check-folds
```

Expected: `heartbeat check-folds: ok, 22 subjects in 5 folds, /Users/din/Develop/heartbeat/config/folds.json matches its pin`.

## Step 2: the freeze record, committed and pushed (R47)

```bash
uv run heartbeat export --freeze
```

Expected: `heartbeat export --freeze: wrote /Users/din/Develop/heartbeat/models/heartbeat-v1/freeze.json; commit it and push`. It refuses a dirty tree, an existing record, or model files that differ from `results/export.json`; a refusal writes nothing.

```bash
git status --short
```

Expected: one line, `?? models/heartbeat-v1/freeze.json`.

```bash
git add models/heartbeat-v1/freeze.json
```

```bash
git commit -m "chore(freeze): freeze heartbeat-v1 before the sealed run"
```

```bash
git push
```

```bash
git fetch
```

```bash
git status
```

Expected: `Your branch is up to date with 'origin/main'` and `nothing to commit, working tree clean`. The freeze record changes no card block (R50), so `uv run heartbeat cards` would print `unchanged` for both cards here.

## Step 3: the sealed run, once

```bash
caffeinate -ims uv run heartbeat evaluate-test
```

It prints nothing until it ends. Expected, one line: `heartbeat evaluate-test: logged run 1 (sealed) in /Users/din/Develop/heartbeat/results/test_runs.jsonl; report results/test_runs/1-sealed.json`.

**Time (a guess until measured):** under a minute. The DS1 rehearsal, which runs the same `run_sealed` on the 22 DS1 records with the 10,000-draw bootstrap and then builds and checks the demo data, took 12.9 s in the test (16.0 s wall, `tests/data/test_demo_ds2_rehearsal_real.py`, 2026-11-02). DS2 has 21 records.

**If it refuses** (a line starting `heartbeat evaluate-test:` that names the freeze, the gate or the log, exit 1): the gate runs before any record is read, so no DS2 data was opened. Nothing was logged. Bring the message to a Claude session; do not edit anything to get past it.

## Step 4: render the cards (R50)

```bash
uv run heartbeat cards
```

Expected, two lines: `heartbeat cards: MODEL_CARD.md:` followed by the nine test blocks (`test_headline`, `test_comparison`, `test_fpr`, `test_s_without_232`, `test_per_patient`, `test_confusion`, `test_n_f`, `test_seed_range`, `test_calibration`), and `heartbeat cards: DATA_CARD.md: unchanged`.

## Step 5: commit the log, the report and the cards, and push right away (OPS-07)

```bash
git status --short
```

Expected: exactly these three lines, and nothing else: ` M docs/MODEL_CARD.md`, `?? results/test_runs.jsonl`, `?? results/test_runs/` (the log and its folder are new with the first entry).

```bash
git add results/test_runs.jsonl results/test_runs docs/MODEL_CARD.md
```

```bash
git commit -m "chore(results): the sealed run on DS2, logged, with the rendered model card"
```

```bash
git push
```

Goal B starts from this commit, on a new branch `phase-7-sealed`.

## If `evaluate-test` fails partway (settling 8)

`run_sealed` checks the gate, prepares DS2 in memory, scores, builds the report, writes the report file, then appends the log line. Which case applies depends on whether any DS2 number exists anywhere: on disk (a new file under `results/test_runs/`, a new line in `results/test_runs.jsonl`) or on screen (including inside a traceback or an error message).

**Case 1: a DS2 number was written or shown.** It counts as a sealed run (A3). Stop; do not rerun. Write a ledger entry for the run (and keep its log entry, if it got that far), then bring it to a Claude session: the fix lands through a pull request, the rerun is logged, and both runs stay on record. Reading (Claude's, for Din to confirm): the rerun needs a new freeze, made the same way as in case 2, because the sealed gate refuses any change since the freeze commit besides the record; settling 8 does not spell out these mechanics for case 1.

**Case 2: the run crashed before any DS2 number existed.** It is not a run. Record the traceback in the ledger, with no numbers. The fix goes through a pull request. A commit with its own ledger entry removes `models/heartbeat-v1/freeze.json`. Then freeze again from step 1. Only code may change; the model files may not.

## What to send Goal B

The step 5 commit hash, confirmation that it is on `origin/main`, the output lines of steps 2 to 5 as printed, how long step 3 took, and anything that differed from this runbook.
