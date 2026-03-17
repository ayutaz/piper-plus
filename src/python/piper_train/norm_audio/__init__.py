import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Optional, Union

import numpy as np
import soundfile as sf
import torch
import torchaudio

from piper_train.vits.mel_processing import spectrogram_torch

from .trim import trim_silence
from .vad import SileroVoiceActivityDetector


_DIR = Path(__file__).parent


def _atomic_torch_save(obj, path: Path) -> None:
    """Save a tensor to *path* atomically using a temp file + rename.

    ``torch.save`` writes directly to the target path, so a crash mid-write
    leaves a truncated (corrupt) file.  Writing to a sibling temp file first
    and then renaming (which is atomic on POSIX) avoids this.
    """
    path = Path(path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.close(tmp_fd)
        torch.save(obj, tmp_path)
        os.replace(tmp_path, path)  # atomic on POSIX
    except Exception:
        # Clean up temp file if anything went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def energy_vad_numpy(
    audio_16k: np.ndarray,
    chunk_size: int = 480,
    threshold: float = 0.02,
    keep_before: int = 2,
    keep_after: int = 2,
    sr: int = 16000,
) -> tuple[float, float | None]:
    """Fast energy-based VAD using vectorized numpy RMS.

    ~1793x faster than Silero ONNX with 100% agreement on LibriTTS-R.
    LibriTTS-R has essentially no leading/trailing silence, so this is safe.

    Returns:
        (offset_sec, duration_sec) tuple.
        duration_sec is None if no voiced content detected.
    """
    n = len(audio_16k) // chunk_size
    if n == 0:
        return 0.0, None
    chunks = audio_16k[: n * chunk_size].reshape(n, chunk_size)
    rms = np.sqrt(np.mean(chunks**2, axis=1))
    idx = np.where(rms >= threshold)[0]
    if len(idx) == 0:
        return 0.0, None
    first = max(0, idx[0] - keep_before)
    last = min(n - 1, idx[-1] + keep_after)
    s = chunk_size / sr
    return first * s, (last + 1) * s - first * s


def cache_norm_audio_fast(
    audio_path: str | Path,
    cache_dir: str | Path,
    sample_rate: int,
    energy_vad_threshold: float = 0.02,
    filter_length: int = 1024,
    window_length: int = 1024,
    hop_length: int = 256,
    ignore_cache: bool = False,
) -> tuple[Path, Path]:
    """Fast audio caching using energy VAD + soxr (no Silero ONNX).

    ~61x faster single-thread, ~7.7x faster in parallel vs Silero-based pipeline.
    Recommended for LibriTTS-R (pre-cleaned, virtually no silence).
    """
    import soxr  # noqa: PLC0415 — lazy import: not needed for Silero path

    audio_path = Path(audio_path).absolute()
    cache_dir = Path(cache_dir)

    audio_cache_id = sha256(str(audio_path).encode()).hexdigest()
    audio_norm_path = cache_dir / f"{audio_cache_id}.pt"
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    audio_norm_tensor: torch.Tensor | None = None

    if ignore_cache or (not audio_norm_path.exists()):
        audio_data, src_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)  # stereo → mono

        # Energy VAD on 16kHz audio
        audio_16k = (
            soxr.resample(audio_data, src_sr, 16000, quality="HQ")
            if src_sr != 16000
            else audio_data
        )
        offset_sec, duration_sec = energy_vad_numpy(
            audio_16k, threshold=energy_vad_threshold
        )

        # Trim at source sample rate
        offset_samples = int(offset_sec * src_sr)
        if duration_sec is not None:
            end_samples = min(
                offset_samples + int(duration_sec * src_sr), len(audio_data)
            )
        else:
            end_samples = len(audio_data)
        trimmed = audio_data[offset_samples:end_samples]

        # Resample to target sample rate
        audio_rs = (
            soxr.resample(trimmed, src_sr, sample_rate, quality="HQ")
            if src_sr != sample_rate
            else trimmed
        )
        audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
        _atomic_torch_save(audio_norm_tensor, audio_norm_path)

    if ignore_cache or (not audio_spec_path.exists()):
        if audio_norm_tensor is None:
            audio_norm_tensor = torch.load(audio_norm_path, weights_only=True)

        audio_spec_tensor = spectrogram_torch(
            y=audio_norm_tensor,
            n_fft=filter_length,
            sampling_rate=sample_rate,
            hop_size=hop_length,
            win_size=window_length,
            center=False,
        ).squeeze(0)
        _atomic_torch_save(audio_spec_tensor.half(), audio_spec_path)

    return audio_norm_path, audio_spec_path


def resample_only_no_vad(
    audio_path: str | Path,
    cache_dir: str | Path,
    sample_rate: int,
    resample_quality: str = "MQ",
    ignore_cache: bool = False,
) -> tuple[Path, str]:
    """Resample audio without VAD and save .pt only (no spectrogram).

    For use with GPU batch spectrogram pipeline. Skips 16kHz resampling
    and energy VAD — suitable for pre-cleaned corpora (AISHELL-3, CML-TTS).

    Returns:
        (norm_path, cache_id) for subsequent spectrogram computation.
    """
    import soxr  # noqa: PLC0415

    audio_path = Path(audio_path).absolute()
    cache_dir = Path(cache_dir)

    audio_cache_id = sha256(str(audio_path).encode()).hexdigest()
    audio_norm_path = cache_dir / f"{audio_cache_id}.pt"

    if ignore_cache or not audio_norm_path.exists():
        audio_data, src_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        if src_sr != sample_rate:
            audio_rs = soxr.resample(
                audio_data, src_sr, sample_rate, quality=resample_quality
            )
        else:
            audio_rs = audio_data

        audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
        _atomic_torch_save(audio_norm_tensor, audio_norm_path)

    return audio_norm_path, audio_cache_id


