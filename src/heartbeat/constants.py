"""Values fixed by a planning decision, each with its decision ID (CONVENTIONS 2).

Run settings that a run may vary live in `config/default.toml` instead.
"""

from collections.abc import Mapping
from types import MappingProxyType

# B3, D4: MIT-BIH is sampled at 360 Hz; the canonical trace is int16 at 200
# units per mV.
FS_HZ = 360
ADU_PER_MV = 200

# B3, DATA-05 (Phase 2 settling 2): order 4 Butterworth, 0.5 to 40 Hz, applied
# forward and backward with sosfiltfilt.
BANDPASS_LOW_HZ = 0.5
BANDPASS_HIGH_HZ = 40.0
BANDPASS_ORDER = 4

# B3: window of 256 samples, 96 before the annotation and 160 after
WINDOW_BEFORE_SAMPLES = 96
WINDOW_AFTER_SAMPLES = 160
WINDOW_SAMPLES = WINDOW_BEFORE_SAMPLES + WINDOW_AFTER_SAMPLES

# B3 amendment (2026-10-29), DATA-06: z = (x - mean) / max(std, 2), in int16 units.
ZSCORE_STD_FLOOR_ADU = 2.0

# B3, DATA-07 (Phase 2 settling 3): the local average spans the last 10
# intervals; the long average every interval ending at most 5 minutes
# (108,000 samples) before the beat.
RR_LOCAL_INTERVALS = 10
RR_LONG_WINDOW_SAMPLES = 5 * 60 * FS_HZ

# DATA-07: column order of the RR feature matrix. Stored raw; the log of the two
# ratios is taken in the model input step (C2).
RR_FEATURE_NAMES = (
    "pre_rr_s",
    "post_rr_s",
    "local_avg_rr_s",
    "long_avg_rr_s",
    "pre_over_local",
    "post_over_pre",
)

# B4, DATA-09: annotation symbol to AAMI class, exactly as listed.
AAMI_CLASS: Mapping[str, str] = MappingProxyType(
    {
        "N": "N",
        "L": "N",
        "R": "N",
        "e": "N",
        "j": "N",
        "A": "S",
        "a": "S",
        "J": "S",
        "S": "S",
        "V": "V",
        "E": "V",
        "F": "F",
        "/": "Q",
        "f": "Q",
        "Q": "Q",
    }
)

# B4, DATA-09: annotations that are not beats: rhythm change, noise, isolated
# QRS-like artifact, flutter wave, non-conducted P wave, flutter start and end,
# comment. Any symbol in neither set fails loudly (R10).
NON_BEAT_SYMBOLS = frozenset('+~|!x[]"')

# B4, DATA-10: the four scored classes. Q counts for RR only.
SCORED_CLASSES = ("N", "S", "V", "F")

# C1, EVAL-03: five folds on DS1, grouped by subject.
N_FOLDS = 5

# Phase 2 task plan: more DS1 windows than this at the z-score floor stops the
# run and goes back to Din (B3 amendment, point 3).
FLOOR_HIT_LIMIT = 5

# C4, Phase 3 settling 1: the headline and every selection step use macro F1
# over N, S and V; four-class macro F1 is reported beside it.
HEADLINE_CLASSES = ("N", "S", "V")

# C2, MODEL-01: the baseline's C grid, chosen on the C1 folds. Widened to
# 0.0001 once by Phase 4 settling 1 and never again.
BASELINE_C_GRID = (0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0)
# Phase 3 task plan, design call 5: lbfgs iterations; non-convergence stops the run.
BASELINE_MAX_ITER = 10_000

# C4, EVAL-09: paired patient bootstrap. The seed is fixed for every run
# (Phase 3 task plan, design call 1) and differs from the fold seed.
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 20261029
# Phase 3 settling 5: 95% percentile intervals.
INTERVAL_PERCENTILES = (2.5, 97.5)

# C4, EVAL-12: equal-mass bins for ECE and reliability data.
ECE_BINS = 10

# C4, EVAL-08 item 4 (Phase 3 settling 3): a per-patient cell shows a
# percentage only when its own denominator is at least this many beats.
PER_PATIENT_MIN_BEATS = 10

# EVAL-11: the bounded search for the temperature; an optimum within 1% of
# either bound stops the run (Phase 3 task plan, stop condition 5).
TEMPERATURE_BOUNDS = (0.05, 20.0)

# C3, MODEL-02: the CNN. Channels of the four conv blocks at width 1; the
# widths scale them, the hidden layer stays 64.
CNN_WIDTHS = (0.5, 1.0, 2.0)
CNN_CHANNELS = (16, 32, 64, 64)
CNN_KERNEL = 7
CNN_HIDDEN = 64
CNN_DROPOUT = 0.3
# C3, MODEL-03: AdamW at a constant rate, batch 256.
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
BATCH_SIZE = 256

# C6, MODEL-05: three master seeds; seed 0 ships.
CNN_SEEDS = (0, 1, 2)
SHIPPED_SEED = 0

# Phase 4 settling 2: every run trains 40 epochs; a pick at epoch 36 or later
# stops the run for Din.
MAX_EPOCHS = 40
EPOCH_EDGE_FIRST = 36

# Phase 4 settling 4: shift by up to 5 samples each way, noise of standard
# deviation 0.05 in z-units; training only, never tuned.
SHIFT_MAX_SAMPLES = 5
NOISE_STD_Z = 0.05

# Phase 4 settling 5: every training run, MPS or CPU, uses 4 threads.
TORCH_THREADS = 4

# Phase 4 task plan, design call 1: the exhibit's beat-level split (C5), distinct
# from the fold and bootstrap seeds.
LEAKY_SPLIT_SEED = 20261030
