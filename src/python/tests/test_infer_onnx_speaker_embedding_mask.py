"""Regression tests for infer_onnx.py speaker_embedding_mask handling.

These tests mirror commit 5188b088 (voice.py fix): when an ONNX model
declares `speaker_embedding_mask` as a required input, the training-side
`infer_onnx.py` CLI must feed it; when the model does NOT declare it
(post-Issue #527 forward-compat zero-shot models), the CLI must NOT
feed a mask (ORT would otherwise raise InvalidArgument).

The current `infer_onnx.py:1057` only feeds `speaker_embedding` and
never inspects/forwards `speaker_embedding_mask`. That mirrors the
exact bug fixed in voice.py:1051. We pin both branches here so the
behaviour stays correct once the production code is patched.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# Make `piper_train` importable when running this file directly.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src" / "python"))

from piper_train import infer_onnx  # noqa: E402


pytestmark = pytest.mark.unit


@pytest.fixture
def invoke_cli(tmp_path, monkeypatch):
    def run(payload=None, vector=None, dimension=192):
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fixture")
        _write_minimal_config(model_path)
        session = _make_session_mock(
            [
                "input",
                "input_lengths",
                "scales",
                "sid",
                "speaker_embedding",
                "speaker_embedding_mask",
            ]
        )
        for item in session.get_inputs():
            if item.name == "speaker_embedding":
                item.shape = [1, dimension]
        args = [
            "infer",
            "--model",
            str(model_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--dataset-dir",
            str(tmp_path),
        ]
        if vector is not None:
            path = tmp_path / "reference.npy"
            np.save(path, vector)
            args += ["--speaker-embedding", str(path)]
        if payload is None:
            args += ["--text", "abcde"]
        else:
            monkeypatch.setattr(
                sys,
                "stdin",
                io.StringIO(
                    json.dumps({"phoneme_ids": [1] + [10] * 16 + [2], **payload}) + "\n"
                ),
            )
        monkeypatch.setattr(sys, "argv", args)
        monkeypatch.setattr(
            infer_onnx, "create_session_with_cache", lambda *args, **kwargs: session
        )
        monkeypatch.setattr(
            infer_onnx, "warmup_onnx_session", lambda *args, **kwargs: None
        )
        return session, infer_onnx.main

    return run


@pytest.mark.parametrize("jsonl", [False, True])
def test_cli_no_reference_feeds_zero_with_mask_zero(invoke_cli, jsonl):
    session, run = invoke_cli({} if jsonl else None)
    run()
    feeds = session.run.call_args.args[1]
    assert not feeds["speaker_embedding"].any()
    assert feeds["speaker_embedding_mask"].tolist() == [[0]]
    assert "sid" in feeds


@pytest.mark.parametrize("jsonl", [False, True])
@pytest.mark.parametrize("dimension", [192, 256])
def test_cli_normalizes_reference_using_graph_dimension(invoke_cli, jsonl, dimension):
    vector = np.arange(1, dimension + 1, dtype=np.float32)
    session, run = invoke_cli(
        {"speaker_embedding": vector.tolist()} if jsonl else None,
        None if jsonl else vector,
        dimension,
    )
    run()
    feeds = session.run.call_args.args[1]
    assert feeds["speaker_embedding"].shape == (1, dimension)
    assert np.linalg.norm(feeds["speaker_embedding"]) == pytest.approx(1)
    assert feeds["speaker_embedding_mask"].tolist() == [[1]]


@pytest.mark.parametrize("jsonl", [False, True])
@pytest.mark.parametrize(
    "vector",
    [
        np.zeros(192),
        np.full(192, np.nan),
        np.full(192, np.inf),
        np.ones((2, 96)),
        np.ones(256),
    ],
)
def test_cli_rejects_invalid_explicit_reference_before_ort(invoke_cli, jsonl, vector):
    session, run = invoke_cli(
        {"speaker_embedding": vector.tolist()} if jsonl else None,
        None if jsonl else vector,
    )
    with pytest.raises((ValueError, SystemExit)):
        run()
    session.run.assert_not_called()


def test_cli_jsonl_resolves_dataset_relative_embedding_path(invoke_cli, tmp_path):
    vector = np.arange(1, 193, dtype=np.float32)
    np.save(tmp_path / "entry.npy", vector)
    session, run = invoke_cli({"speaker_embedding_path": "entry.npy"})
    run()
    feeds = session.run.call_args.args[1]
    np.testing.assert_allclose(
        feeds["speaker_embedding"][0],
        vector.astype(np.float64) / np.linalg.norm(vector.astype(np.float64)),
    )
    assert feeds["speaker_embedding_mask"].tolist() == [[1]]


@pytest.mark.parametrize("source", ["file", "speaker-id", "audio"])
@pytest.mark.parametrize("valid", [False, True])
def test_resolver_validates_all_reference_sources(tmp_path, monkeypatch, source, valid):
    vector = np.arange(1, 193, dtype=np.float32) if valid else np.full(192, np.nan)
    np.save(tmp_path / "speaker_7.npy", vector)
    audio = tmp_path / "ref.wav"
    encoder = tmp_path / "encoder.onnx"
    audio.write_bytes(b"fixture")
    encoder.write_bytes(b"fixture")
    monkeypatch.setattr(
        infer_onnx, "_extract_speaker_embedding_from_audio", lambda *args: vector
    )
    options = {
        "speaker_audio": str(audio) if source == "audio" else None,
        "speaker_encoder": str(encoder),
        "speaker_embedding_path": str(tmp_path / "speaker_7.npy")
        if source == "file"
        else None,
        "speaker_id": 7 if source == "speaker-id" else None,
        "model_path": tmp_path / "model.onnx",
        "dataset_dir": tmp_path,
    }
    if valid:
        result = infer_onnx._resolve_speaker_embedding(**options)
        assert np.linalg.norm(result) == pytest.approx(1)
    else:
        with pytest.raises(ValueError, match="speaker_embedding"):
            infer_onnx._resolve_speaker_embedding(**options)


def _make_session_mock(input_names: list[str]) -> MagicMock:
    """Return a MagicMock that quacks like an onnxruntime InferenceSession.

    `get_inputs()` returns objects with a `.name` attribute matching the
    requested input list — that's all the production code's input-detection
    block at line 878 reads. `run()` returns a (waveform, durations) pair
    shaped so the trim / WAV-writing path downstream stays happy.
    """
    session = MagicMock()
    session.get_providers.return_value = ["CPUExecutionProvider"]
    # NB: MagicMock(name=...) sets the mock's *repr* name, not a `.name`
    # attribute. Assign `.name` explicitly so production code's
    # `inp.name for inp in session.get_inputs()` returns strings.
    inputs = []
    for n in input_names:
        m = MagicMock()
        m.name = n
        inputs.append(m)
    session.get_inputs.return_value = inputs

    # Return a tiny waveform [B, 1, T] and a durations vector [B, T_text].
    waveform = np.zeros((1, 1, 4096), dtype=np.float32)
    durations = np.ones((1, 8), dtype=np.float32)
    session.run.return_value = [waveform, durations]
    return session


def _write_minimal_config(model_path: Path) -> Path:
    """Drop a config.json next to the (non-existent) ONNX file.

    `infer_onnx.main()` reads phoneme_id_map from this in `--text` mode.
    The phoneme_id_map only needs to cover characters used in the test
    text below.
    """
    cfg = {
        "audio": {"sample_rate": 22050, "hop_size": 256},
        "phoneme_type": "raw",
        "phoneme_id_map": {ch: [i + 4] for i, ch in enumerate("abcdefghij")},
        "num_symbols": 50,
        "num_speakers": 1,
        "speaker_id_map": {"default": 0},
        "language_map": {},
        "espeak": {"voice": "en-us"},
        "inference": {"noise_scale": 0.4, "length_scale": 1.0, "noise_w": 0.5},
    }
    cfg_path = model_path.with_suffix(model_path.suffix + ".json")
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


def _run_main_capturing_feeds(
    tmp_path: Path,
    input_names: list[str],
    spk_emb_path: Path,
) -> dict:
    """Invoke `infer_onnx.main()` end-to-end and return the feeds dict
    handed to `session.run()`.

    `create_session_with_cache` and `warmup_onnx_session` are patched
    out so no real ONNX file is required.
    """
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"\x00")  # presence check only
    _write_minimal_config(model_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    session = _make_session_mock(input_names)

    argv = [
        "piper_train.infer_onnx",
        "--model",
        str(model_path),
        "--output-dir",
        str(out_dir),
        "--text",
        "abcde",
        "--speaker-embedding",
        str(spk_emb_path),
    ]

    with (
        patch.object(infer_onnx, "create_session_with_cache", return_value=session),
        patch.object(infer_onnx, "warmup_onnx_session"),
        patch.object(sys, "argv", argv),
    ):
        infer_onnx.main()

    assert session.run.called, "session.run was never called"
    # session.run(None, inputs) — second positional arg is the feeds dict.
    call_args, call_kwargs = session.run.call_args
    feeds = call_args[1] if len(call_args) > 1 else call_kwargs["input_feed"]
    return feeds


@pytest.fixture()
def speaker_embedding_npy(tmp_path: Path) -> Path:
    """A canonical 192-dim L2-normalised CAM++ embedding on disk."""
    emb = np.random.RandomState(0).randn(infer_onnx._SPK_EMBED_DIM).astype(np.float32)
    emb /= np.linalg.norm(emb) + 1e-9
    path = tmp_path / "speaker.npy"
    np.save(path, emb)
    return path


class TestSpeakerEmbeddingMaskDetection:
    """Line 878: input_names parsing must surface mask as a separate flag."""

    def test_infer_onnx_detects_speaker_embedding_mask_in_input_names(self) -> None:
        """The input-name detection block must recognise mask as a distinct
        input. Today the production code only sets ``has_spk_emb``; once
        fixed it should also expose ``has_spk_emb_mask`` (or equivalent).

        We pin behaviour at the data layer: given a session that declares
        both inputs, the name set the CLI inspects MUST contain both.
        """
        session = _make_session_mock(
            [
                "input",
                "input_lengths",
                "scales",
                "speaker_embedding",
                "speaker_embedding_mask",
            ]
        )
        input_names = [inp.name for inp in session.get_inputs()]
        assert "speaker_embedding" in input_names
        assert "speaker_embedding_mask" in input_names


class TestSpeakerEmbeddingMaskFeed:
    """Lines 1049-1057: feeds dict construction for zero-shot models."""

    def test_infer_onnx_feeds_mask_when_model_declares_it(
        self, tmp_path: Path, speaker_embedding_npy: Path
    ) -> None:
        """Models that declare speaker_embedding_mask require a mask feed
        of shape (1,) int64 with value 1 (= use external embedding)."""
        feeds = _run_main_capturing_feeds(
            tmp_path,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "speaker_embedding",
                "speaker_embedding_mask",
            ],
            spk_emb_path=speaker_embedding_npy,
        )
        assert "speaker_embedding" in feeds
        assert "speaker_embedding_mask" in feeds, (
            f"Model declares speaker_embedding_mask but feeds dict only"
            f" has: {sorted(feeds.keys())}"
        )
        mask = feeds["speaker_embedding_mask"]
        assert mask.dtype == np.int64, f"mask dtype {mask.dtype} != int64"
        assert mask.shape in ((1,), (1, 1)), (
            f"mask shape {mask.shape} not in {{(1,), (1, 1)}}"
        )
        # mask=1 selects external embedding over emb_g(sid) fallback.
        assert int(mask.flat[0]) == 1

    def test_infer_onnx_omits_mask_when_model_lacks_it(
        self, tmp_path: Path, speaker_embedding_npy: Path
    ) -> None:
        """Forward-compat: post-Issue #527 zero-shot models drop the mask
        input. Feeding one anyway raises ORT InvalidArgument, so the CLI
        must not include it in the feeds dict."""
        feeds = _run_main_capturing_feeds(
            tmp_path,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "speaker_embedding",
            ],
            spk_emb_path=speaker_embedding_npy,
        )
        assert "speaker_embedding" in feeds
        assert "speaker_embedding_mask" not in feeds, (
            f"Model lacks mask input but feeds dict includes it: {sorted(feeds.keys())}"
        )
