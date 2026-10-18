"""参照音声trim (学習時と同じenergy VAD) のテスト。"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf


# Windows CI (``[test,inference]``) は torch / soxr を入れない。module 最上位で
# torch を import するので、collection の ImportError ではなく skip にする
pytest.importorskip("torch", reason="reference frontend tests require torch")
pytest.importorskip("soxr", reason="reference frontend tests require soxr")

from piper_train.extract_speaker_embedding import preprocess_audio  # noqa: E402
from piper_train.reference_frontend import trim_reference_audio  # noqa: E402

pytestmark = pytest.mark.unit


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
# 参照 spec (F-mel) frontend: 名前付きの学習 cache builder を bit 単位で再現する
# (Ruling R14: frontend は実在する cache builder を写した明示的な選択肢)
# ---------------------------------------------------------------------------

from piper_train.norm_audio import (  # noqa: E402
    cache_norm_audio_fast,
    cache_norm_audio_no_vad,
    energy_vad_numpy,
)
from piper_train.reference_frontend import (  # noqa: E402
    reference_spec_from_audio,
    reference_spec_from_file,
)
from piper_train.reference_spec_contract import (  # noqa: E402
    REFERENCE_SPEC_FRONTENDS,
    REFERENCE_SPEC_MAX_SECONDS,
    max_reference_frames,
)
from piper_train.vits.mel_processing import spectrogram_torch  # noqa: E402


_SPEC_KW = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}
VAD = "energy-vad@16k;soxr-hq"
NO_VAD_MQ = "no-vad;soxr-mq"
NO_VAD_HQ = "no-vad;soxr-hq"
ALL_FRONTENDS = [VAD, NO_VAD_MQ, NO_VAD_HQ]


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
    n = round(voiced * sr)
    body = tone(n, 0.3, sr, freq) + (0.01 * rng.standard_normal(n)).astype(np.float32)
    return np.concatenate(
        [
            np.zeros(round(lead * sr), dtype=np.float32),
            body.astype(np.float32),
            np.zeros(round(tail * sr), dtype=np.float32),
        ]
    )


def write_wav(path: Path, audio: np.ndarray, sr: int) -> Path:
    # FLOAT subtype: 学習 cache と frontend が同じ float32 sample を読む
    sf.write(str(path), audio, sr, subtype="FLOAT")
    return path


def builder_spec(
    frontend: str, path: Path, cache_dir: Path, target_sr: int, **kw
) -> torch.Tensor:
    """frontend 名が写すはずの実在 cache builder を走らせ ``.spec.pt`` (fp16) を読む。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    stft = {
        "filter_length": kw.get("filter_length", 1024),
        "window_length": kw.get("win_length", 1024),
        "hop_length": kw.get("hop_length", 256),
    }
    if frontend == VAD:
        _norm, spec_path = cache_norm_audio_fast(path, cache_dir, target_sr, **stft)
    else:
        quality = {NO_VAD_MQ: "MQ", NO_VAD_HQ: "HQ"}[frontend]
        _norm, spec_path = cache_norm_audio_no_vad(
            path, cache_dir, target_sr, resample_quality=quality, **stft
        )
    return torch.load(spec_path, weights_only=True)


