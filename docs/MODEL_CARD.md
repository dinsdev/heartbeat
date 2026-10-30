# Heartbeat model card: heartbeat-v1

|  |  |
| --- | --- |
| **Status** | Template (F6, locked by Din 2026-10-27). Committed and pushed before any result exists, so the layout of every table below is part of the pre-registered plan. |
| **Model** | `models/heartbeat-v1/` (written only by `heartbeat export`) |
| **Requirements** | PUB-04 (this card), EVAL-08 to EVAL-12, EXHIBIT-01 to EXHIBIT-03, PUB-02, PUB-03 |
| **Related** | `docs/DATA_CARD.md` (the data), `docs/PRD.md`, `docs/WORK_LEDGER.md` |

The layout follows Mitchell et al., "Model Cards for Model Reporting" (FAT\* 2019), section by section.

## How the numbers get here

Every count and metric in this card sits in a generated block between `<!-- card:begin NAME -->` and `<!-- card:end NAME -->`. `heartbeat cards` renders each block from committed `results/` files, and `heartbeat verify` fails if any block differs from what the current results would render (R50). Each rendered block names its source file and says whether its numbers are out-of-fold (DS1) or test (DS2), and MPS or CPU. The prose around the blocks is written by hand and holds definitions only, never a result.

A block that reads "Pending" has no run behind it yet. DS1 blocks fill in during development; DS2 blocks stay pending until the sealed run is logged (Phase 7). Any section or table added after the sealed run is listed in the change log at the end, so a reader can tell the pre-registered report from later additions.

## 1. Model details

- **Developed by:** Din (Dinesh Dawonauth), working with Claude. Questions and corrections: issues on `dinsdev/heartbeat`.
- **Version:** heartbeat-v1, the CNN trained with seed 0 (MODEL-05). Seeds 1 and 2 are trained and tested the same way and reported as a range.
- **Type:** a small 1D convolutional network that labels one heartbeat at a time as N, S, V or F (AAMI EC57 classes).
- **Inputs:** a 256-sample window of the filtered MLII signal (96 samples before the beat annotation, 160 after), z-scored per window, plus six RR interval features (pre-RR, post-RR, local and long average RR, and two ratios, the ratios on a log scale), standardized with a scaler fitted on the training data. Details in `docs/DATA_CARD.md`.
- **Architecture (MODEL-02):** four blocks of Conv1d (kernel 7), batch norm, ReLU and max-pool by 2; global average pooling; the six RR features concatenated; a 64-unit layer with dropout 0.3; four outputs.
- **Training (MODEL-03, MODEL-06):** cross-entropy with balanced class weights; fixed augmentation (time shift up to 5 samples each way, light Gaussian noise); AdamW at a constant learning rate of 1e-3, weight decay 1e-4, batch 256; no early stopping. The frozen model trains on all of DS1 on CPU in PyTorch deterministic mode.
- **Selection (MODEL-04):** width multiplier (0.5, 1 or 2) and epoch count chosen on the five patient-grouped DS1 folds by the seed mean of pooled out-of-fold macro F1 over N, S and V (four-class reported beside it).
- **Outputs:** a label (argmax of the weighted model) and a calibrated probability per class (logit adjustment, then one temperature fitted on DS1 out-of-fold predictions). Calibration never changes a label (EVAL-11).
- **Format:** one ONNX file (opset 20, batch norm folded), with the scaler and calibration as JSON and the freeze record, all under `models/heartbeat-v1/`. The same file runs in Python and in the browser with ONNX Runtime 1.30.0.
- **Baseline:** multinomial logistic regression on the six RR features only (MODEL-01), tuned on the same folds with the same budget and reported beside the CNN everywhere. It does not ship to the browser.
- **License:** the code is MIT (`LICENSE`). The training data is the MIT-BIH Arrhythmia Database under ODC-By 1.0 (`DATA_LICENSE.md`), which requires attribution. The model weights are MIT, like the code. They were trained on that database, so `models/heartbeat-v1/NOTICE` carries the ODC-By 1.0 notice (section 4.3) and ships with the model.

<!-- card:begin model_details -->

Source: `results/selection.json` and `results/export.json` (width and epochs chosen on DS1 out-of-fold, MPS; frozen models, CPU).

