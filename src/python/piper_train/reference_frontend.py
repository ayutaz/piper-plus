"""参照音声のフロントエンド処理 (学習時 audio_norm と同じ前処理への寄せ込み)。

学習時の CAM++ embedding は energy VAD で trim した ``audio_norm`` から抽出されて
いる。推論時の参照 WAV は無加工で fbank 化されるため、前後の無音が CMVN 平均に
混入する。``trim_reference_audio`` は ``cache_norm_audio_fast`` と同じ手順
(16kHz soxr HQ → ``energy_vad_numpy`` → 元 sample rate で切り出し) を再現する。
"""

from __future__ import annotations

import numpy as np
import torch


VAD_METHOD = "energy_vad_numpy@16k"

# 参照 spec の前処理を表す文字列 (config.json ``reference_conditioning.frontend``
# と評価 manifest に記録する契約値)。trim=False は別の文字列にする
REFERENCE_SPEC_FRONTEND = "energy-vad@16k;soxr-hq"
REFERENCE_SPEC_FRONTEND_NO_TRIM = "no-vad;soxr-hq"


def reference_spec_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    *,
    target_sample_rate: int,
    filter_length: int,
    hop_length: int,
    win_length: int,
    trim: bool = True,
) -> tuple[torch.Tensor, dict]:
    """学習 cache (``cache_norm_audio_fast``) と同じ手順で参照の線形振幅 spec を作る。

    手順: float32 化 → stereo なら channel 平均 → (trim 時) 16kHz soxr HQ 上で
    ``energy_vad_numpy`` (cache と同じ閾値・chunk) → 元 sample rate で切り出し →
    soxr HQ で ``target_sample_rate`` へ → ``spectrogram_torch(center=False)``。
    学習 cache の ``.spec.pt`` はこの戻り値を ``.half()`` したものと一致する。

    Args:
        audio: ``[samples]`` または soundfile 形式の ``[samples, channels]``。
            浮動小数点 ([-1, 1] に正規化済み) のみ受け付ける。
        sample_rate: ``audio`` の sample rate。
        target_sample_rate: モデルの sample rate。
        filter_length / hop_length / win_length: STFT 設定 (学習 hparams と同じ)。
        trim: False なら VAD を通さず全長を使う (frontend 文字列も変わる)。

    Returns:
        (spec ``[filter_length // 2 + 1, T]`` float32, info)。info は
        ``frontend`` / ``trim`` / ``offset_sec`` / ``duration_sec`` /
        ``frames`` / ``sample_rate`` / STFT 設定 / ``center``。

    Raises:
        TypeError: 浮動小数点でない音声 (int PCM の取り違え)。
        ValueError: 空・形状違い・非有限値・sample rate が正でない・有声区間なし
            (trim 時)・STFT 1 frame に満たない長さ。
    """
    import soxr  # noqa: PLC0415 — lazy import (optional runtime dependency)

    from .vits.mel_processing import spectrogram_torch  # noqa: PLC0415

    for name, value in (
        ("sample_rate", sample_rate),
        ("target_sample_rate", target_sample_rate),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be an integer, got {value!r}")
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value}")
    audio = np.asarray(audio)
    if not np.issubdtype(audio.dtype, np.floating):
        raise TypeError(
            f"reference audio must be floating point in [-1, 1], got {audio.dtype}"
        )
    if audio.ndim not in (1, 2):
        raise ValueError(
            "reference audio must be 1-D [samples] or 2-D [samples, channels], "
            f"got shape {audio.shape}"
        )
    if audio.size == 0:
        raise ValueError("reference audio is empty")
    # cache は soundfile の float32 読み出しを使う (新しい配列を作るので入力は不変)
    audio = audio.astype(np.float32)
    if not np.isfinite(audio).all():
        raise ValueError("reference audio must be finite (NaN/Inf found)")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)  # stereo → mono (cache と同じ)

    if trim:
        trimmed, vad = trim_reference_audio(audio, int(sample_rate))
        offset_sec, duration_sec = vad["offset_sec"], vad["duration_sec"]
        frontend = REFERENCE_SPEC_FRONTEND
    else:
        trimmed, offset_sec, duration_sec = audio, 0.0, len(audio) / sample_rate
        frontend = REFERENCE_SPEC_FRONTEND_NO_TRIM
    audio_rs = (
        soxr.resample(trimmed, sample_rate, target_sample_rate, quality="HQ")
        if sample_rate != target_sample_rate
        else trimmed
    )
    pad = int((filter_length - hop_length) / 2)
    if len(audio_rs) <= pad or len(audio_rs) + 2 * pad < filter_length:
        raise ValueError(
            f"reference audio too short for one STFT frame: {len(audio_rs)} "
            f"samples at {target_sample_rate} Hz (need > {pad})"
        )
    spec = spectrogram_torch(
        y=torch.from_numpy(np.ascontiguousarray(audio_rs)).unsqueeze(0),
        n_fft=filter_length,
        sampling_rate=target_sample_rate,
        hop_size=hop_length,
        win_size=win_length,
        center=False,
    ).squeeze(0)
    info = {
        "frontend": frontend,
        "trim": bool(trim),
        "offset_sec": float(offset_sec),
        "duration_sec": float(duration_sec),
        "frames": int(spec.shape[-1]),
        "sample_rate": int(target_sample_rate),
        "filter_length": int(filter_length),
        "hop_length": int(hop_length),
        "win_length": int(win_length),
        "center": False,
    }
    return spec, info


