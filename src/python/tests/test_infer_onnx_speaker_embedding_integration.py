"""Integration test: infer_onnx.py CLI exercises Issue #426 fallback.

`infer_onnx.py:867-882` decides at runtime whether to feed the
zero-embedding + mask=0 fallback. Unit-mocking the InferenceSession only
covers the input *list*; we need a real ort.Session to confirm the
tensor dtype/shape and that the model produces audio when no embedding
is supplied.

The fixture ONNX is generated on-the-fly by
`tests/fixtures/mb_istft_speaker_embedding/build_fixture.py` (or
pre-built in CI). The test skips if the fixture isn't present.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "mb_istft_speaker_embedding"
_FIXTURE_MODEL = _FIXTURE_DIR / "model.onnx"
_FIXTURE_BUILDER = _FIXTURE_DIR / "build_fixture.py"


def _ensure_fixture() -> Path:
    if _FIXTURE_MODEL.exists():
        return _FIXTURE_MODEL
    # Build it on first use so local devs don't need a separate setup step.
    result = subprocess.run(
        [sys.executable, str(_FIXTURE_BUILDER)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip(
            f"Could not build speaker_embedding fixture: {result.stderr[-500:]}"
        )
    return _FIXTURE_MODEL


def _make_minimal_config(tmp_path: Path) -> Path:
    """Write a minimal piper-style config.json the CLI accepts.

    The fixture model has n_vocab=50 and prosody_dim=0; phoneme_id_map only
    needs to cover the ids we send in via JSONL.
    """
    cfg = {
        "audio": {"sample_rate": 22050},
        "phoneme_type": "raw",
        "phoneme_id_map": {str(i): [i] for i in range(50)},
        "num_symbols": 50,
        "num_speakers": 2,
        "speaker_id_map": {"default": 0, "second": 1},
        "language_map": {},
        "espeak": {"voice": "en-us"},
        "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
    }
    path = tmp_path / "model.onnx.json"
    path.write_text(json.dumps(cfg))
    return path


@pytest.fixture()
def fixture_model(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the fixture next to a generated config.json so the CLI's
    config-resolution logic (model.onnx -> model.onnx.json) finds both."""
    src = _ensure_fixture()
    dst = tmp_path / "model.onnx"
    dst.write_bytes(src.read_bytes())
    cfg = _make_minimal_config(tmp_path)
    assert cfg.exists()
    return dst, cfg


class TestInferOnnxSpeakerEmbeddingFallback:
    """The CLI must run end-to-end without --speaker-embedding when the
    model declares speaker_embedding as an input (Issue #426)."""

    def test_jsonl_input_without_embedding_produces_wav(
        self, fixture_model, tmp_path: Path
    ):
        """The zero+mask=0 fallback path must produce a valid WAV."""
        model_path, _ = fixture_model
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # phoneme_ids: 1 = BOS, 2 = EOS, others arbitrary in [0, 50).
        request = json.dumps({"phoneme_ids": [1, 10, 20, 30, 40, 2], "speaker_id": 0})

        # PIPER_DISABLE_WARMUP keeps the test fast — the warmup path is
        # covered separately by test_voice_speaker_embedding.py.
        import os

        env = os.environ.copy()
        env["PIPER_DISABLE_WARMUP"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = ""

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper_train.infer_onnx",
                "--model",
                str(model_path),
                "--output-dir",
                str(out_dir),
            ],
            check=False,
            input=request,
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=120,
            env=env,
        )

        assert result.returncode == 0, (
            f"CLI failed (Issue #426 regression?):\n"
            f"stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}"
        )

        # One WAV per JSONL line.
        wavs = sorted(out_dir.glob("*.wav"))
        assert len(wavs) == 1, f"expected 1 wav, got {wavs}"
        # RIFF/WAVE magic — proves it's a real WAV, not an empty file.
        header = wavs[0].read_bytes()[:12]
        assert header[:4] == b"RIFF", f"bad WAV header: {header!r}"
        assert header[8:12] == b"WAVE", f"bad WAV header: {header!r}"
        assert wavs[0].stat().st_size > 1000, "WAV unexpectedly small"
