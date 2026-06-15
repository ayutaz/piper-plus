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


# ---------------------------------------------------------------------------
# Additional contract tests (audit follow-up — error paths, CLI defaults,
# stratify branch, and I/O round-trip for fetch + split helpers).
# ---------------------------------------------------------------------------


def test_stratified_split_raises_valueerror_on_insufficient_records() -> None:
    """AI-01 surface: stratified_split must reject too-small corpora with a
    ValueError whose message embeds the requested totals and observed count."""
    records = _synthetic_records(100)
    with pytest.raises(ValueError) as excinfo:
        stratified_split(records, train=6_200, val=200, test=200, seed=42)
    msg = str(excinfo.value)
    assert "need 6600" in msg, f"expected 'need 6600' in message, got: {msg!r}"
    assert "train=6200" in msg, f"expected 'train=6200' in message, got: {msg!r}"
    assert "val=200" in msg, f"expected 'val=200' in message, got: {msg!r}"
    assert "test=200" in msg, f"expected 'test=200' in message, got: {msg!r}"
    assert "got 100" in msg, f"expected 'got 100' in message, got: {msg!r}"


def test_stratified_split_partitions_are_disjoint_and_union_covers_consumed() -> None:
    """AI-01 Unit Test 1: union of train/val/test == consumed records, no
    duplicates across splits. Stronger than the existing disjoint test in
    that it pins union size and full coverage of the input set."""
    records = _synthetic_records(6_600)
    train, val, test = stratified_split(
        records, train=6_200, val=200, test=200, seed=42
    )
    train_set = {r.filename for r in train}
    val_set = {r.filename for r in val}
    test_set = {r.filename for r in test}
    union = train_set | val_set | test_set
    # Total consumed == train+val+test, and every record appears at most once.
    assert len(union) == 6_600, (
        f"union size {len(union)} != 6600 — duplicate filename across splits"
    )
    # Since input size == train+val+test, union must equal the input set.
    assert union == {r.filename for r in records}, (
        "union of splits must cover every input record when len(records) == total"
    )


def test_stratify_by_title_distributes_titles_across_splits() -> None:
    """AI-01 surface: stratify_by_title=True interleaves titles so each split
    contains all 3 book titles (regression guard for the round-robin branch
    in stratified_split)."""
    records = _synthetic_records(6_600)
    train, val, test = stratified_split(
        records,
        train=6_200,
        val=200,
        test=200,
        seed=42,
        stratify_by_title=True,
    )
    expected_titles = {"meian", "gongitsune", "kokoro"}
    for split_name, split in (("train", train), ("val", val), ("test", test)):
        titles = {r.title for r in split}
        assert titles == expected_titles, (
            f"{split_name} should contain all 3 titles via round-robin, got {titles}"
        )


def test_cli_argparse_defaults_match_ticket_contract() -> None:
    """AI-01 CLI contract: bare `_parse_args([])` yields the ticket defaults
    (train=6200, val=200, test=200, seed=42, stratify_by_title=False)."""
    cfg = split_css10_ja_poc._parse_args([])
    assert cfg.train == 6_200, f"train default drift: {cfg.train}"
    assert cfg.val == 200, f"val default drift: {cfg.val}"
    assert cfg.test == 200, f"test default drift: {cfg.test}"
    assert cfg.seed == 42, f"seed default drift: {cfg.seed}"
    assert cfg.stratify_by_title is False, (
        "stratify_by_title must default to False per AI-01 ticket"
    )
    # The default dataset_dir resolves to .../dataset-css10-ja-poc/processed.
    assert cfg.dataset_dir.name == "processed", (
        f"dataset_dir leaf should be 'processed', got: {cfg.dataset_dir}"
    )
    assert cfg.dataset_dir.parent.name == "dataset-css10-ja-poc", (
        f"dataset_dir parent should be 'dataset-css10-ja-poc', "
        f"got: {cfg.dataset_dir.parent}"
    )


def test_cli_stratify_flag_toggles_round_trip() -> None:
    """AI-01 CLI surface: the --stratify-by-title / --no-stratify-by-title
    pair (store_true/store_false on shared dest) resolves both directions
    correctly, with False as the silent default."""
    cfg_on = split_css10_ja_poc._parse_args(["--stratify-by-title"])
    assert cfg_on.stratify_by_title is True, (
        "--stratify-by-title flag should produce True"
    )
    cfg_off = split_css10_ja_poc._parse_args(["--no-stratify-by-title"])
    assert cfg_off.stratify_by_title is False, (
        "--no-stratify-by-title flag should produce False"
    )
    cfg_default = split_css10_ja_poc._parse_args([])
    assert cfg_default.stratify_by_title is False, (
        "default (no flag) must resolve to False per set_defaults"
    )


def test_verify_layout_raises_filenotfounderror_with_missing_entries(
    tmp_path: Path,
) -> None:
    """AI-01 surface: verify_layout must raise FileNotFoundError listing
    every entry from REQUIRED_ENTRIES that is absent under raw/, and return
    cleanly once all 3 entries exist."""
    from piper_train.tools import fetch_css10_ja

    # Pass 1: empty tree -> all REQUIRED_ENTRIES are missing.
    with pytest.raises(FileNotFoundError) as excinfo:
        fetch_css10_ja.verify_layout(tmp_path)
    msg = str(excinfo.value)
    assert "meian" in msg, f"expected 'meian' in error, got: {msg!r}"
    assert "gongitsune" in msg, f"expected 'gongitsune' in error, got: {msg!r}"
    assert "transcript.txt" in msg, f"expected 'transcript.txt' in error, got: {msg!r}"

    # Pass 2: create the 3 required entries -> verify_layout returns None.
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "meian").mkdir()
    (raw_dir / "gongitsune").mkdir()
    (raw_dir / "transcript.txt").touch()
    # No exception expected.
    assert fetch_css10_ja.verify_layout(tmp_path) is None