def cache_norm_audio_no_vad(
    audio_path: str | Path,
    cache_dir: str | Path,
    sample_rate: int,
    resample_quality: str = "MQ",
    filter_length: int = 1024,
    window_length: int = 1024,
    hop_length: int = 256,
    ignore_cache: bool = False,
) -> tuple[Path, Path]:
    """Cache audio without VAD — for pre-cleaned corpora.

    Skips 16kHz resampling and energy VAD, saving ~30% processing time.
    Uses soxr MQ (vs HQ) for additional ~30-40% resample speedup.
    """
    import soxr  # noqa: PLC0415

    audio_path = Path(audio_path).absolute()
    cache_dir = Path(cache_dir)

    audio_cache_id = sha256(str(audio_path).encode()).hexdigest()
    audio_norm_path = cache_dir / f"{audio_cache_id}.pt"
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    audio_norm_tensor: torch.Tensor | None = None

    if ignore_cache or not audio_norm_path.exists():
        audio_data, src_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        if src_sr != sample_rate:
            audio_rs = soxr.resample(
                audio_data, src_sr, sample_rate, quality=resample_quality
            )
        else:
            audio_rs = audio_data

        audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
        _atomic_torch_save(audio_norm_tensor, audio_norm_path)

    if ignore_cache or not audio_spec_path.exists():
        if audio_norm_tensor is None:
            audio_norm_tensor = torch.load(audio_norm_path, weights_only=True)

        audio_spec_tensor = spectrogram_torch(
            y=audio_norm_tensor,
            n_fft=filter_length,
            sampling_rate=sample_rate,
            hop_size=hop_length,
            win_size=window_length,
            center=False,
        ).squeeze(0)
        _atomic_torch_save(audio_spec_tensor.half(), audio_spec_path)

    return audio_norm_path, audio_spec_path


def make_silence_detector() -> SileroVoiceActivityDetector:
    silence_model = _DIR / "models" / "silero_vad.onnx"
    return SileroVoiceActivityDetector(silence_model)


def cache_norm_audio(
    audio_path: str | Path,
    cache_dir: str | Path,
    detector: SileroVoiceActivityDetector,
    sample_rate: int,
    silence_threshold: float = 0.2,
    silence_samples_per_chunk: int = 480,
    silence_keep_chunks_before: int = 2,
    silence_keep_chunks_after: int = 2,
    filter_length: int = 1024,
    window_length: int = 1024,
    hop_length: int = 256,
    ignore_cache: bool = False,
) -> tuple[Path, Path]:
    audio_path = Path(audio_path).absolute()
    cache_dir = Path(cache_dir)

    # Cache id is the SHA256 of the full audio path
    audio_cache_id = sha256(str(audio_path).encode()).hexdigest()

    audio_norm_path = cache_dir / f"{audio_cache_id}.pt"
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    # Normalize audio
    audio_norm_tensor: torch.FloatTensor | None = None
    if ignore_cache or (not audio_norm_path.exists()):
        # Load audio once at native sample rate using soundfile (fast, no TorchCodec needed)
        audio_data, src_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        if audio_data.ndim == 1:
            waveform = torch.from_numpy(audio_data).unsqueeze(0)  # (1, samples)
        else:
            # (samples, channels) -> (channels, samples) -> mono
            waveform = torch.from_numpy(audio_data.T.copy()).mean(dim=0, keepdim=True)

        # Resample to 16kHz for VAD
        vad_sample_rate = 16000
        if src_sr != vad_sample_rate:
            resampler_16k = torchaudio.transforms.Resample(src_sr, vad_sample_rate)
            audio_16khz_tensor = resampler_16k(waveform)
        else:
            audio_16khz_tensor = waveform

        audio_16khz = audio_16khz_tensor.squeeze(0).numpy()

        offset_sec, duration_sec = trim_silence(
            audio_16khz,
            detector,
            threshold=silence_threshold,
            samples_per_chunk=silence_samples_per_chunk,
            sample_rate=vad_sample_rate,
            keep_chunks_before=silence_keep_chunks_before,
            keep_chunks_after=silence_keep_chunks_after,
        )

        # Slice at source sample rate, then resample to target
        offset_samples = int(offset_sec * src_sr)
        if duration_sec is not None:
            end_samples = min(
                offset_samples + int(duration_sec * src_sr), waveform.shape[-1]
            )
        else:
            end_samples = waveform.shape[-1]
        audio_trimmed = waveform[:, offset_samples:end_samples]

        if src_sr != sample_rate:
            resampler = torchaudio.transforms.Resample(src_sr, sample_rate)
            audio_norm_tensor = resampler(audio_trimmed)
        else:
            audio_norm_tensor = audio_trimmed.clone()

        # Save to cache directory (atomic write: temp file → rename)
        _atomic_torch_save(audio_norm_tensor, audio_norm_path)

    # Compute spectrogram
    if ignore_cache or (not audio_spec_path.exists()):
        if audio_norm_tensor is None:
            # Load pre-cached normalized audio
            audio_norm_tensor = torch.load(audio_norm_path, weights_only=True)

        audio_spec_tensor = spectrogram_torch(
            y=audio_norm_tensor,
            n_fft=filter_length,
            sampling_rate=sample_rate,
            hop_size=hop_length,
            win_size=window_length,
            center=False,
        ).squeeze(0)
        _atomic_torch_save(audio_spec_tensor.half(), audio_spec_path)

    return audio_norm_path, audio_spec_path
