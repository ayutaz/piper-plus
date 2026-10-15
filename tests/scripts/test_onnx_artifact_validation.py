"""Validate real ONNX bytes with ORT; text-token scans cannot satisfy this."""

import sys
from pathlib import Path

import numpy as np
import onnx
import pytest
from google.protobuf.message import DecodeError
from onnx import TensorProto, helper


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))
from piper_train.onnx_validation import check_fp16_parity, validate_export  # noqa: E402


def make_graph(path, *, nan=False):
    node = helper.make_node("Identity", ["x"], ["output"])
    inputs = [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])]
    if nan:
        node = helper.make_node(
            "Constant",
            [],
            ["output"],
            value=helper.make_tensor("bad", TensorProto.FLOAT, [1], [float("nan")]),
        )
    model = helper.make_model(
        helper.make_graph(
            [node],
            "probe",
            inputs,
            [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1])],
        ),
        opset_imports=[helper.make_opsetid("", 15)],
        ir_version=8,
    )
    onnx.save(model, path)


def test_executes_actual_export(tmp_path):
    path = tmp_path / "model.onnx"
    make_graph(path)
    outputs = validate_export(path, {"x": np.array([2], dtype=np.float32)})
    np.testing.assert_array_equal(outputs[0], [2])


def test_nonfinite_export_fails(tmp_path):
    path = tmp_path / "nan.onnx"
    make_graph(path, nan=True)
    with pytest.raises(ValueError, match="nonfinite"):
        validate_export(path, {"x": np.array([2], dtype=np.float32)})


def test_corrupted_export_fails(tmp_path):
    path = tmp_path / "corrupt.onnx"
    path.write_bytes(b"not ONNX")
    with pytest.raises(DecodeError):
        validate_export(path, {})


def test_fp16_parity_reports_bad_values():
    reference = [np.array([1.0], dtype=np.float32)]
    assert check_fp16_parity(reference, [np.array([1.001], dtype=np.float16)])
    assert not check_fp16_parity(reference, [np.array([2.0], dtype=np.float16)])


def test_export_source_comments_are_not_executable_validation(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_onnx_export_contract

    path = tmp_path / "fake.py"
    path.write_text(
        "OPSET_VERSION = 15\n# onnx.checker.check_model\n# onnx.shape_inference.infer_shapes\n"
    )
    assert check_onnx_export_contract.check_opset(path, 15, "probe")


@pytest.mark.parametrize(
    "source", ["export_onnx.py", "speaker_encoder/export_encoder.py"]
)
def test_both_export_paths_validate_fp32_and_converted_artifacts(source):
    import ast

    tree = ast.parse(
        (ROOT / "src/python/piper_train" / source).read_text(encoding="utf-8")
    )
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert calls.count("validate_export") >= 2
    assert "check_fp16_parity" in calls