def frontend_spec(path: Path, target_sr: int, frontend: str, **kw):
    audio, src_sr = sf.read(str(path), dtype="float32", always_2d=False)
    return reference_spec_from_audio(
        audio,
        src_sr,
        target_sample_rate=target_sr,
        frontend=frontend,
        **{**_SPEC_KW, **kw},
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


def test_reference_spec_frontends_are_a_closed_set():
    # 実在する CPU 逐次の cache builder を写すものだけ。GPU batch STFT の
    # builder (batch 内 0 埋め後の reflect pad / pad 512) は bit 単位で写せない
    assert set(REFERENCE_SPEC_FRONTENDS) == set(ALL_FRONTENDS)


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
def test_reference_spec_matches_training_cache_builder(tmp_path, frontend):
    sr = 22050
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    ours, _info = frontend_spec(path, sr, frontend)
    assert_cache_parity(ours, builder_spec(frontend, path, tmp_path / "cache", sr))


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
@pytest.mark.parametrize(
    "src_sr,target_sr", [(16000, 22050), (44100, 22050), (22050, 16000)]
)
def test_reference_spec_resamples_16k_and_44k(tmp_path, frontend, src_sr, target_sr):
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(src_sr), src_sr)
    ours, info = frontend_spec(path, target_sr, frontend)
    assert info["sample_rate"] == target_sr
    assert_cache_parity(
        ours, builder_spec(frontend, path, tmp_path / "cache", target_sr)
    )


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
def test_reference_spec_stereo_mixdown_matches_cache(tmp_path, frontend):
    sr = 22050
    left = voiced_with_silence(sr, freq=220.0, seed=1)
    right = voiced_with_silence(sr, freq=330.0, seed=2) * np.float32(0.5)
    path = write_wav(tmp_path / "stereo.wav", np.stack([left, right], axis=1), sr)
    ours, _info = frontend_spec(path, sr, frontend)
    assert_cache_parity(ours, builder_spec(frontend, path, tmp_path / "cache", sr))


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
def test_reference_spec_non_default_stft_matches_cache(tmp_path, frontend):
    sr = 22050
    kw = {"filter_length": 512, "hop_length": 128, "win_length": 512}
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    ours, _info = frontend_spec(path, sr, frontend, **kw)
    assert ours.shape[0] == 512 // 2 + 1
    assert_cache_parity(
        ours, builder_spec(frontend, path, tmp_path / "cache", sr, **kw)
    )


def test_reference_spec_mq_and_hq_differ():
    # 品質の取り違えを parity テストが見分けられること (MQ と HQ で値が違う)
    audio = voiced_with_silence(44100)
    mq, _ = reference_spec_from_audio(
        audio, 44100, target_sample_rate=22050, frontend=NO_VAD_MQ, **_SPEC_KW
    )
    hq, _ = reference_spec_from_audio(
        audio, 44100, target_sample_rate=22050, frontend=NO_VAD_HQ, **_SPEC_KW
    )
    assert mq.shape == hq.shape
    assert not torch.equal(mq.half(), hq.half())


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
def test_reference_spec_from_file_matches_array_api(tmp_path, frontend):
    sr = 44100
    path = write_wav(tmp_path / "ref.wav", voiced_with_silence(sr), sr)
    from_file, file_info = reference_spec_from_file(
        path, target_sample_rate=22050, frontend=frontend, **_SPEC_KW
    )
    from_array, array_info = frontend_spec(path, 22050, frontend)
    assert torch.equal(from_file, from_array)
    assert file_info == array_info


def test_reference_spec_trim_bounds_follow_energy_vad():
    # 先頭 0.5 s 無音: 30 ms chunk の index 16 (0.48-0.51 s) が最初の有声 chunk、
    # keep_before=2 で 14 → offset 0.42 s。有声は 1.5 s で終わり、最後の有声
    # chunk 49 (1.47-1.50 s) + keep_after=2 → 51 → end 1.56 s (duration 1.14 s)
    sr = 22050
    _spec, info = reference_spec_from_audio(
        voiced_with_silence(sr), sr, target_sample_rate=sr, frontend=VAD, **_SPEC_KW
    )
    assert info["vad"] is True
    assert info["offset_sec"] == pytest.approx(0.42, abs=1e-9)
    assert info["duration_sec"] == pytest.approx(1.14, abs=1e-9)


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_keeps_whole_audio(frontend):
    # VAD なしは前後の無音を残す: center=False の frame 数は全長から決まる
    # ((L + 2 * 384 - 1024) // 256 + 1、L = 2.2 s × 22050 = 48510 → 189)
    sr = 22050
    audio = voiced_with_silence(sr)
    assert len(audio) == 48510
    spec, info = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, frontend=frontend, **_SPEC_KW
    )
    assert spec.shape[-1] == (48510 + 768 - 1024) // 256 + 1 == 189
    assert info["vad"] is False
    assert info["offset_sec"] == 0.0


