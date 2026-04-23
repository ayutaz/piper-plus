"""Unit tests for ``piper_train.tools.build_pea_style_bank`` (Phase 3 P3-T02).

All tests run offline: the PE-A audio model is either mocked outright or the
``extract_audio_embedding`` helper is monkeypatched, so no HuggingFace
download is triggered.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

try:
    import soundfile as sf  # noqa: F401

    _HAS_SOUNDFILE = True
except ImportError:
    _HAS_SOUNDFILE = False

from piper_train.tools import build_pea_style_bank as builder


def _write_wav(path: Path, samplerate: int = 16000) -> None:
    assert _HAS_SOUNDFILE
    import soundfile as _sf
    data = np.zeros(int(0.05 * samplerate), dtype=np.float32)
    _sf.write(str(path), data, samplerate, subtype="PCM_16")


@pytest.fixture
def dummy_crema_dir(tmp_path: Path) -> Path:
    """10 utterances across 2 emotions (ANG x5, HAP x5)."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "crema-mini"
    audio = root / "AudioWAV"
    audio.mkdir(parents=True)
    for i in range(5):
        _write_wav(audio / f"100{i}_IWW_ANG_HI.wav")
        _write_wav(audio / f"100{i}_IWW_HAP_MD.wav")
    return root


@pytest.fixture
def mock_pea_model():
    return {"kind": "mock", "model": mock.MagicMock(), "name": "mock-pe-a"}


@pytest.mark.unit
def test_build_style_bank_schema(
    tmp_path: Path, dummy_crema_dir: Path, mock_pea_model, monkeypatch
):
    """End-to-end: 10 dummy WAVs + mock PE-A -> ``.npz`` with expected schema."""
    emotion_vec = {
        "angry": np.array([1.0, 0.0, 0.5, 0, 0, 0, 0, 0], dtype=np.float32),
        "happy": np.array([0.0, 1.0, 0.0, 0.5, 0, 0, 0, 0], dtype=np.float32),
    }

    def fake_extract(handle, audio, device="cpu"):
        fake_extract.calls += 1  # type: ignore[attr-defined]
        call = fake_extract.calls
        is_ang = (call % 2) == 1
        vec = emotion_vec["angry" if is_ang else "happy"].copy()
        vec += 1e-3 * np.sin(np.arange(len(vec)) + call).astype(np.float32)
        return vec / float(np.linalg.norm(vec))

    fake_extract.calls = 0  # type: ignore[attr-defined]
    monkeypatch.setattr(builder, "extract_audio_embedding", fake_extract)

    dataset = builder.EmotionAudioDataset(dataset_dir=dummy_crema_dir)
    assert len(dataset) == 10

    emotion_names, centroids, global_c, counts = builder.build_style_bank(
        dataset, mock_pea_model, device="cpu"
    )

    assert emotion_names == ["angry", "happy"]
    assert centroids.shape == (2, 8)
    assert centroids.dtype == np.float32
    assert global_c.shape == (8,)
    assert global_c.dtype == np.float32
    assert counts == {"angry": 5, "happy": 5}
    assert np.allclose(np.linalg.norm(centroids, axis=-1), 1.0, atol=1e-3)

    out = tmp_path / "test_bank.npz"
    builder.save_style_bank(out, emotion_names, centroids, global_c)
    bank = np.load(str(out), allow_pickle=True)
    assert set(bank.files) == {"emotion_names", "emotion_centroids", "global_centroid"}
    assert list(str(e) for e in bank["emotion_names"]) == ["angry", "happy"]
    assert bank["emotion_centroids"].dtype == np.float32


@pytest.mark.unit
def test_compute_centroids_numerical():
    """Known embeddings yield expected L2-normalised centroids."""
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.8, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.5, 0.0],
        ],
        dtype=np.float32,
    )
    labels = ["angry", "angry", "happy", "happy"]
    names, centroids, global_c = builder.compute_centroids(embeddings, labels)
    assert names == ["angry", "happy"]
    assert np.allclose(centroids[0], np.array([1.0, 0.0, 0.0], dtype=np.float32), atol=1e-6)
    assert np.allclose(centroids[1], np.array([0.0, 1.0, 0.0], dtype=np.float32), atol=1e-6)
    assert np.allclose(global_c, np.array([0.45, 0.375, 0.0], dtype=np.float32), atol=1e-6)


@pytest.mark.unit
def test_compute_centroids_shape_validation():
    """Mismatched labels / embeddings raise ValueError."""
    embeds = np.zeros((3, 4), dtype=np.float32)
    with pytest.raises(ValueError):
        builder.compute_centroids(embeds, ["a", "b"])  # len mismatch
    with pytest.raises(ValueError):
        builder.compute_centroids(np.zeros((3,), dtype=np.float32), ["a", "b", "c"])


@pytest.mark.unit
def test_save_style_bank_rejects_non_normalised_rows(tmp_path: Path):
    """``save_style_bank`` refuses centroids whose L2 norm differs from 1."""
    bad = np.array([[2.0, 0.0], [0.0, 3.0]], dtype=np.float32)
    with pytest.raises(ValueError, match="not L2-normalised"):
        builder.save_style_bank(
            tmp_path / "bad.npz",
            ["angry", "happy"],
            bad,
            np.array([1.0, 1.5], dtype=np.float32),
        )