def test_fetch_css10_ja_module_constants_pinned() -> None:
    """AI-01 contract: module constants (URL/SHA256/EXPECTED_HOURS/
    REQUIRED_ENTRIES) are present, correctly typed, and the SHA256 still
    carries the placeholder sentinel until the first real fetch lands."""
    from piper_train.tools import fetch_css10_ja

    assert fetch_css10_ja.EXPECTED_HOURS == 14.0
    assert fetch_css10_ja.REQUIRED_ENTRIES == (
        "meian",
        "gongitsune",
        "transcript.txt",
    )
    assert fetch_css10_ja.CSS10_JA_URL.startswith("https://"), (
        f"CSS10_JA_URL must be https, got: {fetch_css10_ja.CSS10_JA_URL!r}"
    )
    assert isinstance(fetch_css10_ja.CSS10_JA_SHA256, str)
    # Either still the placeholder sentinel, or a real 64-hex SHA256.
    assert (
        fetch_css10_ja.CSS10_JA_SHA256.startswith("TODO_")
        or len(fetch_css10_ja.CSS10_JA_SHA256) == 64
    ), (
        "CSS10_JA_SHA256 must be the TODO placeholder until the real fetch "
        f"completes, then a 64-char hex digest. Got: "
        f"{fetch_css10_ja.CSS10_JA_SHA256!r}"
    )


def test_download_and_extract_raise_notimplementederror_in_skeleton(
    tmp_path: Path,
) -> None:
    """AI-01 skeleton gate: download_archive and extract_archive must still
    raise NotImplementedError with the TODO(AI-01) marker until the
    data-prep impl lands. Flipping this test is the explicit signal that
    the skeleton pass is over."""
    from piper_train.tools.fetch_css10_ja import (
        download_archive,
        extract_archive,
    )

    with pytest.raises(NotImplementedError) as e1:
        download_archive("https://example.invalid/x", tmp_path / "a.tar.gz", "sha")
    assert "TODO(AI-01)" in str(e1.value), (
        f"download_archive should still be a skeleton stub, got: {e1.value!r}"
    )

    with pytest.raises(NotImplementedError) as e2:
        extract_archive(tmp_path / "a.tar.gz", tmp_path / "out")
    assert "TODO(AI-01)" in str(e2.value), (
        f"extract_archive should still be a skeleton stub, got: {e2.value!r}"
    )


def test_load_metadata_raises_filenotfounderror_when_missing(
    tmp_path: Path,
) -> None:
    """AI-01 surface: load_metadata must (a) raise FileNotFoundError with
    actionable guidance when metadata.csv is absent, and (b) fall back to
    title='unknown' when the LJSpeech row only has 2 columns."""
    from piper_train.tools.split_css10_ja_poc import load_metadata

    # Pass 1: empty dir -> FileNotFoundError with the prep-script hint.
    with pytest.raises(FileNotFoundError) as excinfo:
        load_metadata(tmp_path)
    assert "prepare_multilingual_dataset.py" in str(excinfo.value), (
        f"FileNotFoundError should guide the user to the prep script, "
        f"got: {excinfo.value!r}"
    )

    # Pass 2: write a 2-row metadata.csv (one full row, one title-less row).
    metadata = tmp_path / "metadata.csv"
    metadata.write_text("a.wav|hello|meian\nb.wav|hi\n", encoding="utf-8")
    records = load_metadata(tmp_path)
    assert len(records) == 2, f"expected 2 records, got {len(records)}"
    assert records[0].filename == "a.wav"
    assert records[0].text == "hello"
    assert records[0].title == "meian"
    assert records[1].filename == "b.wav"
    assert records[1].text == "hi"
    assert records[1].title == "unknown", (
        f"missing title column must fall back to 'unknown', got {records[1].title!r}"
    )


def test_write_splits_roundtrip_creates_three_files(tmp_path: Path) -> None:
    """AI-01 surface: write_splits creates the target directory if absent
    and writes LJSpeech-delimited train/val/test files with the correct
    row counts and column layout."""
    import csv as _csv

    from piper_train.tools.split_css10_ja_poc import write_splits

    splits_dir = tmp_path / "splits"
    # Intentionally do NOT pre-create splits_dir — write_splits must mkdir.
    assert not splits_dir.exists()

    rec = Record(filename="a.wav", text="t", title="meian")
    train_recs = [rec, rec, rec]
    val_recs = [rec]
    test_recs = [rec]
    write_splits(splits_dir, train_recs, val_recs, test_recs)

    train_path = splits_dir / "train.csv"
    val_path = splits_dir / "val.csv"
    test_path = splits_dir / "test.csv"
    assert train_path.exists(), "train.csv was not written"
    assert val_path.exists(), "val.csv was not written"
    assert test_path.exists(), "test.csv was not written"

    expected = {"train.csv": 3, "val.csv": 1, "test.csv": 1}
    for name, expected_rows in expected.items():
        with (splits_dir / name).open("r", encoding="utf-8") as fh:
            rows = list(_csv.reader(fh, delimiter="|"))
        assert len(rows) == expected_rows, (
            f"{name} should have {expected_rows} rows, got {len(rows)}"
        )
        for row in rows:
            assert row == ["a.wav", "t", "meian"], (
                f"{name} row layout drift: got {row!r}"
            )
