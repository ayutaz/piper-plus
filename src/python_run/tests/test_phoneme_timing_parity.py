"""Cross-runtime phoneme timing parity test for the canonical Python runtime.

Loads ``tests/fixtures/phoneme_timing/golden_matrix.json`` (generated from
``src/python_run/piper/timing.py:durations_to_timing`` via
``scripts/regenerate_timing_fixture.py``) and asserts that the canonical
Python implementation self-agrees with every case in the fixture.

Why this exists
---------------
Python is the *canonical* implementation: every other runtime (Rust, Go,
C++, C#, WASM/JS) loads the same fixture and asserts byte-equivalence to
Python's expected blocks.  Until this file existed, **no test verified that
Python's own ``durations_to_timing`` still matched the fixture**.  If Python
was edited without regenerating, the workflow ``timing-parity.yml`` would
catch the drift via ``--check``, but local pytest runs would not — and a
silent change to (e.g.) the cursor-walk semantics would propagate through
the fixture into all 5 satellite runtimes simultaneously.

This test pins the canonical contract from the *test layer* so any local
regression in ``durations_to_timing`` fails ``pytest`` immediately without
relying on the CI drift workflow.

Spec: ``docs/spec/phoneme-timing-contract.toml`` v1.0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper.timing import (
    durations_to_timing,
    timing_to_json,
    timing_to_json_compact,
    timing_to_srt,
    timing_to_tsv,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "phoneme_timing" / "golden_matrix.json"
)

# Tolerance for inter-runtime float comparison (milliseconds).
# 1e-6 ms is well below the spec's 3-decimal display precision and matches
# the tolerance used by the C++/WASM parity tests.
TOLERANCE_MS = 1e-6


def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(
            f"golden fixture missing at {FIXTURE_PATH} — run "
            "`python scripts/regenerate_timing_fixture.py`"
        )
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case_ids(fixture: dict) -> list[str]:
    return [case["name"] for case in fixture["cases"]]


# Module-level fixture load so the parametrize ids are stable.
_FIXTURE = _load_fixture()


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_fixture_schema_version_is_supported():
    """The in-tree fixture must be at the schema version this test understands."""
    assert _FIXTURE.get("schema_version") == 1, (
        "Unknown phoneme-timing fixture schema_version. Adapt this test or "
        "regenerate the fixture."
    )
    assert _FIXTURE.get("cases"), "fixture must contain at least one case"


def test_fixture_calculation_formula_matches_spec():
    """The fixture annotates the canonical formula — must match the spec."""
    assert (
        _FIXTURE.get("calculation_formula")
        == "frame_time_ms = (hop_length / sample_rate) * 1000"
    ), "fixture formula drifted from spec [calculation].formula"


# ---------------------------------------------------------------------------
# Per-case parity vs canonical Python implementation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=_case_ids(_FIXTURE))
def test_canonical_python_matches_fixture(case: dict):
    """Each fixture case is reproducible by ``durations_to_timing``.

    The fixture was generated *from* this exact function — so a self-mismatch
    means somebody edited ``timing.py`` without regenerating the fixture.
    """
    inputs = case["inputs"]
    expected = case["expected"]

    result = durations_to_timing(
        durations=list(inputs["durations"]),
        phoneme_tokens=list(inputs["phoneme_tokens"]),
        sample_rate=inputs["sample_rate"],
        hop_length=inputs["hop_length"],
    )

    # sample_rate parity
    assert result.sample_rate == expected["sample_rate"], (
        f"case '{case['name']}': sample_rate mismatch"
    )

    # phoneme array length parity
    assert len(result.phonemes) == len(expected["phonemes"]), (
        f"case '{case['name']}': phoneme count mismatch — "
        f"got {len(result.phonemes)}, expected {len(expected['phonemes'])}"
    )

    # total_duration_ms parity (cursor-walk semantics per spec)
    assert abs(result.total_duration_ms - expected["total_duration_ms"]) < TOLERANCE_MS, (
        f"case '{case['name']}': total_duration_ms mismatch — "
        f"Python={result.total_duration_ms}, expected={expected['total_duration_ms']}"
    )

    # per-phoneme parity
    for i, (got, want) in enumerate(zip(result.phonemes, expected["phonemes"])):
        assert got.phoneme == want["phoneme"], (
            f"case '{case['name']}' phoneme[{i}]: token mismatch — "
            f"got {got.phoneme!r}, expected {want['phoneme']!r}"
        )
        assert abs(got.start_ms - want["start_ms"]) < TOLERANCE_MS, (
            f"case '{case['name']}' phoneme[{i}] {got.phoneme!r}: start_ms "
            f"got={got.start_ms}, expected={want['start_ms']}"
        )
        assert abs(got.end_ms - want["end_ms"]) < TOLERANCE_MS, (
            f"case '{case['name']}' phoneme[{i}] {got.phoneme!r}: end_ms "
            f"got={got.end_ms}, expected={want['end_ms']}"
        )
        assert abs(got.duration_ms - want["duration_ms"]) < TOLERANCE_MS, (
            f"case '{case['name']}' phoneme[{i}] {got.phoneme!r}: duration_ms "
            f"got={got.duration_ms}, expected={want['duration_ms']}"
        )


# ---------------------------------------------------------------------------
# Spec-defined invariants enforced across every fixture case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=_case_ids(_FIXTURE))
def test_continuous_boundaries_preserved(case: dict):
    """Spec [calculation.cursor_walk]: each phoneme's end_ms == next start_ms."""
    inputs = case["inputs"]
    result = durations_to_timing(
        durations=list(inputs["durations"]),
        phoneme_tokens=list(inputs["phoneme_tokens"]),
        sample_rate=inputs["sample_rate"],
        hop_length=inputs["hop_length"],
    )
    for i in range(len(result.phonemes) - 1):
        prev_end = result.phonemes[i].end_ms
        next_start = result.phonemes[i + 1].start_ms
        assert abs(prev_end - next_start) < TOLERANCE_MS, (
            f"case '{case['name']}': discontinuous boundary between "
            f"phoneme[{i}] {result.phonemes[i].phoneme!r} (end={prev_end}) "
            f"and phoneme[{i + 1}] {result.phonemes[i + 1].phoneme!r} "
            f"(start={next_start})"
        )


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=_case_ids(_FIXTURE))
def test_total_equals_cursor_walk(case: dict):
    """Spec: total_duration_ms = cursor_ms after walking all phonemes."""
    inputs = case["inputs"]
    result = durations_to_timing(
        durations=list(inputs["durations"]),
        phoneme_tokens=list(inputs["phoneme_tokens"]),
        sample_rate=inputs["sample_rate"],
        hop_length=inputs["hop_length"],
    )
    if not result.phonemes:
        assert result.total_duration_ms == 0.0
    else:
        # cursor-walk: total equals last phoneme's end_ms (NOT a separate accumulator).
        assert abs(result.total_duration_ms - result.phonemes[-1].end_ms) < TOLERANCE_MS


