"""AI-01: contract tests for the CSS10 JA PoC dataset prep pipeline.

Implementation plan: docs/tickets/tickets/AI-01-css10-dataset-prep.md

Covers the 6 acceptance assertions from the ticket:

1. Split ratio is exactly 6,200 / 200 / 200.
2. Split is deterministic under ``seed=42`` (re-running yields identical lists).
3. Prosody npz shape is ``[T_phoneme, 16]`` (16-dim prosody features).
4. Phoneme-set is compatible with the 6lang base config (subset of symbols).
5. Sample rate 22,050 Hz and mono channel for every wav in ``processed/``.
6. ``lid==0`` and ``speaker_id==0`` constant across every record.

The FS-bound tests are gated behind a ``skipif`` that checks for the
processed dataset on the host (see ``PIPER_DATA_ROOT`` below). The two
split-logic tests also have a pure-Python inline variant that exercises
``split_css10_ja_poc.stratified_split`` against a synthetic 6,600-record
fixture, so the skeleton-pass logic is testable today without disk access.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from piper_train.tools import split_css10_ja_poc
from piper_train.tools.split_css10_ja_poc import Record, stratified_split


# ---------------------------------------------------------------------------
# Shared fixture constants
#
# The training-host paths (``${PIPER_DATA_ROOT}/dataset-css10-ja-poc`` and
# ``${PIPER_MODEL_ROOT}/output-multilingual-6lang-mb-istft``) are
# resolved from env vars so this file stays out of the
# ``check_secret_path_reference`` ALLOWLIST. Maintainer convention on the
# training host is to export ``PIPER_DATA_ROOT=/data/piper`` and
# ``PIPER_MODEL_ROOT=/data/piper``; CI / local dev runs leave them unset
# and the tests skip gracefully.
# ---------------------------------------------------------------------------

_DATA_ROOT = Path(os.environ.get("PIPER_DATA_ROOT", "./datasets"))
_MODEL_ROOT = Path(os.environ.get("PIPER_MODEL_ROOT", "./models"))

PROCESSED_DIR = _DATA_ROOT / "dataset-css10-ja-poc" / "processed"
BASE_6LANG_CONFIG = str(
    _MODEL_ROOT / "output-multilingual-6lang-mb-istft" / "config.json"
)

DATASET_AVAILABLE = PROCESSED_DIR.exists()
SKIP_NO_DATASET = pytest.mark.skipif(
    not DATASET_AVAILABLE,
    reason="AI-01 dataset not yet generated (set PIPER_DATA_ROOT to enable).",
)


def _synthetic_records(n: int = 6_600) -> list[Record]:
    """Generate a deterministic 6,600-record fixture with 3 book titles."""
    titles = ("meian", "gongitsune", "kokoro")
    return [
        Record(
            filename=f"{titles[i % 3]}/utt_{i:05d}.wav",
            text=f"sample text {i}",
            title=titles[i % 3],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Pure-Python split-logic tests (no FS dependency — runnable in skeleton pass).
# ---------------------------------------------------------------------------


def test_split_ratio_exact() -> None:
    """Contract 1: split sizes are exactly (6200, 200, 200) from a 6600 corpus."""
    records = _synthetic_records(6_600)
    train, val, test = stratified_split(
        records, train=6_200, val=200, test=200, seed=42
    )
    assert len(train) == 6_200
    assert len(val) == 200
    assert len(test) == 200
    # No record appears in more than one split.
    train_set = {r.filename for r in train}
    val_set = {r.filename for r in val}
    test_set = {r.filename for r in test}
    assert train_set.isdisjoint(val_set)
    assert train_set.isdisjoint(test_set)
    assert val_set.isdisjoint(test_set)


def test_split_deterministic_with_seed() -> None:
    """Contract 2: seed=42 yields byte-identical splits on a re-run."""
    records = _synthetic_records(6_600)
    a = stratified_split(records, train=6_200, val=200, test=200, seed=42)
    b = stratified_split(records, train=6_200, val=200, test=200, seed=42)
    assert [r.filename for r in a[0]] == [r.filename for r in b[0]]
    assert [r.filename for r in a[1]] == [r.filename for r in b[1]]
    assert [r.filename for r in a[2]] == [r.filename for r in b[2]]


# ---------------------------------------------------------------------------
# FS-bound contract tests (skipped pre-data-prep).
# ---------------------------------------------------------------------------


@SKIP_NO_DATASET
def test_split_ratio_exact_on_disk() -> None:
    """Contract 1 (on-disk): the written split files contain exactly 6200/200/200."""
    splits_dir = PROCESSED_DIR / "splits"
    # TODO(AI-01): assert line counts of train.csv / val.csv / test.csv.
    raise NotImplementedError(
        "TODO(AI-01) test_split_ratio_exact_on_disk: implement once "
        "splits/*.csv are present."
    )


@SKIP_NO_DATASET
def test_split_deterministic_with_seed_on_disk() -> None:
    """Contract 2 (on-disk): re-running split_css10_ja_poc with seed=42 is idempotent."""
    # TODO(AI-01): invoke split_css10_ja_poc.main(["--seed", "42", ...]) twice
    # and diff the produced csv files.
    raise NotImplementedError(
        "TODO(AI-01) test_split_deterministic_with_seed_on_disk: implement "
        "once dataset is materialized."
    )


@SKIP_NO_DATASET
def test_prosody_npz_shape_16dim() -> None:
    """Contract 3: every prosody npz under processed/ has shape ``[T_phoneme, 16]``."""
    # TODO(AI-01): glob processed/**/*.prosody.npz and assert arr.shape[-1] == 16.
    raise NotImplementedError(
        "TODO(AI-01) test_prosody_npz_shape_16dim: needs add_prosody_features "
        "output on disk."
    )


@SKIP_NO_DATASET
def test_phoneme_set_compatibility_6lang() -> None:
    """Contract 4: dataset's phoneme set is a subset of the 6lang base config."""
    base_config = Path(BASE_6LANG_CONFIG)
    if not base_config.exists():
        pytest.skip(f"6lang base config not present at {base_config}")
    # TODO(AI-01): load processed/config.json + base_config and assert
    # set(processed_symbols).issubset(set(base_symbols)).
    raise NotImplementedError(
        "TODO(AI-01) test_phoneme_set_compatibility_6lang: implement after "
        "prepare_multilingual_dataset.py --single-speaker run."
    )


