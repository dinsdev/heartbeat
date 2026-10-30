"""EVAL-02, EVAL-03: make-folds and check-folds on synthetic data (R13, R14)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from heartbeat import cli
from heartbeat.cli import main
from heartbeat.config import DataSettings, FoldSettings, Settings
from heartbeat.constants import N_FOLDS, WINDOW_SAMPLES
from heartbeat.data import folds as folds_module
from heartbeat.data.folds import (
    FoldCheckError,
    Folds,
    check_folds,
    make_folds,
    read_folds,
    write_folds,
)
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits

DS1 = tuple(f"{r}" for r in range(301, 313))  # 12 synthetic DS1 records
SPLITS = Splits(
    ds1=(*DS1[:-1], "201"),
    ds2=("100", "103"),
    excluded={"202": "same subject as 201", "102": "paced"},
    lead="MLII",
)
SUBJECTS = {r: f"s{r}" for r in (*SPLITS.ds1, "100", "103", "102")} | {"202": "s201"}
DS1_SUBJECTS = sorted(SUBJECTS[r] for r in SPLITS.ds1)


def _beats(include_q: bool = False) -> BeatTable:
    rng = np.random.default_rng(0)
    rows: list[tuple[str, str]] = []
    for i, record in enumerate(SPLITS.ds1):
        classes = ["N"] * 40 + ["S"] * (1 + i % 3) + ["V"] * (2 + i % 4)
        classes += ["F"] * (3 if i % 4 == 0 else 0)
        classes += ["Q"] if include_q else []
        rows.extend((record, c) for c in classes)
    n = len(rows)
    return BeatTable(
        record_id=np.array([r for r, _ in rows]),
        subject_id=np.array([SUBJECTS[r] for r, _ in rows]),
        sample=np.arange(n, dtype=np.int64) * 300 + 400,
        beat_class=np.array([c for _, c in rows]),
        window_adu=rng.integers(-500, 500, (n, WINDOW_SAMPLES)).astype(np.int16),
        rr_s=np.ones((n, 6)),
    )


def _manifests(tmp_path: Path) -> tuple[Path, Path]:
    splits = tmp_path / "splits.toml"
    subjects = tmp_path / "subjects.toml"
    splits.write_text("synthetic splits\n", encoding="utf-8")
    subjects.write_text("synthetic subjects\n", encoding="utf-8")
    return splits, subjects


def _make(tmp_path: Path, seed: int = 20261026) -> Folds:
    return make_folds(_beats(), seed, manifest_paths=_manifests(tmp_path))


def _write_with_pin(tmp_path: Path, folds: Folds) -> tuple[Path, Path]:
    folds_path = tmp_path / "folds.json"
    write_folds(folds, folds_path)
    pin = tmp_path / "folds.sha256"
    digest = hashlib.sha256(folds_path.read_bytes()).hexdigest()
    pin.write_text(f"{digest}  config/folds.json\n", encoding="utf-8")
    return folds_path, pin


def _check(tmp_path: Path, folds_path: Path, pin: Path) -> Folds:
    return check_folds(
        folds_path, pin, SPLITS, SUBJECTS, manifest_paths=_manifests(tmp_path)
    )


def _replant(folds_path: Path, pin: Path, text: str) -> None:
    """Write a changed fold file and re-pin it, so only the content check is left."""
    folds_path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(folds_path.read_bytes()).hexdigest()
    pin.write_text(f"{digest}  config/folds.json\n", encoding="utf-8")


# make_folds


def test_make_folds_is_deterministic_for_one_seed(tmp_path: Path) -> None:
    assert _make(tmp_path) == _make(tmp_path)


def test_every_subject_is_in_exactly_one_fold(tmp_path: Path) -> None:
    folds = _make(tmp_path)
    assert sorted(folds.subject_fold) == DS1_SUBJECTS
    assert set(folds.subject_fold.values()) == set(range(N_FOLDS))


def test_class_counts_add_up_to_the_scored_beats(tmp_path: Path) -> None:
    folds = make_folds(_beats(include_q=True), 1, manifest_paths=_manifests(tmp_path))
    beats = _beats()
    for cls in ("N", "S", "V", "F"):
        total = sum(counts.get(cls, 0) for counts in folds.class_counts.values())
        assert total == int(np.sum(beats.beat_class == cls))
    assert all("Q" not in counts for counts in folds.class_counts.values())
    assert sorted(folds.class_counts) == [str(k) for k in range(N_FOLDS)]


def test_fold_file_records_seed_version_and_manifest_hashes(tmp_path: Path) -> None:
    import sklearn

    folds = _make(tmp_path, seed=7)
    splits, subjects = _manifests(tmp_path)
    assert folds.seed == 7
    assert folds.sklearn_version == sklearn.__version__
    assert folds.manifest_sha256 == {
        "splits.toml": hashlib.sha256(splits.read_bytes()).hexdigest(),
        "subjects.toml": hashlib.sha256(subjects.read_bytes()).hexdigest(),
    }


def test_make_folds_uses_the_sklearn_splitter_as_settled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    from sklearn.model_selection import StratifiedGroupKFold

    def spy(**kwargs: object) -> object:
        seen.update(kwargs)
        return StratifiedGroupKFold(**kwargs)

    monkeypatch.setattr(folds_module, "StratifiedGroupKFold", spy)
    _make(tmp_path, seed=20261026)
    assert seen == {"n_splits": 5, "shuffle": True, "random_state": 20261026}


# write_folds and read_folds


def test_write_is_canonical_json(tmp_path: Path) -> None:
    folds = _make(tmp_path)
    path = tmp_path / "folds.json"
    write_folds(folds, path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    assert read_folds(path) == folds


def test_write_refuses_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "folds.json"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_folds(_make(tmp_path), path)
    assert path.read_text(encoding="utf-8") == "{}\n"


# check_folds: a valid file passes


def test_valid_pinned_file_passes(tmp_path: Path) -> None:
    folds = _make(tmp_path)
    folds_path, pin = _write_with_pin(tmp_path, folds)
    assert _check(tmp_path, folds_path, pin) == folds


# R14: the pinned hash, and no regeneration


@pytest.mark.rule("R14")
def test_one_flipped_byte_fails_on_the_pinned_hash(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = bytearray(folds_path.read_bytes())
    index = data.index(b'"seed"') + 1
    data[index] ^= 0x01
    folds_path.write_bytes(bytes(data))
    with pytest.raises(FoldCheckError, match="SHA256"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R14")
def test_a_valid_but_different_fold_file_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path, seed=1))
    folds_path.unlink()
    write_folds(_make(tmp_path, seed=2), folds_path)
    with pytest.raises(FoldCheckError, match="SHA256"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R14")
def test_missing_pin_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    pin.unlink()
    with pytest.raises(FoldCheckError, match="pin"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R14")
def test_malformed_pin_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    pin.write_text("not a hash\n", encoding="utf-8")
    with pytest.raises(FoldCheckError, match="pin"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R14")
def test_missing_fold_file_fails_naming_make_folds(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    folds_path.unlink()
    with pytest.raises(FoldCheckError, match="make-folds"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R14")
def test_check_folds_never_calls_the_splitter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds = _make(tmp_path)
    folds_path, pin = _write_with_pin(tmp_path, folds)

    def refuse(**kwargs: object) -> object:
        raise AssertionError("check_folds must not regenerate folds")

    monkeypatch.setattr(folds_module, "StratifiedGroupKFold", refuse)
    monkeypatch.setattr(folds_module, "make_folds", refuse)
    assert _check(tmp_path, folds_path, pin) == folds


# R13: no subject on both sides of any fold, on planted files


@pytest.mark.rule("R13")
def test_one_subject_in_two_folds_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    text = folds_path.read_text(encoding="utf-8")
    fold = read_folds(folds_path).subject_fold["s301"]
    other = (fold + 1) % N_FOLDS
    # A JSON object with the subject twice, once per fold.
    planted = text.replace(
        f'"s301": {fold},', f'"s301": {fold},\n    "s301": {other},', 1
    )
    assert planted != text
    _replant(folds_path, pin, planted)
    with pytest.raises(FoldCheckError, match=r"s301.*two folds"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R13")
def test_a_ds2_subject_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = json.loads(folds_path.read_text(encoding="utf-8"))
    data["subject_fold"]["s100"] = 0
    _replant(folds_path, pin, json.dumps(data, indent=2, sort_keys=True) + "\n")
    with pytest.raises(FoldCheckError, match=r"s100.*DS2"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R13")
def test_an_excluded_subject_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = json.loads(folds_path.read_text(encoding="utf-8"))
    data["subject_fold"]["s102"] = 0
    _replant(folds_path, pin, json.dumps(data, indent=2, sort_keys=True) + "\n")
    with pytest.raises(FoldCheckError, match=r"s102.*excluded"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R13")
def test_a_missing_ds1_subject_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = json.loads(folds_path.read_text(encoding="utf-8"))
    del data["subject_fold"]["s305"]
    _replant(folds_path, pin, json.dumps(data, indent=2, sort_keys=True) + "\n")
    with pytest.raises(FoldCheckError, match=r"s305.*missing"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R13")
def test_201_and_202_split_apart_fails(tmp_path: Path) -> None:
    # A file made as if 202 were its own subject: s201 in one fold, s202 in another.
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = json.loads(folds_path.read_text(encoding="utf-8"))
    data["subject_fold"]["s202"] = (data["subject_fold"]["s201"] + 1) % N_FOLDS
    _replant(folds_path, pin, json.dumps(data, indent=2, sort_keys=True) + "\n")
    with pytest.raises(FoldCheckError, match="s202"):
        _check(tmp_path, folds_path, pin)


@pytest.mark.rule("R13")
def test_fold_made_from_other_manifests_fails(tmp_path: Path) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    (tmp_path / "subjects.toml").write_text(
        "202 is its own subject\n", encoding="utf-8"
    )
    with pytest.raises(FoldCheckError, match=r"subjects\.toml"):
        check_folds(
            folds_path,
            pin,
            SPLITS,
            SUBJECTS,
            manifest_paths=(tmp_path / "splits.toml", tmp_path / "subjects.toml"),
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(subject_fold={**d["subject_fold"], "s301": 5}), "fold 5"),
        (lambda d: d.update(seed="1"), "seed"),
        (lambda d: d.pop("class_counts"), "class_counts"),
        (lambda d: d.update(extra=1), "extra"),
    ],
)
def test_schema_errors_fail(tmp_path: Path, change: object, message: str) -> None:
    folds_path, pin = _write_with_pin(tmp_path, _make(tmp_path))
    data = json.loads(folds_path.read_text(encoding="utf-8"))
    change(data)  # type: ignore[operator]
    _replant(folds_path, pin, json.dumps(data, indent=2, sort_keys=True) + "\n")
    with pytest.raises(FoldCheckError, match=message):
        _check(tmp_path, folds_path, pin)


# The CLI, in process (the shell form of make-folds is Din's, F5)


def _cli_settings(tmp_path: Path) -> Settings:
    return Settings(
        data=DataSettings(
            raw_dir=tmp_path / "raw",
            prepared_dir=tmp_path / "prepared",
            sources=("https://a.example/",),
        ),
        folds=FoldSettings(seed=20261026),
    )


def _patch_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda _: _cli_settings(tmp_path))
    monkeypatch.setattr(cli, "load_splits", lambda _: SPLITS)
    monkeypatch.setattr(cli, "load_subjects", lambda _: SUBJECTS)
    monkeypatch.setattr(cli, "load_ds1", lambda *a, **k: _beats())
    monkeypatch.setattr(cli, "FOLD_MANIFESTS", _manifests(tmp_path))


def test_make_folds_and_check_folds_in_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli(tmp_path, monkeypatch)
    out = tmp_path / "out" / "folds.json"
    assert main(["make-folds", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "fold 0:" in printed
    assert "sha256" in printed
    assert read_folds(out).seed == 20261026
    # A second run refuses to overwrite.
    assert main(["make-folds", "--out", str(out)]) == 1
    assert "exists" in capsys.readouterr().err

    pin = tmp_path / "folds.sha256"
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    pin.write_text(f"{digest}  config/folds.json\n", encoding="utf-8")
    monkeypatch.setattr(cli, "FOLDS_JSON", out)
    monkeypatch.setattr(cli, "FOLDS_PIN", pin)
    assert main(["check-folds"]) == 0
    assert "ok" in capsys.readouterr().out
    pin.write_text(f"{'0' * 64}  config/folds.json\n", encoding="utf-8")
    assert main(["check-folds"]) == 1
    assert "SHA256" in capsys.readouterr().err
