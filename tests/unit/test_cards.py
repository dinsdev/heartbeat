"""F6, R50: `heartbeat cards` renders every block from committed files."""

import json
from pathlib import Path

import pytest
from card_support import (
    FREEZE_COMMIT,
    FREEZE_DATE,
    log_sealed_run,
    plant_freeze_record,
    sources,
)

from heartbeat.cards.blocks import (
    DATA_CARD_BLOCKS,
    MODEL_CARD_BLOCKS,
    SHIPPED_PENDING,
    TEST_PENDING,
    CardSources,
    card_specs,
    render_blocks,
    table,
)
from heartbeat.cards.render import (
    CardError,
    block_bodies,
    block_names,
    pending_after_sealed,
    render_card,
    stale_blocks,
)
from heartbeat.checks.wording import check_dashes, check_published
from heartbeat.paths import DATA_CARD, MODEL_CARD

DS1_LABELS = ("DS1 out-of-fold, MPS", "DS1 out-of-fold, CPU")


@pytest.fixture
def card_sources(tmp_path: Path) -> CardSources:
    return sources(tmp_path)


def test_the_renderers_cover_every_marker_in_the_committed_cards() -> None:
    assert sorted(block_names(MODEL_CARD.read_text("utf-8"))) == sorted(
        MODEL_CARD_BLOCKS
    )
    assert sorted(block_names(DATA_CARD.read_text("utf-8"))) == sorted(DATA_CARD_BLOCKS)


@pytest.mark.rule("R50")
def test_each_ds1_block_names_its_source_and_label(card_sources: CardSources) -> None:
    blocks = render_blocks(MODEL_CARD_BLOCKS, card_sources)
    cv_cnn = json.loads((card_sources.results_dir / "cv_cnn.json").read_text())
    selection = json.loads((card_sources.results_dir / "selection.json").read_text())
    point = cv_cnn["bootstrap"]["intervals"]["macro_f1_nsv"]["point"]
    assert f"{point:.4f}" in blocks["dev_selection"]
    assert "`results/selection.json`" in blocks["dev_selection"]
    assert f"Width multiplier {selection['width']:g}" in blocks["model_details"]
    assert "Freeze" not in blocks["model_details"]
    assert "`results/export.json`" in blocks["model_details"]
    assert "`results/exhibit.json`" in blocks["exhibit"]
    assert "Accuracy" in blocks["exhibit"]
    assert "`results/cv_baseline.json`" in blocks["calibration_fit"]
    for name in ("dev_selection", "calibration_fit"):
        assert all(label in blocks[name] for label in DS1_LABELS), name
    data = render_blocks(DATA_CARD_BLOCKS, card_sources)
    for name in ("data_counts", "data_counts_per_record", "data_demographics"):
        assert "`results/data_summary.json`" in data[name], name
    assert "record 103 (age)" in data["data_demographics"]
    assert data["shipped_data"] == SHIPPED_PENDING


@pytest.mark.rule("R50")
def test_rendering_twice_gives_the_same_text(card_sources: CardSources) -> None:
    for card, renderers in card_specs(MODEL_CARD, DATA_CARD):
        text = card.read_text("utf-8")
        once = render_card(text, render_blocks(renderers, card_sources))
        twice = render_card(once, render_blocks(renderers, card_sources))
        assert once == twice
        assert stale_blocks(once, render_blocks(renderers, card_sources)) == []


@pytest.mark.rule("R50")
def test_a_hand_edited_block_is_stale(card_sources: CardSources) -> None:
    blocks = render_blocks(DATA_CARD_BLOCKS, card_sources)
    text = render_card(DATA_CARD.read_text("utf-8"), blocks)
    edited = text.replace("| DS1 | annotated |", "| DS1 | annotated  |", 1)
    edited = edited.replace(" 1860 ", " 1861 ", 1)
    assert edited != text
    assert stale_blocks(edited, blocks) != []
    prose = text.replace("## 1. Motivation", "## 1. Motivation, edited")
    assert stale_blocks(prose, blocks) == []


