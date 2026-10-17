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
