"""F0 extraction utilities for training data preparation."""

import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio


_LOGGER = logging.getLogger("piper_train.f0_extraction")

# Try to import pyworld, but make it optional
try:
    import pyworld as pw

    HAS_PYWORLD = True
except ImportError:
    HAS_PYWORLD = False
    _LOGGER.warning("pyworld not installed. F0 extraction will be disabled.")


def extract_f0_pyworld(
    audio: np.ndarray,
    sample_rate: int,
    hop_length: int = 256,
    f0_min: float = 80.0,
    f0_max: float = 880.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract F0 using WORLD vocoder.

    Args:
        audio: Audio signal as numpy array
        sample_rate: Sample rate of the audio
        hop_length: Hop length for F0 extraction
        f0_min: Minimum F0 value
        f0_max: Maximum F0 value

    Returns:
        f0: F0 values (0 for unvoiced frames)
        voiced: Binary voicing decisions
    """
    if not HAS_PYWORLD:
        raise RuntimeError("pyworld is required for F0 extraction")

    # Ensure audio is double precision
    audio = audio.astype(np.float64)

    # Extract F0 using DIO algorithm
    f0, timeaxis = pw.dio(
        audio,
        sample_rate,
        f0_floor=f0_min,
        f0_ceil=f0_max,
        frame_period=hop_length * 1000.0 / sample_rate,  # Convert to ms
    )

    # Refine F0 using StoneMask
    f0 = pw.stonemask(audio, f0, timeaxis, sample_rate)

    # Get voicing decisions
    voiced = (f0 > 0).astype(np.float32)

    # Replace unvoiced F0 with f0_min (better for neural networks than 0)
    f0[f0 == 0] = f0_min

    return f0.astype(np.float32), voiced


def extract_f0_torch(
    audio_path: Path,
    sample_rate: int,
    hop_length: int = 256,
    f0_min: float = 80.0,
    f0_max: float = 880.0,
    method: str = "pyworld",
) -> tuple[torch.Tensor, torch.Tensor] | None:
    """Extract F0 from audio file.

    Args:
        audio_path: Path to audio file
        sample_rate: Expected sample rate
        hop_length: Hop length for F0 extraction
        f0_min: Minimum F0 value
        f0_max: Maximum F0 value
        method: F0 extraction method (currently only "pyworld")

    Returns:
        f0_tensor: F0 values as tensor
        voiced_tensor: Voicing decisions as tensor
        Or None if extraction fails
    """
    try:
        # Load audio
        audio, sr = torchaudio.load(audio_path)

        # Resample if necessary
        if sr != sample_rate:
            resampler = torchaudio.transforms.Resample(sr, sample_rate)
            audio = resampler(audio)

        # Convert to mono if necessary
        if audio.shape[0] > 1:
            audio = audio.mean(dim=0, keepdim=True)

        # Convert to numpy
        audio_np = audio.squeeze().numpy()

        # Extract F0
        if method == "pyworld":
            f0, voiced = extract_f0_pyworld(
                audio_np, sample_rate, hop_length, f0_min, f0_max
            )
        else:
            raise ValueError(f"Unknown F0 extraction method: {method}")

        # Convert to tensors
        f0_tensor = torch.from_numpy(f0)
        voiced_tensor = torch.from_numpy(voiced)

        return f0_tensor, voiced_tensor

    except Exception as e:
        _LOGGER.error(f"Failed to extract F0 from {audio_path}: {e}")
        return None


def interpolate_f0(f0: np.ndarray, voiced: np.ndarray) -> np.ndarray:
    """Interpolate F0 in unvoiced regions.

    Args:
        f0: F0 values
        voiced: Binary voicing decisions

    Returns:
        Interpolated F0 values
    """
    # Find voiced segments
    voiced_indices = np.where(voiced > 0)[0]

    if len(voiced_indices) == 0:
        # No voiced frames, return as is
        return f0

    if len(voiced_indices) == len(f0):
        # All voiced, no interpolation needed
        return f0

    # Interpolate unvoiced regions
    f0_interp = f0.copy()
    unvoiced_indices = np.where(voiced == 0)[0]

    # Use linear interpolation
    f0_interp[unvoiced_indices] = np.interp(
        unvoiced_indices, voiced_indices, f0[voiced_indices]
    )

    return f0_interp


def f0_to_discrete_bins(
    f0: torch.Tensor,
    n_bins: int = 256,
    f0_min: float = 80.0,
    f0_max: float = 880.0,
    use_log: bool = True,
) -> torch.Tensor:
    """Convert continuous F0 to discrete bins.

    Args:
        f0: Continuous F0 values
        n_bins: Number of discrete bins
        f0_min: Minimum F0 value
        f0_max: Maximum F0 value
        use_log: Use log scale for binning

    Returns:
        Discrete F0 bin indices
    """
    if use_log:
        # Convert to log scale
        f0_log = torch.log(f0.clamp(min=f0_min))
        f0_min_log = np.log(f0_min)
        f0_max_log = np.log(f0_max)

        # Normalize to [0, 1]
        f0_norm = (f0_log - f0_min_log) / (f0_max_log - f0_min_log)
    else:
        # Linear scale
        f0_norm = (f0 - f0_min) / (f0_max - f0_min)

    # Convert to bins
    f0_bins = (f0_norm * (n_bins - 1)).round().long()
    f0_bins = f0_bins.clamp(0, n_bins - 1)

    return f0_bins


def cache_f0(
    audio_path: Path,
    cache_dir: Path,
    sample_rate: int,
    hop_length: int = 256,
    f0_min: float = 80.0,
    f0_max: float = 880.0,
    method: str = "pyworld",
) -> Path | None:
    """Extract and cache F0 for an audio file.

    Args:
        audio_path: Path to audio file
        cache_dir: Directory to store cached F0
        sample_rate: Sample rate
        hop_length: Hop length for F0 extraction
        f0_min: Minimum F0 value
        f0_max: Maximum F0 value
        method: F0 extraction method

    Returns:
        Path to cached F0 file, or None if extraction fails
    """
    # Create cache filename
    cache_name = audio_path.stem + "_f0.pt"
    cache_path = cache_dir / cache_name

    # Check if already cached
    if cache_path.exists():
        return cache_path

    # Extract F0
    result = extract_f0_torch(
        audio_path, sample_rate, hop_length, f0_min, f0_max, method
    )

    if result is None:
        return None

    f0, voiced = result

    # Save to cache
    torch.save(
        {
            "f0": f0,
            "voiced": voiced,
            "sample_rate": sample_rate,
            "hop_length": hop_length,
            "f0_min": f0_min,
            "f0_max": f0_max,
            "method": method,
        },
        cache_path,
    )

    return cache_path
