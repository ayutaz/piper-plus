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


# ---------------------------------------------------------------------------
# 参照 spec (F-mel) frontend: 学習 cache (cache_norm_audio_fast) と同じ手順
# ---------------------------------------------------------------------------

from piper_train.norm_audio import (  # noqa: E402
    cache_norm_audio_fast,
    energy_vad_numpy,
)
from piper_train.reference_frontend import (  # noqa: E402
    REFERENCE_SPEC_FRONTEND,
    reference_spec_from_audio,
    reference_spec_from_file,
)
from piper_train.vits.mel_processing import spectrogram_torch  # noqa: E402


_SPEC_KW = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}


def voiced_with_silence(
    sr: int,
    *,
    lead: float = 0.5,
    voiced: float = 1.0,
    tail: float = 0.7,
    freq: float = 220.0,
    seed: int = 0,
) -> np.ndarray:
    """前後に無音を持つ有声区間 (tone + 弱い noise) を float32 で作る。"""
    rng = np.random.default_rng(seed)
    n = int(round(voiced * sr))
    body = tone(n, 0.3, sr, freq) + (0.01 * rng.standard_normal(n)).astype(
        np.float32
    )
    return np.concatenate(
        [
            np.zeros(int(round(lead * sr)), dtype=np.float32),
            body.astype(np.float32),
            np.zeros(int(round(tail * sr)), dtype=np.float32),
        ]
    )


def write_wav(path: Path, audio: np.ndarray, sr: int) -> Path:
    # FLOAT subtype: 学習 cache と frontend が同じ float32 sample を読む
    sf.write(str(path), audio, sr, subtype="FLOAT")
    return path


