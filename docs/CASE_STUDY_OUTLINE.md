# Heartbeat case study outline (G1)

Written in Phase 7 before the freeze (settling 5, design call 8), so it is on `origin/main` before any DS2 result exists. It fixes the case study's fields, its sections in order and the headline sentence for each EVAL-10 outcome. It holds no result: every number is a slot naming the file and key it comes from, filled in Phase 7 Goal B or Phase 8 from committed files only (rigor rule 2). Din writes the prose; the draft lines below are in Din's voice for Din to change.

## Slots

A slot reads `{{source: key}}`. The sources:

| Source | File | What it is |
| --- | --- | --- |
| `sealed` | The report the last `"type": "sealed"` entry in `results/test_runs.jsonl` names (`results/test_runs/<id>-sealed.json`), never a reproduction report | Test numbers on DS2, CPU |
| `log` | That entry in `results/test_runs.jsonl` | When the sealed run happened |
| `freeze` | `models/heartbeat-v1/freeze.json` | The commit and date the model was fixed |
| `exhibit` | `results/exhibit.json`; a row is picked by its `side` (`patient` or `beat`) and `model` (`cnn` or `baseline`) | DS1 out-of-fold numbers; the CNN rows on MPS, the baseline rows on CPU |
| `data` | `results/data_summary.json` | Counts of records, patients and beats |
| `selection` | `results/selection.json` | The width and epoch count chosen on DS1 cross-validation |

An interval is three slots: `point`, `low` and `high` under the same key, from a patient bootstrap with `{{sealed: bootstrap.draws}}` draws and percentiles `{{sealed: bootstrap.percentiles}}`. Wherever a number appears, the page says whether it is a test number (DS2) or out-of-fold (DS1). Record numbers such as 200, 201 and 202 are names, not results. Rounding is Din's call in the prose; the same rounding applies everywhere on the page.

## Fields of the dins.dev `projects` collection

From the zod schema in `~/Develop/dins.dev/docs/site/plans/M1-pages.md` (Task 3, `makeProjectSchema`), read and not edited.

| Field | Rule | Draft |
| --- | --- | --- |
| `title` | 1 to 80 characters | Heartbeat |
| `kind` | `ml`, `data-engineering`, `data-science` or `research` | `ml` |
| `summary` | 1 to 200 characters | A small neural network that labels heartbeats from one ECG lead, tested once on patients it never saw, beside a simple baseline and the leak a random beat split hides. |
| `role` | 1 to 300 characters | Everything, alone: the question, the pre-registered plan, the data pipeline, both models, the evaluation, the browser demo and this write-up. |
| `stack` | one or more names | Python, PyTorch, scikit-learn, ONNX Runtime (Python and browser), WFDB, Svelte, Cloudflare Workers |
| `results` | one or more `{value, label}` pairs | See below |
| `featured` | 1 to 4, optional | Din's call |
| `demo` | `{type, src}`, optional | `type: live`, `src` the Heartbeat demo. The schema takes a site path today; PUB-08 hands dins.dev an allowlist for `https://heartbeat.dins.dev` (open on the dins.dev side, assumption AS6) |
| `capture` | image, 16:10 | A still of record 200 from the DS2 demo, recorded in Phase 8 with the stage video |
| `captureAlt` | 1 character or more | An ECG trace of record 200 scrolling, each beat marked with the model's letter, irregular beats in color |
| `repo` | https link, optional | https://github.com/dinsdev/heartbeat |
| `status` | `draft` or `published` | `draft` until Din publishes |

`results`, three pairs, all from committed files:

1. `value`: `{{sealed: headline.intervals.cnn.macro_f1_nsv.point}}` (`{{sealed: headline.intervals.cnn.macro_f1_nsv.low}}` to `{{sealed: headline.intervals.cnn.macro_f1_nsv.high}}`). `label`: Macro F1 over N, S and V on `{{sealed: patients}}` (its length) patients it never saw.
2. `value`: `{{exhibit: rows[side=beat, model=cnn].metrics.macro_f1_nsv.point}}` against `{{exhibit: rows[side=patient, model=cnn].metrics.macro_f1_nsv.point}}`. `label`: The same model inside DS1, beats split at random against patients kept apart (out-of-fold).
3. `value`: `{{sealed: comparison.metrics.macro_f1_nsv.point}}` (`{{sealed: comparison.metrics.macro_f1_nsv.low}}` to `{{sealed: comparison.metrics.macro_f1_nsv.high}}`). `label`: The CNN minus the baseline on the same draws, in the words of the headline sentence below.

## The page, in order