@SKIP_NO_DATASET
def test_sample_rate_and_mono() -> None:
    """Contract 5: every wav under processed/ is 22050Hz mono."""
    # TODO(AI-01): walk processed/wav/*.wav, soundfile.info, assert sr==22050,
    # channels==1.
    raise NotImplementedError(
        "TODO(AI-01) test_sample_rate_and_mono: needs processed wav tree."
    )


@SKIP_NO_DATASET
def test_lid_speaker_id_constant() -> None:
    """Contract 6: every record has ``lid==0`` and ``speaker_id==0`` (single ja speaker)."""
    # TODO(AI-01): scan metadata.csv (or processed manifest) for the lid /
    # speaker_id columns and assert uniformly zero.
    raise NotImplementedError(
        "TODO(AI-01) test_lid_speaker_id_constant: requires processed "
        "manifest with lid / speaker_id columns."
    )


# ---------------------------------------------------------------------------
# Module-import smoke (always runs — catches syntax / import regressions).
# ---------------------------------------------------------------------------


def test_module_imports_clean() -> None:
    """Skeleton-pass guard: both AI-01 CLI modules import without side effects."""
    from piper_train.tools import (
        fetch_css10_ja,  # noqa: F401
        split_css10_ja_poc as _split,  # noqa: F401
    )

    assert _split.DEFAULT_TRAIN == 6_200
    assert _split.DEFAULT_VAL == 200
    assert _split.DEFAULT_TEST == 200
    assert _split.DEFAULT_SEED == 42
    assert split_css10_ja_poc is _split
