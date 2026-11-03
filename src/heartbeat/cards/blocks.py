"""One renderer per generated card block (F6; Phase 5 task plan, design call 12).

Every block renders from committed files only: `results/*.json`, the bundle in
`models/heartbeat-v1/` and the sealed-run log. Numbers have four decimals,
intervals read "a to b", and each block names its source file and whether its
numbers are DS1 out-of-fold or DS2 test, MPS or CPU. `test_*` blocks stay
pending until a sealed entry is logged (R50). The freeze commit renders in
`test_headline` from the sealed report's `freeze_commit`, so committing the
freeze record changes no block (Phase 7 settling 1). Tables are padded the
way Prettier pads them, so the Markdown check passes on rendered cards.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from heartbeat.constants import SCORED_CLASSES
from heartbeat.export.bundle import FREEZE_NAME
from heartbeat.sealed.log import read_log
from heartbeat.train.exhibit import card_row

TEST_PENDING = "_Pending: rendered from the sealed run (Phase 7)._"
SHIPPED_PENDING = (
    "_Pending: shipped file sizes and hashes, rendered from the demo data "
    "manifest (Phases 6 and 7)._"
)
TEST_LABEL = "DS2 test, CPU"

METRIC_LABELS = {
    "macro_f1_nsv": "Macro F1 over N, S and V",
    "macro_f1_all": "Four-class macro F1",
    "S_recall": "S recall",
    "S_precision": "S precision",
    "V_recall": "V recall",
    "V_precision": "V precision",
    "S_fpr": "S false positive rate",
    "V_fpr": "V false positive rate",
    "N_recall": "N recall",
    "N_precision": "N precision",
    "F_recall": "F recall",
    "F_precision": "F precision",
    "ec57_S_se": "S sensitivity (EC57)",
    "ec57_S_ppv": "S positive predictivity (EC57)",
    "ec57_S_fpr": "S false positive rate (EC57)",
    "ec57_V_se": "V sensitivity (EC57)",
    "ec57_V_ppv": "V positive predictivity (EC57)",
    "ec57_V_fpr": "V false positive rate (EC57)",
}
HEADLINE = (
    "S_recall",
    "S_precision",
    "V_recall",
    "V_precision",
    "macro_f1_nsv",
    "macro_f1_all",
)
DEV_METRICS = (*HEADLINE, "S_fpr", "V_fpr")


@dataclass(frozen=True)
class CardSources:
    """Where the blocks read from.

    Attributes:
        results_dir: The committed `results/` folder.
        models_dir: The bundle (`models/heartbeat-v1/`).
        log_path: The sealed-run log.
        log_root: The folder the log's report paths are relative to.
    """

    results_dir: Path
    models_dir: Path
    log_path: Path
    log_root: Path

    def result(self, name: str) -> dict[str, Any]:
        """A committed results file."""
        path = self.results_dir / f"{name}.json"
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return payload

    def sealed_report(self) -> tuple[str, dict[str, Any]] | None:
        """The last sealed entry's report path and content, or None before one."""
        sealed = [e for e in read_log(self.log_path) if e["type"] == "sealed"]
        if not sealed:
            return None
        path = str(sealed[-1]["report"])
        report: dict[str, Any] = json.loads(
            (self.log_root / path).read_text(encoding="utf-8")
        )
        return path, report


# Formatting


def num(value: float | None) -> str:
    """Four decimals, or "undefined" (never 0) for a metric with no value."""
    return "undefined" if value is None else f"{value:.4f}"


def interval(entry: Mapping[str, Any]) -> str:
    """The point and its interval, "point (low to high)", or "(no interval)"."""
    point = num(entry["point"])
    if entry["low"] is None:
        return f"{point} (no interval)"
    return f"{point} ({num(entry['low'])} to {num(entry['high'])})"


