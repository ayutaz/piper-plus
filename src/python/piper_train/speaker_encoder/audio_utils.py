"""Audio preprocessing utilities for the Speaker Encoder.

Provides NumPy-based mel spectrogram computation and audio loading so that
the speaker encoder pipeline has no hard dependency on torchaudio or librosa
at inference time.  ``scipy.signal`` is used only for the mel filterbank;
the rest is pure NumPy.

Default parameters match the VoxCeleb / ECAPA-TDNN convention:
    - Sample rate: 16 kHz
    - FFT size: 512  (32 ms window)
    - Hop length: 160 (10 ms stride)
    - Mel bins: 80
    - Frequency range: 20--7600 Hz
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger(__name__)

# Default audio parameters
DEFAULT_SR = 16000
DEFAULT_N_FFT = 512
DEFAULT_HOP_LENGTH = 160
DEFAULT_N_MELS = 80
DEFAULT_FMIN = 20.0
DEFAULT_FMAX = 7600.0


def load_audio(path: str | Path, sr: int = DEFAULT_SR) -> np.ndarray:
    """Load an audio file as a mono 16 kHz float32 waveform.

    Uses ``soundfile`` for reading, which supports WAV/FLAC/OGG without
    heavy native dependencies.  If the file has multiple channels they
    are averaged to mono.  Resampling is applied when the native sample
    rate differs from *sr*.

    Args:
        path: Path to audio file (WAV, FLAC, OGG, etc.).
        sr: Target sample rate (default: 16000).

    Returns:
        1-D float32 NumPy array.

    Raises:
        FileNotFoundError: If *path* does not exist.
        RuntimeError: If soundfile cannot read the file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    try:
        import soundfile as sf  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "soundfile is required for audio loading. "
            "Install with: pip install soundfile"
        ) from exc

    audio, native_sr = sf.read(str(path), dtype="float32")

    # Stereo -> mono
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Resample if necessary
    if native_sr != sr:
        audio = _resample(audio, native_sr, sr)

    return audio.astype(np.float32)


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio using linear interpolation.

    For the speaker encoder use-case (16 kHz target), this simple approach
    is sufficient.  If higher quality resampling is needed, ``scipy.signal.resample``
    can be used as a drop-in replacement.

    Args:
        audio: 1-D float32 array.
        orig_sr: Original sample rate.
        target_sr: Target sample rate.

    Returns:
        Resampled 1-D float32 array.
    """
    if orig_sr == target_sr:
        return audio

    ratio = target_sr / orig_sr
    new_length = int(len(audio) * ratio)

    # Use scipy for high-quality resampling when available
    try:
        from scipy.signal import resample as scipy_resample  # noqa: PLC0415

        return scipy_resample(audio, new_length).astype(np.float32)
    except ImportError:
        pass

    # Fallback: linear interpolation
    indices = np.linspace(0, len(audio) - 1, new_length)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Peak-normalize audio to [-1, 1].

    If the signal is silent (all zeros), returns the array unchanged.

    Args:
        audio: 1-D float32 waveform.

    Returns:
        Peak-normalized 1-D float32 array.
    """
    peak = np.abs(audio).max()
    if peak < 1e-10:
        return audio
    return (audio / peak).astype(np.float32)


def _hz_to_mel(freq: float) -> float:
    """Convert frequency in Hz to mel scale (HTK formula)."""
    return 2595.0 * np.log10(1.0 + freq / 700.0)


