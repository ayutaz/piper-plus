"""参照音声のフロントエンド処理 (学習時 audio_norm と同じ前処理への寄せ込み)。

学習時の CAM++ embedding は energy VAD で trim した ``audio_norm`` から抽出されて
いる。推論時の参照 WAV は無加工で fbank 化されるため、前後の無音が CMVN 平均に
混入する。``trim_reference_audio`` は ``cache_norm_audio_fast`` と同じ手順
(16kHz soxr HQ → ``energy_vad_numpy`` → 元 sample rate で切り出し) を再現する。
"""

from __future__ import annotations

import numpy as np


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