def reference_spec_from_file(
    path,
    *,
    target_sample_rate: int,
    filter_length: int,
    hop_length: int,
    win_length: int,
    trim: bool = True,
) -> tuple[torch.Tensor, dict]:
    """音声ファイルを学習 cache と同じ reader で読み ``reference_spec_from_audio`` へ渡す。"""
    from .norm_audio import _read_audio_any  # noqa: PLC0415

    audio, sample_rate = _read_audio_any(path)
    return reference_spec_from_audio(
        audio,
        sample_rate,
        target_sample_rate=target_sample_rate,
        filter_length=filter_length,
        hop_length=hop_length,
        win_length=win_length,
        trim=trim,
    )


def reference_spec_sha256(spec: torch.Tensor) -> str:
    """参照 spec の来歴 hash (float32 little-endian・C 順の bytes の sha256)。

    Raises:
        TypeError: float32 でない (fp16 cache 等の丸めた spec を float32 の
            来歴として記録させない)。
    """
    import hashlib  # noqa: PLC0415

    if spec.dtype != torch.float32:
        raise TypeError(f"reference spec hash requires float32, got {spec.dtype}")
    array = np.ascontiguousarray(spec.detach().cpu().numpy(), dtype=np.dtype("<f4"))
    return hashlib.sha256(array.tobytes()).hexdigest()


def trim_reference_audio(
    audio: np.ndarray, sample_rate: int
) -> tuple[np.ndarray, dict]:
    """学習時と同じ energy VAD で参照音声の前後無音を除去する。

    Args:
        audio: モノラル波形 (1 次元)。
        sample_rate: ``audio`` の sample rate。

    Returns:
        (trim 後の波形 (元 sample rate), {offset_sec, duration_sec, method})。

    Raises:
        ValueError: 有声区間が検出できない場合。
    """
    from .norm_audio import energy_vad_numpy  # noqa: PLC0415

    audio = np.asarray(audio)
    if sample_rate != 16000:
        import soxr  # noqa: PLC0415 — lazy import (optional runtime dependency)

        audio_16k = soxr.resample(audio, sample_rate, 16000, quality="HQ")
    else:
        audio_16k = audio

    offset_sec, duration_sec = energy_vad_numpy(
        audio_16k, chunk_size=480, threshold=0.02, keep_before=2, keep_after=2
    )
    if duration_sec is None:
        raise ValueError("no voiced segment detected in reference audio")

    # cache_norm_audio_fast と同じ: 元 sample rate の sample 数へ換算して切る
    offset_samples = int(offset_sec * sample_rate)
    end_samples = min(offset_samples + int(duration_sec * sample_rate), len(audio))
    trimmed = audio[offset_samples:end_samples]
    info = {
        "offset_sec": float(offset_sec),
        "duration_sec": float(duration_sec),
        "method": VAD_METHOD,
    }
    return trimmed, info


def in_graph_capture() -> bool:
    """ONNX export / jit trace / torch.compile の graph 取得中なら True。

    データ依存の検査 (``bool(tensor)``) はこの間に走らせると trace 時の入力で
    分岐が定数として焼き込まれる (または graph break になる) ため飛ばす。
    """
    return (
        torch.onnx.is_in_onnx_export()
        or torch.jit.is_tracing()
        or torch.compiler.is_compiling()
    )


def masked_time_mean_fp32(
    x: torch.Tensor, mask: torch.Tensor, *, check: bool = True
) -> torch.Tensor:
    """mask 付き時間平均を float32 で計算する。

    fp16 入力でも overflow しないよう、float32 へ上げて ``x / length`` を先に
    計算してから時間方向に和をとる。

    Args:
        x: ``[B, C, T]``。
        mask: ``[B, 1, T]`` (1=有効, 0=無効)。
        check: 有効フレーム 0 の行を検査する (host 同期 1 回)。呼び出し側で
            長さを検査済みなら False。graph 取得中は常に省略する。

    Returns:
        ``[B, C]`` float32。

    Raises:
        ValueError: ``check`` 時、いずれかの行で mask の有効フレームが 0 の場合。
    """
    mask32 = mask.to(torch.float32)
    length = mask32.sum(dim=-1)  # [B, 1]
    if check and not in_graph_capture() and bool((length <= 0).any()):
        raise ValueError("mask has a row with no valid frames")
    weighted = x.to(torch.float32) * mask32 / length.unsqueeze(-1)
    return weighted.sum(dim=-1)


def campplus_stats(model, fbank: torch.Tensor) -> torch.Tensor:
    """CAM++ の statistics pooling 直前 (``out_nonlinear`` 出力) の平均+標準偏差。

    ``head`` と ``xvector`` の ``stats`` / ``dense`` を除く全モジュールを通し、
    時間方向の平均と不偏標準偏差 (``statistics_pooling`` と同じ定義) を float32
    で計算する (reduction 前に float32 へ upcast)。fbank は 1 batch 内で同一長
    を前提とし、padding mask は扱わない。

    Args:
        model: ``CAMPPlus``。
        fbank: ``[B, T, 80]``。

    Returns:
        ``[B, 1024]`` float32 (``cat(mean, std)``)。``dense`` は通さない。
    """
    x = fbank.permute(0, 2, 1)  # (B,T,F) => (B,F,T)
    x = model.head(x)
    for name, module in model.xvector.named_children():
        if name in ("stats", "dense"):
            break
        x = module(x)
    x = x.to(torch.float32)
    mean = x.mean(dim=-1)
    std = x.std(dim=-1, unbiased=True)
    return torch.cat([mean, std], dim=-1)
