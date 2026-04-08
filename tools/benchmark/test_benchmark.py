#!/usr/bin/env python3
"""Tests for the benchmark tools.

These tests are designed to run without actual TTS models by using
mock/dummy data where inference would otherwise be needed.

Usage:
    uv run python -m pytest tools/benchmark/test_benchmark.py -v
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

# ---------------------------------------------------------------------------
# Locate project root and benchmark directory
# ---------------------------------------------------------------------------

BENCHMARK_DIR = Path(__file__).resolve().parent
TEXTS_DIR = BENCHMARK_DIR / "texts"
MODELS_YAML = BENCHMARK_DIR / "models.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_wav(path: Path, *, sample_rate: int = 22050, duration_sec: float = 1.0) -> None:
    """Create a minimal mono 16-bit WAV file with a sine wave."""
    n_frames = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n_frames, endpoint=False)
    # 440 Hz sine at -6 dBFS
    samples = (np.sin(2 * np.pi * 440 * t) * 16384).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def _create_silent_wav(path: Path, *, sample_rate: int = 22050, duration_sec: float = 1.0) -> None:
    """Create a silent mono 16-bit WAV file."""
    n_frames = int(sample_rate * duration_sec)
    data = b"\x00\x00" * n_frames
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


# ===========================================================================
# TestModelsConfig
# ===========================================================================


class TestModelsConfig:
    """models.yaml parsing tests."""

    def test_load_models_config(self):
        """models.yaml should parse correctly and contain expected keys."""
        with open(MODELS_YAML, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        models = raw.get("models", [])
        assert len(models) > 0, "models.yaml should define at least one model"

        for model in models:
            assert "name" in model, "Each model must have a 'name' key"
            assert "type" in model, "Each model must have a 'type' key"

    def test_known_model_types(self):
        """All model types should be known values."""
        with open(MODELS_YAML, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        known_types = {"piper-plus", "external"}
        for model in raw.get("models", []):
            assert model["type"] in known_types, (
                f"Unknown model type '{model['type']}' for model '{model['name']}'"
            )

    def test_piper_plus_models_have_path(self):
        """piper-plus type models must have a 'path' key."""
        with open(MODELS_YAML, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        for model in raw.get("models", []):
            if model["type"] == "piper-plus":
                assert "path" in model, (
                    f"piper-plus model '{model['name']}' must have a 'path' key"
                )

    def test_external_models_have_command(self):
        """External type models must have a 'command' key."""
        with open(MODELS_YAML, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        for model in raw.get("models", []):
            if model["type"] == "external":
                assert "command" in model, (
                    f"external model '{model['name']}' must have a 'command' key"
                )

    def test_env_var_expansion(self):
        """${MODELS_DIR} should be expanded using os.environ."""
        from generate_samples import _expand_env  # noqa: PLC0415

        # Set a test environment variable
        os.environ["MODELS_DIR"] = "/tmp/test_models"
        try:
            result = _expand_env("${MODELS_DIR}/some-model.onnx")
            assert result == "/tmp/test_models/some-model.onnx"
        finally:
            del os.environ["MODELS_DIR"]

    def test_env_var_expansion_missing(self):
        """Missing env vars should be left as-is."""
        from generate_samples import _expand_env  # noqa: PLC0415

        # Ensure the var does not exist
        os.environ.pop("NONEXISTENT_VAR_XYZ", None)
        result = _expand_env("${NONEXISTENT_VAR_XYZ}/path")
        assert result == "${NONEXISTENT_VAR_XYZ}/path"

    def test_load_models_config_expands_env(self):
        """_load_models_config should expand environment variables in paths."""
        from generate_samples import _load_models_config  # noqa: PLC0415

        os.environ["MODELS_DIR"] = "/data/test"
        try:
            models = _load_models_config(MODELS_YAML)
            # At least one piper-plus model should have an expanded path
            piper_models = [m for m in models if m.get("type") == "piper-plus"]
            assert len(piper_models) > 0
            for m in piper_models:
                assert "${MODELS_DIR}" not in m["path"], (
                    f"Path not expanded for model '{m['name']}': {m['path']}"
                )
                assert m["path"].startswith("/data/test")
        finally:
            del os.environ["MODELS_DIR"]


# ===========================================================================
# TestComputeMetrics
# ===========================================================================


class TestComputeMetrics:
    """Automatic metrics computation tests."""

    def test_compute_audio_duration(self):
        """WAV file duration should be computed correctly."""
        from compute_metrics import _read_wav_info  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            _create_wav(wav_path, sample_rate=22050, duration_sec=2.0)
            info = _read_wav_info(wav_path)
            assert abs(info["duration_sec"] - 2.0) < 0.01

    def test_compute_audio_duration_short(self):
        """Short audio duration should also be handled correctly."""
        from compute_metrics import _read_wav_info  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "short.wav"
            _create_wav(wav_path, sample_rate=22050, duration_sec=0.1)
            info = _read_wav_info(wav_path)
            assert abs(info["duration_sec"] - 0.1) < 0.01

    def test_sample_rate_check(self):
        """Sample rate verification should flag mismatches."""
        from compute_metrics import _read_wav_info  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            # Correct sample rate
            wav_ok = Path(tmpdir) / "ok.wav"
            _create_wav(wav_ok, sample_rate=22050)
            info_ok = _read_wav_info(wav_ok)
            assert info_ok["sample_rate_ok"] is True

            # Wrong sample rate
            wav_bad = Path(tmpdir) / "bad.wav"
            _create_wav(wav_bad, sample_rate=16000)
            info_bad = _read_wav_info(wav_bad)
            assert info_bad["sample_rate_ok"] is False

    def test_compute_rms(self):
        """RMS level should be a reasonable negative dB value for a sine wave."""
        from compute_metrics import _compute_rms_db  # noqa: PLC0415

        # -6 dBFS sine wave (amplitude = 0.5)
        t = np.linspace(0, 1.0, 22050, endpoint=False)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
        rms = _compute_rms_db(audio)
        # RMS of a sine with amplitude 0.5 is 0.5/sqrt(2) ~ -6 dB + (-3 dB) = ~ -9 dB
        assert -12.0 < rms < -5.0, f"RMS {rms} dB out of expected range"

    def test_compute_rms_silence(self):
        """RMS of silence should be -100 dB."""
        from compute_metrics import _compute_rms_db  # noqa: PLC0415

        audio = np.zeros(22050, dtype=np.float32)
        rms = _compute_rms_db(audio)
        assert rms == -100.0

    def test_compute_peak_db(self):
        """Peak level should match the expected amplitude."""
        from compute_metrics import _compute_peak_db  # noqa: PLC0415

        # Full-scale signal
        audio = np.ones(1000, dtype=np.float32)
        peak = _compute_peak_db(audio)
        assert abs(peak - 0.0) < 0.1, f"Expected ~0 dBFS, got {peak}"

    def test_silence_ratio(self):
        """Silence ratio should be 1.0 for a fully silent signal."""
        from compute_metrics import _compute_silence_ratio  # noqa: PLC0415

        audio = np.zeros(22050, dtype=np.float32)  # 1 second of silence
        ratio = _compute_silence_ratio(audio)
        assert ratio == 1.0

    def test_silence_ratio_loud(self):
        """Silence ratio should be ~0.0 for a loud signal."""
        from compute_metrics import _compute_silence_ratio  # noqa: PLC0415

        t = np.linspace(0, 1.0, 22050, endpoint=False)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
        ratio = _compute_silence_ratio(audio)
        assert ratio < 0.05, f"Expected near-zero silence ratio, got {ratio}"

    def test_silence_ratio_empty(self):
        """Empty audio should return 0.0 silence ratio."""
        from compute_metrics import _compute_silence_ratio  # noqa: PLC0415

        audio = np.array([], dtype=np.float32)
        ratio = _compute_silence_ratio(audio)
        assert ratio == 0.0

    def test_scan_samples_dir(self):
        """_scan_samples_dir should find WAV files in model/lang/ structure."""
        from compute_metrics import _scan_samples_dir  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Create model/lang/text_id.wav structure
            (base / "model-a" / "ja").mkdir(parents=True)
            (base / "model-a" / "en").mkdir(parents=True)
            _create_wav(base / "model-a" / "ja" / "000.wav")
            _create_wav(base / "model-a" / "ja" / "001.wav")
            _create_wav(base / "model-a" / "en" / "000.wav")

            samples = _scan_samples_dir(base)
            assert len(samples) == 3
            models = {s["model"] for s in samples}
            assert models == {"model-a"}
            langs = {s["language"] for s in samples}
            assert langs == {"ja", "en"}


# ===========================================================================
# TestMosSurvey
# ===========================================================================


class TestMosSurvey:
    """MOS survey HTML generation tests."""

    def _make_samples_dir(self, tmpdir: str) -> Path:
        """Create a minimal samples directory with WAV files."""
        base = Path(tmpdir)
        for model in ("model-a", "model-b"):
            for lang in ("ja", "en"):
                d = base / model / lang
                d.mkdir(parents=True)
                _create_wav(d / "000.wav", duration_sec=0.5)
                _create_wav(d / "001.wav", duration_sec=0.5)
        return base

    def test_generate_html_contains_audio(self):
        """Generated HTML should contain base64-encoded audio data URIs."""
        from generate_mos_survey import _generate_html, _scan_samples  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = self._make_samples_dir(tmpdir)
            samples = _scan_samples(samples_dir)
            assert len(samples) > 0

            html = _generate_html(
                samples,
                texts={},
                evaluator_id_hint=5,
                randomize=False,
                blind=True,
            )

            assert "data:audio/wav;base64," in html
            assert "<audio" in html
            assert "MOS Evaluation Survey" in html

    def test_generate_html_contains_all_samples(self):
        """HTML should contain one card per sample."""
        from generate_mos_survey import _generate_html, _scan_samples  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = self._make_samples_dir(tmpdir)
            samples = _scan_samples(samples_dir)
            n = len(samples)

            html = _generate_html(
                samples,
                texts={},
                evaluator_id_hint=5,
                randomize=False,
                blind=True,
            )

            # Each sample should have a rating group
            assert html.count('class="rating-group"') == n

    def test_generate_html_randomizes(self):
        """Randomization should produce different orderings (probabilistic)."""
        import random as _random  # noqa: PLC0415

        from generate_mos_survey import _generate_html, _scan_samples  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = self._make_samples_dir(tmpdir)
            samples = _scan_samples(samples_dir)

            # Generate two HTMLs with different seeds
            _random.seed(42)
            html_a = _generate_html(
                samples[:],
                texts={},
                evaluator_id_hint=5,
                randomize=True,
                blind=True,
            )

            _random.seed(99)
            html_b = _generate_html(
                samples[:],
                texts={},
                evaluator_id_hint=5,
                randomize=True,
                blind=True,
            )

            # With 8 samples, probability of identical ordering is 1/8! ~ 0.002%
            # We check the SAMPLE_METADATA JSON array ordering differs
            assert html_a != html_b, (
                "Two different random seeds should produce different HTML output"
            )

    def test_generate_html_blind_hides_model_name(self):
        """Blind mode should not show model names in the HTML."""
        from generate_mos_survey import _generate_html, _scan_samples  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = self._make_samples_dir(tmpdir)
            samples = _scan_samples(samples_dir)

            html = _generate_html(
                samples,
                texts={},
                evaluator_id_hint=5,
                randomize=False,
                blind=True,
            )

            # In blind mode, model name should only appear in JS metadata,
            # not in visible card headers (i.e., no "model-a / ja" labels)
            assert "model-a / ja" not in html
            assert "model-b / en" not in html

    def test_encode_wav_base64(self):
        """_encode_wav_base64 should produce a valid data URI."""
        from generate_mos_survey import _encode_wav_base64  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            _create_wav(wav_path, duration_sec=0.1)
            data_uri = _encode_wav_base64(wav_path)
            assert data_uri.startswith("data:audio/wav;base64,")
            # Verify the base64 content is decodable
            import base64  # noqa: PLC0415

            b64_part = data_uri.split(",", 1)[1]
            decoded = base64.b64decode(b64_part)
            # Should start with RIFF header
            assert decoded[:4] == b"RIFF"


# ===========================================================================
# TestTextFiles
# ===========================================================================


class TestTextFiles:
    """Test sentence file validation."""

    EXPECTED_LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt"]

    def test_all_languages_have_texts(self):
        """All 6 languages should have a text file."""
        for lang in self.EXPECTED_LANGUAGES:
            txt_path = TEXTS_DIR / f"{lang}.txt"
            assert txt_path.exists(), f"Missing text file for language '{lang}'"

    def test_each_file_has_10_lines(self):
        """Each text file should contain exactly 10 non-empty lines."""
        for lang in self.EXPECTED_LANGUAGES:
            txt_path = TEXTS_DIR / f"{lang}.txt"
            lines = [
                line.strip()
                for line in txt_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert len(lines) == 10, (
                f"{lang}.txt has {len(lines)} non-empty lines, expected 10"
            )

    def test_no_empty_lines_in_middle(self):
        """Text files should not have blank lines between sentences."""
        for lang in self.EXPECTED_LANGUAGES:
            txt_path = TEXTS_DIR / f"{lang}.txt"
            content = txt_path.read_text(encoding="utf-8")
            # Strip trailing whitespace/newlines, then check
            stripped = content.rstrip()
            lines = stripped.split("\n")
            for i, line in enumerate(lines):
                assert line.strip(), (
                    f"{lang}.txt has empty line at position {i + 1}"
                )

    def test_text_files_are_utf8(self):
        """All text files should be valid UTF-8."""
        for lang in self.EXPECTED_LANGUAGES:
            txt_path = TEXTS_DIR / f"{lang}.txt"
            # This will raise UnicodeDecodeError if not valid UTF-8
            txt_path.read_text(encoding="utf-8")

    def test_load_texts_function(self):
        """_load_texts should load the correct number of sentences."""
        from generate_samples import _load_texts  # noqa: PLC0415

        texts = _load_texts(TEXTS_DIR, self.EXPECTED_LANGUAGES)
        assert len(texts) == 6
        for lang in self.EXPECTED_LANGUAGES:
            assert lang in texts
            assert len(texts[lang]) == 10


# ===========================================================================
# TestGenerateSamplesHelpers
# ===========================================================================


class TestGenerateSamplesHelpers:
    """Tests for helper functions in generate_samples.py."""

    def test_audio_float_to_int16(self):
        """_audio_float_to_int16 should normalize and clip to int16 range."""
        from generate_samples import _audio_float_to_int16  # noqa: PLC0415

        audio = np.array([0.0, 0.5, 1.0, -0.5, -1.0], dtype=np.float32)
        result = _audio_float_to_int16(audio)
        assert result.dtype == np.int16
        # Max absolute value should be near 32767
        assert np.max(np.abs(result)) <= 32767

    def test_write_wav_creates_file(self):
        """_write_wav should create a valid WAV file."""
        from generate_samples import _write_wav  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.wav"
            data = np.zeros(22050, dtype=np.int16)
            _write_wav(str(out), 22050, data)
            assert out.exists()
            with wave.open(str(out), "rb") as wf:
                assert wf.getframerate() == 22050
                assert wf.getnchannels() == 1
                assert wf.getnframes() == 22050

    def test_read_wav_duration(self):
        """_read_wav_duration should return correct duration."""
        from generate_samples import _read_wav_duration  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            _create_wav(wav_path, sample_rate=22050, duration_sec=1.5)
            duration = _read_wav_duration(str(wav_path))
            assert abs(duration - 1.5) < 0.01