# The repo's Prettier settings: 80 columns, `proseWrap: never`.
PRINT_WIDTH = 80


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A Markdown table as Prettier writes it with `proseWrap: never`.

    Padded to each column's width when every line fits in 80 columns;
    otherwise the compact form, one space around each cell.
    """
    widths = [
        max(3, len(header[k]), *(len(r[k]) for r in rows)) for k in range(len(header))
    ]
    if 4 + sum(widths) + 3 * (len(widths) - 1) > PRINT_WIDTH:
        compact = ["| " + " | ".join(cells) + " |" for cells in (header, *rows)]
        return "\n".join(
            [compact[0], "| " + " | ".join(["---"] * len(widths)) + " |", *compact[1:]]
        )

    def line(cells: Sequence[str]) -> str:
        return (
            "| "
            + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))
            + " |"
        )

    return "\n".join(
        [line(header), line(["-" * w for w in widths]), *(line(r) for r in rows)]
    )


def source(files: Sequence[str], label: str) -> str:
    """The source line every block starts with."""
    names = " and ".join(f"`{name}`" for name in files)
    return f"Source: {names} ({label})."


def _skips(rows: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> str:
    notes = [
        f"{model} {METRIC_LABELS.get(metric, metric)} {entry['skipped']} of "
        f"{entry['draws']}"
        for model, metrics in rows.items()
        for metric, entry in metrics.items()
        if entry["skipped"]
    ]
    if not notes:
        return "Bootstrap draws skipped as undefined: none."
    return "Bootstrap draws skipped as undefined: " + "; ".join(notes) + "."


# Model card, DS1 and export blocks


def model_details(sources: CardSources) -> str:
    """Width, epochs, parameters, each ONNX file's size and SHA256, the freeze."""
    selection = sources.result("selection")
    export = sources.result("export")
    files = {f["path"].split("heartbeat-v1/", 1)[-1]: f for f in export["files"]}
    lines = [
        source(
            ["results/selection.json", "results/export.json"],
            "width and epochs chosen on DS1 out-of-fold, MPS; frozen models, CPU",
        ),
        "",
        f"- Width multiplier {selection['width']:g}, {selection['epoch']} epochs.",
        f"- Parameters: {export['parameters']} (PyTorch, before batch-norm folding).",
        f"- ONNX opset {export['opset']}, one file per seed, each under "
        f"{export['size_limit_bytes']} bytes:",
    ]
    for model in export["models"]:
        name = model["path"].split("heartbeat-v1/", 1)[-1]
        facts = files[name]
        role = " (shipped)" if model["seed"] == export["shipped_seed"] else ""
        lines.append(
            f"  - Seed {model['seed']}{role}, `{name}`: {facts['bytes']} bytes, "
            f"SHA256 `{facts['sha256']}`."
        )
    baseline = files["baseline.json"]
    lines.append(f"- Baseline, `baseline.json`: SHA256 `{baseline['sha256']}`.")
    return "\n".join(lines)


def _calibration_rows(name: str, calibration: Mapping[str, Any]) -> list[list[str]]:
    cross = calibration["cross_fitted"]
    return [
        [
            name,
            num(calibration["temperature"]),
            num(calibration["ece"]["S"]),
            num(calibration["ece"]["V"]),
            num(calibration["log_loss"]),
            num(calibration["brier"]),
        ],
        [
            f"{name}, cross-fitted",
            "one per fold",
            num(cross["ece"]["S"]),
            num(cross["ece"]["V"]),
            num(cross["log_loss"]),
            "not computed",
        ],
    ]


def calibration_fit(sources: CardSources) -> str:
    """Fitted temperatures and DS1 calibration, in-sample and cross-fitted."""
    cnn = sources.result("cv_cnn")
    baseline = sources.result("cv_baseline")
    seeds = ", ".join(
        f"seed {t['seed']} {num(t['temperature'])}" for t in cnn["temperatures"]
    )
    return "\n".join(
        [
            source(["results/cv_cnn.json"], cnn["data"])
            + " "
            + source(["results/cv_baseline.json"], baseline["data"]),
            "",
            "Calibration error is one-vs-rest with "
            f"{cnn['calibration']['bins']} equal-mass bins. Plain rows use the "
            "temperature fitted on these predictions (the one that ships); "
            "cross-fitted rows fit each fold's temperature on the other four.",
            "",
            table(
                [
                    "Model",
                    "Temperature",
                    "S calibration error",
                    "V calibration error",
                    "Log loss",
                    "Brier",
                ],
                [
                    *_calibration_rows("CNN seed 0", cnn["calibration"]),
                    *_calibration_rows("Baseline", baseline["calibration"]),
                ],
            ),
            "",
            f"CNN temperatures by seed: {seeds}.",
        ]
    )


def _fold_range(spread: Mapping[str, Any]) -> str:
    if spread["min"] is None:
        return "undefined"
    text = f"{num(spread['min'])} to {num(spread['max'])}"
    if spread["undefined_folds"]:
        text += f" ({spread['undefined_folds']} undefined)"
    return text


