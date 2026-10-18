"""参照 spec (F-mel、``reference_conditioning="ref_spec"``) の契約値 (torch 非依存)。

frontend 名・ONNX config の schema 名・T_ref の上限・spec hash の定義を 1 箇所に
置く。``reference_frontend`` (torch)・``evaluation_manifest`` (numpy のみ)・
ONNX export はここから import する (文字列の重複によるずれを防ぐ)。

frontend は**実在する学習 cache builder を bit 単位で写した名前付きの選択肢**
(Ruling R14)。推論・評価でどれを使うかはモデルが学習した cache の作り方で
決まるので、既定値は持たない。

* ``"energy-vad@16k;soxr-hq"`` — ``norm_audio.cache_norm_audio_fast``:
  mono 化 → 16 kHz soxr HQ 上の ``energy_vad_numpy`` (閾値 0.02) で前後無音を
  切る (元 sr で切り出し) → soxr HQ でモデル sr へ → ``spectrogram_torch``。
* ``"no-vad;soxr-mq"`` / ``"no-vad;soxr-hq"`` — ``norm_audio.cache_norm_audio_no_vad``
  (``resample_quality="MQ"`` / ``"HQ"``、``prepare_multilingual_dataset`` の CPU
  経路。既定は MQ): mono 化 → soxr でモデル sr へ → ``spectrogram_torch``。

写していない builder (bit 単位では写せない):

* ``prepare_multilingual_dataset --gpu-spec-device``: audio は no-vad と同じだが、
  spec は 0 埋めした batch に ``spectrogram_torch`` をかけてから frame 数で切る
  ため、末尾の reflect pad 領域にかかる frame が単体計算と異なる (GPU FFT でもある)。
* ``tools/cache_audio.py`` + ``tools/batch_spectrograms.py``: VAD 用 16 kHz を
  soxr MQ で作り、spec は reflect pad ``n_fft // 2`` (= 512、``spectrogram_torch``
  の 384 と異なる) の GPU batch STFT。frame の位置と数が違う。
* ``norm_audio.cache_norm_audio`` (Silero VAD + torchaudio resample)。
"""

from __future__ import annotations

import hashlib

import numpy as np


REFERENCE_SPEC_SCHEMA = "ref_spec_v1"

# frontend 名 → 手順 (vad: 16 kHz soxr HQ 上の energy VAD で trim するか、
# resample_quality: モデル sr への soxr 品質、builder: 写している cache builder)
REFERENCE_SPEC_FRONTENDS: dict[str, dict] = {
    "energy-vad@16k;soxr-hq": {
        "vad": True,
        "resample_quality": "HQ",
        "builder": "piper_train.norm_audio.cache_norm_audio_fast",
    },
    "no-vad;soxr-mq": {
        "vad": False,
        "resample_quality": "MQ",
        "builder": "piper_train.norm_audio.cache_norm_audio_no_vad(resample_quality='MQ')",
    },
    "no-vad;soxr-hq": {
        "vad": False,
        "resample_quality": "HQ",
        "builder": "piper_train.norm_audio.cache_norm_audio_no_vad(resample_quality='HQ')",
    },
}

# T_ref の上限 (秒)。学習は参照 spec を最大 512 frame (~5.9 s) に切り出す。
# 30 s は長い参照を誤って丸ごと渡す事故 (self-attention は O(T^2)) を止める
# ための余裕を持った上限で、正常な参照発話を弾かない
REFERENCE_SPEC_MAX_SECONDS = 30.0


def frontend_steps(frontend: str) -> dict:
    """frontend 名の手順を返す。

    Raises:
        ValueError: 閉じた集合 ``REFERENCE_SPEC_FRONTENDS`` に無い名前。
    """
    if not isinstance(frontend, str) or frontend not in REFERENCE_SPEC_FRONTENDS:
        raise ValueError(
            f"Unknown reference spec frontend {frontend!r}; expected one of "
            f"{sorted(REFERENCE_SPEC_FRONTENDS)}"
        )
    return REFERENCE_SPEC_FRONTENDS[frontend]


def max_reference_frames(sample_rate: int, hop_length: int) -> int:
    """T_ref の上限 frame 数 (``int(30 s × sample_rate) // hop_length``)。"""
    return int(REFERENCE_SPEC_MAX_SECONDS * sample_rate) // hop_length


def spec_array_sha256(array: np.ndarray) -> str:
    """参照 spec の来歴 hash (float32 little-endian・C 順の bytes の sha256)。

    Raises:
        TypeError: float32 でない (fp16 cache 等の丸めた spec を float32 の
            来歴として記録させない)。
    """
    array = np.asarray(array)
    if array.dtype != np.float32:
        raise TypeError(f"reference spec hash requires float32, got {array.dtype}")
    data = np.ascontiguousarray(array, dtype=np.dtype("<f4"))
    return hashlib.sha256(data.tobytes()).hexdigest()