- Width multiplier 1, 10 epochs.
- Parameters: 52036 (PyTorch, before batch-norm folding).
- ONNX opset 20, one file per seed, each under 1000000 bytes:
  - Seed 0 (shipped), `model.onnx`: 235466 bytes, SHA256 `b0292e6c4763b0bf6e70976aa9ddc754c70dc8c8eabd329576c9fa3ea5025e5f`.
  - Seed 1, `seeds/seed-1/model.onnx`: 235466 bytes, SHA256 `e152852e78b5418184146a40dbf6c43450926dad033fcb0347e5411d6f2a8d24`.
  - Seed 2, `seeds/seed-2/model.onnx`: 235466 bytes, SHA256 `783ca6f59fa225ab06b8594faf491fb8e76df33637265404b6ebe5d8509e1312`.
- Baseline, `baseline.json`: SHA256 `782d65c5e4df60bf2ee9e5b2dd9abb818f5e7a2fc61f9dd131f044490025e2a3`.
- Freeze commit and date: Pending (Phase 7).

<!-- card:end model_details -->

## 2. Intended use

**Primary use:** a research demo of how to evaluate a heartbeat classifier honestly, on patients it never saw. It labels heartbeats in recordings from a public research database, in the browser demo at `heartbeat.dins.dev` and in the dins.dev case study.

**Primary users:** readers of the case study, and engineers or reviewers checking the method, the split and the numbers.

**Out of scope:**

- Any health decision, for anyone. The model has not been clinically validated.
- ECGs from people, devices or leads outside the MIT-BIH Arrhythmia Database. The demo accepts no uploads and no live input.
- Finding beats. The model only labels beats whose positions are given; it was trained and tested on the database's expert beat annotations.
- Paced rhythms. The four paced records were excluded from training and testing.
- Rhythm-level labels (for example atrial fibrillation episodes). The model labels single beats.

The demo carries this note (D7): "This is a research demo. The model has not been clinically validated and must not be used to make health decisions. The recordings come from the MIT-BIH Arrhythmia Database, collected in a hospital lab between 1975 and 1979. Nothing here uses your data, and you cannot upload your own. If you have concerns about your heart, talk to a doctor."

## 3. Factors

**Relevant factors:**

- **The patient.** Beat shapes and class mix differ more between people than within one recording. This is why every number here comes from patients the model did not train on.
- **Class prevalence per patient.** Irregular beats cluster in a few patients, so pooled numbers can be one person's numbers (see the record 232 and F lines below).
- **Lead and equipment.** One lead (modified limb lead II, MLII), from two-channel ambulatory recordings made between 1975 and 1979 in one hospital lab.
- **Beat locations.** Given by the expert annotations, not found by the model.
- **Signal quality.** Noisy segments are kept, not removed.

**Evaluation factors:** results are reported per patient (section 7.1), with S also reported without record 232, and F named as one patient on each side.

**Demographic groups:** the age and sex of the patients in each set are listed in `docs/DATA_CARD.md`. No subgroup metrics are reported: 21 test patients cannot support a claim about any group, and a table of them would invite one.

## 4. Metrics

Pre-registered in A3, B4 and C4 before any test result existed.

**Model performance measures:**