def dev_selection(sources: CardSources) -> str:
    """Width by seed, the chosen epoch and C, pooled metrics and fold spread."""
    selection = sources.result("selection")
    cnn = sources.result("cv_cnn")
    baseline = sources.result("cv_baseline")
    best = {float(b["width"]): b for b in selection["best_per_width"]}
    width_rows = []
    for curve in selection["curves"]:
        b = best[float(curve["width"])]
        by_seed = {int(s["seed"]): s for s in curve["per_seed"]}
        width_rows.append(
            [
                f"{curve['width']:g}",
                str(b["epoch"]),
                *(
                    num(by_seed[s]["macro_f1_nsv"][b["epoch"] - 1])
                    for s in sorted(by_seed)
                ),
                num(b["score"]),
                num(b["four_class"]),
            ]
        )
    cnn_i, base_i = cnn["bootstrap"]["intervals"], baseline["bootstrap"]["intervals"]
    metric_rows = [
        [
            METRIC_LABELS[m],
            interval(cnn_i[m]),
            _fold_range(cnn["fold_spread"][m]),
            interval(base_i[m]),
            _fold_range(baseline["fold_spread"][m]),
        ]
        for m in DEV_METRICS
    ]
    others = cnn["other_seeds"]["range"]["macro_f1_nsv"]
    paired = cnn["paired_difference"]["metrics"]
    draws = cnn["bootstrap"]["settings"]["draws"]
    return "\n".join(
        [
            source(["results/selection.json", "results/cv_cnn.json"], cnn["data"])
            + " "
            + source(["results/cv_baseline.json"], baseline["data"]),
            "",
            f"Chosen: width {selection['width']:g}, {selection['epoch']} "
            f"epochs, by the {selection['rule']}. Baseline C: "
            f"{baseline['chosen_c']:g}.",
            "",
            "Macro F1 over N, S and V at each width's best epoch, per seed and as "
            "the seed mean:",
            "",
            table(
                [
                    "Width",
                    "Best epoch",
                    "Seed 0",
                    "Seed 1",
                    "Seed 2",
                    "Seed mean",
                    "Four-class seed mean",
                ],
                width_rows,
            ),
            "",
            f"Pooled out-of-fold metrics with 95% patient bootstrap intervals "
            f"({draws} draws), and the range across the five folds:",
            "",
            table(
                ["Metric", "CNN seed 0", "CNN folds", "Baseline", "Baseline folds"],
                metric_rows,
            ),
            "",
            f"- {_skips({'CNN': cnn_i, 'Baseline': base_i})}",
            "- CNN seeds 1 and 2, macro F1 over N, S and V: "
            + (
                f"{num(others['min'])} to {num(others['max'])}."
                if others
                else "undefined."
            ),
            "- CNN seed 0 minus the baseline on the same draws, macro F1 over "
            f"N, S and V: {interval(paired['macro_f1_nsv'])}.",
        ]
    )


EXHIBIT_SIDES = {"patient": "patient-grouped", "beat": "beat-level"}


def exhibit(sources: CardSources) -> str:
    """The leakage exhibit: both splits, both models, and the exhibit's own row."""
    payload = sources.result("exhibit")
    rows = payload["rows"]
    columns = [
        f"{'CNN' if r['model'] == 'cnn' else 'Baseline'}, {EXHIBIT_SIDES[r['side']]}"
        for r in rows
    ]
    labels = {r["model"]: r["data"] for r in rows}
    own_name, own_intervals, own_label = card_row(payload)
    metrics = [
        [own_name, *(interval(entry) for entry in own_intervals)],
        *(
            [METRIC_LABELS[m], *(interval(r["metrics"][m]) for r in rows)]
            for m in DEV_METRICS
        ),
    ]
    split = payload["leaky_split"]
    chosen = payload["selection"]
    return "\n".join(
        [
            source(
                ["results/exhibit.json"],
                f"DS1 out-of-fold; CNN {labels['cnn'].split(', ')[-1]}, baseline "
                f"{labels['baseline'].split(', ')[-1]}",
            ),
            "",
            f"Configuration from the honest folds on both sides: width "
            f"{chosen['width']:g}, {chosen['epoch']} epochs, baseline C "
            f"{chosen['C']:g}. Beat-level split: {split['method']}, "
            f"{split['n_splits']} folds, seed {split['seed']}. Intervals: 95%, one "
            f"shared set of {payload['bootstrap']['draws']} patient draws for every "
            "column.",
            "",
            table(["Metric", *columns], metrics),
            "",
            own_label,
        ]
    )