def test_reference_spec_vad_frontend_trims_frames():
    sr = 22050
    audio = voiced_with_silence(sr)
    trimmed, _ = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, frontend=VAD, **_SPEC_KW
    )
    whole, _ = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, frontend=NO_VAD_HQ, **_SPEC_KW
    )
    assert trimmed.shape[-1] < whole.shape[-1]


@pytest.mark.parametrize("frontend", ALL_FRONTENDS)
def test_reference_spec_info_records_frontend_and_frames(frontend):
    sr = 22050
    spec, info = reference_spec_from_audio(
        voiced_with_silence(sr),
        sr,
        target_sample_rate=sr,
        frontend=frontend,
        **_SPEC_KW,
    )
    assert info["frontend"] == frontend
    assert info["frames"] == spec.shape[-1]
    assert spec.shape[0] == 513
    assert {
        k: info[k] for k in ("filter_length", "hop_length", "win_length", "center")
    } == {**_SPEC_KW, "center": False}


def test_reference_spec_unknown_frontend_raises():
    with pytest.raises(ValueError, match="frontend"):
        reference_spec_from_audio(
            voiced_with_silence(22050),
            22050,
            target_sample_rate=22050,
            frontend="silero-vad;torchaudio",
            **_SPEC_KW,
        )


def test_reference_spec_frontend_is_required():
    # 既定値で 1 つの builder を黙って仮定しない
    with pytest.raises(TypeError):
        reference_spec_from_audio(
            voiced_with_silence(22050), 22050, target_sample_rate=22050, **_SPEC_KW
        )


def test_reference_spec_float64_input_is_cast_like_cache():
    # cache は soundfile の float32 読み出しを使う。float64 を渡しても float32
    # へ落としてから同じ手順を通す (精度を上げた別経路にしない)
    sr = 22050
    audio = voiced_with_silence(sr)
    a, _ = reference_spec_from_audio(
        audio, sr, target_sample_rate=sr, frontend=VAD, **_SPEC_KW
    )
    b, _ = reference_spec_from_audio(
        audio.astype(np.float64), sr, target_sample_rate=sr, frontend=VAD, **_SPEC_KW
    )
    assert torch.equal(a, b)


def test_reference_spec_shortest_voiced_audio_gives_one_frame():
    # 有声判定の最小単位は 16 kHz の 1 chunk (480 sample = 30 ms)。VAD なしで
    # 16 kHz の 480 sample は (480 + 768 - 1024) // 256 + 1 = 1 frame
    spec, info = reference_spec_from_audio(
        np.full(480, 0.1, dtype=np.float32),
        16000,
        target_sample_rate=16000,
        frontend=NO_VAD_HQ,
        **_SPEC_KW,
    )
    assert spec.shape == (513, 1)
    assert info["frames"] == 1


