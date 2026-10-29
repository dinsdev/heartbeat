# Heartbeat data card

|                  |                                                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status**       | Template (F6, locked by Din 2026-10-27). Committed and pushed before any result exists.                                                                                         |
| **Covers**       | The beat dataset Heartbeat derives from the MIT-BIH Arrhythmia Database 1.0.0: which records, how they are split, how beats are cut and labeled, and what ships to the browser. |
| **Requirements** | PUB-04 (this card), DATA-01 to DATA-11, EVAL-01 to EVAL-03, DEMO-07, DEMO-08, DEMO-16, PUB-07                                                                                   |
| **Related**      | `docs/MODEL_CARD.md`, `manifests/`, `DATA_LICENSE.md`, `docs/WORK_LEDGER.md` (B1 to B5, C1, D4)                                                                                 |

The layout follows Gebru et al., "Datasheets for Datasets" (arXiv 1803.09010, v8), section by section, answering the questions that apply to a dataset derived from a public one. Facts about the source database come from its PhysioNet page and are cited, not repeated in full.

## How the numbers get here

Every count in this card sits in a generated block between `<!-- card:begin NAME -->` and `<!-- card:end NAME -->`, rendered by `heartbeat cards` from committed `results/` files and checked by `heartbeat verify` (R50). The prose holds definitions only: record lists, exclusions and processing steps, all decided before any data was processed. A block that reads "Pending" has no run behind it yet.

## 1. Motivation

- **Purpose:** to train and evaluate a heartbeat classifier on patients it never saw, and to show in a browser demo that the shipped model is the one that was evaluated.
- **Created by:** Din (Dinesh Dawonauth), working with Claude, for the dins.dev portfolio.
- **Gap it fills:** the standard inter-patient split (de Chazal et al., 2004) puts records 201 and 202, which come from the same person, on opposite sides. This dataset removes that leak and enforces the split in code.

## 2. Composition

**Source:** the MIT-BIH Arrhythmia Database 1.0.0 (Moody and Mark), 48 half-hour two-channel ambulatory ECG recordings from 47 people. PhysioNet lists 25 men aged 32 to 89 and 22 women aged 23 to 89 across the whole database.

**Records used:** 44 of the 48 records (the four paced records are excluded), from 43 people.

| Set      | Records                                                                                                      | Role                                                            |
| -------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| DS1      | 101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230 | Training and development (22 records, 22 patients)              |
| DS2      | 100, 103, 105, 111, 113, 117, 121, 123, 200, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234      | Test, sealed until one logged run (21 records, 21 patients)     |
| Excluded | 102, 104, 107, 217                                                                                           | Paced rhythms (AAMI practice)                                   |
| Excluded | 202                                                                                                          | Same person as 201, which stays in DS1 (fixes the 201/202 leak) |

Source of truth: `manifests/splits.toml`, with the record-to-person map in `manifests/subjects.toml`. The DS1 and DS2 lists follow de Chazal et al. (2004), checked against the paper's full text (Table II footnote) on 2026-10-29. The only change is record 202, removed from DS2 because it comes from the same person as DS1's record 201.

**Instances:** one instance per annotated beat, except the first and last beat of each record. Each has:

- a 256-sample window of the filtered MLII signal (96 samples before the annotation, 160 after), z-scored per window;
- six RR interval features: pre-RR, post-RR, local average RR (previous 10 beats), long average RR (previous 5 minutes), pre-RR over local average, post-RR over pre-RR;
- an AAMI class label (section 4);
- the record and person IDs.

**Class counts per set (N, S, V, F, Q).**

<!-- card:begin data_counts -->

_Pending: rendered from the counts `prepare` writes (Phase 2)._

<!-- card:end data_counts -->

**Class counts per record.**

<!-- card:begin data_counts_per_record -->

_Pending: rendered from the counts `prepare` writes (Phase 2)._

<!-- card:end data_counts_per_record -->

**Age and sex per set, from the record headers.**

<!-- card:begin data_demographics -->

_Pending: rendered from the record headers by `prepare` (Phase 2)._

<!-- card:end data_demographics -->

**Known concentrations:** irregular beats cluster in a few people. Most of DS2's S beats are in record 232, and nearly all F beats are in one record on each side (208 in DS1, 213 in DS2). The model card reports S with and without record 232 and names F as one patient per side.

**Labels and their limits:** reference annotations made by cardiologists (section 3). They can contain errors, and every number in the model card treats them as ground truth.

**Missing or excluded content:** Q beats (paced, fusion of paced and normal, unclassifiable) are kept for RR features but not scored. Non-beat annotations (flutter waves, non-conducted P waves, noise and rhythm markers) are not beats. Noisy segments are kept.

