"""Tests for parallel VAD / audio-cache preprocessing.

Pin the contract that when ``cache_audio.py`` (and the batch worker helpers
used by ``prepare_multilingual_dataset.py`` / ``prepare_bilingual_dataset.py``)
fan out ``energy_vad_numpy`` across a ``multiprocessing.Pool``, the trimmed
audio is byte-identical to the single-worker path.

If we ever regress the worker-side path (e.g. change chunk_size defaults in
Pool init or introduce non-determinism into ``energy_vad_numpy``), the
parallel preprocessing would silently drift from the serial path documented
in ``CLAUDE.md`` (v7 zero-shot dataset preparation). These tests fail loud
on such drift.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
from pathlib import Path

import numpy as np
import pytest


# piper_train.norm_audio.__init__ pulls in torchaudio at module top-level;
# skip the whole file if that stack is not installed (matches
# test_energy_vad.py's guard).
pytest.importorskip("torchaudio")
pytest.importorskip("soxr")
pytest.importorskip("soundfile")

from piper_train.norm_audio import (  # noqa: E402
    default_num_processes,
    energy_vad_numpy,
)


# ---------------------------------------------------------------------------
# default_num_processes contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultNumProcesses:
    def test_returns_at_least_one(self):
        assert default_num_processes() >= 1

    def test_caps_at_32(self):
        # 64-vCPU A100 host would yield 32 under min(cpu//2, 32).
        # cpu_count() on the test host is unknown, but the ceiling
        # must never exceed 32 regardless.
        assert default_num_processes() <= 32

    def test_at_most_half_of_cpu_count(self):
        # min(cpu//2, 32) — never exceeds half of cpu_count().
        cpu = os.cpu_count() or 1
        assert default_num_processes() <= max(1, cpu // 2) or cpu <= 2


# ---------------------------------------------------------------------------
# energy_vad_numpy: Pool.imap parity vs serial
# ---------------------------------------------------------------------------


def _make_audio_batch(n: int, sr: int = 16000, seed: int = 0):
    """Build a deterministic batch of 1-second audios with mixed content."""
    rng = np.random.default_rng(seed)
    batch: list[np.ndarray] = []
    for i in range(n):
        # Alternate silence + tone segments so VAD offsets vary per item.
        silence = np.zeros(sr // 2, dtype=np.float32)
        # Rotate amplitude so each item has a distinguishable duration profile
        tone = np.ones(sr // 2, dtype=np.float32) * (0.05 + 0.05 * ((i % 5) + 1))
        noise = rng.normal(0, 0.001, size=sr).astype(np.float32)
        audio = np.concatenate([silence, tone]) + noise[:sr]
        batch.append(audio)
    return batch


def _vad_worker(audio: np.ndarray):
    """Module-level worker so multiprocessing can pickle it on Windows."""
    return energy_vad_numpy(audio, threshold=0.02)


@pytest.mark.unit
class TestEnergyVadPoolParity:
    """energy_vad_numpy must produce identical results serial vs Pool.imap."""

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Windows CI spawn overhead is too slow for Pool test; "
        "coverage is provided by Linux CI",
    )
    def test_pool_imap_matches_serial(self):
        batch = _make_audio_batch(n=8)

        serial = [energy_vad_numpy(a, threshold=0.02) for a in batch]

        # Use spawn to match the actual behaviour on Windows / macOS Python 3.14
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=2) as pool:
            parallel = list(pool.imap(_vad_worker, batch, chunksize=2))

        assert len(serial) == len(parallel)
        for s, p in zip(serial, parallel, strict=True):
            # (offset, duration) tuples: byte-identical because energy_vad_numpy
            # is pure-numpy and deterministic. Any drift here indicates a
            # non-deterministic code path snuck into the VAD.
            assert s == p, f"parallel VAD drift: serial={s}, parallel={p}"

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Windows CI spawn overhead is too slow for Pool test",
    )
    def test_pool_imap_preserves_input_order(self):
        # imap (not imap_unordered) must yield results in input order —
        # cache_audio.py relies on this for progress reporting to match the
        # dataset.jsonl update.
        batch = _make_audio_batch(n=6, seed=42)
        expected = [energy_vad_numpy(a, threshold=0.02) for a in batch]

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=2) as pool:
            got = list(pool.imap(_vad_worker, batch, chunksize=1))
        assert got == expected


# ---------------------------------------------------------------------------
# cache_audio._process_one: Pool.imap parity vs direct call
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheAudioProcessOneParity:
    """The Pool worker in cache_audio.py must produce identical .pt files."""

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Windows CI spawn overhead is too slow for Pool test",
    )
    def test_process_one_serial_vs_pool(self, tmp_path: Path):
        import soundfile as sf  # noqa: PLC0415
        import torch  # noqa: PLC0415

        from piper_train.tools import cache_audio  # noqa: PLC0415

        # Build 4 tiny WAV files with mixed content.
        sr = 16000
        wav_dir = tmp_path / "wavs"
        wav_dir.mkdir()
        rng = np.random.default_rng(123)
        wav_paths: list[str] = []
        for i in range(4):
            audio = np.concatenate(
                [
                    np.zeros(sr // 2, dtype=np.float32),
                    rng.normal(0, 0.3, size=sr).astype(np.float32),
                    np.zeros(sr // 2, dtype=np.float32),
                ]
            )
            p = wav_dir / f"utt_{i:02d}.wav"
            sf.write(str(p), audio, sr)
            wav_paths.append(str(p))

        # ---- Serial reference ----
        serial_cache = tmp_path / "cache_serial"
        serial_cache.mkdir()
        cache_audio._worker_init(
            str(serial_cache), sample_rate=22050, vad_threshold=0.02
        )
        serial_results = [cache_audio._process_one(p) for p in wav_paths]

        for _, norm_path, err in serial_results:
            assert err is None, f"serial cache failed: {err}"
            assert norm_path is not None
            assert Path(norm_path).exists()

        # ---- Parallel via Pool ----
        parallel_cache = tmp_path / "cache_parallel"
        parallel_cache.mkdir()
        ctx = mp.get_context("spawn")
        with ctx.Pool(
            processes=2,
            initializer=cache_audio._worker_init,
            initargs=(str(parallel_cache), 22050, 0.02),
        ) as pool:
            parallel_results = list(
                pool.imap(cache_audio._process_one, wav_paths, chunksize=1)
            )

        # Same input order + same sha256(abs_path) hashing → same cache_id
        # filenames. Contents must be byte-identical tensors.
        assert len(serial_results) == len(parallel_results)
        for (wav_s, norm_s, _err_s), (wav_p, norm_p, err_p) in zip(
            serial_results, parallel_results, strict=True
        ):
            assert err_p is None, f"parallel cache failed: {err_p}"
            assert wav_s == wav_p
            assert Path(norm_s).name == Path(norm_p).name  # same cache_id

            t_serial = torch.load(norm_s, weights_only=True)
            t_parallel = torch.load(norm_p, weights_only=True)
            assert t_serial.shape == t_parallel.shape, (
                f"tensor shape drift: serial={t_serial.shape} "
                f"parallel={t_parallel.shape}"
            )
            assert torch.allclose(t_serial, t_parallel, atol=0, rtol=0), (
                "cache_audio parallel path produced non-byte-identical .pt: "
                f"max_abs_diff={(t_serial - t_parallel).abs().max().item()}"
            )


# ---------------------------------------------------------------------------
# Edge case: empty inputs must not crash the Pool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmptyInput:
    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Windows CI spawn overhead is too slow for Pool test",
    )
    def test_pool_imap_empty_batch(self):
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=2) as pool:
            got = list(pool.imap(_vad_worker, [], chunksize=1))
        assert got == []
