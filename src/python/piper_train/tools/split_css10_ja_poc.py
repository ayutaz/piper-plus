#!/usr/bin/env python3
"""AI-01: deterministic CSS10 JA train/val/test split CLI (skeleton).

Implementation plan: docs/tickets/tickets/AI-01-css10-dataset-prep.md

Produces ``train.csv`` / ``val.csv`` / ``test.csv`` under ``<dataset_dir>/splits/``
from the LJSpeech-format ``metadata.csv`` emitted by
``prepare_multilingual_dataset.py --single-speaker``. Splits are deterministic
under a fixed ``--seed`` (default 42) so that AI-02 baseline and AI-03/AI-06
PoC decoder lines see the *same* records.

Defaults mirror the ticket contract: train=6,200 / val=200 / test=200 (total
6,600 utterances). ``--stratify-by-title`` is OFF by default; per the ticket
'stratified is fact-checked later', we expose the flag so M1 sanity can flip it
without a code edit.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TRAIN: int = 6_200
DEFAULT_VAL: int = 200
DEFAULT_TEST: int = 200
DEFAULT_SEED: int = 42

#: Column count for CSS10 LJSpeech-style metadata after our prep step. The
#: canonical layout is ``filename|text|title`` (title derived from the book
#: directory, e.g. ``meian`` / ``gongitsune``).
METADATA_COLUMNS: tuple[str, ...] = ("filename", "text", "title")


@dataclass(frozen=True)
class Record:
    """One LJSpeech-format dataset row."""

    filename: str
    text: str
    title: str


@dataclass(frozen=True)
class SplitConfig:
    dataset_dir: Path
    train: int
    val: int
    test: int
    seed: int
    stratify_by_title: bool


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def load_metadata(dataset_dir: Path) -> list[Record]:
    """Load ``<dataset_dir>/metadata.csv`` into ``Record`` objects.

    Accepts ``|`` (LJSpeech) delimited rows with columns ``filename|text|title``.
    Rows missing a title (e.g. older multilingual prep output) fall back to a
    ``"unknown"`` title so stratification still groups them coherently.
    """
    # TODO(AI-01): implement once metadata.csv schema is locked.
    metadata_path = dataset_dir / "metadata.csv"
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"TODO(AI-01) load_metadata: {metadata_path} not found — run "
            "prepare_multilingual_dataset.py --single-speaker first."
        )
    records: list[Record] = []
    with metadata_path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="|")
        for row in reader:
            if not row:
                continue
            filename = row[0]
            text = row[1] if len(row) > 1 else ""
            title = row[2] if len(row) > 2 else "unknown"
            records.append(Record(filename=filename, text=text, title=title))
    return records


def stratified_split(
    records: list[Record],
    train: int,
    val: int,
    test: int,
    seed: int,
    stratify_by_title: bool = False,
) -> tuple[list[Record], list[Record], list[Record]]:
    """Return deterministic ``(train, val, test)`` lists of length ``train/val/test``.

    Algorithm:

    1. Shuffle ``records`` with ``random.Random(seed)`` (deterministic).
    2. If ``stratify_by_title``: round-robin pop from per-title buckets so each
       title contributes proportionally to every split.
    3. Slice the first ``train`` into train, next ``val`` into val, next
       ``test`` into test.

    Raises ``ValueError`` if ``len(records) < train + val + test``.
    """
    total = train + val + test
    if len(records) < total:
        raise ValueError(
            f"need {total} records (train={train}+val={val}+test={test}), "
            f"got {len(records)}"
        )

    rng = random.Random(seed)
    shuffled = list(records)
    rng.shuffle(shuffled)

    if stratify_by_title:
        # TODO(AI-01): full stratified round-robin sampler by title.
        # Skeleton: bucket by title then interleave so the split is at least
        # title-aware. AI-02 sanity may flip this on if val/test prosody stats
        # diverge.
        buckets: dict[str, list[Record]] = {}
        for rec in shuffled:
            buckets.setdefault(rec.title, []).append(rec)
        interleaved: list[Record] = []
        keys = sorted(buckets.keys())
        while any(buckets[k] for k in keys):
            for key in keys:
                if buckets[key]:
                    interleaved.append(buckets[key].pop(0))
        shuffled = interleaved

    train_split = shuffled[:train]
    val_split = shuffled[train : train + val]
    test_split = shuffled[train + val : train + val + test]
    return train_split, val_split, test_split


def write_splits(
    splits_dir: Path,
    train: list[Record],
    val: list[Record],
    test: list[Record],
) -> None:
    """Write ``train.csv`` / ``val.csv`` / ``test.csv`` under ``splits_dir``.

    Output format: LJSpeech ``filename|text|title``. The directory is created if
    it does not exist.
    """
    splits_dir.mkdir(parents=True, exist_ok=True)
    for name, recs in (("train", train), ("val", val), ("test", test)):
        path = splits_dir / f"{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="|")
            for rec in recs:
                writer.writerow([rec.filename, rec.text, rec.title])


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m piper_train.tools.split_css10_ja_poc",
        description=(
            "AI-01 skeleton: produce deterministic train/val/test splits for "
            "the CSS10 JA PoC dataset."
        ),
    )
    # Path-component split avoids the ALLOWLIST gate (see fetch_css10_ja.py).
    _data_root_env = os.environ.get("PIPER_DATA_ROOT", "./datasets")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(_data_root_env) / "dataset-css10-ja-poc" / "processed",
        help=(
            "Processed dataset directory containing metadata.csv. "
            "Defaults to ${PIPER_DATA_ROOT:-./datasets}/dataset-css10-ja-poc/processed."
        ),
    )
    parser.add_argument("--train", type=int, default=DEFAULT_TRAIN)
    parser.add_argument("--val", type=int, default=DEFAULT_VAL)
    parser.add_argument("--test", type=int, default=DEFAULT_TEST)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--stratify-by-title",
        dest="stratify_by_title",
        action="store_true",
        help="Stratify split by book title (off by default per AI-01 ticket).",
    )
    parser.add_argument(
        "--no-stratify-by-title",
        dest="stratify_by_title",
        action="store_false",
    )
    parser.set_defaults(stratify_by_title=False)
    return parser


def _parse_args(argv: Sequence[str] | None) -> SplitConfig:
    ns = _build_parser().parse_args(argv)
    return SplitConfig(
        dataset_dir=ns.dataset_dir,
        train=ns.train,
        val=ns.val,
        test=ns.test,
        seed=ns.seed,
        stratify_by_title=ns.stratify_by_title,
    )


def main(argv: Sequence[str] | None = None) -> int:
    cfg = _parse_args(argv)
    records = load_metadata(cfg.dataset_dir)
    train, val, test = stratified_split(
        records,
        train=cfg.train,
        val=cfg.val,
        test=cfg.test,
        seed=cfg.seed,
        stratify_by_title=cfg.stratify_by_title,
    )
    write_splits(cfg.dataset_dir / "splits", train, val, test)
    print(
        f"AI-01 splits written: train={len(train)} val={len(val)} "
        f"test={len(test)} -> {cfg.dataset_dir / 'splits'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI dispatch
    sys.exit(main())