@pytest.mark.unit
def test_dataset_requires_source():
    """Dataset must be given either dataset_dir or manifest_path."""
    with pytest.raises(ValueError):
        builder.EmotionAudioDataset()


@pytest.mark.unit
def test_dataset_load_from_jsonl(tmp_path: Path):
    """JSONL manifest ingestion routes through ``_load_jsonl``."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    wav = tmp_path / "a.wav"
    _write_wav(wav)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"audio_path": str(wav), "emotion": "angry"}) + "\n"
        + json.dumps({"audio_path": str(wav), "emotion": "happy"}) + "\n",
        encoding="utf-8",
    )
    dataset = builder.EmotionAudioDataset(manifest_path=manifest)
    assert len(dataset) == 2
    assert {s["emotion"] for s in dataset.samples} == {"angry", "happy"}


@pytest.mark.unit
def test_dataset_load_from_csv(tmp_path: Path):
    """CSV manifest ingestion extracts audio_path + emotion with lowercase normalisation."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    wav = tmp_path / "a.wav"
    _write_wav(wav)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "audio_path,emotion\n"
        f"{wav},angry\n"
        f"{wav},HAPPY\n",
        encoding="utf-8",
    )
    dataset = builder.EmotionAudioDataset(manifest_path=manifest)
    assert len(dataset) == 2
    assert [s["emotion"] for s in dataset.samples] == ["angry", "happy"]


@pytest.mark.unit
def test_dataset_unknown_crema_emotion_code_skipped(tmp_path: Path):
    """CREMA-D loader skips unknown emotion codes and malformed names."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "c"
    (root / "AudioWAV").mkdir(parents=True)
    _write_wav(root / "AudioWAV" / "1001_IWW_ZZZ_XX.wav")  # unknown emotion
    _write_wav(root / "AudioWAV" / "short.wav")  # malformed
    _write_wav(root / "AudioWAV" / "1001_IWW_ANG_XX.wav")  # good
    dataset = builder.EmotionAudioDataset(dataset_dir=root)
    assert len(dataset) == 1
    assert dataset.samples[0]["emotion"] == "angry"


@pytest.mark.unit
def test_load_pea_model_reports_install_hint(monkeypatch):
    """When both loaders fail, ``PEAModelError`` lists install options."""
    import builtins

    orig_import = builtins.__import__

    def fail_import(name, *args, **kwargs):
        if name == "transformers" or name.startswith("transformers."):
            raise ImportError("transformers unavailable in test")
        if name == "perception_models" or name.startswith("perception_models"):
            raise ImportError("perception_models unavailable in test")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_import)
    with pytest.raises(builder.PEAModelError, match="Install"):
        builder.load_pea_model("facebook/pe-av-small", device="cpu")


@pytest.mark.unit
def test_extract_audio_embedding_l2_normalises():
    """A mock model returning a 1-D tensor is L2-normalised by the helper."""
    torch = pytest.importorskip("torch")

    class Dummy:
        def get_audio_embeds(self, x):
            return torch.tensor([3.0, 4.0, 0.0])  # norm = 5

    out = builder.extract_audio_embedding(
        {"kind": "mock", "model": Dummy(), "name": "dummy"},
        np.zeros(16000, dtype=np.float32),
        device="cpu",
    )
    assert out.shape == (3,)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-6


@pytest.mark.unit
def test_extract_audio_embedding_pool_3d_output():
    """3-D outputs [B, T, D] are mean-pooled over the time axis."""
    torch = pytest.importorskip("torch")

    class Dummy:
        def get_audio_embeds(self, x):
            return torch.tensor([[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]])  # [1,3,2]

    out = builder.extract_audio_embedding(
        {"kind": "mock", "model": Dummy(), "name": "dummy"},
        np.zeros(16000, dtype=np.float32),
        device="cpu",
    )
    assert out.shape == (2,)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-6


@pytest.mark.unit
def test_generate_report_contains_cosine_matrix(tmp_path: Path):
    """``generate_report`` writes a JSON blob with a cosine similarity matrix."""
    centroids = np.eye(3, dtype=np.float32)
    global_c = centroids.mean(axis=0)
    report_path = tmp_path / "r.json"
    builder.generate_report(
        report_path,
        emotion_names=["a", "b", "c"],
        emotion_centroids=centroids,
        global_centroid=global_c.astype(np.float32),
        per_emotion_counts={"a": 3, "b": 3, "c": 3},
    )
    report = json.loads(report_path.read_text())
    assert report["emotion_names"] == ["a", "b", "c"]
    assert report["embedding_dim"] == 3
    matrix = report["cosine_similarity_matrix"]
    assert len(matrix) == 3
    # Diagonal entries are 1.0
    assert abs(matrix[0][0] - 1.0) < 1e-6
    # Off-diagonal orthogonal entries are 0.0
    assert abs(matrix[0][1]) < 1e-6


@pytest.mark.unit
def test_build_style_bank_raises_on_empty_dataset(tmp_path: Path):
    """Zero-sample dataset raises a clear error."""
    if not _HAS_SOUNDFILE:
        pytest.skip("soundfile not installed")
    root = tmp_path / "empty"
    (root / "AudioWAV").mkdir(parents=True)
    dataset = builder.EmotionAudioDataset(dataset_dir=root)
    assert len(dataset) == 0
    with pytest.raises(RuntimeError, match="No audio samples"):
        builder.build_style_bank(dataset, {"kind": "mock"}, device="cpu")