def test_reference_spec_vad_shorter_than_one_vad_chunk_raises():
    # VAD frontend: 479 sample (< 1 chunk) は有声判定ができないので、有声区間
    # なしとして拒否する
    with pytest.raises(ValueError, match="no voiced"):
        reference_spec_from_audio(
            np.full(479, 0.1, dtype=np.float32),
            16000,
            target_sample_rate=16000,
            frontend=VAD,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_accepts_audio_shorter_than_one_vad_chunk(frontend):
    # VAD なしの builder (cache_norm_audio_no_vad) は VAD chunk の長さを問わない。
    # STFT 1 frame 分あれば受け付ける: (479 + 768 - 1024) // 256 + 1 = 1 frame
    spec, info = reference_spec_from_audio(
        np.full(479, 0.1, dtype=np.float32),
        16000,
        target_sample_rate=16000,
        frontend=frontend,
        **_SPEC_KW,
    )
    assert spec.shape == (513, 1)
    assert info["frames"] == 1


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_quiet_audio_matches_builder(tmp_path, frontend):
    # 全 chunk が VAD 閾値 (RMS 0.02) 未満の小音量録音も、VAD なしの builder は
    # 学習 cache に入れる。frontend も拒否せず、builder と bit 一致させる
    sr = 44100
    audio = tone(sr, 0.005, sr)  # RMS ≈ 0.0035
    path = write_wav(tmp_path / "quiet.wav", audio, sr)
    ours, _info = frontend_spec(path, 22050, frontend)
    assert_cache_parity(ours, builder_spec(frontend, path, tmp_path / "cache", 22050))


def test_reference_spec_vad_quiet_audio_raises():
    # VAD frontend は有声区間なしとして拒否する (従来どおり)
    with pytest.raises(ValueError, match="no voiced"):
        reference_spec_from_audio(
            tone(44100, 0.005, 44100),
            44100,
            target_sample_rate=22050,
            frontend=VAD,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_single_nonzero_sample_accepted(frontend):
    # デジタル無音 (全 sample が厳密に 0) でなければ受け付ける
    audio = np.zeros(22050, dtype=np.float32)
    audio[100] = 1e-4
    spec, _info = reference_spec_from_audio(
        audio, 22050, target_sample_rate=22050, frontend=frontend, **_SPEC_KW
    )
    assert spec.shape[-1] == (22050 + 768 - 1024) // 256 + 1


_LONG_FFT = {"filter_length": 8192, "hop_length": 256, "win_length": 8192}


def test_reference_spec_reflect_pad_boundary_passes():
    # filter 8192 / hop 256 の reflect pad は (8192 - 256) / 2 = 3968。reflect は
    # pad < 長さを要するので 3969 sample が最短 → (3969 + 7936 - 8192) // 256 + 1 = 15
    spec, _ = reference_spec_from_audio(
        np.full(3969, 0.1, dtype=np.float32),
        16000,
        target_sample_rate=16000,
        frontend=NO_VAD_HQ,
        **_LONG_FFT,
    )
    assert spec.shape == (4097, 15)


def test_reference_spec_below_reflect_pad_raises():
    with pytest.raises(ValueError, match="too short"):
        reference_spec_from_audio(
            np.full(3968, 0.1, dtype=np.float32),
            16000,
            target_sample_rate=16000,
            frontend=NO_VAD_HQ,
            **_LONG_FFT,
        )


def test_reference_spec_max_frames_boundary_passes():
    # 上限 T_ref = int(30 s × sr) // hop。16 kHz / hop 256 なら 1875 frame。
    # VAD なしで L = 1875 × 256 sample → (L + 768 - 1024) // 256 + 1 = 1875
    sr = 16000
    limit = max_reference_frames(sr, 256)
    assert REFERENCE_SPEC_MAX_SECONDS == 30.0
    assert limit == 1875
    spec, _ = reference_spec_from_audio(
        np.full(limit * 256, 0.1, dtype=np.float32),
        sr,
        target_sample_rate=sr,
        frontend=NO_VAD_HQ,
        **_SPEC_KW,
    )
    assert spec.shape[-1] == limit


def test_reference_spec_above_max_frames_raises():
    sr = 16000
    limit = max_reference_frames(sr, 256)
    with pytest.raises(ValueError, match="T_ref"):
        reference_spec_from_audio(
            np.full((limit + 1) * 256, 0.1, dtype=np.float32),
            sr,
            target_sample_rate=sr,
            frontend=NO_VAD_HQ,
            **_SPEC_KW,
        )


def test_reference_spec_vad_silent_audio_raises():
    with pytest.raises(ValueError, match="no voiced"):
        reference_spec_from_audio(
            np.zeros(44100, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            frontend=VAD,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_digital_silence_raises(frontend):
    # VAD なしの frontend は、デジタル無音 (全 sample が厳密に 0) だけを
    # 話者情報のない参照として拒否する (小音量・短い録音は builder どおり通す)
    with pytest.raises(ValueError, match="digitally silent"):
        reference_spec_from_audio(
            np.zeros(44100, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            frontend=frontend,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("frontend", [NO_VAD_MQ, NO_VAD_HQ])
def test_reference_spec_no_vad_digital_silence_stereo_raises(frontend):
    with pytest.raises(ValueError, match="digitally silent"):
        reference_spec_from_audio(
            np.zeros((44100, 2), dtype=np.float32),
            22050,
            target_sample_rate=22050,
            frontend=frontend,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_reference_spec_non_finite_audio_raises(bad):
    audio = voiced_with_silence(22050)
    audio[1000] = bad
    with pytest.raises(ValueError, match="finite"):
        reference_spec_from_audio(
            audio, 22050, target_sample_rate=22050, frontend=VAD, **_SPEC_KW
        )


def test_reference_spec_overflowing_spec_raises():
    # 入力は有限でも |x| が極端に大きいと STFT の pow(2) が float32 で overflow
    # する (1e30 × 窓和 ~512 → 二乗で 1e65 > 3.4e38)。feed 前に拒否する
    audio = np.full(4000, 1e30, dtype=np.float32)
    with pytest.raises(ValueError, match="finite"):
        reference_spec_from_audio(
            audio, 22050, target_sample_rate=22050, frontend=NO_VAD_HQ, **_SPEC_KW
        )


def test_reference_spec_empty_audio_raises():
    with pytest.raises(ValueError, match="empty"):
        reference_spec_from_audio(
            np.zeros(0, dtype=np.float32),
            22050,
            target_sample_rate=22050,
            frontend=VAD,
            **_SPEC_KW,
        )


def test_reference_spec_rejects_3d_audio():
    with pytest.raises(ValueError, match="1-D"):
        reference_spec_from_audio(
            np.zeros((2, 2, 1000), dtype=np.float32),
            22050,
            target_sample_rate=22050,
            frontend=VAD,
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
            frontend=VAD,
            **_SPEC_KW,
        )


@pytest.mark.parametrize("field", ["sample_rate", "target_sample_rate"])
@pytest.mark.parametrize("value", [0, -16000])
def test_reference_spec_rejects_non_positive_sample_rate(field, value):
    kwargs = {
        "sample_rate": 22050,
        "target_sample_rate": 22050,
        "frontend": VAD,
        **_SPEC_KW,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="sample_rate"):
        reference_spec_from_audio(voiced_with_silence(22050), **kwargs)


def test_reference_spec_does_not_mutate_input():
    audio = voiced_with_silence(22050)
    before = audio.copy()
    reference_spec_from_audio(
        audio, 22050, target_sample_rate=22050, frontend=VAD, **_SPEC_KW
    )
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
        audio, sr, target_sample_rate=sr, frontend=VAD, **_SPEC_KW
    )
    assert info["offset_sec"] == pytest.approx(offset)
    assert info["duration_sec"] == pytest.approx(duration)
    assert info["offset_sec"] > 0.9


def test_reference_spec_trim_matches_trim_spectrogram_independent():
    # VAD frontend: energy VAD 区間を元 sr で切ってから soxr HQ → STFT
    # (独立に組み立てた手順と bit 一致)
    import soxr

    src_sr, target_sr = 44100, 22050
    audio = voiced_with_silence(src_sr)
    trimmed, _ = trim_reference_audio(audio, src_sr)
    expected = spectrogram_torch(
        torch.from_numpy(soxr.resample(trimmed, src_sr, target_sr, quality="HQ"))[None],
        1024,
        target_sr,
        256,
        1024,
        center=False,
    ).squeeze(0)
    ours, _ = reference_spec_from_audio(
        audio, src_sr, target_sample_rate=target_sr, frontend=VAD, **_SPEC_KW
    )
    assert torch.equal(ours, expected)


def test_reference_spec_sha256_hashes_float32_c_order_bytes():
    import hashlib

    from piper_train.reference_frontend import reference_spec_sha256

    spec = torch.arange(12, dtype=torch.float32).reshape(3, 4) / 7
    expected = hashlib.sha256(
        np.asarray(spec.numpy(), dtype="<f4", order="C").tobytes()
    ).hexdigest()
    assert reference_spec_sha256(spec) == expected


def test_reference_spec_sha256_matches_numpy_contract_hash():
    # manifest 検証 (torch なし) は numpy 配列で同じ hash を計算する
    from piper_train.reference_frontend import reference_spec_sha256
    from piper_train.reference_spec_contract import spec_array_sha256

    spec = torch.randn(513, 7, generator=torch.Generator().manual_seed(0)).abs()
    assert reference_spec_sha256(spec) == spec_array_sha256(spec.numpy())


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