1. **Header.** Eyebrow, `title` and `summary`, from the fields above.
2. **The live demo.** The `?embed=page` iframe, `loading="lazy"`, with a `title` (PUB-08). It opens on record 200 and shows DEMO-09's line, that the record was picked before testing because it has many irregular beats.
3. **Summary block.** `role`, `stack` and `results`, rendered by the site.
4. **The question.** One short paragraph: a model that labels heartbeats is only useful on people it has not seen, so the test keeps patients apart and is run once.
5. **The trap, shown.** The leakage exhibit (G2, C5): two rows, the same CNN and the same `{{exhibit: patients}}` (its length) DS1 patients, beats split at random (`{{exhibit: rows[side=beat, model=cnn].metrics.macro_f1_nsv.point}}`) beside patients kept apart (`{{exhibit: rows[side=patient, model=cnn].metrics.macro_f1_nsv.point}}`), both with intervals, out-of-fold. One sentence of explanation. Accuracy appears here only (`{{exhibit: rows[side=beat, model=cnn].accuracy.point}}`, EXHIBIT-03), as the number papers often lead with. Credit de Chazal's Table VI as the precedent (PUB-03).
6. **The test.** The model was fixed at commit `{{freeze: commit}}` on `{{freeze: date}}`, and the test ran once, on `{{log: date}}`. The DS2 headline with intervals: macro F1 over N, S and V (`{{sealed: headline.intervals.cnn.macro_f1_nsv}}`), S recall and precision (`{{sealed: headline.intervals.cnn.S_recall}}`, `{{sealed: headline.intervals.cnn.S_precision}}`), V recall and precision (`{{sealed: headline.intervals.cnn.V_recall}}`, `{{sealed: headline.intervals.cnn.V_precision}}`), on `{{sealed: beats.scored}}` scored beats. The baseline's line beside it (`{{sealed: headline.intervals.baseline}}`). The seed range of the other two final models (`{{sealed: seed_range.range}}`).
7. **The CNN against the baseline.** The one headline sentence that `{{sealed: comparison.metrics.macro_f1_nsv.verdict}}` picks, from the three below, unchanged apart from its slots.
8. **Patient by patient.** The per-patient table (`{{sealed: per_patient}}`), the S line without record 232 (`{{sealed: s_without_excluded}}`, EVAL-08), and the F caveat (`{{sealed: n_and_f.caveat}}`).
9. **The 201 and 202 leak.** Records 201 and 202 come from the same person, so 202 is left out everywhere and the patient sits only in DS1 (B1).
10. **Limits.** In plain words (PUB-02, G5): beat locations come from the expert annotations, so these numbers assume every beat has already been found; F is one patient on each side; record 232 drives the S result; calibrated probabilities are fragile across patients (`{{sealed: calibration}}`); a label shows one beat late; the model reads one lead and was tested on `{{sealed: patients}}` (its length) patients; Q beats are not scored (`{{sealed: beats.q_not_scored}}`).
11. **How to check it.** The pre-registered plan, the freeze record, the append-only test log, the leakage tests in CI and the parity tests, all in the repo. `uv run heartbeat verify` checks them in minutes; `uv run heartbeat rebuild` reproduces the rest.
12. **Credits.** The MIT-BIH Arrhythmia Database (Moody and Mark) through PhysioNet, de Chazal and colleagues for the DS1 and DS2 split and Table VI, and the AAMI EC57 classes.

## The headline sentence, one per EVAL-10 outcome

Written now, before the result. The page uses the one whose name equals `{{sealed: comparison.metrics.macro_f1_nsv.verdict}}`. In each, `{{n}}` is `{{sealed: patients}}` (its length) and the three numbers are `{{sealed: comparison.metrics.macro_f1_nsv.point}}`, `.low` and `.high`.

**CNN better than baseline.** On `{{n}}` patients it never saw, the CNN beat the logistic-regression baseline: its macro F1 over N, S and V was higher by `{{point}}`, with an interval from `{{low}}` to `{{high}}` that sits above zero.

**no clear difference.** On `{{n}}` patients it never saw, the CNN and the logistic-regression baseline show no clear difference: the CNN's macro F1 over N, S and V minus the baseline's is `{{point}}`, with an interval from `{{low}}` to `{{high}}` that includes zero. The CNN still ships, as the plan said before the test.

**baseline better than CNN.** On `{{n}}` patients it never saw, the logistic-regression baseline beat the CNN: the CNN's macro F1 over N, S and V minus the baseline's is `{{point}}`, with an interval from `{{low}}` to `{{high}}` that sits below zero. The CNN still ships, as the plan said before the test, and the simpler model did better here.

## The home stage line (G1)

The stage video's one plain line, for Din to settle with the summary wording (Q6): "Labels each heartbeat of a real ECG. Tested on patients it never saw."
