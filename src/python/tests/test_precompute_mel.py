"""Tests for ``piper_train.tools.precompute_mel``.

Covers:

* ``cache_id_from_spec_path`` correctly strips known cache suffixes.
* ``mel_path_for`` composes the sibling ``.mel.npy`` path.
* ``compute_spectrogram`` numerically matches ``spectrogram_torch`` — this is
  the key correctness contract: reading the precomputed ``.mel.npy`` at
  training time must yield the same tensor that the on-the-fly path would
  produce.
* ``run(dataset_jsonl, ...)`` end-to-end: writes .npy files, skips existing
  files unless ``overwrite=True``.
* ``PiperDataset(precomputed_mel_dir=...)`` picks up the precomputed cache
  and ``__getitem__`` returns a spectrogram numerically equal (fp32 upcast)
  to the on-the-fly path.
* Missing ``.mel.npy`` silently falls back to ``audio_spec_path`` — proves
  the backward-compat contract in the task spec.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch")

from piper_train.tools.precompute_mel import (  # noqa: E402
    cache_id_from_spec_path,
    compute_spectrogram,
    mel_path_for,
    run,
)
from piper_train.vits.dataset import PiperDataset, Utterance  # noqa: E402
from piper_train.vits.mel_processing import spectrogram_torch  # noqa: E402


# ---------------------------------------------------------------------------
# STFT / cache-id helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("deadbeef.spec.pt", "deadbeef"),
        ("deadbeef.spec.npy", "deadbeef"),
        ("deadbeef.pt", "deadbeef"),
        ("deadbeef.npy", "deadbeef"),
        ("no_suffix", "no_suffix"),
    ],
)
def test_cache_id_from_spec_path(name, expected):
    assert cache_id_from_spec_path(Path(name)) == expected


@pytest.mark.unit
def test_mel_path_for_composition(tmp_path):
    out = tmp_path / "mel"
    assert mel_path_for(out, Path("cafebabe.spec.pt")) == out / "cafebabe.mel.npy"


# ---------------------------------------------------------------------------
# Numerical parity: precompute_mel output == spectrogram_torch on-the-fly
# ---------------------------------------------------------------------------


def _make_audio_pt(tmp_path: Path, name: str, samples: int = 24000) -> Path:
    """Save a deterministic 1-D audio tensor as .pt and return its path."""
    torch.manual_seed(0xC0FFEE)
    audio = torch.randn(1, samples) * 0.1  # (1, T) matches norm_audio contract
    path = tmp_path / name
    torch.save(audio, path)
    return path


@pytest.mark.unit
def test_compute_spectrogram_matches_spectrogram_torch(tmp_path):
    """compute_spectrogram must produce the same values (fp16) as the
    on-GPU-flow ``spectrogram_torch``. This is the load-time correctness
    contract for the precomputed cache."""
    audio_path = _make_audio_pt(tmp_path, "audio.pt")

    # Reference: exactly what the training pipeline computes today.
    audio = torch.load(audio_path, weights_only=True, map_location="cpu").squeeze()
    ref = spectrogram_torch(
        y=audio.unsqueeze(0),
        n_fft=1024,
        sampling_rate=22050,
        hop_size=256,
        win_size=1024,
        center=False,
    ).squeeze(0)

    arr = compute_spectrogram(audio_path, sample_rate=22050)

    assert arr.dtype == np.float16
    assert arr.shape == tuple(ref.shape)
    # fp16 quantisation tolerance: 5e-3 relative is generous for typical
    # spec magnitudes (~1e-2 to 1e2 range in log space, but linear here).
    np.testing.assert_allclose(
        arr.astype(np.float32),
        ref.to(torch.float16).to(torch.float32).numpy(),
        rtol=0,
        atol=0,
    )


# ---------------------------------------------------------------------------
# End-to-end: run() over a synthetic dataset.jsonl
# ---------------------------------------------------------------------------


def _synth_dataset(tmp_path: Path, n: int = 3) -> Path:
    """Create a synthetic dataset.jsonl with ``n`` utterances and their
    ``.pt`` (audio norm) + ``.spec.pt`` (spectrogram cache) siblings.

    Returns the dataset.jsonl path.
    """
    dataset_dir = tmp_path
    cache_dir = dataset_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for i in range(n):
        # Deterministic per-utterance signal so the parity assertion is stable.
        torch.manual_seed(1000 + i)
        audio = torch.randn(1, 22050) * 0.05
        cache_id = sha256(f"utt-{i}".encode()).hexdigest()
        pt_path = cache_dir / f"{cache_id}.pt"
        spec_path = cache_dir / f"{cache_id}.spec.pt"
        torch.save(audio, pt_path)

        # Precompute the .spec.pt sibling so PiperDataset can fall back to it.
        spec = spectrogram_torch(
            y=audio.squeeze(0).unsqueeze(0),
            n_fft=1024,
            sampling_rate=22050,
            hop_size=256,
            win_size=1024,
            center=False,
        ).squeeze(0)
        torch.save(spec.half(), spec_path)

        records.append(
            {
                "phoneme_ids": [1, 2, 3, 4],
                "audio_norm_path": str(pt_path),
                "audio_spec_path": str(spec_path),
                "speaker_id": i,
                "language_id": 0,
            }
        )

    dataset_jsonl = dataset_dir / "dataset.jsonl"
    with open(dataset_jsonl, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return dataset_jsonl


@pytest.mark.unit
def test_run_writes_expected_files(tmp_path):
    dataset_jsonl = _synth_dataset(tmp_path, n=3)
    mel_dir = tmp_path / "mel"

    n_ok, n_err = run(
        dataset_jsonl=dataset_jsonl,
        output_dir=mel_dir,
        sample_rate=22050,
        # ``workers=1`` keeps the test single-process so pytest/import
        # semantics on Windows do not double-load the module.
        workers=1,
    )
    assert n_ok == 3
    assert n_err == 0
    written = sorted(p.name for p in mel_dir.glob("*.mel.npy"))
    assert len(written) == 3


@pytest.mark.unit
def test_run_resume_default_skips_existing(tmp_path):
    dataset_jsonl = _synth_dataset(tmp_path, n=2)
    mel_dir = tmp_path / "mel"

    # First pass: creates .mel.npy files.
    run(
        dataset_jsonl=dataset_jsonl,
        output_dir=mel_dir,
        sample_rate=22050,
        workers=1,
    )
    mtimes = {p.name: p.stat().st_mtime_ns for p in mel_dir.glob("*.mel.npy")}
    assert len(mtimes) == 2

    # Second pass without --overwrite must NOT rewrite the files.
    run(
        dataset_jsonl=dataset_jsonl,
        output_dir=mel_dir,
        sample_rate=22050,
        workers=1,
    )
    mtimes_after = {p.name: p.stat().st_mtime_ns for p in mel_dir.glob("*.mel.npy")}
    assert mtimes_after == mtimes, (
        "Second run without overwrite=True should have skipped existing files"
    )


@pytest.mark.unit
def test_run_overwrite_rewrites_existing(tmp_path):
    dataset_jsonl = _synth_dataset(tmp_path, n=2)
    mel_dir = tmp_path / "mel"

    run(dataset_jsonl=dataset_jsonl, output_dir=mel_dir, sample_rate=22050, workers=1)
    files = list(mel_dir.glob("*.mel.npy"))
    for p in files:
        # Force a stale mtime so the "was rewritten" check has signal.
        p.write_bytes(b"stale")

    run(
        dataset_jsonl=dataset_jsonl,
        output_dir=mel_dir,
        sample_rate=22050,
        workers=1,
        overwrite=True,
    )
    for p in mel_dir.glob("*.mel.npy"):
        arr = np.load(p, allow_pickle=False)
        # Valid spec has 513 channels (n_fft // 2 + 1) and dtype fp16 —
        # proves overwrite=True replaced the b"stale" payload with a real
        # spectrogram.
        assert arr.shape[0] == 513
        assert arr.dtype == np.float16


# ---------------------------------------------------------------------------
# PiperDataset integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dataset_prefers_precomputed_mel_when_present(tmp_path):
    """When ``.mel.npy`` exists, ``__getitem__`` must load from it and return
    the same values as the ``audio_spec_path`` fallback (up to fp16 quant)."""
    dataset_jsonl = _synth_dataset(tmp_path, n=2)
    mel_dir = tmp_path / "mel"
    run(dataset_jsonl=dataset_jsonl, output_dir=mel_dir, sample_rate=22050, workers=1)

    # Load once WITH the precomputed cache and once WITHOUT — both must
    # produce the same spectrogram tensor (fp16-quantised comparison).
    ds_precomp = PiperDataset(
        [dataset_jsonl],
        precomputed_mel_dir=mel_dir,
    )
    ds_legacy = PiperDataset([dataset_jsonl])

    assert len(ds_precomp) == 2
    assert len(ds_legacy) == 2

    # At least one utterance must have picked up the .mel.npy cache;
    # verifies the resolver actually attached the file.
    assert any(u.precomputed_mel_path is not None for u in ds_precomp.utterances)
    assert all(u.precomputed_mel_path is None for u in ds_legacy.utterances)

    for i in range(2):
        a = ds_precomp[i].spectrogram
        b = ds_legacy[i].spectrogram
        assert a.shape == b.shape
        # Both paths save the same fp16 payload — after fp32 upcast they
        # must match exactly (both were quantised through .half()).
        torch.testing.assert_close(a, b, rtol=0, atol=0)


@pytest.mark.unit
def test_dataset_falls_back_when_mel_missing(tmp_path):
    """Backward-compat: passing ``precomputed_mel_dir`` on an un-precomputed
    dataset must NOT raise; per-utterance fall back to audio_spec_path."""
    dataset_jsonl = _synth_dataset(tmp_path, n=2)
    empty_mel_dir = tmp_path / "mel"
    empty_mel_dir.mkdir()  # exists but is empty

    ds = PiperDataset([dataset_jsonl], precomputed_mel_dir=empty_mel_dir)
    assert len(ds) == 2
    # Empty cache: no utterance has a precomputed path attached.
    assert all(u.precomputed_mel_path is None for u in ds.utterances)
    # Loading still works via the audio_spec_path fallback.
    tensors = ds[0]
    assert tensors.spectrogram.shape[0] == 513


@pytest.mark.unit
def test_dataset_handles_missing_precomputed_mel_dir(tmp_path):
    """A non-existent ``precomputed_mel_dir`` must degrade gracefully to the
    legacy path (log warning, no crash)."""
    dataset_jsonl = _synth_dataset(tmp_path, n=1)
    ds = PiperDataset([dataset_jsonl], precomputed_mel_dir=tmp_path / "does_not_exist")
    assert len(ds) == 1
    # Directory is treated as absent → precomputed_mel_dir attribute is None.
    assert ds.precomputed_mel_dir is None
    tensors = ds[0]
    assert tensors.spectrogram.shape[0] == 513


@pytest.mark.unit
def test_dataset_default_construction_still_works(tmp_path):
    """Regression: existing callers that don't pass ``precomputed_mel_dir``
    must keep behaving exactly as before (Utterance.precomputed_mel_path is
    None everywhere)."""
    dataset_jsonl = _synth_dataset(tmp_path, n=2)
    ds = PiperDataset([dataset_jsonl])
    assert ds.precomputed_mel_dir is None
    for u in ds.utterances:
        assert u.precomputed_mel_path is None


@pytest.mark.unit
def test_utterance_default_precomputed_mel_path_is_none():
    """The new dataclass field must default to None so existing code paths
    that construct ``Utterance(...)`` without it keep type-checking."""
    utt = Utterance(
        phoneme_ids=np.array([1, 2, 3], dtype=np.int16),
        audio_norm_path=Path("dummy.pt"),
        audio_spec_path=Path("dummy.spec.pt"),
    )
    assert utt.precomputed_mel_path is None
