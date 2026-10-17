"""参照音声trim (学習時と同じenergy VAD) のテスト。"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from piper_train.extract_speaker_embedding import preprocess_audio
from piper_train.reference_frontend import trim_reference_audio


def tone(n: int, amp: float, sr: int = 22050, freq: float = 220.0) -> np.ndarray:
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def wav_with_silence(tmp_path):
    sr = 22050
    audio = np.concatenate([np.zeros(sr), tone(sr, 0.3, sr), np.zeros(sr)])
    path = tmp_path / "ref.wav"
    sf.write(str(path), audio.astype(np.float32), sr)
    return path


def test_trim_matches_training_vad_bounds():
    audio = np.concatenate([np.zeros(22050), tone(22050, 0.3), np.zeros(22050)])
    out, info = trim_reference_audio(audio, 22050)
    assert 0.9 < info["offset_sec"] < 1.0
    assert len(out) < len(audio)
    assert info["method"] == "energy_vad_numpy@16k"
    assert info["duration_sec"] > 0


def test_trim_rejects_all_silence():
    with pytest.raises(ValueError, match="no voiced"):
        trim_reference_audio(np.zeros(44100, dtype=np.float32), 22050)


def test_preprocess_audio_trim_default_off_is_unchanged(wav_with_silence):
    assert np.array_equal(
        preprocess_audio(wav_with_silence),
        preprocess_audio(wav_with_silence, trim=False),
    )


def test_preprocess_audio_trim_shortens_features(wav_with_silence):
    untrimmed = preprocess_audio(wav_with_silence)
    trimmed = preprocess_audio(wav_with_silence, trim=True)
    assert trimmed.shape[0] < untrimmed.shape[0]
    assert trimmed.shape[1] == 80


# ---------------------------------------------------------------------------
# fp32 時間平均 / CAM++ pooling 前統計
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

import torch  # noqa: E402

from piper_train.reference_frontend import (  # noqa: E402
    campplus_stats,
    masked_time_mean_fp32,
)
from piper_train.speaker_encoder.campplus_torch import CAMPPlus  # noqa: E402


@pytest.fixture
def campplus_random():
    torch.manual_seed(0)
    return CAMPPlus(feat_dim=80, embedding_size=192).eval()


def reference_statspool_via_hook(model, fbank):
    """xvector.stats の出力を forward hook で捕まえる (独立参照)。"""
    captured = {}
    handle = model.xvector.stats.register_forward_hook(
        lambda _m, _i, out: captured.__setitem__("out", out)
    )
    try:
        with torch.no_grad():
            model(fbank)
    finally:
        handle.remove()
    return captured["out"].float()


def test_masked_mean_fp16_long_input_is_finite():
    x = torch.full((1, 4, 200_000), 60000.0, dtype=torch.float16)
    out = masked_time_mean_fp32(x, torch.ones(1, 1, 200_000))
    assert out.dtype == torch.float32 and torch.isfinite(out).all()
    assert torch.allclose(out, torch.full((1, 4), 60000.0), rtol=1e-3)


def test_masked_mean_respects_mask():
    x = torch.tensor([[[1.0, 2.0, 100.0]], [[4.0, 4.0, 4.0]]])
    mask = torch.tensor([[[1.0, 1.0, 0.0]], [[1.0, 1.0, 1.0]]])
    out = masked_time_mean_fp32(x, mask)
    assert torch.allclose(out, torch.tensor([[1.5], [4.0]]))


def test_masked_mean_rejects_empty_mask_row():
    x = torch.ones(2, 3, 5)
    mask = torch.ones(2, 1, 5)
    mask[1] = 0
    with pytest.raises(ValueError):
        masked_time_mean_fp32(x, mask)


def test_campplus_stats_matches_internal_statspool(campplus_random):
    fbank = torch.randn(2, 300, 80)
    stats = campplus_stats(campplus_random, fbank)
    assert stats.shape == (2, 1024)
    assert stats.dtype == torch.float32
    assert torch.allclose(
        stats, reference_statspool_via_hook(campplus_random, fbank), atol=1e-5
    )


REPO_ROOT = Path(__file__).resolve().parents[3]
_TORCH_WEIGHTS = (
    REPO_ROOT
    / "output/zero-shot-cpu-preparation-20261017/evaluation-models"
    / "campplus-torch/campplus_cn_common.bin"
)
_CAMPPLUS_ONNX = (
    REPO_ROOT
    / "output/public-base-release-20261010/bundle/releases/zs-v1/campplus.onnx"
)


@pytest.mark.skipif(
    not (_TORCH_WEIGHTS.is_file() and _CAMPPLUS_ONNX.is_file()),
    reason="local CAM++ torch weights or CAM++ ONNX (output/ artifacts) not present",
)
def test_real_torch_weights_match_onnx_192():
    import numpy as np
    import onnxruntime

    from piper_train.extract_speaker_embedding import extract_embedding

    model = CAMPPlus(feat_dim=80, embedding_size=192)
    sd = torch.load(_TORCH_WEIGHTS, map_location="cpu", weights_only=True)
    if isinstance(sd, dict) and "state_dict" in sd:
        sd = sd["state_dict"]
    model.load_state_dict(sd, strict=True)
    model.eval()

    torch.manual_seed(1)
    fbank = torch.randn(400, 80) * 2.0
    fbank = fbank - fbank.mean(dim=0, keepdim=True)
    with torch.no_grad():
        torch_emb = model(fbank.unsqueeze(0))[0].numpy()
    session = onnxruntime.InferenceSession(
        str(_CAMPPLUS_ONNX), providers=["CPUExecutionProvider"]
    )
    onnx_emb = extract_embedding(session, fbank.numpy())  # L2 正規化済み
    cos = float(
        np.dot(torch_emb, onnx_emb)
        / (np.linalg.norm(torch_emb) * np.linalg.norm(onnx_emb))
    )
    print(f"torch-vs-onnx cosine = {cos:.6f}")
    assert cos > 0.999
