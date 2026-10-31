"""Single-file ONNX export and its checks (E2, E3; PARITY-01, PARITY-03, R25, R26).

`export_onnx` turns a final model into one self-contained ONNX file at opset
20 with a dynamic batch: inputs `window` `(batch, 1, 256)` and `rr`
`(batch, 6)`, float32, output `logits` `(batch, 4)` in `SCORED_CLASSES` order
(Phase 5 task plan, design call 3). The exporter's optimizer folds batch norm
into the convolutions; `export_onnx` drops the exporter's metadata (stack
traces with absolute paths, which made the bytes depend on the checkout's
location; Phase 5 stop 2). `check_onnx` refuses a file that still has a
BatchNormalization node, metadata, external data, other names or shapes, or
1 MB or more. `check_parity` compares PyTorch with Python ONNX Runtime within 1e-5
with equal labels.
"""

import hashlib
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import torch
from numpy.typing import NDArray

from heartbeat.constants import (
    MODEL_SIZE_LIMIT_BYTES,
    ONNX_OPSET,
    PARITY_TOLERANCE,
    RR_FEATURE_NAMES,
    SCORED_CLASSES,
    WINDOW_SAMPLES,
)
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.sealed.score import (
    INPUT_NAMES,
    OUTPUT_NAME,
    onnx_logits,
    onnx_session,
)
from heartbeat.train.loop import cnn_logits

# The dynamic batch dimension's name in the exported file.
BATCH_DIM = "batch"

_EXPECTED_IO = {
    "inputs": [
        (INPUT_NAMES[0], [BATCH_DIM, 1, WINDOW_SAMPLES]),
        (INPUT_NAMES[1], [BATCH_DIM, len(RR_FEATURE_NAMES)]),
    ],
    "outputs": [(OUTPUT_NAME, [BATCH_DIM, len(SCORED_CLASSES)])],
}


class ExportError(RuntimeError):
    """An export input or output breaks a rule (stop conditions 3 and 4)."""


class SizeGateError(ExportError):
    """A model file is 1 MB or more (R25, D5)."""


class ParityError(ExportError):
    """PyTorch and ONNX Runtime disagree beyond 1e-5, or on a label (R26)."""


def load_checkpoint(path: Path, width: float, expected_sha256: str) -> HeartbeatCNN:
    """Load a final model's state dict on CPU, in eval mode.

    Raises:
        ExportError: If the file's SHA256 differs from the one recorded in
            `results/train_final.json`.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ExportError(
            f"{path}: sha256 {digest} differs from results/train_final.json "
            f"({expected_sha256}); rerun `uv run heartbeat rebuild --from train-final`"
        )
    model = HeartbeatCNN(width)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return model.eval()


def _dims(value: onnx.ValueInfoProto) -> list[str | int]:
    return [d.dim_param or d.dim_value for d in value.type.tensor_type.shape.dim]


def _rename_batch(model: onnx.ModelProto) -> None:
    # Dim.DYNAMIC exports the shared batch as a generated name ("s0"); name it.
    generated = {
        _dims(v)[0]
        for v in (*model.graph.input, *model.graph.output)
        if isinstance(_dims(v)[0], str)
    }
    if len(generated) != 1:
        raise ExportError(f"expected one dynamic batch dimension, got {generated}")
    (name,) = generated
    for value in (*model.graph.input, *model.graph.output, *model.graph.value_info):
        for dim in value.type.tensor_type.shape.dim:
            if dim.dim_param == name:
                dim.dim_param = BATCH_DIM


def _metadata_holders(model: onnx.ModelProto) -> list[Any]:
    # Every message that can carry metadata_props or a doc_string.
    graph = model.graph
    holders: list[Any] = [model, graph, *graph.node, *graph.initializer]
    holders += [*graph.input, *graph.output, *graph.value_info]
    for function in model.functions:
        holders += [function, *function.node]
    return holders


def _strip_metadata(model: onnx.ModelProto) -> None:
    for holder in _metadata_holders(model):
        del holder.metadata_props[:]
        holder.doc_string = ""


def export_onnx(model: HeartbeatCNN) -> bytes:
    """Export an eval-mode model to one ONNX file's bytes (deterministic)."""
    assert not model.training, "export in eval mode"
    example = (
        torch.zeros(2, 1, WINDOW_SAMPLES),
        torch.zeros(2, len(RR_FEATURE_NAMES)),
    )
    batch = torch.export.Dim.DYNAMIC
    with warnings.catch_warnings():
        # The exporter warns about its own internals on stable releases; none
        # of it changes the graph, which check_onnx verifies.
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.simplefilter("ignore", FutureWarning)
        program = torch.onnx.export(
            model,
            example,
            None,
            dynamo=True,
            opset_version=ONNX_OPSET,
            input_names=list(INPUT_NAMES),
            output_names=[OUTPUT_NAME],
            dynamic_shapes={INPUT_NAMES[0]: {0: batch}, INPUT_NAMES[1]: {0: batch}},
            external_data=False,
            verbose=False,
        )
    assert program is not None
    proto = program.model_proto
    _rename_batch(proto)
    _strip_metadata(proto)
    data: bytes = proto.SerializeToString()
    return data