def _mel_to_hz(mel: float) -> float:
    """Convert mel scale to frequency in Hz (HTK formula)."""
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _create_mel_filterbank(
    sr: int,
    n_fft: int,
    n_mels: int,
    fmin: float,
    fmax: float,
) -> np.ndarray:
    """Create a mel-scale triangular filterbank matrix.

    Args:
        sr: Sample rate.
        n_fft: FFT size.
        n_mels: Number of mel bands.
        fmin: Minimum frequency (Hz).
        fmax: Maximum frequency (Hz).

    Returns:
        (n_mels, n_fft // 2 + 1) float32 filterbank matrix.
    """
    n_freqs = n_fft // 2 + 1

    # Mel-spaced center frequencies
    mel_min = _hz_to_mel(fmin)
    mel_max = _hz_to_mel(fmax)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = np.array([_mel_to_hz(m) for m in mel_points])

    # Convert Hz to FFT bin indices
    bins = np.floor((n_fft + 1) * hz_points / sr).astype(int)

    filterbank = np.zeros((n_mels, n_freqs), dtype=np.float32)
    for i in range(n_mels):
        left = bins[i]
        center = bins[i + 1]
        right = bins[i + 2]

        # Ensure the filter covers at least one bin: if left == center == right,
        # widen to guarantee a non-zero response.
        if left == center and center == right:
            center = min(center + 1, n_freqs - 1)
            right = min(right + 2, n_freqs - 1)
        elif left == center:
            center = min(center + 1, n_freqs - 1)
        if center == right:
            right = min(right + 1, n_freqs - 1)

        # Rising slope
        for j in range(left, center):
            if center > left:
                filterbank[i, j] = (j - left) / (center - left)

        # Falling slope
        for j in range(center, right):
            if right > center:
                filterbank[i, j] = (right - j) / (right - center)

        # Ensure center bin always has weight 1.0
        if 0 <= center < n_freqs:
            filterbank[i, center] = max(filterbank[i, center], 1.0)

    return filterbank


def compute_mel_spectrogram(
    audio: np.ndarray,
    sr: int = DEFAULT_SR,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
    n_mels: int = DEFAULT_N_MELS,
    fmin: float = DEFAULT_FMIN,
    fmax: float = DEFAULT_FMAX,
) -> np.ndarray:
    """Compute a log-mel spectrogram from a waveform using NumPy.

    Applies a Hann window, STFT via ``np.fft.rfft``, mel filterbank, and
    log compression.  No external audio library is required.

    Args:
        audio: 1-D float32 waveform (mono, at sample rate *sr*).
        sr: Sample rate (default: 16000).
        n_fft: FFT window size (default: 512).
        hop_length: Hop size in samples (default: 160).
        n_mels: Number of mel frequency bins (default: 80).
        fmin: Lowest frequency for mel filterbank (default: 20.0 Hz).
        fmax: Highest frequency for mel filterbank (default: 7600.0 Hz).

    Returns:
        (n_mels, time) float32 log-mel spectrogram.
    """
    # Ensure float32
    audio = np.asarray(audio, dtype=np.float32)

    # Pad to ensure we get at least one frame
    if len(audio) < n_fft:
        audio = np.pad(audio, (0, n_fft - len(audio)))

    # Hann window
    window = np.hanning(n_fft).astype(np.float32)

    # Frame the signal
    n_frames = 1 + (len(audio) - n_fft) // hop_length
    frames = np.lib.stride_tricks.as_strided(
        audio,
        shape=(n_frames, n_fft),
        strides=(audio.strides[0] * hop_length, audio.strides[0]),
    )

    # Apply window and compute RFFT
    windowed = frames * window
    spectrum = np.fft.rfft(windowed, n=n_fft, axis=1)
    # Clamp to avoid overflow in power computation
    magnitude = np.minimum(np.abs(spectrum), 1e10)
    power_spectrum = magnitude**2  # (n_frames, n_fft // 2 + 1)

    # Mel filterbank
    mel_fb = _create_mel_filterbank(sr, n_fft, n_mels, fmin, fmax)

    # Suppress floating-point warnings from matmul (e.g. inf * 0 in
    # edge-case frames).  The subsequent clamp to 1e-10 handles any
    # resulting NaN or zero values.
    with np.errstate(all="ignore"):
        mel_spec = power_spectrum @ mel_fb.T  # (n_frames, n_mels)

    # Replace any NaN/Inf that may have leaked through
    mel_spec = np.nan_to_num(mel_spec, nan=0.0, posinf=1e20, neginf=0.0)

    # Log compression with floor to avoid log(0)
    mel_spec = np.log(np.maximum(mel_spec, 1e-10))

    # Transpose to (n_mels, time) to match PyTorch convention
    return mel_spec.T.astype(np.float32)
