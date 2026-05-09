"""Layer-2 E2E cosine gate for the speaker encoder.

See ``docs/spec/speaker-encoder-contract.md``. This test is **opt-in** and
skips by default — it activates only when:

1. The fixture ``test/fixtures/speaker_encoder_golden.json`` contains an
   ``e2e_cosine_gate`` block (i.e. someone ran the generator with
   ``--encoder-onnx`` populated), AND
2. A local encoder ONNX is available — either via env var
   ``PIPER_SPEAKER_ENCODER_ONNX_PATH`` or via HF Hub download (the latter
   only when ``PIPER_SPEAKER_ENCODER_E2E=1`` is set, to avoid hitting the
   network on every CI run).

Test semantics: compute embedding from the reference WAV using the local
encoder, assert ``cosine(actual, expected) >= cosine_threshold``. The
threshold (0.999) is permissive on purpose — see the spec for the rationale
on why byte-equality across ORT execution providers is not feasible.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "speaker_encoder_golden.json"


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_encoder_path(gate: dict) -> Path | None:
    """Locate the encoder ONNX. Returns None to signal `skip`.

    Priority:
      1. ``PIPER_SPEAKER_ENCODER_ONNX_PATH`` env var (explicit override).
      2. HF Hub download, only when ``PIPER_SPEAKER_ENCODER_E2E=1``.
    """
    env_path = os.environ.get("PIPER_SPEAKER_ENCODER_ONNX_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        pytest.skip(f"PIPER_SPEAKER_ENCODER_ONNX_PATH={env_path} does not exist")

    if os.environ.get("PIPER_SPEAKER_ENCODER_E2E") != "1":
        return None  # opt-in only — skip silently

    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        pytest.skip("huggingface_hub not installed; cannot download encoder ONNX")

    enc = gate["encoder_onnx"]
    return Path(
        hf_hub_download(
            repo_id=enc["hf_repo"],
            filename=enc["hf_filename"],
            revision=enc["hf_revision"],
        )
    )


def _verify_sha256(path: Path, expected: str) -> None:
    import hashlib  # noqa: PLC0415

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        pytest.fail(
            f"encoder ONNX sha256 mismatch (silent upstream replacement?):\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}\n"
            f"  path:     {path}"
        )


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def test_e2e_cosine_gate_against_pinned_embedding() -> None:
    fixture = _load_fixture()
    gate = fixture.get("e2e_cosine_gate")
    if gate is None:
        pytest.skip(
            "fixture has no e2e_cosine_gate block — generator was run without "
            "--encoder-onnx; the layer-1 mel parity tests still apply"
        )

    encoder_path = _resolve_encoder_path(gate)
    if encoder_path is None:
        pytest.skip(
            "encoder ONNX not available locally and PIPER_SPEAKER_ENCODER_E2E "
            "is not set — opt-in test, skipping by default"
        )

    expected_sha = gate["encoder_onnx"].get("sha256")
    if expected_sha and expected_sha != "":
        _verify_sha256(encoder_path, expected_sha)

    # Lazy imports — ``onnxruntime`` is only required on the active path.
    try:
        import onnxruntime  # noqa: F401, PLC0415
    except ImportError:
        pytest.skip("onnxruntime not installed; cannot exercise E2E gate")

    # Re-use the generator's compute helper so the test stays a thin shell.
    from generate_speaker_encoder_golden import _compute_e2e_embedding  # noqa: PLC0415

    wav_path = Path(gate["reference_wav"]["path"])
    if not wav_path.is_absolute():
        wav_path = (Path(__file__).parent.parent / wav_path).resolve()
    if not wav_path.exists():
        pytest.skip(f"reference WAV not found at {wav_path}")

    actual_embedding, _ = _compute_e2e_embedding(encoder_path, wav_path)
    expected_embedding = np.asarray(
        gate["expected_embedding"]["values"], dtype=np.float32
    )

    assert actual_embedding.shape == expected_embedding.shape, (
        f"embedding dim drift: actual={actual_embedding.shape}, "
        f"expected={expected_embedding.shape}"
    )

    cos = _cosine(actual_embedding, expected_embedding)
    threshold = float(gate["cosine_threshold"])
    assert cos >= threshold, (
        f"cosine gate failed: cos={cos:.6f} < threshold={threshold:.6f}\n"
        f"  encoder: {encoder_path}\n"
        f"  WAV:     {wav_path}\n"
        f"  fixture sha256={gate['encoder_onnx'].get('sha256', '<unset>')}"
    )
