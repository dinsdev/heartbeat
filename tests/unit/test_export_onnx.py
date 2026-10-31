"""E2, E3, PARITY-01, R25, R26: single-file ONNX export and its checks."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import pytest
import torch
from numpy.typing import NDArray
from onnx import helper
from onnxruntime import InferenceSession

from heartbeat.constants import MODEL_SIZE_LIMIT_BYTES, ONNX_OPSET, PARITY_TOLERANCE
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.export import onnx as onnx_module
from heartbeat.export.onnx import (
    ExportError,
    ParityError,
    SizeGateError,
    check_onnx,
    check_parity,
    export_onnx,
    load_checkpoint,
    parity_survey,
    pytorch_logits,
)
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.paths import REPO_ROOT
from heartbeat.sealed.score import onnx_logits, onnx_session

WIDTH = 0.5


def _model(seed: int = 3) -> HeartbeatCNN:
    torch.manual_seed(seed)
    model = HeartbeatCNN(WIDTH)
    # Batch-norm statistics away from their defaults, so folding matters.
    with torch.no_grad():
        for module in model.modules():
            if isinstance(module, torch.nn.BatchNorm1d):
                assert module.running_mean is not None
                assert module.running_var is not None
                module.running_mean.uniform_(-0.5, 0.5)
                module.running_var.uniform_(0.5, 2.0)
                module.weight.uniform_(0.5, 1.5)
                module.bias.uniform_(-0.2, 0.2)
    return model.eval()


def _inputs(n: int, seed: int = 0) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    rng = np.random.default_rng(seed)
    windows = rng.standard_normal((n, 1, 256)).astype(np.float32)
    rr = rng.standard_normal((n, 6)).astype(np.float32)
    return windows, rr


@pytest.fixture(scope="module")
def exported() -> bytes:
    return export_onnx(_model())


def _dims(value: onnx.ValueInfoProto) -> list[str | int]:
    return [d.dim_param or d.dim_value for d in value.type.tensor_type.shape.dim]


@pytest.mark.rule("R25")
def test_the_export_is_one_self_contained_file_at_opset_20(exported: bytes) -> None:
    model = onnx.load_model_from_string(exported)
    onnx.checker.check_model(model, full_check=True)
    assert [(o.domain, o.version) for o in model.opset_import] == [("", ONNX_OPSET)]
    assert not any(
        t.data_location == onnx.TensorProto.EXTERNAL for t in model.graph.initializer
    )
    assert "BatchNormalization" not in {n.op_type for n in model.graph.node}
    assert len(exported) < MODEL_SIZE_LIMIT_BYTES
    facts = check_onnx(exported)
    assert facts["bytes"] == len(exported)
    assert facts["opset"] == ONNX_OPSET


def test_inputs_and_output_are_named_and_shaped_with_a_dynamic_batch(
    exported: bytes,
) -> None:
    model = onnx.load_model_from_string(exported)
    assert [(i.name, _dims(i)) for i in model.graph.input] == [
        ("window", ["batch", 1, 256]),
        ("rr", ["batch", 6]),
    ]
    assert [(o.name, _dims(o)) for o in model.graph.output] == [
        ("logits", ["batch", 4])
    ]
    for value in (*model.graph.input, *model.graph.output):
        assert value.type.tensor_type.elem_type == onnx.TensorProto.FLOAT


@pytest.mark.rule("R26")
@pytest.mark.parametrize("n", [1, 5, 33])
def test_onnx_runtime_matches_pytorch_at_any_batch_size(
    exported: bytes, n: int
) -> None:
    windows, rr = _inputs(n, seed=n)
    expected = pytorch_logits(_model(), windows, rr)
    got = onnx_logits(onnx_session(exported), windows, rr)
    assert got.dtype == np.float32
    np.testing.assert_allclose(got, expected, rtol=0, atol=PARITY_TOLERANCE)
    np.testing.assert_array_equal(
        predict_labels(got.astype(np.float64)),
        predict_labels(expected.astype(np.float64)),
    )
    assert check_parity(_model(), exported, windows, rr) <= PARITY_TOLERANCE


@pytest.mark.rule("R26")
def test_a_parity_miss_raises(exported: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    windows, rr = _inputs(8)

    def off_by(
        session: InferenceSession, w: NDArray[np.float32], r: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        out = onnx_logits(session, w, r)
        out[0, 0] += 2 * PARITY_TOLERANCE
        return out

    monkeypatch.setattr(onnx_module, "onnx_logits", off_by)
    with pytest.raises(ParityError, match="1e-05"):
        check_parity(_model(), exported, windows, rr)


@pytest.mark.rule("R26")
def test_a_label_flip_within_tolerance_still_raises(
    exported: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows, rr = _inputs(4)
    ties = np.zeros((4, 4), dtype=np.float32)
    flipped = ties.copy()
    flipped[0, 1] = PARITY_TOLERANCE / 2
    monkeypatch.setattr(onnx_module, "pytorch_logits", lambda m, w, r: ties)
    monkeypatch.setattr(onnx_module, "onnx_logits", lambda s, w, r: flipped)
    with pytest.raises(ParityError, match="label"):
        check_parity(_model(), exported, windows, rr)


def _metadata(model: onnx.ModelProto) -> list[str]:
    graph = model.graph
    holders: list[Any] = [model, graph, *graph.node, *graph.initializer]
    holders += [*graph.input, *graph.output, *graph.value_info]
    for function in model.functions:
        holders += [function, *function.node]
    found = [f"{type(h).__name__}: {p.key}" for h in holders for p in h.metadata_props]
    return found + [f"{type(h).__name__} doc" for h in holders if h.doc_string]


def test_the_export_carries_no_metadata_or_local_paths(exported: bytes) -> None:
    # The exporter records stack traces with absolute paths; they made the
    # bytes depend on the checkout's location (Phase 5 stop 2).
    assert _metadata(onnx.load_model_from_string(exported)) == []
    for path in (REPO_ROOT, Path.home(), Path(torch.__file__).parent):
        assert str(path).encode() not in exported
    assert b".py" not in exported


def test_a_file_with_metadata_is_refused(exported: bytes) -> None:
    model = onnx.load_model_from_string(exported)
    entry = model.graph.node[0].metadata_props.add()
    entry.key, entry.value = "pkg.torch.onnx.stack_trace", '"/somewhere/cnn.py"'
    with pytest.raises(ExportError, match="metadata"):
        check_onnx(model.SerializeToString())


def test_two_exports_are_byte_identical(exported: bytes) -> None:
    again = export_onnx(_model())
    assert hashlib.sha256(again).hexdigest() == hashlib.sha256(exported).hexdigest()
    assert export_onnx(_model(seed=4)) != exported


@pytest.mark.rule("R25")
def test_a_model_of_the_limit_or_more_fails_the_size_gate(
    exported: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert MODEL_SIZE_LIMIT_BYTES == 1_000_000
    monkeypatch.setattr(onnx_module, "MODEL_SIZE_LIMIT_BYTES", len(exported))
    with pytest.raises(SizeGateError, match=str(len(exported))):
        check_onnx(exported)
    monkeypatch.setattr(onnx_module, "MODEL_SIZE_LIMIT_BYTES", len(exported) + 1)
    check_onnx(exported)


def _tiny_model(op: str, external: bool = False) -> bytes:
    weight = helper.make_tensor(
        "w", onnx.TensorProto.FLOAT, [1], np.ones(1, np.float32).tobytes(), raw=True
    )
    if external:
        onnx.external_data_helper.set_external_data(weight, location="weights.bin")
    nodes = (
        [helper.make_node(op, ["x", "w"], ["y"])]
        if op == "Mul"
        else [helper.make_node("BatchNormalization", ["x", "w", "w", "w", "w"], ["y"])]
    )
    graph = helper.make_graph(
        nodes,
        "g",
        [helper.make_tensor_value_info("x", onnx.TensorProto.FLOAT, [1, 1])],
        [helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, [1, 1])],
        [weight],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 20)])
    data: bytes = model.SerializeToString()
    return data


@pytest.mark.rule("R25")
def test_external_data_or_a_batch_norm_node_is_refused() -> None:
    with pytest.raises(ExportError, match="external"):
        check_onnx(_tiny_model("Mul", external=True))
    with pytest.raises(ExportError, match="BatchNormalization"):
        check_onnx(_tiny_model("BatchNormalization"))
    with pytest.raises(ExportError, match="inputs"):
        check_onnx(_tiny_model("Mul"))


def test_a_checkpoint_is_loaded_only_when_its_sha256_matches(tmp_path: Path) -> None:
    path = tmp_path / "model.pt"
    torch.save(_model().state_dict(), path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_checkpoint(path, WIDTH, digest)
    assert not loaded.training
    assert export_onnx(loaded) == export_onnx(_model())
    with pytest.raises(ExportError, match=r"results/train_final\.json"):
        load_checkpoint(path, WIDTH, "0" * 64)


@pytest.mark.rule("R26")
def test_the_survey_counts_differences_and_refuses_a_label_change(
    exported: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows, rr = _inputs(6)
    base = np.zeros((6, 4), dtype=np.float32)
    base[:, 0] = 1.0
    off = base.copy()
    off[2, 3] += 3 * PARITY_TOLERANCE
    monkeypatch.setattr(onnx_module, "pytorch_logits", lambda m, w, r: base)
    monkeypatch.setattr(onnx_module, "onnx_logits", lambda s, w, r: off)
    survey = parity_survey(_model(), exported, windows, rr)
    assert survey["over_tolerance"] == 1
    assert survey["label_changes"] == 0
    assert survey["max_abs_diff"] == pytest.approx(3 * PARITY_TOLERANCE)
    flipped = base.copy()
    flipped[4, 1] = 2.0
    monkeypatch.setattr(onnx_module, "onnx_logits", lambda s, w, r: flipped)
    with pytest.raises(ParityError, match="label of 1 beats"):
        parity_survey(_model(), exported, windows, rr)
