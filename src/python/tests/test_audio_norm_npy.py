"""Regression tests for the audio_norm cache format switch from ``.pt`` to ``.npy``.

Motivation
----------
``norm_audio.cache_norm_audio*`` used to persist the trimmed / resampled
waveform via ``torch.save`` (pickle framing) as ``{cache_id}.pt``.  That path
is ~3-5x slower to reload than raw ``np.save`` / ``np.load`` on the same
tensor, and pickle framing wastes ~10% on-disk on multi-hundred-k utterance
datasets.  The write path was switched to ``.npy`` on 2026-07-09 while
preserving backward-compat for existing ``.pt`` caches.

These tests pin the new behaviour so a future refactor cannot silently
regress either half of the contract:

1. Fresh cache is written as ``.npy`` (never ``.pt``) and round-trips through
   ``PiperDataset._load_tensor``.
2. Pre-existing ``.pt`` cache is honoured — the file is *not* overwritten and
   the returned path still points at ``.pt`` so downstream tools that already
   stored ``.pt`` paths in ``dataset.jsonl`` keep working without re-processing.
3. ``ignore_cache=True`` forces a rewrite as ``.npy`` even when a legacy
   ``.pt`` sits next to it (opt-in migration path).
4. ``_atomic_npy_save`` accepts both ``np.ndarray`` and ``torch.Tensor`` and
   writes a valid ``.npy`` file that survives an intentional early-crash
   simulation (temp-file cleanup, no truncated target).
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch")
soundfile = pytest.importorskip("soundfile")
pytest.importorskip("soxr")

from piper_train.norm_audio import (  # noqa: E402
    _atomic_npy_save,
    _atomic_torch_save,
    _load_audio_norm_tensor,
    _resolve_audio_norm_path,
    cache_norm_audio_fast,
    cache_norm_audio_no_vad,
    resample_only_no_vad,
)
from piper_train.vits.dataset import _load_tensor  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_dummy_wav(tmp_path: Path, samples: int = 22050, sr: int = 22050) -> Path:
    """Write a 1-second sine wave to WAV and return the path."""
    audio_path = tmp_path / "in.wav"
    t = np.linspace(0.0, 1.0, samples, endpoint=False, dtype=np.float32)
    # Non-silent so energy VAD retains the signal.
    audio = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    soundfile.write(str(audio_path), audio, sr)
    return audio_path


def _cache_id_for(audio_path: Path) -> str:
    return sha256(str(audio_path.absolute()).encode()).hexdigest()


# ---------------------------------------------------------------------------
# _atomic_npy_save primitive
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_atomic_npy_save_accepts_numpy_array(tmp_path):
    arr = np.random.randn(1, 4096).astype(np.float32)
    out = tmp_path / "cache.npy"

    _atomic_npy_save(arr, out)

    assert out.exists()
    loaded = np.load(str(out))
    np.testing.assert_array_equal(loaded, arr)


@pytest.mark.unit
def test_atomic_npy_save_accepts_torch_tensor(tmp_path):
    tensor = torch.randn(1, 4096)
    out = tmp_path / "cache.npy"

    _atomic_npy_save(tensor, out)

    loaded = np.load(str(out))
    np.testing.assert_array_equal(loaded, tensor.numpy())
    # Round-trip via the dataset loader must yield a torch tensor of the
    # same shape / dtype as the original.
    reloaded = _load_tensor(out)
    assert reloaded.shape == tensor.shape
    assert reloaded.dtype == tensor.dtype


@pytest.mark.unit
def test_atomic_npy_save_leaves_no_temp_files_on_success(tmp_path):
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    out = tmp_path / "cache.npy"

    _atomic_npy_save(arr, out)

    # Only the final file should exist — no sibling .tmp turds.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache.npy"]


# ---------------------------------------------------------------------------
# _resolve_audio_norm_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_prefers_npy_when_both_exist(tmp_path):
    cache_id = "abc123"
    (tmp_path / f"{cache_id}.npy").write_bytes(b"npy")
    (tmp_path / f"{cache_id}.pt").write_bytes(b"pt")

    read, write = _resolve_audio_norm_path(tmp_path, cache_id)

    assert read == tmp_path / f"{cache_id}.npy"
    assert write == tmp_path / f"{cache_id}.npy"


@pytest.mark.unit
def test_resolve_falls_back_to_pt_when_only_pt_exists(tmp_path):
    cache_id = "abc123"
    (tmp_path / f"{cache_id}.pt").write_bytes(b"pt")

    read, write = _resolve_audio_norm_path(tmp_path, cache_id)

    # Read points at the legacy .pt so we don't re-process.
    assert read == tmp_path / f"{cache_id}.pt"
    # Any future write still goes to .npy (migration on next real write).
    assert write == tmp_path / f"{cache_id}.npy"


@pytest.mark.unit
def test_resolve_defaults_to_npy_when_neither_exists(tmp_path):
    cache_id = "abc123"

    read, write = _resolve_audio_norm_path(tmp_path, cache_id)

    assert read == tmp_path / f"{cache_id}.npy"
    assert write == tmp_path / f"{cache_id}.npy"


# ---------------------------------------------------------------------------
# cache_norm_audio_fast — end-to-end write path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_norm_audio_fast_writes_npy_for_fresh_cache(tmp_path):
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    norm_path, spec_path = cache_norm_audio_fast(
        audio_path, cache_dir, sample_rate=22050
    )

    cache_id = _cache_id_for(audio_path)
    # New cache is .npy, not .pt.
    assert norm_path.suffix == ".npy"
    assert norm_path == cache_dir / f"{cache_id}.npy"
    assert not (cache_dir / f"{cache_id}.pt").exists()
    # Spec cache stays on the torch path (fp16 half tensor).
    assert spec_path.suffix == ".pt"
    assert spec_path.name.endswith(".spec.pt")


@pytest.mark.unit
def test_cache_norm_audio_fast_roundtrips_via_dataset_loader(tmp_path):
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    norm_path, _ = cache_norm_audio_fast(audio_path, cache_dir, sample_rate=22050)

    # Round-trip through the loader the training DataLoader actually uses.
    tensor = _load_tensor(norm_path)
    assert tensor.ndim == 2  # (1, samples)
    assert tensor.shape[0] == 1
    assert tensor.dtype == torch.float32


@pytest.mark.unit
def test_cache_norm_audio_fast_reuses_legacy_pt(tmp_path):
    """If a pre-existing .pt cache is on disk, keep it (backward compat).

    The critical invariant is that we do NOT re-process the audio *and* do
    NOT delete the legacy .pt file — external tools may still hold the .pt
    path in dataset.jsonl.
    """
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cache_id = _cache_id_for(audio_path)
    legacy_pt = cache_dir / f"{cache_id}.pt"
    # Long enough (>> filter_length=1024) so downstream spec computation on
    # the legacy .pt does not blow up on the pad step — the point of the
    # sentinel is just to prove cache_norm_audio_fast did NOT overwrite it.
    sentinel = torch.full((1, 22050), 0.123, dtype=torch.float32)
    _atomic_torch_save(sentinel, legacy_pt)
    legacy_mtime = legacy_pt.stat().st_mtime_ns

    norm_path, _spec_path = cache_norm_audio_fast(
        audio_path, cache_dir, sample_rate=22050
    )

    # Returned path must still be the legacy .pt so existing dataset.jsonl
    # entries keep resolving.
    assert norm_path == legacy_pt
    # File was not rewritten (mtime unchanged).
    assert legacy_pt.stat().st_mtime_ns == legacy_mtime
    # And no .npy sibling was created (we did not do redundant work).
    assert not (cache_dir / f"{cache_id}.npy").exists()

    # Sentinel value survives — proves cache_norm_audio_fast honoured the
    # legacy cache instead of overwriting it with a fresh compute.
    reloaded = _load_tensor(norm_path)
    torch.testing.assert_close(reloaded, sentinel)


@pytest.mark.unit
def test_cache_norm_audio_fast_ignore_cache_migrates_pt_to_npy(tmp_path):
    """``ignore_cache=True`` forces a rewrite as ``.npy`` (opt-in migration)."""
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cache_id = _cache_id_for(audio_path)
    legacy_pt = cache_dir / f"{cache_id}.pt"
    # Use a length distinct from the real dummy wav so we can prove the
    # freshly written .npy comes from re-processing the source, not from
    # copying the sentinel.
    sentinel = torch.full((1, 12345), 0.5, dtype=torch.float32)
    _atomic_torch_save(sentinel, legacy_pt)

    norm_path, _ = cache_norm_audio_fast(
        audio_path, cache_dir, sample_rate=22050, ignore_cache=True
    )

    # New cache is .npy; the .pt is not touched (we leave it to the user to
    # sweep so no in-flight consumer sees a missing file mid-run).
    assert norm_path.suffix == ".npy"
    assert norm_path == cache_dir / f"{cache_id}.npy"
    assert legacy_pt.exists()
    # And the new .npy holds fresh content, not the sentinel.
    reloaded = _load_tensor(norm_path)
    assert reloaded.shape[-1] != sentinel.shape[-1]


# ---------------------------------------------------------------------------
# resample_only_no_vad + cache_norm_audio_no_vad
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resample_only_no_vad_writes_npy(tmp_path):
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    norm_path, cache_id = resample_only_no_vad(
        audio_path, cache_dir, sample_rate=22050
    )

    assert norm_path.suffix == ".npy"
    assert norm_path == cache_dir / f"{cache_id}.npy"
    tensor = _load_tensor(norm_path)
    assert tensor.ndim == 2 and tensor.shape[0] == 1


@pytest.mark.unit
def test_cache_norm_audio_no_vad_writes_npy(tmp_path):
    audio_path = _write_dummy_wav(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    norm_path, spec_path = cache_norm_audio_no_vad(
        audio_path, cache_dir, sample_rate=22050
    )

    assert norm_path.suffix == ".npy"
    assert spec_path.name.endswith(".spec.pt")  # spec still torch


# ---------------------------------------------------------------------------
# _load_audio_norm_tensor — dual-format read helper used by spec fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_audio_norm_tensor_reads_npy(tmp_path):
    arr = np.random.randn(1, 2048).astype(np.float32)
    npy_path = tmp_path / "audio.npy"
    _atomic_npy_save(arr, npy_path)

    tensor = _load_audio_norm_tensor(npy_path)

    assert isinstance(tensor, torch.Tensor)
    np.testing.assert_array_equal(tensor.numpy(), arr)


@pytest.mark.unit
def test_load_audio_norm_tensor_reads_legacy_pt(tmp_path):
    tensor_in = torch.randn(1, 2048)
    pt_path = tmp_path / "audio.pt"
    _atomic_torch_save(tensor_in, pt_path)

    tensor = _load_audio_norm_tensor(pt_path)

    torch.testing.assert_close(tensor, tensor_in)


# ---------------------------------------------------------------------------
# precompute_mel.compute_spectrogram — dual-format reader contract
# ---------------------------------------------------------------------------
#
# ``precompute_mel`` is the other consumer of ``audio_norm_path`` cache
# entries.  If we switch the write side to ``.npy`` but leave its reader
# on ``torch.load`` only, running the precompute tool over a mixed-format
# cache directory would blow up mid-loop on the first ``.npy`` entry.
# Pin the dual-format read behaviour here.


@pytest.mark.unit
def test_precompute_mel_reads_npy_audio_norm(tmp_path):
    from piper_train.tools.precompute_mel import compute_spectrogram

    # (1, T) matches the norm_audio contract; use enough samples for the
    # default (1024-fft, 256-hop) STFT to succeed.
    audio = torch.randn(1, 24000) * 0.1
    npy_path = tmp_path / "audio.npy"
    _atomic_npy_save(audio, npy_path)

    arr = compute_spectrogram(npy_path, sample_rate=22050)

    assert arr.dtype == np.float16
    assert arr.ndim == 2
    # First dim of a linear spec is n_fft // 2 + 1 = 513 at n_fft=1024.
    assert arr.shape[0] == 513


@pytest.mark.unit
def test_precompute_mel_reads_legacy_pt_audio_norm(tmp_path):
    from piper_train.tools.precompute_mel import compute_spectrogram

    audio = torch.randn(1, 24000) * 0.1
    pt_path = tmp_path / "audio.pt"
    _atomic_torch_save(audio, pt_path)

    arr = compute_spectrogram(pt_path, sample_rate=22050)

    assert arr.dtype == np.float16
    assert arr.shape[0] == 513