# Model card, test blocks (pending until the sealed run is logged)


def _test_block(
    render: Callable[[str, dict[str, Any]], str],
) -> Callable[[CardSources], str]:
    def block(sources: CardSources) -> str:
        found = sources.sealed_report()
        if found is None:
            return TEST_PENDING
        path, report = found
        return render(path, report)

    return block


def _test_source(path: str, report: Mapping[str, Any]) -> str:
    return source([path], f"{TEST_LABEL}; {report['data']}")


def _pair_table(
    report: Mapping[str, Any], block: Mapping[str, Any], metrics: Sequence[str]
) -> str:
    return table(
        ["Metric", "CNN seed 0", "Baseline"],
        [
            [
                METRIC_LABELS[m],
                interval(block["cnn"][m]),
                interval(block["baseline"][m]),
            ]
            for m in metrics
        ],
    )


def _freeze_line(sources: CardSources, report: Mapping[str, Any]) -> str:
    """The report's freeze commit, dated from the record that names it."""
    commit = str(report["freeze_commit"])
    record = json.loads((sources.models_dir / FREEZE_NAME).read_text("utf-8"))
    if record["commit"] != commit:
        raise ValueError(
            f"the freeze record names {record['commit'][:12]}, the sealed report "
            f"{commit[:12]}"
        )
    return f"Freeze commit `{commit}`, dated {record['date']}."


def headline_block(sources: CardSources) -> str:
    """The headline table, after the freeze line (Phase 7 settling 1)."""
    found = sources.sealed_report()
    if found is None:
        return TEST_PENDING
    path, report = found
    intervals = report["headline"]["intervals"]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            _freeze_line(sources, report),
            "",
            _pair_table(report, intervals, HEADLINE),
            "",
            _skips(
                {
                    "CNN": {m: intervals["cnn"][m] for m in HEADLINE},
                    "Baseline": {m: intervals["baseline"][m] for m in HEADLINE},
                }
            ),
        ]
    )


VERDICT_SENTENCES = {
    "CNN better than baseline": (
        "The CNN is better than the baseline: the interval of the paired "
        "difference sits above zero."
    ),
    "no clear difference": (
        "No clear difference between the CNN and the baseline: the interval of "
        "the paired difference includes zero."
    ),
    "baseline better than CNN": (
        "The baseline is better than the CNN: the interval of the paired "
        "difference sits below zero. The CNN still ships (EVAL-10)."
    ),
}


def _test_comparison(path: str, report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    head = comparison["metrics"][comparison["headline_metric"]]
    rows = [
        [METRIC_LABELS[m], interval(entry), entry["verdict"]]
        for m, entry in comparison["metrics"].items()
    ]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            "CNN seed 0 minus baseline on the same patient draws, "
            f"{METRIC_LABELS[comparison['headline_metric']]}: {interval(head)}. "
            f"{VERDICT_SENTENCES[head['verdict']]}",
            "",
            table(["Metric", "Difference", "By the EVAL-10 rule"], rows),
        ]
    )


def _test_fpr(path: str, report: dict[str, Any]) -> str:
    ec57 = report["fpr"]["ec57"]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            _pair_table(report, report["fpr"]["one_vs_rest"], ("S_fpr", "V_fpr")),
            "",
            f"Beside de Chazal's numbers: {ec57['label']}. The "
            f"{ec57['q_not_scored']} Q beats are not scored here.",
            "",
            _pair_table(
                report,
                ec57,
                (
                    "ec57_S_se",
                    "ec57_S_ppv",
                    "ec57_S_fpr",
                    "ec57_V_se",
                    "ec57_V_ppv",
                    "ec57_V_fpr",
                ),
            ),
        ]
    )


def _test_s_without(path: str, report: dict[str, Any]) -> str:
    block = report["s_without_excluded"]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            f"Record {block['record']} left out; the bootstrap resamples the other "
            f"{len(block['patients'])} patients.",
            "",
            _pair_table(report, block["intervals"], ("S_recall", "S_precision")),
        ]
    )


def _cell(cell: Mapping[str, Any]) -> str:
    if cell["note"]:
        return str(cell["note"])
    text = f"{cell['numerator']} of {cell['denominator']}"
    if cell["percent"] is not None:
        text += f", {cell['percent']:.1f}%"
    return text