def parameter_count(model: HeartbeatCNN) -> int:
    """Trainable parameters of the PyTorch model (before batch-norm folding)."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def check_onnx(data: bytes) -> dict[str, Any]:
    """Check one exported file against design call 3 and the size gate.

    Returns:
        Facts for `results/export.json`: bytes, opset and the sorted op types.

    Raises:
        SizeGateError: At 1 MB or more (R25).
        ExportError: On external data, a BatchNormalization node, metadata
            or doc strings, another opset, or input and output names and
            shapes other than design call 3's.
    """
    if len(data) >= MODEL_SIZE_LIMIT_BYTES:
        raise SizeGateError(
            f"model is {len(data)} bytes; the gate is under {MODEL_SIZE_LIMIT_BYTES}"
        )
    model = onnx.load_model_from_string(data)
    if any(
        t.data_location == onnx.TensorProto.EXTERNAL for t in model.graph.initializer
    ):
        raise ExportError("model keeps external data; export must be one file")
    ops = sorted({node.op_type for node in model.graph.node})
    if "BatchNormalization" in ops:
        raise ExportError("model keeps a BatchNormalization node; it must be folded")
    if any(h.metadata_props or h.doc_string for h in _metadata_holders(model)):
        raise ExportError("model keeps metadata or doc strings; export strips them")
    opsets = [(o.domain, o.version) for o in model.opset_import]
    if opsets != [("", ONNX_OPSET)]:
        raise ExportError(f"model opsets {opsets}, expected opset {ONNX_OPSET}")
    found = {
        "inputs": [(v.name, _dims(v)) for v in model.graph.input],
        "outputs": [(v.name, _dims(v)) for v in model.graph.output],
    }
    for side in ("inputs", "outputs"):
        if found[side] != _EXPECTED_IO[side]:
            raise ExportError(
                f"model {side} {found[side]}, expected {_EXPECTED_IO[side]}"
            )
    onnx.checker.check_model(model, full_check=True)
    return {"bytes": len(data), "opset": ONNX_OPSET, "ops": ops}


def pytorch_logits(
    model: HeartbeatCNN, windows: NDArray[np.float32], rr: NDArray[np.float32]
) -> NDArray[np.float32]:
    """Raw PyTorch logits on CPU, the scoring path of training (`cnn_logits`)."""
    return cnn_logits(model, windows, rr, torch.device("cpu"))


def check_parity(
    model: HeartbeatCNN,
    data: bytes,
    windows: NDArray[np.float32],
    rr: NDArray[np.float32],
) -> float:
    """Compare PyTorch with Python ONNX Runtime on the same inputs (R26).

    Returns:
        The largest absolute logit difference.

    Raises:
        ParityError: If any logit differs by more than 1e-5, or any label
            (argmax) differs.
    """
    expected = pytorch_logits(model, windows, rr)
    got = onnx_logits(onnx_session(data), windows, rr)
    diff = float(np.max(np.abs(got.astype(np.float64) - expected))) if got.size else 0.0
    if not diff <= PARITY_TOLERANCE:
        raise ParityError(
            f"ONNX Runtime differs from PyTorch by {diff:.3g}, tolerance "
            f"{PARITY_TOLERANCE}; stop and ask Din (Phase 5 plan, stop 3)"
        )
    same = predict_labels(got.astype(np.float64)) == predict_labels(
        expected.astype(np.float64)
    )
    if not np.all(same):
        raise ParityError(
            f"ONNX Runtime changes the label of {int((~same).sum())} beats; "
            "stop and ask Din (Phase 5 plan, stop 3)"
        )
    return diff


def parity_survey(
    model: HeartbeatCNN,
    data: bytes,
    windows: NDArray[np.float32],
    rr: NDArray[np.float32],
) -> dict[str, Any]:
    """PyTorch against ONNX Runtime on many beats: labels gated, logits measured.

    Returns:
        The largest absolute logit difference, the beats whose difference is
        above 1e-5, and the label changes (always 0 on return).

    Raises:
        ParityError: If any label (argmax) differs.
    """
    expected = pytorch_logits(model, windows, rr).astype(np.float64)
    got = onnx_logits(onnx_session(data), windows, rr).astype(np.float64)
    changed = int(np.sum(predict_labels(got) != predict_labels(expected)))
    if changed:
        raise ParityError(
            f"ONNX Runtime changes the label of {changed} beats; "
            "stop and ask Din (Phase 5 plan, stop 3)"
        )
    per_beat = np.max(np.abs(got - expected), axis=1) if got.size else np.zeros(0)
    return {
        "max_abs_diff": float(per_beat.max()) if per_beat.size else 0.0,
        "over_tolerance": int(np.sum(per_beat > PARITY_TOLERANCE)),
        "label_changes": changed,
    }