# ---------------------------------------------------------------------------
# Output format spec compliance (Python canonical)
# ---------------------------------------------------------------------------


def test_json_pretty_uses_2_space_indent():
    """Spec [output_formats.json_pretty]: indent = 2."""
    case = _FIXTURE["cases"][0]
    result = durations_to_timing(
        durations=list(case["inputs"]["durations"]),
        phoneme_tokens=list(case["inputs"]["phoneme_tokens"]),
        sample_rate=case["inputs"]["sample_rate"],
        hop_length=case["inputs"]["hop_length"],
    )
    text = timing_to_json(result)
    # Pretty JSON has multi-line layout with 2-space indent before the first key.
    assert "\n" in text
    assert '\n  "phonemes"' in text or '\n  "total_duration_ms"' in text, (
        "json_pretty must indent top-level keys with 2 spaces per spec"
    )


def test_json_compact_is_single_line():
    """Spec [output_formats.json_compact]: single-line for streaming/network use."""
    case = _FIXTURE["cases"][0]
    result = durations_to_timing(
        durations=list(case["inputs"]["durations"]),
        phoneme_tokens=list(case["inputs"]["phoneme_tokens"]),
        sample_rate=case["inputs"]["sample_rate"],
        hop_length=case["inputs"]["hop_length"],
    )
    compact = timing_to_json_compact(result)
    assert "\n" not in compact, "json_compact must contain no newlines"
    # Still valid JSON.
    assert json.loads(compact)["sample_rate"] == case["inputs"]["sample_rate"]


def test_json_ensure_ascii_false_preserves_unicode():
    """Spec [output_formats.json_pretty/json_compact]: ensure_ascii = false.

    Unicode phoneme tokens must round-trip without ``\\uXXXX`` escapes.
    """
    result = durations_to_timing(
        durations=[5.0],
        phoneme_tokens=["ɑː"],  # IPA — non-ASCII
        sample_rate=22050,
        hop_length=256,
    )
    pretty = timing_to_json(result)
    compact = timing_to_json_compact(result)
    # The literal Unicode char appears (NOT escaped to ɑː).
    assert "ɑː" in pretty, f"ensure_ascii=False must keep Unicode literal: {pretty!r}"
    assert "ɑː" in compact
    assert "\\u0251" not in pretty
    assert "\\u0251" not in compact