def _test_per_patient(path: str, report: dict[str, Any]) -> str:
    cnn, baseline = (report["per_patient"][n] for n in ("cnn-seed-0", "baseline"))
    rows = [
        [
            a["patient"],
            _cell(a["S"]["recall"]),
            _cell(a["S"]["precision"]),
            _cell(b["S"]["recall"]),
            _cell(b["S"]["precision"]),
            _cell(a["V"]["recall"]),
            _cell(a["V"]["precision"]),
            _cell(b["V"]["recall"]),
            _cell(b["V"]["precision"]),
        ]
        for a, b in zip(cnn, baseline, strict=True)
    ]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            table(
                [
                    "Patient",
                    "CNN S recall",
                    "CNN S precision",
                    "Baseline S recall",
                    "Baseline S precision",
                    "CNN V recall",
                    "CNN V precision",
                    "Baseline V recall",
                    "Baseline V precision",
                ],
                rows,
            ),
        ]
    )


def _matrix(matrix: Sequence[Sequence[int]]) -> str:
    return table(
        ["True class", *(f"Labeled {c}" for c in SCORED_CLASSES)],
        [
            [c, *(str(n) for n in row)]
            for c, row in zip(SCORED_CLASSES, matrix, strict=True)
        ],
    )


def _test_confusion(path: str, report: dict[str, Any]) -> str:
    confusion = report["confusion"]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            f"{confusion['note']}: {confusion['q_not_scored']} Q beats.",
            "",
            "CNN seed 0:",
            "",
            _matrix(confusion["matrices"]["cnn-seed-0"]),
            "",
            "Baseline:",
            "",
            _matrix(confusion["matrices"]["baseline"]),
        ]
    )


def _test_n_f(path: str, report: dict[str, Any]) -> str:
    block = report["n_and_f"]
    return "\n".join(
        [
            _test_source(path, report),
            "",
            _pair_table(
                report, block, ("N_recall", "N_precision", "F_recall", "F_precision")
            ),
            "",
            f"F caveat: {block['caveat']}.",
        ]
    )


def _test_seed_range(path: str, report: dict[str, Any]) -> str:
    seeds = report["seed_range"]
    head = report["headline"]["intervals"]["cnn"]
    rows = []
    for m in (*HEADLINE, "S_fpr", "V_fpr"):
        span = seeds["range"][m]
        rows.append(
            [
                METRIC_LABELS[m],
                num(head[m]["point"]),
                "undefined"
                if span is None
                else f"{num(span['min'])} to {num(span['max'])}",
            ]
        )
    return "\n".join(
        [
            _test_source(path, report),
            "",
            table(["Metric", "Seed 0", "Seeds 1 and 2"], rows),
        ]
    )


def _test_calibration(path: str, report: dict[str, Any]) -> str:
    rows = []
    names = {"cnn-seed-0": "CNN seed 0", "cnn-seed-1": "CNN seed 1"}
    names |= {"cnn-seed-2": "CNN seed 2", "baseline": "Baseline"}
    for key, label in names.items():
        c = report["calibration"][key]
        rows.append(
            [
                label,
                num(c["temperature"]),
                num(c["ece"]["S"]),
                num(c["ece"]["V"]),
                num(c["log_loss"]),
                num(c["brier"]),
            ]
        )
    parts = [
        _test_source(path, report),
        "",
        table(
            [
                "Model",
                "Temperature",
                "S calibration error",
                "V calibration error",
                "Log loss",
                "Brier",
            ],
            rows,
        ),
    ]
    for cls in ("S", "V"):
        bins = report["calibration"]["cnn-seed-0"]["reliability"][cls]
        parts += [
            "",
            f"Reliability, CNN seed 0, class {cls} (equal-mass bins):",
            "",
            table(
                ["Bin", "Beats", "Mean probability", "Observed rate"],
                [
                    [
                        str(k + 1),
                        str(b["count"]),
                        num(b["mean_probability"]),
                        num(b["observed_rate"]),
                    ]
                    for k, b in enumerate(bins)
                ],
            ),
        ]
    return "\n".join(parts)


# Data card blocks


def _counts(row: Mapping[str, int] | None, classes: Sequence[str]) -> list[str]:
    if row is None:
        return ["not loaded"] * (len(classes) + 1)
    return [*(str(row[c]) for c in classes), str(sum(row[c] for c in classes))]


DATA_SOURCE_LABEL = (
    "annotated beats from PhysioNet's published per-record table, DS1 and DS2; "
    "kept beats from the DS1 prepared files"
)