def cache_spec(path: Path, cache_dir: Path, target_sr: int, **kw) -> torch.Tensor:
    """学習 cache の ``.spec.pt`` (fp16) を作って読む。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    _norm, spec_path = cache_norm_audio_fast(
        path,
        cache_dir,
        target_sr,
        filter_length=kw.get("filter_length", 1024),
        window_length=kw.get("win_length", 1024),
        hop_length=kw.get("hop_length", 256),
    )
    return torch.load(spec_path, weights_only=True)


def frontend_spec(path: Path, target_sr: int, **kw):
    audio, src_sr = sf.read(str(path), dtype="float32", always_2d=False)
    return reference_spec_from_audio(
        audio, src_sr, target_sample_rate=target_sr, **{**_SPEC_KW, **kw}
    )


def assert_cache_parity(ours: torch.Tensor, cached: torch.Tensor) -> None:
    # 許容誤差 0 の根拠: cache は ``spectrogram_torch(...)`` の float32 結果を
    # ``.half()`` で保存する。frontend が同じ float32 sample に同じ演算列を
    # 適用していれば float32 値は bit 一致し、fp16 への丸め (round-to-nearest-
    # even、決定的) も一致する。1 ulp でもずれれば手順の差 (VAD 境界・resample
    # 品質・mixdown 順序) を意味するので緩めない。
    assert ours.dtype == torch.float32
    assert cached.dtype == torch.float16
    assert ours.shape == cached.shape
    assert torch.equal(ours.half(), cached)


def test_reference_spec_matches_cache_norm_audio_fast(tmp_path):
    sr = 22050
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    ours, _info = frontend_spec(path, sr)
    assert_cache_parity(ours, cache_spec(path, tmp_path / "cache", sr))


@pytest.mark.parametrize(
    "src_sr,target_sr", [(16000, 22050), (44100, 22050), (22050, 16000)]
)
def test_reference_spec_resamples_16k_and_44k(tmp_path, src_sr, target_sr):
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(src_sr), src_sr)
    ours, info = frontend_spec(path, target_sr)
    assert info["sample_rate"] == target_sr
    assert_cache_parity(ours, cache_spec(path, tmp_path / "cache", target_sr))


def test_reference_spec_stereo_mixdown_matches_cache(tmp_path):
    sr = 22050
    left = voiced_with_silence(sr, freq=220.0, seed=1)
    right = voiced_with_silence(sr, freq=330.0, seed=2) * np.float32(0.5)
    path = write_wav(tmp_path / "stereo.wav", np.stack([left, right], axis=1), sr)
    ours, _info = frontend_spec(path, sr)
    assert_cache_parity(ours, cache_spec(path, tmp_path / "cache", sr))


def test_reference_spec_non_default_stft_matches_cache(tmp_path):
    sr = 22050
    kw = {"filter_length": 512, "hop_length": 128, "win_length": 512}
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    ours, _info = frontend_spec(path, sr, **kw)
    assert ours.shape[0] == 512 // 2 + 1
    assert_cache_parity(ours, cache_spec(path, tmp_path / "cache", sr, **kw))


def test_reference_spec_from_file_matches_array_api(tmp_path):
    sr = 44100
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    from_file, file_info = reference_spec_from_file(
        path, target_sample_rate=22050, **_SPEC_KW
    )
    from_array, array_info = frontend_spec(path, 22050)
    assert torch.equal(from_file, from_array)
    assert file_info == array_info


def test_reference_spec_trim_bounds_follow_energy_vad():
    # 先頭 0.5 s 無音: 30 ms chunk の index 16 (0.48-0.51 s) が最初の有声 chunk、
    # keep_before=2 で 14 → offset 0.42 s。有声は 1.5 s で終わり、最後の有声
    # chunk 49 (1.47-1.50 s) + keep_after=2 → 51 → end 1.56 s (duration 1.14 s)
    sr = 22050
    _spec, info = reference_spec_from_audio(
        voiced_with_silence(sr), sr, target_sample_rate=sr, **_SPEC_KW
    )
    assert info["trim"] is True
    assert info["offset_sec"] == pytest.approx(0.42, abs=1e-9)
    assert info["duration_sec"] == pytest.approx(1.14, abs=1e-9)


def test_reference_spec_info_records_frontend_and_frames():
    sr = 22050
    spec, info = reference_spec_from_audio(
        voiced_with_silence(sr), sr, target_sample_rate=sr, **_SPEC_KW
    )
    assert REFERENCE_SPEC_FRONTEND == "energy-vad@16k;soxr-hq"
    assert info["frontend"] == REFERENCE_SPEC_FRONTEND
    assert info["frames"] == spec.shape[-1]
    assert spec.shape[0] == 513
    assert {
        k: info[k] for k in ("filter_length", "hop_length", "win_length", "center")
    } == {**_SPEC_KW, "center": False}


def test_reference_spec_trim_false_uses_whole_audio():
    import soxr

    src_sr, target_sr = 44100, 22050
    audio = voiced_with_silence(src_sr)
    ours, info = reference_spec_from_audio(
        audio, src_sr, target_sample_rate=target_sr, trim=False, **_SPEC_KW
    )
    # 独立に組んだ「VAD なし」: soxr HQ で全長を resample → spectrogram_torch。
    # 同じ演算列なので bit 一致を要求する
    expected = spectrogram_torch(
        torch.from_numpy(soxr.resample(audio, src_sr, target_sr, quality="HQ"))[None],
        1024,
        target_sr,
        256,
        1024,
        center=False,
    ).squeeze(0)
    assert torch.equal(ours, expected)
    assert info["trim"] is False
    assert info["frontend"] != REFERENCE_SPEC_FRONTEND


def test_reference_spec_trim_shortens_frames():
    sr = 22050
    audio = voiced_with_silence(sr)
    trimmed, _ = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, **_SPEC_KW
    )
    whole, _ = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, trim=False, **_SPEC_KW
    )
    assert trimmed.shape[-1] < whole.shape[-1]


def test_reference_spec_float64_input_is_cast_like_cache():
    # cache は soundfile の float32 読み出しを使う。float64 を渡しても float32
    # へ落としてから同じ手順を通す (精度を上げた別経路にしない)
    sr = 22050
    audio = voiced_with_silence(sr)
    a, _ = reference_spec_from_audio(audio, sr, target_sample_rate=sr, **_SPEC_KW)
    b, _ = reference_spec_from_audio(
        audio.astype(np.float64), sr, target_sample_rate=sr, **_SPEC_KW
    )
    assert torch.equal(a, b)


def test_reference_spec_minimum_length_gives_one_frame():
    # center=False + reflect pad (n_fft - hop) / 2 = 384: reflect は pad < 長さ
    # を要するので最小長は 385 sample、frame 数は (385 + 768 - 1024) // 256 + 1 = 1
    spec, info = reference_spec_from_audio(
        np.full(385, 0.1, dtype=np.float32),
        22050,
        target_sample_rate=22050,
        trim=False,
        **_SPEC_KW,
    )
    assert spec.shape == (513, 1)
    assert info["frames"] == 1


def test_reference_spec_below_minimum_length_raises():
    with pytest.raises(ValueError, match="too short"):
        reference_spec_from_audio(
            np.full(384, 0.1, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            trim=False,
            **_SPEC_KW,
        )


def test_reference_spec_silent_audio_raises():
    with pytest.raises(ValueError, match="no voiced"):
        reference_spec_from_audio(
            np.zeros(44100, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_reference_spec_non_finite_audio_raises(bad):
    audio = voiced_with_silence(22050)
    audio[1000] = bad
    with pytest.raises(ValueError, match="finite"):
        reference_spec_from_audio(audio, 22050, target_sample_rate=22050, **_SPEC_KW)


def test_reference_spec_empty_audio_raises():
    with pytest.raises(ValueError, match="empty"):
        reference_spec_from_audio(
            np.zeros(0, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            **_SPEC_KW,
        )


def test_reference_spec_rejects_3d_audio():
    with pytest.raises(ValueError, match="1-D"):
        reference_spec_from_audio(
            np.zeros((2, 2, 1000), dtype=np.float32),
            22050,
            target_sample_rate=22050,
            **_SPEC_KW,
        )


def test_reference_spec_rejects_integer_pcm():
    # int16 をそのまま float へ上げると振幅が 32768 倍になる (cache は
    # soundfile が [-1, 1] へ正規化した float32 を使う)
    with pytest.raises(TypeError, match="floating"):
        reference_spec_from_audio(
            np.zeros(4000, dtype=np.int16),
            22050,
            target_sample_rate=22050,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("field", ["sample_rate", "target_sample_rate"])
@pytest.mark.parametrize("value", [0, -16000])
def test_reference_spec_rejects_non_positive_sample_rate(field, value):
    kwargs = {"sample_rate": 22050, "target_sample_rate": 22050, **_SPEC_KW}
    kwargs[field] = value
    with pytest.raises(ValueError, match="sample_rate"):
        reference_spec_from_audio(voiced_with_silence(22050), **kwargs)


def test_reference_spec_does_not_mutate_input():
    audio = voiced_with_silence(22050)
    before = audio.copy()
    reference_spec_from_audio(audio, 22050, target_sample_rate=22050, **_SPEC_KW)
    assert np.array_equal(audio, before)


def test_reference_spec_vad_uses_cache_threshold():
    # RMS 0.019 (cache の閾値 0.02 をわずかに下回る) の区間は無音として切る。
    # 閾値を独自に変えると cache と異なる区間を切り出す
    sr = 16000
    quiet = np.full(sr, 0.019, dtype=np.float32)
    loud = voiced_with_silence(sr, lead=0.0, tail=0.0)
    audio = np.concatenate([quiet, loud, quiet])
    offset, duration = energy_vad_numpy(audio, threshold=0.02)
    _spec, info = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, **_SPEC_KW
    )
    assert info["offset_sec"] == pytest.approx(offset)
    assert info["duration_sec"] == pytest.approx(duration)
    assert info["offset_sec"] > 0.9


def test_reference_spec_sha256_hashes_float32_c_order_bytes():
    import hashlib

    from piper_train.reference_frontend import reference_spec_sha256

    spec = torch.arange(12, dtype=torch.float32).reshape(3, 4) / 7
    expected = hashlib.sha256(
        np.asarray(spec.numpy(), dtype="<f4", order="C").tobytes()
    ).hexdigest()
    assert reference_spec_sha256(spec) == expected


def test_reference_spec_sha256_ignores_memory_layout():
    from piper_train.reference_frontend import reference_spec_sha256

    spec = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    non_contiguous = spec.t().contiguous().t()
    assert not non_contiguous.is_contiguous()
    assert reference_spec_sha256(non_contiguous) == reference_spec_sha256(spec)


def test_reference_spec_sha256_detects_one_value_change():
    from piper_train.reference_frontend import reference_spec_sha256

    spec = torch.ones(513, 10)
    changed = spec.clone()
    changed[512, 9] = torch.nextafter(torch.tensor(1.0), torch.tensor(2.0))
    assert reference_spec_sha256(changed) != reference_spec_sha256(spec)


@pytest.mark.parametrize("dtype", [torch.float16, torch.float64, torch.int64])
def test_reference_spec_sha256_rejects_non_float32(dtype):
    # 丸めた spec (fp16 cache 等) を float32 の来歴として記録させない
    from piper_train.reference_frontend import reference_spec_sha256

    with pytest.raises(TypeError, match="float32"):
        reference_spec_sha256(torch.ones(4, 3, dtype=dtype))
