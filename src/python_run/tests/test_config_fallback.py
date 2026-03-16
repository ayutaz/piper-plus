"""
Tests for PiperVoice.load() config path fallback logic.

Verifies the three-tier resolution:
  1. {model}.onnx.json  (auto-detected)
  2. config.json         (fallback in same directory)
  3. FileNotFoundError   (neither exists)
"""

import json
import shutil
from pathlib import Path

import pytest


# Guard: skip entire module when onnxruntime is unavailable
ort = pytest.importorskip("onnxruntime", reason="onnxruntime is required")

from piper.voice import PiperVoice  # noqa: E402


# Absolute path to the real test model shipped with the repo
_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/python_run/tests -> repo root
_TEST_MODEL = _REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
_TEST_CONFIG = _REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx.json"


@pytest.fixture()
def config_dict():
    """Return the reference config dict from the test model."""
    with open(_TEST_CONFIG, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Helper: copy the real .onnx into tmp_path so each test is isolated
# ------------------------------------------------------------------
def _copy_model(tmp_path: Path) -> Path:
    """Copy the real ONNX model into *tmp_path* and return its path."""
    dest = tmp_path / "model.onnx"
    shutil.copy2(_TEST_MODEL, dest)
    return dest


class TestConfigFallback:
    """PiperVoice.load() config resolution."""

    @pytest.mark.unit
    def test_onnx_json_auto_detected(self, tmp_path, config_dict):
        """{model}.onnx.json is picked up when config_path is None."""
        model_path = _copy_model(tmp_path)
        config_path = tmp_path / "model.onnx.json"
        config_path.write_text(json.dumps(config_dict), encoding="utf-8")

        voice = PiperVoice.load(model_path)

        assert voice.config.sample_rate == config_dict["audio"]["sample_rate"]
        assert len(voice.config.phoneme_id_map) > 0

    @pytest.mark.unit
    def test_config_json_fallback(self, tmp_path, config_dict):
        """config.json in the same directory is used when .onnx.json is absent."""
        model_path = _copy_model(tmp_path)
        # Do NOT create model.onnx.json; place config.json instead
        fallback_path = tmp_path / "config.json"
        fallback_path.write_text(json.dumps(config_dict), encoding="utf-8")

        voice = PiperVoice.load(model_path)

        assert voice.config.sample_rate == config_dict["audio"]["sample_rate"]
        assert len(voice.config.phoneme_id_map) > 0

    @pytest.mark.unit
    def test_no_config_raises(self, tmp_path):
        """FileNotFoundError is raised when no config file exists at all."""
        model_path = _copy_model(tmp_path)
        # No config files in tmp_path

        with pytest.raises(FileNotFoundError):
            PiperVoice.load(model_path)