def test_tsv_header_matches_spec():
    """Spec [output_formats.tsv].header = "start_ms\\tend_ms\\tduration_ms\\tphoneme"."""
    result = durations_to_timing(
        durations=[5.0],
        phoneme_tokens=["a"],
        sample_rate=22050,
        hop_length=256,
    )
    tsv = timing_to_tsv(result)
    assert tsv.startswith("start_ms\tend_ms\tduration_ms\tphoneme\n"), (
        f"TSV header drifted from spec: {tsv.splitlines()[0]!r}"
    )


def test_tsv_has_trailing_newline():
    """Spec [output_formats.tsv].trailing_newline = true.

    Final byte of TSV output must be ``\\n`` so tools like ``cat`` and
    line-iterators handle the file consistently.
    """
    result = durations_to_timing(
        durations=[5.0, 10.0],
        phoneme_tokens=["a", "b"],
        sample_rate=22050,
        hop_length=256,
    )
    tsv = timing_to_tsv(result)
    assert tsv.endswith("\n"), "TSV must end with a trailing newline per spec"


def test_tsv_empty_input_emits_header_only_with_trailing_newline():
    """Spec: empty fixture → TSV is just the header row + trailing \\n."""
    result = durations_to_timing(durations=[], phoneme_tokens=[], sample_rate=22050)
    tsv = timing_to_tsv(result)
    # Header line and trailing newline only — no data rows.
    assert tsv == "start_ms\tend_ms\tduration_ms\tphoneme\n"


def test_tsv_float_precision_matches_spec_3_decimals():
    """Spec [output_formats.tsv].float_precision = 3 (toFixed(3) / "{:.3f}")."""
    # 5 frames @ 22050 Hz / 256 hop = 58.04988... ms -> "58.050" with .3f
    result = durations_to_timing(
        durations=[5.0],
        phoneme_tokens=["a"],
        sample_rate=22050,
        hop_length=256,
    )
    tsv = timing_to_tsv(result)
    data_line = tsv.splitlines()[1]
    cols = data_line.split("\t")
    # Each numeric column must match the {:.3f} format (exactly 3 decimals).
    for col in cols[:3]:
        decimal_part = col.split(".")[1] if "." in col else ""
        assert len(decimal_part) == 3, (
            f"TSV float column {col!r} doesn't match :.3f format (3 decimals)"
        )


def test_srt_indexing_starts_at_one():
    """Spec [output_formats.srt].indexing_starts_at = 1."""
    result = durations_to_timing(
        durations=[5.0, 10.0, 15.0],
        phoneme_tokens=["a", "b", "c"],
        sample_rate=22050,
        hop_length=256,
    )
    srt = timing_to_srt(result)
    # First cue must start with "1\n".
    assert srt.startswith("1\n")
    # Each cue index should be sequential (1, 2, 3).
    blocks = [b for b in srt.split("\n\n") if b.strip()]
    for i, block in enumerate(blocks, start=1):
        idx_line = block.split("\n", 1)[0]
        assert idx_line == str(i), (
            f"SRT cue {i} index drifted: got {idx_line!r}, expected {i!r}"
        )


def test_srt_timestamp_format_matches_spec():
    """Spec [output_formats.srt].timestamp_format = "HH:MM:SS,mmm"."""
    import re

    result = durations_to_timing(
        durations=[10.0],
        phoneme_tokens=["a"],
        sample_rate=22050,
        hop_length=256,
    )
    srt = timing_to_srt(result)
    # Pattern: HH:MM:SS,mmm --> HH:MM:SS,mmm
    assert re.search(
        r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$",
        srt.splitlines()[1],
    ), f"SRT timestamp line drifted from spec: {srt.splitlines()[1]!r}"


def test_srt_blank_line_between_cues_per_spec():
    """Spec [output_formats.srt].cue_format ends with a blank line ("\\n\\n")."""
    result = durations_to_timing(
        durations=[5.0, 10.0],
        phoneme_tokens=["a", "b"],
        sample_rate=22050,
        hop_length=256,
    )
    srt = timing_to_srt(result)
    # The cue format is "{idx}\n{start --> end}\n{phoneme}\n\n".
    # Two cues must have a "\n\n" boundary between them.
    assert "\n\n" in srt, "SRT cues must be separated by a blank line per spec"
    # Last cue also ends with \n\n (empty trailing block).
    assert srt.endswith("\n\n")
