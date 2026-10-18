"""参照音声のフロントエンド処理 (学習時 audio_norm と同じ前処理への寄せ込み)。

学習時の CAM++ embedding は energy VAD で trim した ``audio_norm`` から抽出されて
いる。推論時の参照 WAV は無加工で fbank 化されるため、前後の無音が CMVN 平均に
混入する。``trim_reference_audio`` は ``cache_norm_audio_fast`` と同じ手順
(16kHz soxr HQ → ``energy_vad_numpy`` → 元 sample rate で切り出し) を再現する。

参照 spec (F-mel、``reference_conditioning="ref_spec"``) は
``reference_spec_from_audio`` が名前付き frontend (``reference_spec_contract``
の閉じた集合。各名前が実在する学習 cache builder を bit 単位で写す) で作る。
参照 spec の frontend 選択は CAM++ 192 次元の経路 (``campplus_stats`` 等) を
変えない。
"""

from __future__ import annotations

import numpy as np
import torch

from .reference_spec_contract import (
    frontend_steps,
    max_reference_frames,
    spec_array_sha256,
)


VAD_METHOD = "energy_vad_numpy@16k"


def reference_spec_from_audio(
    audio: np.ndarray,
    sample_rate: int,
    *,
    target_sample_rate: int,
    filter_length: int,
    hop_length: int,
    win_length: int,
    frontend: str,
) -> tuple[torch.Tensor, dict]:
    """名前付きの学習 cache builder と同じ手順で参照の線形振幅 spec を作る。

    ``frontend`` は ``reference_spec_contract.REFERENCE_SPEC_FRONTENDS`` の閉じた
    集合から選ぶ (既定値なし。モデルが学習した cache の作り方に合わせる)。
    手順: float32 化 → stereo なら channel 平均 → (VAD frontend のみ) 16kHz
    soxr HQ 上で ``energy_vad_numpy`` (cache と同じ閾値・chunk) → 元 sample rate
    で切り出し → frontend の品質の soxr で ``target_sample_rate`` へ →
    ``spectrogram_torch(center=False)``。対応する builder の ``.spec.pt`` は
    この戻り値を ``.half()`` したものと一致する。

    Args:
        audio: ``[samples]`` または soundfile 形式の ``[samples, channels]``。
            浮動小数点のみ (soundfile の float32 読み出しと同じ [-1, 1] 正規化を
            想定。振幅範囲は cache と同じく検査しないが、STFT が非有限になる
            極端な振幅は拒否する)。
        sample_rate: ``audio`` の sample rate。
        target_sample_rate: モデルの sample rate。
        filter_length / hop_length / win_length: STFT 設定 (学習 hparams と同じ)。
        frontend: frontend 名 (例 ``"no-vad;soxr-mq"``)。

    Returns:
        (spec ``[filter_length // 2 + 1, T]`` float32, info)。info は
        ``frontend`` / ``vad`` / ``offset_sec`` / ``duration_sec`` / ``frames`` /
        ``sample_rate`` / STFT 設定 / ``center``。

    Raises:
        TypeError: 浮動小数点でない音声 (int PCM の取り違え)。
        ValueError: 未知の frontend・空・形状違い・非有限値 (入力または spec)・
            sample rate が正でない・有声区間なし (VAD frontend) またはデジタル
            無音 = 全 sample が 0 (VAD なしの frontend。builder が受け付ける
            小音量・短い録音は拒否しない)・STFT 1 frame に満たない長さ・
            T_ref が上限 (30 s 相当) を超える。
    """
    import soxr  # noqa: PLC0415 — lazy import (optional runtime dependency)

    from .vits.mel_processing import spectrogram_torch  # noqa: PLC0415

    steps = frontend_steps(frontend)
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

    if steps["vad"]:
        # VAD trim (有声区間なしは拒否)。極端な振幅で RMS の二乗が overflow
        # しても判定結果 (inf >= 閾値) は変わらないので警告だけ抑える
        with np.errstate(over="ignore", invalid="ignore"):
            trimmed, vad = trim_reference_audio(audio, int(sample_rate))
        offset_sec, duration_sec = vad["offset_sec"], vad["duration_sec"]
    else:
        # VAD なしの builder は長さ・音量を問わず受け付けるので、拒否するのは
        # 話者情報が全くないデジタル無音だけ (STFT 1 frame 未満は下で拒否)
        if not np.any(audio):
            raise ValueError(
                "reference audio is digitally silent (all samples are exactly 0)"
            )
        trimmed, offset_sec, duration_sec = audio, 0.0, len(audio) / sample_rate
    audio_rs = (
        soxr.resample(
            trimmed,
            sample_rate,
            target_sample_rate,
            quality=steps["resample_quality"],
        )
        if sample_rate != target_sample_rate
        else trimmed
    )
    pad = int((filter_length - hop_length) / 2)
    if len(audio_rs) <= pad or len(audio_rs) + 2 * pad < filter_length:
        raise ValueError(
            f"reference audio too short for one STFT frame: {len(audio_rs)} "
            f"samples at {target_sample_rate} Hz (need > {pad})"
        )
    frames = (len(audio_rs) + 2 * pad - filter_length) // hop_length + 1
    limit = max_reference_frames(int(target_sample_rate), int(hop_length))
    if frames > limit:
        raise ValueError(
            f"reference spec T_ref={frames} frames exceeds the limit {limit} "
            f"(30 s at {target_sample_rate} Hz / hop {hop_length}); use a "
            "shorter reference utterance"
        )
    spec = spectrogram_torch(
        y=torch.from_numpy(np.ascontiguousarray(audio_rs)).unsqueeze(0),
        n_fft=filter_length,
        sampling_rate=target_sample_rate,
        hop_size=hop_length,
        win_size=win_length,
        center=False,
    ).squeeze(0)
    if not bool(torch.isfinite(spec).all()):
        raise ValueError(
            "reference spec is not finite (STFT overflow: is the audio "
            "normalized to [-1, 1]?)"
        )
    info = {
        "frontend": frontend,
        "vad": bool(steps["vad"]),
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
    frontend: str,
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
        frontend=frontend,
    )


def reference_spec_sha256(spec: torch.Tensor) -> str:
    """参照 spec の来歴 hash (float32 little-endian・C 順の bytes の sha256)。

    Raises:
        TypeError: float32 でない (fp16 cache 等の丸めた spec を float32 の
            来歴として記録させない)。
    """
    if spec.dtype != torch.float32:
        raise TypeError(f"reference spec hash requires float32, got {spec.dtype}")
    return spec_array_sha256(spec.detach().cpu().numpy())


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