@pytest.mark.rule("R50")
def test_test_blocks_stay_pending_until_a_sealed_run_is_logged(
    card_sources: CardSources,
) -> None:
    blocks = render_blocks(MODEL_CARD_BLOCKS, card_sources)
    tests = [name for name in blocks if name.startswith("test_")]
    assert len(tests) == 9
    assert all(blocks[name] == TEST_PENDING for name in tests)
    pending = render_card(MODEL_CARD.read_text("utf-8"), blocks)
    log_sealed_run(card_sources)
    after = render_blocks(MODEL_CARD_BLOCKS, card_sources)
    for name in tests:
        assert after[name] != TEST_PENDING, name
        assert "`results/test_runs/1-sealed.json` (DS2 test, CPU" in after[name]
    assert sorted(pending_after_sealed(pending, TEST_PENDING)) == sorted(tests)
    assert sorted(stale_blocks(pending, after)) == sorted(tests)
    rendered = render_card(pending, after)
    assert pending_after_sealed(rendered, TEST_PENDING) == []


@pytest.mark.rule("R50")
def test_committing_the_freeze_record_changes_no_block(
    card_sources: CardSources,
) -> None:
    """Phase 7 settling 1.1: the freeze commit alone keeps `verify` green."""
    before = [
        render_blocks(renderers, card_sources)
        for _, renderers in card_specs(MODEL_CARD, DATA_CARD)
    ]
    plant_freeze_record(card_sources)
    after = [
        render_blocks(renderers, card_sources)
        for _, renderers in card_specs(MODEL_CARD, DATA_CARD)
    ]
    assert after == before


@pytest.mark.rule("R50")
def test_the_freeze_line_renders_from_the_sealed_report(
    card_sources: CardSources,
) -> None:
    log_sealed_run(card_sources)
    blocks = render_blocks(MODEL_CARD_BLOCKS, card_sources)
    line = f"Freeze commit `{FREEZE_COMMIT}`, dated {FREEZE_DATE}."
    assert line in blocks["test_headline"]
    assert "Freeze" not in blocks["model_details"]


def test_a_freeze_record_for_another_commit_stops_the_render(
    card_sources: CardSources,
) -> None:
    log_sealed_run(card_sources)
    plant_freeze_record(card_sources, commit="d" * 40)
    with pytest.raises(ValueError, match="freeze record"):
        render_blocks(MODEL_CARD_BLOCKS, card_sources)


def test_the_comparison_sentence_comes_from_the_rule(card_sources: CardSources) -> None:
    log_sealed_run(card_sources)
    text = render_blocks(MODEL_CARD_BLOCKS, card_sources)["test_comparison"]
    found = card_sources.sealed_report()
    assert found is not None
    verdict = found[1]["comparison"]["metrics"]["macro_f1_nsv"]["verdict"]
    sentence = {
        "CNN better than baseline": "The CNN is better than the baseline",
        "no clear difference": "No clear difference",
        "baseline better than CNN": "The CNN still ships",
    }[verdict]
    assert sentence in text


@pytest.mark.rule("R50")
@pytest.mark.parametrize("sealed", [False, True])
def test_rendered_cards_pass_the_wording_lint(
    card_sources: CardSources, sealed: bool
) -> None:
    if sealed:
        log_sealed_run(card_sources)
    for card, renderers in card_specs(MODEL_CARD, DATA_CARD):
        text = render_card(
            card.read_text("utf-8"), render_blocks(renderers, card_sources)
        )
        relative = Path("docs") / card.name
        assert check_published(relative, text) == []
        assert check_dashes(relative, text) == []


def test_markers_and_renderers_must_match() -> None:
    text = "a\n<!-- card:begin one -->\n\nx\n\n<!-- card:end one -->\n"
    assert block_bodies(text) == {"one": "x"}
    with pytest.raises(CardError, match="differ"):
        render_card(text, {"two": "y"})
    assert render_card(text, {"one": "y"}) == (
        "a\n<!-- card:begin one -->\n\ny\n\n<!-- card:end one -->\n"
    )
    twice = text + text
    with pytest.raises(CardError, match="twice"):
        render_card(twice, {"one": "y"})


def test_tables_follow_prettier_with_prose_wrap_never() -> None:
    narrow = table(["Set", "N"], [["DS1", "45866"]])
    assert narrow == "| Set | N     |\n| --- | ----- |\n| DS1 | 45866 |"
    cells = ["x" * 36, "y" * 37]
    assert len(table(["a", "b"], [cells]).splitlines()[0]) == 80
    wide = table(["a", "b"], [["x" * 36, "y" * 38]])
    assert wide.splitlines() == [
        "| a | b |",
        "| --- | --- |",
        f"| {'x' * 36} | {'y' * 38} |",
    ]