- Headline: S and V recall and precision on the 21 DS2 patients; macro F1 over N, S and V, with four-class macro F1 beside it. N, S and V make the headline because DS2's F beats come almost entirely from one patient.
- False positive rates for S and V, for comparison with published work. Beside de Chazal's numbers, S and V sensitivity, positive predictivity and false positive rate follow AAMI EC57's definitions (de Chazal's Table V).
- S recall and precision without record 232.
- A per-patient table of S and V results: raw counts in every cell, a percentage only when the patient has at least 10 beats of that class (recall cells), or at least 10 beats flagged as that class (precision cells).
- A four-by-four confusion matrix (Q test beats noted as not scored), and N and F recall and precision with the F caveat.
- Calibration: one-vs-rest calibration error for S and V with 10 equal-mass bins, reliability diagrams, log loss and Brier score.
- Accuracy appears only in the leakage exhibit (section 7.4), labeled as the number papers often lead with. It is dominated by N beats and is not a measure of this model.

**Decision thresholds:** none. The label is the argmax of the weighted model, so rare classes can be flagged with a calibrated probability below 50%, on purpose.

**Variation approaches:**

- Test intervals: a paired patient bootstrap. The 21 DS2 patients are resampled with replacement, 10,000 draws, fixed seed, 95% percentile intervals, with the CNN and the baseline scored on the same draws. A draw with no predicted S beats is skipped for S precision only, and the skip count is reported.
- Development: pooled out-of-fold predictions plus the spread across the five folds.
- Training randomness: headline numbers from seed 0; one line with the range across seeds 1 and 2.
- Comparison rule (EVAL-10): "the CNN is better than the baseline" is stated only when the interval of the paired difference sits above zero. Otherwise this card says there is no clear difference. If the baseline matches or beats the CNN, that is stated plainly and the CNN still ships.

## 5. Evaluation data

- **Test set (DS2):** 21 records from 21 patients: 100, 103, 105, 111, 113, 117, 121, 123, 200, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234. This is de Chazal et al.'s (2004) test set without record 202, which comes from the same patient as training record 201. Source of truth: `manifests/splits.toml`.
- **How it was used:** sealed during development. Read once, by `heartbeat evaluate-test`, after a freeze record (commit, config, model checksum) was committed and pushed; every run is in `results/test_runs.jsonl`.
- **Development evaluation:** DS1 out-of-fold predictions over five patient-grouped folds (`config/folds.json`).
- **Preprocessing:** identical to training. See `docs/DATA_CARD.md`.

Class counts per set are in `docs/DATA_CARD.md` section 2.

## 6. Training data

- **Training set (DS1):** 22 records from 22 patients: 101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230.
- Q beats are left out of training (too few to learn from) but count for the RR features.
- F beats in DS1 come almost entirely from one patient, so the balanced weights give each F beat a very large weight. Overfitting to that patient is a known risk, left visible rather than tuned around.

Class counts are in `docs/DATA_CARD.md` section 2.

## 7. Quantitative analyses

### 7.1 Pre-registered test report (DS2, EVAL-08)

Seed 0 for the CNN; the baseline beside it; intervals from the paired patient bootstrap.

**Headline: S and V recall and precision, macro F1 over N, S and V, four-class macro F1, with bootstrap skip counts.**

<!-- card:begin test_headline -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_headline -->

**CNN against baseline (EVAL-10).** The sentence is chosen by the comparison rule from the interval of the paired difference, not written by hand.

<!-- card:begin test_comparison -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_comparison -->

**False positive rates for S and V.**

<!-- card:begin test_fpr -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_fpr -->

**S without record 232.** Record 232 holds most of DS2's S beats, so the pooled S numbers are largely one patient's. This line repeats S recall and precision over the other 20 patients, with a bootstrap over those 20.

<!-- card:begin test_s_without_232 -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_s_without_232 -->

**Per-patient S and V results.** Raw counts in every cell ("41 of 50"); a percentage only when the patient has at least 10 beats of that class (recall cells), or at least 10 beats flagged as that class (precision cells).

<!-- card:begin test_per_patient -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_per_patient -->

**Confusion matrix (four by four), with Q test beats noted as not scored.**

<!-- card:begin test_confusion -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_confusion -->

**N and F recall and precision.** F caveat: DS2's F beats come almost entirely from one patient, as do DS1's, so the F numbers describe two people, not a class.

<!-- card:begin test_n_f -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_n_f -->

**Seeds 1 and 2.** The range of the headline metrics across the other two final models.

<!-- card:begin test_seed_range -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_seed_range -->

### 7.2 Calibration (EVAL-11, EVAL-12)

Probabilities: subtract the log class weights from the logits, then divide by one temperature fitted on DS1 out-of-fold predictions. Same procedure for both models. Calibration depends on class prevalence, which varies widely between patients, so these probabilities are fragile across patients.

**Fitted temperature (DS1 out-of-fold).**

<!-- card:begin calibration_fit -->

Source: `results/cv_cnn.json` (DS1 out-of-fold, MPS). Source: `results/cv_baseline.json` (DS1 out-of-fold, CPU).

Calibration error is one-vs-rest with 10 equal-mass bins. Plain rows use the temperature fitted on these predictions (the one that ships); cross-fitted rows fit each fold's temperature on the other four.

| Model | Temperature | S calibration error | V calibration error | Log loss | Brier |
| --- | --- | --- | --- | --- | --- |
| CNN seed 0 | 1.7040 | 0.0084 | 0.0115 | 0.2284 | 0.0961 |
| CNN seed 0, cross-fitted | one per fold | 0.0075 | 0.0124 | 0.2370 | not computed |
| Baseline | 1.1744 | 0.0090 | 0.0332 | 0.2867 | 0.1153 |
| Baseline, cross-fitted | one per fold | 0.0082 | 0.0289 | 0.2993 | not computed |

CNN temperatures by seed: seed 0 1.7040, seed 1 1.6413, seed 2 1.6622.

<!-- card:end calibration_fit -->

**Test calibration: S and V calibration error, log loss, Brier score, reliability diagrams.**

<!-- card:begin test_calibration -->

_Pending: rendered from the sealed run (Phase 7)._

<!-- card:end test_calibration -->

### 7.3 Development results (DS1, out-of-fold)

Used to choose the configuration. Slightly optimistic, since the epoch count was chosen on the same out-of-fold numbers.

<!-- card:begin dev_selection -->

Source: `results/selection.json` and `results/cv_cnn.json` (DS1 out-of-fold, MPS). Source: `results/cv_baseline.json` (DS1 out-of-fold, CPU).

Chosen: width 1, 10 epochs, by the joint argmax over width and epoch of the seed mean of pooled out-of-fold macro F1 over N, S and V; ties to the smaller width, then fewer epochs (Phase 4 settling 2). Baseline C: 0.001.

Macro F1 over N, S and V at each width's best epoch, per seed and as the seed mean:

| Width | Best epoch | Seed 0 | Seed 1 | Seed 2 | Seed mean | Four-class seed mean |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 7 | 0.6545 | 0.5930 | 0.6467 | 0.6314 | 0.4912 |
| 1 | 10 | 0.6583 | 0.6189 | 0.6412 | 0.6395 | 0.4911 |
| 2 | 11 | 0.6137 | 0.6433 | 0.6035 | 0.6202 | 0.4818 |

Pooled out-of-fold metrics with 95% patient bootstrap intervals (10000 draws), and the range across the five folds:

| Metric | CNN seed 0 | CNN folds | Baseline | Baseline folds |
| --- | --- | --- | --- | --- |
| S recall | 0.3977 (0.0711 to 0.6076) | 0.0411 to 0.6289 | 0.2280 (0.0562 to 0.5995) | 0.0103 to 0.6073 |
| S precision | 0.1495 (0.0131 to 0.5801) | 0.0172 to 0.9394 | 0.0831 (0.0186 to 0.2081) | 0.0024 to 0.3566 |
| V recall | 0.8651 (0.7658 to 0.9310) | 0.7867 to 0.9937 | 0.5150 (0.3850 to 0.6445) | 0.2118 to 0.7203 |
| V precision | 0.8119 (0.6239 to 0.9639) | 0.4596 to 0.9713 | 0.6865 (0.4301 to 0.8952) | 0.2865 to 0.8793 |
| Macro F1 over N, S and V | 0.6583 (0.5680 to 0.7782) | 0.5098 to 0.8546 | 0.5323 (0.4475 to 0.6153) | 0.3806 to 0.6490 |
| Four-class macro F1 | 0.5030 (0.4301 to 0.5969) | 0.3824 to 0.6410 | 0.4121 (0.3395 to 0.4827) | 0.2855 to 0.4867 |
| S false positive rate | 0.0426 (0.0061 to 0.0949) | 0.0006 to 0.1152 | 0.0474 (0.0194 to 0.0838) | 0.0097 to 0.0916 |
| V false positive rate | 0.0161 (0.0026 to 0.0374) | 0.0015 to 0.0582 | 0.0189 (0.0055 to 0.0350) | 0.0087 to 0.0305 |

- Bootstrap draws skipped as undefined: none.
- CNN seeds 1 and 2, macro F1 over N, S and V: 0.6189 to 0.6412.
- CNN seed 0 minus the baseline on the same draws, macro F1 over N, S and V: 0.1259 (0.0116 to 0.2602).

<!-- card:end dev_selection -->

### 7.4 Leakage exhibit (DS1 only, C5)

Same model, same 22 patients, same code and seeds. The only change: whether beats from one person can land in both training and testing (patient-grouped folds against random beat-level folds). The configuration chosen on the honest folds is used on both sides, with no retuning on the leaky side. Accuracy appears here only.

<!-- card:begin exhibit -->

Source: `results/exhibit.json` (DS1 out-of-fold; CNN MPS, baseline CPU).

Configuration from the honest folds on both sides: width 1, 10 epochs, baseline C 0.001. Beat-level split: StratifiedKFold, 5 folds, seed 20261030. Intervals: 95%, one shared set of 10000 patient draws for every column.

| Metric | CNN, patient-grouped | Baseline, patient-grouped | CNN, beat-level | Baseline, beat-level |
| --- | --- | --- | --- | --- |
| Accuracy | 0.8534 (0.7741 to 0.9233) | 0.7698 (0.6408 to 0.8876) | 0.9512 (0.9279 to 0.9727) | 0.8053 (0.6809 to 0.9166) |
| S recall | 0.3977 (0.0711 to 0.6076) | 0.2280 (0.0562 to 0.5995) | 0.9629 (0.9216 to 0.9760) | 0.3892 (0.2209 to 0.6117) |
| S precision | 0.1495 (0.0131 to 0.5801) | 0.0831 (0.0186 to 0.2081) | 0.3714 (0.2097 to 0.4753) | 0.2121 (0.0558 to 0.4613) |
| V recall | 0.8651 (0.7658 to 0.9310) | 0.5150 (0.3850 to 0.6445) | 0.9754 (0.9583 to 0.9852) | 0.6687 (0.5473 to 0.7817) |
| V precision | 0.8119 (0.6239 to 0.9639) | 0.6865 (0.4301 to 0.8952) | 0.9135 (0.8069 to 0.9768) | 0.7243 (0.4916 to 0.9108) |
| Macro F1 over N, S and V | 0.6583 (0.5680 to 0.7782) | 0.5323 (0.4475 to 0.6153) | 0.8176 (0.7478 to 0.8573) | 0.6233 (0.5308 to 0.7070) |
| Four-class macro F1 | 0.5030 (0.4301 to 0.5969) | 0.4121 (0.3395 to 0.4827) | 0.7565 (0.5919 to 0.8124) | 0.4887 (0.4034 to 0.5691) |
| S false positive rate | 0.0426 (0.0061 to 0.0949) | 0.0474 (0.0194 to 0.0838) | 0.0307 (0.0146 to 0.0507) | 0.0272 (0.0094 to 0.0515) |
| V false positive rate | 0.0161 (0.0026 to 0.0374) | 0.0189 (0.0055 to 0.0350) | 0.0074 (0.0017 to 0.0169) | 0.0204 (0.0059 to 0.0397) |

Accuracy: the number papers often lead with; shown only in this exhibit (EXHIBIT-03).

<!-- card:end exhibit -->

### 7.5 Intersectional results

Not reported. See section 3.

## 8. Ethical considerations

- **Data.** The recordings come from 47 people recorded between 1975 and 1979 and are published by PhysioNet under ODC-By 1.0. This project uses them as published and adds no personal data. The database page does not describe consent or de-identification procedures.
- **Representativeness.** One hospital lab, one era of equipment, one lead, 43 patients in use. Nothing here shows the model works on anyone else.
- **Misreading as medical output.** A labeled ECG can look like a medical result. The demo and case study carry the research-demo line (D7), avoid the wording on D7's avoid list, and show the expert's label beside every model label.
- **Visitor data.** The demo collects nothing: no uploads, accounts, cookies or analytics.

## 9. Caveats and recommendations

- Beat locations come from the database's expert annotations, so these numbers assume every beat has already been found. A real device would also have to find them.
- F is one patient on each side. F results describe those two patients.
- S results are dominated by record 232; read them with the without-232 line.
- Calibrated probabilities are fragile across patients, because class prevalence differs between patients.
- Labels lag by one beat, because one RR feature uses the time to the next beat.
- The model uses one lead and is tested on 21 patients.
- Development numbers ran on MPS and reproduce within tolerance; frozen models train on CPU in deterministic mode and reproduce bit for bit on the same machine and setup.
- De Chazal et al. (2004) report results from a two-lead classifier tested on all 22 DS2 records. Their numbers are context, not a target, and are not directly comparable (PUB-03).
- Recommendation: compare this model only with results measured on patients held out of training. Numbers from random beat-level splits measure something else (section 7.4 shows how much).

## Change log

Sections, tables or figures added after the sealed run are listed here with their date and reason. None so far.