**Sensitive data:** the recordings are published openly by PhysioNet and carry no names. Record headers include age and sex, and some list medications (for example, 101's header lists age, sex and one drug). This project adds no personal data.

## 3. Collection process

**Source recordings (PhysioNet page):** excerpts from about 4,000 24-hour ambulatory ECG recordings collected by the Beth Israel Hospital Arrhythmia Laboratory between 1975 and 1979, about 60% from inpatients and 40% from outpatients. 23 excerpts were chosen at random and 25 were chosen to include uncommon but clinically important arrhythmias. Signals were digitized at 360 samples per second per channel, with 11-bit resolution over a 10 mV range. Beats were first labeled automatically, then two cardiologists reviewed each recording independently and resolved disagreements by consensus.

**How this project gets the data:** the `download` stage of `heartbeat rebuild` fetches exactly 132 files (`.hea`, `.dat` and `.atr` for the 44 records used) from PhysioNet's S3 mirror, falling back to `physionet.org`, into the gitignored cache `data/raw/mitdb/1.0.0/`. Every run checks each file against the SHA256 values pinned in `manifests/mitdb-1.0.0.sha256` and stops on any mismatch.

## 4. Preprocessing, cleaning and labeling

Run by the `prepare` stage of `heartbeat rebuild` (DATA-04 to DATA-10):

1. **Lead:** MLII, picked by signal name, never by channel position (record 114 has its two signals reversed).
2. **Filter:** 0.5 to 40 Hz Butterworth bandpass, zero-phase (forward and backward), once per record, at the native 360 Hz.
3. **Rounding:** the filtered signal is rounded to int16 at 200 units per mV (5 microvolt steps). Training, evaluation and the browser all use this rounded signal, so Python and the browser see identical inputs.
4. **Windows:** 256 samples per beat around the annotation as given, with no realignment; z-scored per window.
5. **RR features:** computed over every annotated beat, including unscored classes, so a skipped beat never creates a false long interval. Only post-RR looks ahead, by one beat.
6. **Edges:** the first and last beat of each record are dropped.
7. **Labels (AAMI EC57):** N = N, L, R, e, j; S = A, a, J, S; V = V, E; F = F; Q = /, f, Q. Any symbol outside this list and the known non-beat symbols stops the pipeline.
8. **Scored classes:** N, S, V and F. Q is not scored.

**Checks:** per-record class counts must match PhysioNet's beat table (DATA-11); no person may appear on both sides of DS1 and DS2 or of any development fold (EVAL-02).

**Raw data:** kept in the local cache and never committed or redistributed by this repo. Everything derived is rebuilt from it by `heartbeat rebuild`.

## 5. Uses

- **Used for:** training and evaluating heartbeat-v1 and its logistic-regression baseline (`docs/MODEL_CARD.md`); the leakage exhibit (DS1 only); the browser demo.
- **Development folds:** five patient-grouped folds over DS1, written once by `heartbeat make-folds` to `config/folds.json` and only checked afterwards.
- **Should not be used for:** any health decision; claims about people outside this database; evaluation with beats from one person on both sides of a split (random beat-level splits, which the leakage exhibit shows inflate results); tuning or selecting anything on DS2.

## 6. Distribution

- **License:** the MIT-BIH Arrhythmia Database is under the Open Data Commons Attribution License 1.0 (`DATA_LICENSE.md`). This repo's MIT license covers the code only.
- **What ships:** the browser demo serves derived data for the 21 DS2 patients after the sealed run (DS1 recordings before it): per patient, the filtered int16 trace (`NNN.trace.i16`) and a beats file with positions, expert labels and the frozen model's labels and probabilities (`NNN.beats.json`), plus a `manifest.json` with class counts, file hashes, the model version and the attribution note.
- **Attribution:** an attribution note ships beside the demo data, the demo shows the dataset credit, and the case study has a credits block.

<!-- card:begin shipped_data -->

_Pending: shipped file sizes and hashes, rendered from the demo data manifest (Phases 6 and 7)._

<!-- card:end shipped_data -->

**Citations:**

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Engineering in Medicine and Biology 20(3):45-50 (2001).
- Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005). https://doi.org/10.13026/C2F305
- Pollard T, et al. PhysioNet as a global platform for biomedical research. Nature Health (2026). https://doi.org/10.1038/s44360-026-00096-z
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat interval features. IEEE Transactions on Biomedical Engineering 51(7):1196-1206 (2004).
- AAMI EC57, testing and reporting performance results of cardiac rhythm and ST segment measurement algorithms.

PhysioNet's requested citation is rechecked before publishing (PUB-07).

## 7. Maintenance

- **Maintained by:** Din. Errors and questions: issues on `dinsdev/heartbeat`.
- **Pinned source:** MIT-BIH 1.0.0, by checksum. A new database version would mean new checksums, a ledger entry and a rebuild.
- **Changes:** the split, the record lists, the person map and the folds are rigor events: they change only with Din's go and a dated entry in `docs/WORK_LEDGER.md`.

## Change log

Changes after the sealed run are listed here with their date and reason. None so far.
