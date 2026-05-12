"""Tests for scripts/check_onnx_inputs.py.

Pins the gate's behaviour after PR #320 / Issue #426 — namely:
- speaker_embedding / speaker_embedding_mask are now ordinary optional
    inputs (no longer rejected as "voice-cloning leak")
- truly unknown input names still fail
- --strict / --expected still enforces an exact match
- --allow-voice-cloning is a deprecated no-op
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_onnx_inputs.py"

onnx = pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")


def _load_check_module():
    """Load scripts/check_onnx_inputs.py as a module."""
    spec = importlib.util.spec_from_file_location("check_onnx_inputs", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_onnx_inputs"] = module
    spec.loader.exec_module(module)
    return module


check_mod = _load_check_module()


def _make_dummy_onnx(tmp_path: Path, input_names: list[str]) -> Path:
    """Build a tiny ONNX file whose graph declares the given inputs.

    The graph is structurally invalid for actual inference, but
    onnxruntime.InferenceSession only needs the input metadata to enumerate
    them — which is all check_onnx_inputs.py inspects.
    """
    inputs = [
        onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [1])
        for name in input_names
    ]
    output = onnx.helper.make_tensor_value_info("output", onnx.TensorProto.FLOAT, [1])
    # An Identity node on the first input keeps the graph load-able even
    # when the remaining inputs are unused.
    node = onnx.helper.make_node(
        "Identity", inputs=[input_names[0]], outputs=["output"]
    )
    graph = onnx.helper.make_graph([node], "dummy", inputs, [output])
    # opset 15 matches docs/spec/onnx-export-contract.toml
    model = onnx.helper.make_model(
        graph, opset_imports=[onnx.helper.make_opsetid("", 15)]
    )
    model.ir_version = 8
    path = tmp_path / "dummy.onnx"
    onnx.save(model, str(path))
    return path


class TestKnownOptionalInputs:
    """The post-PR #320 input set is what mainline runtimes feed."""

    def test_speaker_embedding_in_known_set(self):
        """speaker_embedding / mask must be KNOWN_OPTIONAL (not VC-leak)."""
        assert "speaker_embedding" in check_mod.KNOWN_OPTIONAL_INPUTS
        assert "speaker_embedding_mask" in check_mod.KNOWN_OPTIONAL_INPUTS

    def test_base_inputs_in_known_set(self):
        assert {"input", "input_lengths", "scales"} <= check_mod.KNOWN_OPTIONAL_INPUTS

    def test_optional_inputs_in_known_set(self):
        assert {"sid", "lid", "prosody_features"} <= check_mod.KNOWN_OPTIONAL_INPUTS


class TestCheck:
    """End-to-end behaviour of the check() function."""

    def test_base_only_accepts(self, tmp_path: Path):
        path = _make_dummy_onnx(tmp_path, ["input", "input_lengths", "scales"])
        ok, msg = check_mod.check(path, allow_voice_cloning=False, strict_expected=None)
        assert ok, msg
        assert "OK" in msg

    def test_speaker_embedding_no_longer_leak(self, tmp_path: Path):
        """Post-PR #320: declaring speaker_embedding/mask is normal."""
        path = _make_dummy_onnx(
            tmp_path,
            [
                "input",
                "input_lengths",
                "scales",
                "sid",
                "lid",
                "prosody_features",
                "speaker_embedding",
                "speaker_embedding_mask",
            ],
        )
        ok, msg = check_mod.check(path, allow_voice_cloning=False, strict_expected=None)
        assert ok, f"PR #320 era model should be accepted, got: {msg}"

    def test_unknown_input_rejected(self, tmp_path: Path):
        path = _make_dummy_onnx(
            tmp_path, ["input", "input_lengths", "scales", "foobar"]
        )
        ok, msg = check_mod.check(path, allow_voice_cloning=False, strict_expected=None)
        assert not ok
        assert "foobar" in msg
        assert "Unknown" in msg or "unknown" in msg

    def test_strict_match_accepts(self, tmp_path: Path):
        expected_inputs = ["input", "input_lengths", "scales", "lid"]
        path = _make_dummy_onnx(tmp_path, expected_inputs)
        ok, msg = check_mod.check(
            path, allow_voice_cloning=False, strict_expected=set(expected_inputs)
        )
        assert ok, msg

    def test_strict_extra_rejected(self, tmp_path: Path):
        expected = {"input", "input_lengths", "scales"}
        path = _make_dummy_onnx(tmp_path, ["input", "input_lengths", "scales", "sid"])
        ok, msg = check_mod.check(
            path, allow_voice_cloning=False, strict_expected=expected
        )
        assert not ok
        assert "sid" in msg

    def test_strict_missing_rejected(self, tmp_path: Path):
        expected = {"input", "input_lengths", "scales", "sid"}
        path = _make_dummy_onnx(tmp_path, ["input", "input_lengths", "scales"])
        ok, msg = check_mod.check(
            path, allow_voice_cloning=False, strict_expected=expected
        )
        assert not ok
        assert "sid" in msg

    def test_allow_voice_cloning_is_noop(self, tmp_path: Path):
        """Deprecated flag must not change the verdict either way."""
        path = _make_dummy_onnx(
            tmp_path,
            [
                "input",
                "input_lengths",
                "scales",
                "speaker_embedding",
                "speaker_embedding_mask",
            ],
        )
        ok_with = check_mod.check(path, allow_voice_cloning=True, strict_expected=None)
        ok_without = check_mod.check(
            path, allow_voice_cloning=False, strict_expected=None
        )
        assert ok_with == ok_without
        assert ok_with[0] is True


class TestGetInputNames:
    def test_preserves_graph_order(self, tmp_path: Path):
        names = ["input", "input_lengths", "scales", "sid", "prosody_features"]
        path = _make_dummy_onnx(tmp_path, names)
        assert check_mod.get_input_names(path) == names
