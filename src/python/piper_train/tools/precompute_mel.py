"""Precompute linear spectrograms as ``.npy`` files for faster DataLoader I/O.

Motivation
----------
The training DataLoader currently loads ``audio_spec_path`` (``*.spec.pt``) with
``torch.load`` at every step. On the v8 3,578-speaker × 321k-utterance dataset
that is I/O + CPU bound because ``torch.load`` performs pickle deserialisation
per file. Pre-materialising the same tensor as a raw ``.npy`` file lets the
DataLoader take the numpy path (``np.load`` → ``torch.from_numpy``), which is
2-3x faster and avoids the pickle overhead — a ~8-12h saving over 80 epochs on
the same host.

What this tool writes
---------------------
For every utterance in ``dataset.jsonl`` it computes the *linear* spectrogram
(the same tensor stored in ``audio_spec_path``) from ``audio_norm_path`` via
``spectrogram_torch`` and saves it as ``{output_dir}/{cache_id}.mel.npy``
(fp16, matching the on-disk dtype of the existing ``.spec.pt`` cache). The
directory name ``mel/`` and the file suffix follow the P1 spec convention;
the payload is the linear spec that the model actually consumes (the encoder
needs linear spec, not mel-scale; ``spec_to_mel`` is applied on-GPU inside
``training_step_g``).

Backward-compat
---------------
This is opt-in. Precomputing does NOT modify ``dataset.jsonl`` or the existing
``.spec.pt`` cache. The dataset falls back to ``audio_spec_path`` when the
``.mel.npy`` file is missing or when ``--precomputed-mel`` is not passed to
``piper_train`` (see ``PiperDataset(precomputed_mel_dir=...)``).

Usage
-----
::

    uv run python -m piper_train.tools.precompute_mel \
        --dataset "${DATASET_DIR}/dataset.jsonl" \
        --sample-rate 22050 \
        --workers 30
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from tqdm import tqdm

from piper_train.norm_audio import default_num_processes
from piper_train.vits.mel_processing import spectrogram_torch


logger = logging.getLogger(__name__)


# Suffixes matched (longest first) when recovering the canonical cache_id from
# an ``audio_spec_path``. Kept in this priority order so the double-suffix
# ``.spec.pt`` / ``.spec.npy`` cases strip cleanly before the plain ``.pt`` /
# ``.npy`` fall-through.
_SPEC_SUFFIXES = (".spec.pt", ".spec.npy", ".pt", ".npy")


# Module-level worker state (populated once per worker process by _worker_init).
_worker_output_dir: Path
_worker_filter_length: int
_worker_hop_length: int
_worker_win_length: int
_worker_sample_rate: int
_worker_overwrite: bool


def cache_id_from_spec_path(audio_spec_path: Path | str) -> str:
    """Recover the canonical cache_id from an audio_spec_path.

    ``audio_spec_path`` is normally ``{sha256}.spec.pt`` (produced by
    ``cache_norm_audio``). Strip any of the known cache suffixes so callers
    can compose sibling files like ``{sha256}.mel.npy`` without duplicating
    ``spec`` in the name.
    """
    name = Path(audio_spec_path).name
    for suffix in _SPEC_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(audio_spec_path).stem


def mel_path_for(output_dir: Path, audio_spec_path: Path | str) -> Path:
    """Return the ``.mel.npy`` path used by the precompute cache."""
    return Path(output_dir) / f"{cache_id_from_spec_path(audio_spec_path)}.mel.npy"


def _atomic_np_save(arr: np.ndarray, path: Path) -> None:
    """Save ``arr`` to ``path`` atomically (temp file + rename).

    Mirrors ``_atomic_torch_save`` in ``norm_audio``: writes to a sibling
    tempfile then ``os.replace`` (atomic on POSIX / atomic-ish on NTFS)
    so a crash mid-write leaves the previous good file (or nothing) in
    place rather than a truncated ``.npy``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.close(tmp_fd)
        # ``np.save`` on a file handle does NOT append ``.npy`` (unlike the
        # path-string overload), which is exactly what we want here.
        with open(tmp_path, "wb") as f:
            np.save(f, arr, allow_pickle=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def compute_spectrogram(
    audio_norm_path: Path | str,
    filter_length: int = 1024,
    hop_length: int = 256,
    win_length: int = 1024,
    sample_rate: int = 22050,
) -> np.ndarray:
    """Load a cached audio norm tensor and return its linear spec as fp16 numpy.

    Broken out from ``_process_one`` so tests can call it directly without
    setting up worker globals.  Handles both the legacy ``.pt`` (torch pickle)
    and current ``.npy`` (raw numpy) audio_norm cache formats — the write
    path was switched to ``.npy`` on 2026-07-09 for ~3-5x faster load.
    """
    p = Path(audio_norm_path)
    if p.suffix == ".npy":
        audio = torch.from_numpy(np.load(str(p)))
    else:
        audio = torch.load(str(p), weights_only=True, map_location="cpu")
    audio = audio.squeeze()
    if audio.dim() != 1:
        raise ValueError(f"unexpected audio shape {tuple(audio.shape)}")
    spec = spectrogram_torch(
        y=audio.unsqueeze(0),
        n_fft=filter_length,
        sampling_rate=sample_rate,
        hop_size=hop_length,
        win_size=win_length,
        center=False,
    ).squeeze(0)
    return spec.detach().to(torch.float16).cpu().numpy()


def _worker_init(
    output_dir: str,
    filter_length: int,
    hop_length: int,
    win_length: int,
    sample_rate: int,
    overwrite: bool,
) -> None:
    global _worker_output_dir, _worker_filter_length, _worker_hop_length  # noqa: PLW0603
    global _worker_win_length, _worker_sample_rate, _worker_overwrite  # noqa: PLW0603
    _worker_output_dir = Path(output_dir)
    _worker_filter_length = filter_length
    _worker_hop_length = hop_length
    _worker_win_length = win_length
    _worker_sample_rate = sample_rate
    _worker_overwrite = overwrite
    # Keep BLAS threads at 1 in each worker; the outer Pool provides
    # parallelism. Prevents (workers × BLAS threads) over-subscription.
    torch.set_num_threads(1)


def _process_one(record: dict) -> tuple[str, str | None]:
    """Worker: compute one utterance's spec and return (spec_path, error)."""
    audio_norm_path = record["audio_norm_path"]
    audio_spec_path = record["audio_spec_path"]
    mel_path = mel_path_for(_worker_output_dir, audio_spec_path)

    if not _worker_overwrite and mel_path.exists():
        return (audio_spec_path, None)

    try:
        arr = compute_spectrogram(
            audio_norm_path,
            filter_length=_worker_filter_length,
            hop_length=_worker_hop_length,
            win_length=_worker_win_length,
            sample_rate=_worker_sample_rate,
        )
        _atomic_np_save(arr, mel_path)
        return (audio_spec_path, None)
    except Exception as exc:  # noqa: BLE001 — surface all errors to the parent
        return (audio_spec_path, f"{type(exc).__name__}: {exc}")


def _iter_records(dataset_jsonl: Path):
    """Yield ``{'audio_norm_path', 'audio_spec_path'}`` per non-empty line.

    Relative paths are resolved against ``dataset_jsonl.parent`` — matches
    ``PiperDataset.load_utterance`` semantics.
    """
    dataset_dir = Path(dataset_jsonl).parent
    with open(dataset_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed jsonl line")
                continue
            an = rec.get("audio_norm_path")
            asp = rec.get("audio_spec_path")
            if not an or not asp:
                continue
            an_path = Path(an)
            asp_path = Path(asp)
            if not an_path.is_absolute():
                an_path = dataset_dir / an_path
            if not asp_path.is_absolute():
                asp_path = dataset_dir / asp_path
            yield {
                "audio_norm_path": str(an_path),
                "audio_spec_path": str(asp_path),
            }


def run(
    dataset_jsonl: Path,
    output_dir: Path,
    sample_rate: int,
    filter_length: int = 1024,
    hop_length: int = 256,
    win_length: int = 1024,
    workers: int | None = None,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Precompute ``.mel.npy`` for every utterance in ``dataset_jsonl``.

    Returns
    -------
    (n_ok, n_err): tuple of success / failure counts.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = list(_iter_records(Path(dataset_jsonl)))
    if not records:
        logger.warning("No utterances found in %s", dataset_jsonl)
        return (0, 0)

    workers = workers or default_num_processes()
    logger.info(
        "Precomputing %d spectrogram(s) → %s (workers=%d, overwrite=%s)",
        len(records),
        output_dir,
        workers,
        overwrite,
    )

    n_ok = 0
    n_err = 0
    sample_errors: list[str] = []

    with mp.Pool(
        processes=workers,
        initializer=_worker_init,
        initargs=(
            str(output_dir),
            filter_length,
            hop_length,
            win_length,
            sample_rate,
            overwrite,
        ),
    ) as pool:
        for spec_path, err in tqdm(
            pool.imap_unordered(_process_one, records, chunksize=32),
            total=len(records),
            desc="Precompute mel",
        ):
            if err is None:
                n_ok += 1
            else:
                n_err += 1
                if len(sample_errors) < 20:
                    sample_errors.append(f"{spec_path}: {err}")

    logger.info("Precompute complete: ok=%d err=%d", n_ok, n_err)
    for entry in sample_errors:
        logger.warning("  %s", entry)

    return (n_ok, n_err)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Precompute linear spectrograms as .npy files. Backward-compatible: "
            "the training DataLoader falls back to audio_spec_path when a "
            ".mel.npy file is missing."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to dataset.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for .mel.npy files (default: {dataset_dir}/mel)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        required=True,
        help="Target sample rate (must match config.audio.sample_rate)",
    )
    parser.add_argument(
        "--filter-length",
        type=int,
        default=1024,
        help="STFT n_fft (default: 1024, matches piper VITS)",
    )
    parser.add_argument(
        "--hop-length",
        type=int,
        default=256,
        help="STFT hop_length (default: 256)",
    )
    parser.add_argument(
        "--win-length",
        type=int,
        default=1024,
        help="STFT win_length (default: 1024)",
    )
    parser.add_argument(
        "--workers",
        "--num-processes",
        dest="workers",
        type=int,
        default=default_num_processes(),
        help="Parallel workers (default: min(cpu_count//2, 32))",
    )

    # --overwrite and --resume are mutually exclusive. --resume is the
    # default so passing neither is safe and idempotent.
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute even if the .mel.npy file already exists.",
    )
    exclusive.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Skip files that already exist (default behaviour).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    dataset_jsonl = args.dataset
    output_dir = args.output_dir or (dataset_jsonl.parent / "mel")

    _n_ok, n_err = run(
        dataset_jsonl=dataset_jsonl,
        output_dir=output_dir,
        sample_rate=args.sample_rate,
        filter_length=args.filter_length,
        hop_length=args.hop_length,
        win_length=args.win_length,
        workers=args.workers,
        overwrite=args.overwrite,
    )

    if n_err > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
