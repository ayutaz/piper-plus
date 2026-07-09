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


# ---------------------------------------------------------------------------
# Parallel preprocessing defaults
# ---------------------------------------------------------------------------

# Cap default worker count so tools do not over-subscribe A100 hosts
# (typically 64 vCPU). Using cpu_count() outright causes memory pressure
# (each worker holds soxr / torch state) and NFS thrashing. Half-of-cpu
# with an absolute ceiling of 32 tracks the empirical sweet spot observed
# during v7 dataset preprocessing on 30-worker runs.
_DEFAULT_NUM_PROCESSES_CEILING = 32


def default_num_processes() -> int:
    """Return the recommended default worker count for VAD/preprocess Pools.

    Rationale: ``os.cpu_count()`` on modern A100 hosts is 64+, but per-worker
    memory (soxr resampler + torch tensors) and NFS IOPS make full-fan-out
    counterproductive past ~30 workers on shared filesystems. This helper
    returns ``min(cpu_count // 2, 32)`` with a floor of 1, matching the
    manually tuned ``--workers 30`` used in prepare_multilingual_dataset.py.

    Tools should call this for their ``--num-processes`` / ``--workers``
    default so a single knob governs safe fan-out across cache_audio.py,
    prepare_multilingual_dataset.py, and prepare_bilingual_dataset.py.
    """
    cpu = os.cpu_count() or 1
    return max(1, min(cpu // 2, _DEFAULT_NUM_PROCESSES_CEILING))


def _load_audio_norm_tensor(path: Path) -> torch.Tensor:
    """Load a cached audio_norm tensor from either ``.npy`` or ``.pt``.

    Mirrors ``PiperDataset._load_tensor`` so that the local spec-computation
    fallback in ``cache_norm_audio*`` can read both the new (``.npy``, raw
    numpy) and legacy (``.pt``, torch pickle) formats without duplicating the
    branch inline at each call site.
    """
    path = Path(path)
    if path.suffix == ".npy":
        arr = np.load(str(path))
        return torch.from_numpy(arr)
    return torch.load(path, weights_only=True)


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


def _atomic_npy_save(arr, path: Path) -> None:
    """Save a numpy array (or torch tensor) atomically as ``.npy``.

    Motivation: ``torch.save`` uses pickle framing, which is 3-5x slower to
    ``torch.load`` than ``np.load`` on the ``audio_norm`` cache path (measured
    on v7 preprocess).  Switching audio_norm caches to raw ``.npy`` also saves
    ~10% on-disk (no pickle metadata / class references).  Kept alongside
    ``_atomic_torch_save`` because ``.spec.pt`` (fp16 half tensors) stays on
    the torch path — ``np.save`` does not natively handle the half-complex
    layout used by the STFT cache.

    Uses tempfile + ``os.replace`` for crash safety (atomic on POSIX,
    near-atomic on NTFS).  When ``arr`` is a torch tensor it is detached,
    moved to CPU and converted via ``.numpy()``.
    """
    if isinstance(arr, torch.Tensor):
        arr = arr.detach().cpu().numpy()
    path = Path(path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.close(tmp_fd)
        # np.save on a file handle does NOT auto-append ``.npy`` (unlike the
        # path-string overload) — exactly what we want when writing to a
        # tempfile that will be renamed into a caller-chosen final path.
        with open(tmp_path, "wb") as f:
            np.save(f, arr, allow_pickle=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Headerless PCM support (KsponSpeech / AI-Hub raw distribution)
# ---------------------------------------------------------------------------

# KsponSpeech ships as raw headerless int16 mono @ 16 kHz. soundfile cannot
# read it directly (no RIFF/FLAC header), so users used to run a 3-4 hour
# PCM→WAV pre-conversion pass before the parallel VAD stage. Reading the PCM
# directly saves that whole pass (v8 KO enablement, 2026-07-09).
#
# Spec pin: 16 kHz, mono, signed 16-bit little-endian ("s16le"). This is the
# canonical KsponSpeech shape and is documented in the ETRI distribution
# guide; other sample rates are out of scope for the .pcm dispatch — pass a
# WAV/FLAC path for anything else.
_PCM16_MONO_SAMPLE_RATE = 16000


def _read_pcm16_mono(
    path: Path, sample_rate: int = _PCM16_MONO_SAMPLE_RATE
) -> np.ndarray:
    """Read a headerless int16 mono PCM file and return float32 in [-1, 1].

    Motivation: KsponSpeech (AI-Hub, ETRI) distributes ~969h of Korean speech
    as raw 16 kHz mono s16le PCM with no RIFF header. soundfile refuses to
    read it, so historically we ran an offline PCM→WAV pass (~3-4h wall clock
    per full dataset) before the VAD/spectrogram pipeline could touch it.
    Reading the PCM inline skips that entire pass.

    Normalisation matches soundfile's default float32 read: divide by 32768
    so the full negative range hits exactly -1.0 (per the s16 spec, positive
    values only reach 32767/32768 ≈ 0.99997 which is the standard PCM
    convention). ``sample_rate`` is currently descriptive only — the caller
    is trusted to know the file is 16 kHz mono (KsponSpeech invariant). It is
    accepted so callers can plumb through their config value for logging /
    downstream resample without adding a second constant.
    """
    raw = np.fromfile(str(path), dtype=np.int16)
    return raw.astype(np.float32) / 32768.0


def _read_audio_any(
    path: Path,
    pcm_sample_rate: int = _PCM16_MONO_SAMPLE_RATE,
) -> tuple[np.ndarray, int]:
    """Read audio, dispatching to a PCM reader for headerless ``.pcm`` files.

    Returns ``(audio_data, src_sr)`` matching the shape produced by
    ``sf.read(..., dtype='float32', always_2d=False)`` so callers do not need
    to branch. ``.pcm`` files are assumed to be 16 kHz mono int16 (KsponSpeech
    spec); anything else routes through soundfile as before.
    """
    path = Path(path)
    if path.suffix.lower() == ".pcm":
        return _read_pcm16_mono(path, pcm_sample_rate), pcm_sample_rate
    return sf.read(str(path), dtype="float32", always_2d=False)


def _resolve_audio_norm_path(cache_dir: Path, cache_id: str) -> tuple[Path, Path]:
    """Return ``(read_path, write_path)`` for an audio_norm cache entry.

    Backward-compat policy (2026-07-09, perf switch to ``.npy``):

    * ``write_path`` is always ``{cache_id}.npy`` — new writes drop the
      pickle-framed ``.pt`` format for the raw numpy format.
    * ``read_path`` is the first of ``.npy`` / ``.pt`` that exists on disk,
      falling back to ``write_path`` if neither is present.  This lets
      pre-existing ``.pt`` caches keep serving without re-processing on the
      very next run, while any fresh write lands as ``.npy``.

    ``PiperDataset._load_tensor`` already handles both suffixes, so the path
    returned to callers (and stored in ``dataset.jsonl``) is safe either way.
    """
    npy_path = cache_dir / f"{cache_id}.npy"
    pt_path = cache_dir / f"{cache_id}.pt"
    if npy_path.exists():
        return npy_path, npy_path
    if pt_path.exists():
        return pt_path, npy_path
    return npy_path, npy_path


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
    # audio_norm: prefer existing .pt cache for backward compat; new writes → .npy
    audio_norm_path, audio_norm_write_path = _resolve_audio_norm_path(
        cache_dir, audio_cache_id
    )
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    audio_norm_tensor: torch.Tensor | None = None

    if ignore_cache or (not audio_norm_path.exists()):
        audio_data, src_sr = _read_audio_any(audio_path)
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
        # New writes always go to .npy (~3-5x faster load, ~10% smaller on disk)
        _atomic_npy_save(audio_norm_tensor, audio_norm_write_path)
        audio_norm_path = audio_norm_write_path

    if ignore_cache or (not audio_spec_path.exists()):
        if audio_norm_tensor is None:
            audio_norm_tensor = _load_audio_norm_tensor(audio_norm_path)

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
    audio_norm_path, audio_norm_write_path = _resolve_audio_norm_path(
        cache_dir, audio_cache_id
    )

    if ignore_cache or not audio_norm_path.exists():
        audio_data, src_sr = _read_audio_any(audio_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        if src_sr != sample_rate:
            audio_rs = soxr.resample(
                audio_data, src_sr, sample_rate, quality=resample_quality
            )
        else:
            audio_rs = audio_data

        audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
        _atomic_npy_save(audio_norm_tensor, audio_norm_write_path)
        audio_norm_path = audio_norm_write_path

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
    audio_norm_path, audio_norm_write_path = _resolve_audio_norm_path(
        cache_dir, audio_cache_id
    )
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    audio_norm_tensor: torch.Tensor | None = None

    if ignore_cache or not audio_norm_path.exists():
        audio_data, src_sr = _read_audio_any(audio_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        if src_sr != sample_rate:
            audio_rs = soxr.resample(
                audio_data, src_sr, sample_rate, quality=resample_quality
            )
        else:
            audio_rs = audio_data

        audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
        _atomic_npy_save(audio_norm_tensor, audio_norm_write_path)
        audio_norm_path = audio_norm_write_path

    if ignore_cache or not audio_spec_path.exists():
        if audio_norm_tensor is None:
            audio_norm_tensor = _load_audio_norm_tensor(audio_norm_path)

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

    audio_norm_path, audio_norm_write_path = _resolve_audio_norm_path(
        cache_dir, audio_cache_id
    )
    audio_spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

    # Normalize audio
    audio_norm_tensor: torch.FloatTensor | None = None
    if ignore_cache or (not audio_norm_path.exists()):
        # Load audio once at native sample rate using soundfile (fast, no TorchCodec needed)
        audio_data, src_sr = _read_audio_any(audio_path)
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
        _atomic_npy_save(audio_norm_tensor, audio_norm_write_path)
        audio_norm_path = audio_norm_write_path

    # Compute spectrogram
    if ignore_cache or (not audio_spec_path.exists()):
        if audio_norm_tensor is None:
            # Load pre-cached normalized audio (.npy or legacy .pt)
            audio_norm_tensor = _load_audio_norm_tensor(audio_norm_path)

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