def data_counts(sources: CardSources) -> str:
    """Class counts per set: annotated beats, and DS1's kept beats."""
    summary = sources.result("data_summary")
    classes = summary["classes"]
    rows = []
    for name in ("DS1", "DS2"):
        block = summary["sets"][name]
        rows.append([name, "annotated", *_counts(block["annotated"], classes)])
        if block["kept"] is not None:
            rows.append([name, "kept", *_counts(block["kept"], classes)])
    return "\n".join(
        [
            source(["results/data_summary.json"], DATA_SOURCE_LABEL),
            "",
            "Kept beats leave out the first and last beat of each record. DS2's "
            "own beats are not loaded before the sealed run, so its row is the "
            "published table.",
            "",
            table(["Set", "Beats", *classes, "Total"], rows),
        ]
    )


def data_counts_per_record(sources: CardSources) -> str:
    """Annotated class counts per record, with DS1's kept total."""
    summary = sources.result("data_summary")
    classes = summary["classes"]
    rows = [
        [
            r["record"],
            r["set"],
            *(str(r["annotated"][c]) for c in classes),
            "not loaded" if r["kept"] is None else str(sum(r["kept"].values())),
        ]
        for r in summary["records"]
    ]
    return "\n".join(
        [
            source(["results/data_summary.json"], DATA_SOURCE_LABEL),
            "",
            table(["Record", "Set", *classes, "Kept"], rows),
        ]
    )


def data_demographics(sources: CardSources) -> str:
    """Age and sex per set, from the record headers."""
    summary = sources.result("data_summary")
    rows = []
    for name in ("DS1", "DS2"):
        d = summary["demographics"][name]
        ages = (
            "unknown" if d["age_min"] is None else f"{d['age_min']} to {d['age_max']}"
        )
        median = "unknown" if d["age_median"] is None else f"{d['age_median']:g}"
        rows.append(
            [
                name,
                str(d["patients"]),
                str(d["men"]),
                str(d["women"]),
                str(d["sex_unknown"]),
                ages,
                median,
                str(d["age_unknown"]),
            ]
        )
    unparsed = summary["unparsed"]
    note = (
        "Every header gives an age and a sex."
        if not unparsed
        else "Header values that do not parse, counted as unknown: "
        + ", ".join(f"record {u['record']} ({u['field']})" for u in unparsed)
        + "."
    )
    return "\n".join(
        [
            source(["results/data_summary.json"], "the record headers, DS1 and DS2"),
            "",
            table(
                [
                    "Set",
                    "Patients",
                    "Men",
                    "Women",
                    "Sex unknown",
                    "Age range",
                    "Median age",
                    "Age unknown",
                ],
                rows,
            ),
            "",
            note,
        ]
    )


def shipped_data(sources: CardSources) -> str:
    """Pending until the demo data exists (Phases 6 and 7)."""
    return SHIPPED_PENDING


MODEL_CARD_BLOCKS: Mapping[str, Callable[[CardSources], str]] = {
    "model_details": model_details,
    "test_headline": headline_block,
    "test_comparison": _test_block(_test_comparison),
    "test_fpr": _test_block(_test_fpr),
    "test_s_without_232": _test_block(_test_s_without),
    "test_per_patient": _test_block(_test_per_patient),
    "test_confusion": _test_block(_test_confusion),
    "test_n_f": _test_block(_test_n_f),
    "test_seed_range": _test_block(_test_seed_range),
    "calibration_fit": calibration_fit,
    "test_calibration": _test_block(_test_calibration),
    "dev_selection": dev_selection,
    "exhibit": exhibit,
}
DATA_CARD_BLOCKS: Mapping[str, Callable[[CardSources], str]] = {
    "data_counts": data_counts,
    "data_counts_per_record": data_counts_per_record,
    "data_demographics": data_demographics,
    "shipped_data": shipped_data,
}


def render_blocks(
    renderers: Mapping[str, Callable[[CardSources], str]], sources: CardSources
) -> dict[str, str]:
    """Every block's text."""
    return {name: render(sources) for name, render in renderers.items()}


def card_specs(
    model_card: Path, data_card: Path
) -> list[tuple[Path, Mapping[str, Callable[[CardSources], str]]]]:
    """Each card with its renderers."""
    return [(model_card, MODEL_CARD_BLOCKS), (data_card, DATA_CARD_BLOCKS)]
