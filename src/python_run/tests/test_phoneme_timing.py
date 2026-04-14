"""Comprehensive tests for piper.timing module."""

from __future__ import annotations

import json

import pytest

from piper.timing import (
    DEFAULT_HOP_LENGTH,
    TimingResult,
    build_phoneme_id_reverse_map,
    durations_to_timing,
    timing_to_json,
    timing_to_json_compact,
    timing_to_tsv,
)

# Pre-computed frame time for the standard 22050 Hz / 256 hop configuration.
FRAME_TIME_22050 = (256 / 22050) * 1000.0  # ~11.60998 ms


# ---- core conversion tests ------------------------------------------------


def test_basic_durations():
    """3 phonemes with known durations produce correct ms timestamps."""
    result = durations_to_timing(
        durations=[10.0, 20.0, 15.0],
        phoneme_tokens=["a", "b", "c"],
        sample_rate=22050,
        hop_length=256,
    )

    assert len(result.phonemes) == 3
    assert result.sample_rate == 22050

    ph0, ph1, ph2 = result.phonemes

    # ph0: 10 frames
    assert ph0.phoneme == "a"
    assert ph0.start_ms == pytest.approx(0.0, abs=0.1)
    assert ph0.end_ms == pytest.approx(10 * FRAME_TIME_22050, abs=0.1)
    assert ph0.duration_ms == pytest.approx(10 * FRAME_TIME_22050, abs=0.1)

    # ph1: 20 frames, starts where ph0 ends
    assert ph1.phoneme == "b"
    assert ph1.start_ms == pytest.approx(10 * FRAME_TIME_22050, abs=0.1)
    assert ph1.end_ms == pytest.approx(30 * FRAME_TIME_22050, abs=0.1)
    assert ph1.duration_ms == pytest.approx(20 * FRAME_TIME_22050, abs=0.1)

    # ph2: 15 frames
    assert ph2.phoneme == "c"
    assert ph2.start_ms == pytest.approx(30 * FRAME_TIME_22050, abs=0.1)
    assert ph2.end_ms == pytest.approx(45 * FRAME_TIME_22050, abs=0.1)
    assert ph2.duration_ms == pytest.approx(15 * FRAME_TIME_22050, abs=0.1)

    # total
    assert result.total_duration_ms == pytest.approx(45 * FRAME_TIME_22050, abs=0.1)


def test_zero_duration():
    """All-zero durations produce all-zero timestamps."""
    result = durations_to_timing(
        durations=[0.0, 0.0, 0.0],
        phoneme_tokens=["x", "y", "z"],
        sample_rate=22050,
    )

    for ph in result.phonemes:
        assert ph.start_ms == 0.0
        assert ph.end_ms == 0.0
        assert ph.duration_ms == 0.0

    assert result.total_duration_ms == 0.0


def test_negative_duration_clamped():
    """Negative durations are silently clamped to 0 (no exception)."""
    result = durations_to_timing(
        durations=[-5.0, 10.0, -3.0],
        phoneme_tokens=["a", "b", "c"],
        sample_rate=22050,
    )

    assert result.phonemes[0].duration_ms == 0.0
    assert result.phonemes[1].duration_ms == pytest.approx(
        10 * FRAME_TIME_22050, abs=0.1
    )
    assert result.phonemes[2].duration_ms == 0.0


def test_length_mismatch_error():
    """Mismatched durations/tokens lengths raise ValueError."""
    with pytest.raises(ValueError, match="length mismatch"):
        durations_to_timing(
            durations=[1.0, 2.0],
            phoneme_tokens=["a"],
            sample_rate=22050,
        )


def test_invalid_sample_rate():
    """sample_rate=0 raises ValueError."""
    with pytest.raises(ValueError, match="sample_rate must be positive"):
        durations_to_timing(
            durations=[1.0],
            phoneme_tokens=["a"],
            sample_rate=0,
        )


def test_invalid_hop_length():
    """hop_length=0 raises ValueError."""
    with pytest.raises(ValueError, match="hop_length must be positive"):
        durations_to_timing(
            durations=[1.0],
            phoneme_tokens=["a"],
            sample_rate=22050,
            hop_length=0,
        )


# ---- serialization tests --------------------------------------------------


def _make_sample_result() -> TimingResult:
    """Helper: build a small TimingResult for serialization tests."""
    return durations_to_timing(
        durations=[10.0, 20.0],
        phoneme_tokens=["a", "k"],
        sample_rate=22050,
    )


def test_to_json_format():
    """JSON output is valid and contains the expected top-level keys."""
    result = _make_sample_result()
    text = timing_to_json(result)
    data = json.loads(text)

    assert "phonemes" in data
    assert isinstance(data["phonemes"], list)
    assert len(data["phonemes"]) == 2
    assert "total_duration_ms" in data
    assert "sample_rate" in data
    assert data["sample_rate"] == 22050

    # Each phoneme entry has the expected fields.
    for entry in data["phonemes"]:
        assert "phoneme" in entry
        assert "start_ms" in entry
        assert "end_ms" in entry
        assert "duration_ms" in entry


def test_to_json_compact():
    """Compact JSON is valid and contains no indentation."""
    result = _make_sample_result()
    text = timing_to_json_compact(result)

    # Must be parseable.
    data = json.loads(text)
    assert len(data["phonemes"]) == 2

    # No newline-based indentation (single line).
    assert "\n" not in text


def test_to_tsv_format():
    """TSV output has a header line and the correct number of data lines."""
    result = _make_sample_result()
    text = timing_to_tsv(result)
    lines = text.splitlines()

    # First line is the header.
    assert lines[0] == "start_ms\tend_ms\tduration_ms\tphoneme"

    # One data line per phoneme.
    assert len(lines) == 1 + len(result.phonemes)

    # Each data line has exactly 4 tab-separated columns.
    for line in lines[1:]:
        cols = line.split("\t")
        assert len(cols) == 4


# ---- structural invariant tests -------------------------------------------


def test_timing_continuity():
    """Each phoneme's end_ms equals the next phoneme's start_ms (exact)."""
    result = durations_to_timing(
        durations=[5.0, 12.0, 8.0, 3.0],
        phoneme_tokens=["a", "b", "c", "d"],
        sample_rate=22050,
    )

    for i in range(len(result.phonemes) - 1):
        assert result.phonemes[i].end_ms == result.phonemes[i + 1].start_ms


def test_first_starts_at_zero():
    """The first phoneme always starts at 0.0 ms."""
    result = durations_to_timing(
        durations=[7.0, 3.0],
        phoneme_tokens=["p", "q"],
        sample_rate=22050,
    )

    assert result.phonemes[0].start_ms == 0.0


def test_total_equals_last_end():
    """total_duration_ms equals the last phoneme's end_ms."""
    result = durations_to_timing(
        durations=[5.0, 10.0, 15.0],
        phoneme_tokens=["a", "b", "c"],
        sample_rate=22050,
    )

    assert result.total_duration_ms == result.phonemes[-1].end_ms


def test_different_sample_rates():
    """Same durations at different sample rates produce different timings."""
    durs = [10.0, 20.0]
    tokens = ["a", "b"]

    result_22050 = durations_to_timing(durs, tokens, sample_rate=22050)
    result_16000 = durations_to_timing(durs, tokens, sample_rate=16000)

    # frame_time differs, so total must differ.
    assert result_22050.total_duration_ms != pytest.approx(
        result_16000.total_duration_ms, abs=0.01
    )

    # 16000 Hz has a larger frame time -> longer total.
    assert result_16000.total_duration_ms > result_22050.total_duration_ms


# ---- reverse map tests -----------------------------------------------------


def test_build_reverse_map_basic():
    """Basic phoneme_id_map produces the correct reverse mapping."""
    phoneme_id_map = {"a": [10], "k": [12]}
    rmap = build_phoneme_id_reverse_map(phoneme_id_map)

    assert rmap == {10: "a", 12: "k"}


def test_build_reverse_map_pua():
    """PUA characters are resolved via pua_to_multi_char mapping."""
    pua_char = "\uE019"
    phoneme_id_map = {pua_char: [50], "a": [10]}
    pua_map = {pua_char: "N_m"}

    rmap = build_phoneme_id_reverse_map(phoneme_id_map, pua_to_multi_char=pua_map)

    assert rmap[50] == "N_m"
    assert rmap[10] == "a"


def test_build_reverse_map_pua_without_mapping():
    """PUA characters without an explicit mapping render as U+XXXX."""
    pua_char = "\uE020"
    phoneme_id_map = {pua_char: [60]}

    rmap = build_phoneme_id_reverse_map(phoneme_id_map)

    assert rmap[60] == "U+E020"


# ---- edge case tests -------------------------------------------------------


def test_empty_input():
    """Empty durations and tokens produce an empty TimingResult."""
    result = durations_to_timing(
        durations=[],
        phoneme_tokens=[],
        sample_rate=22050,
    )

    assert result.phonemes == []
    assert result.total_duration_ms == 0.0
    assert result.sample_rate == 22050


def test_default_hop_length_constant():
    """DEFAULT_HOP_LENGTH is 256."""
    assert DEFAULT_HOP_LENGTH == 256


def test_single_phoneme():
    """A single phoneme produces correct timing with start=0."""
    result = durations_to_timing(
        durations=[25.0],
        phoneme_tokens=["s"],
        sample_rate=22050,
    )

    assert len(result.phonemes) == 1
    ph = result.phonemes[0]
    assert ph.start_ms == 0.0
    assert ph.duration_ms == pytest.approx(25 * FRAME_TIME_22050, abs=0.1)
    assert ph.end_ms == ph.duration_ms
    assert result.total_duration_ms == ph.end_ms


# --- SRT format tests ---

def test_srt_basic_format():
    """SRT output contains sequential numbering and --> separator."""
    from piper.timing import timing_to_srt

    result = durations_to_timing([5.0, 10.0, 15.0], ["a", "b", "c"], 22050)
    srt = timing_to_srt(result)

    assert "1\n" in srt
    assert "2\n" in srt
    assert "3\n" in srt
    assert " --> " in srt


def test_srt_timestamp_format():
    """SRT timestamps use HH:MM:SS,mmm format."""
    from piper.timing import timing_to_srt

    result = durations_to_timing([10.0], ["a"], 22050)
    srt = timing_to_srt(result)
    lines = srt.strip().split("\n")
    # Second line should contain the timestamp
    assert "," in lines[1]  # millisecond separator
    assert "-->" in lines[1]


def test_srt_blank_lines_between_entries():
    """SRT entries are separated by blank lines."""
    from piper.timing import timing_to_srt

    result = durations_to_timing([5.0, 10.0], ["a", "b"], 22050)
    srt = timing_to_srt(result)
    # Two entries = at least one double newline separator
    assert "\n\n" in srt


def test_srt_empty_input():
    """Empty input produces empty SRT string."""
    from piper.timing import timing_to_srt

    result = durations_to_timing([], [], 22050)
    srt = timing_to_srt(result)
    assert srt == ""


# --- Edge case tests ---

def test_very_large_duration():
    """1_000_000 frames should produce duration > 40 seconds."""
    result = durations_to_timing([1_000_000.0], ["long"], 22050)
    expected_ms = 1_000_000.0 * (256 / 22050) * 1000
    assert result.phonemes[0].duration_ms == pytest.approx(expected_ms, abs=1.0)
    assert result.total_duration_ms > 40_000


def test_very_small_sample_rate():
    """sr=100 Hz, hop=10 → 1 frame = 100 ms."""
    result = durations_to_timing([1.0], ["p"], 100, hop_length=10)
    assert result.phonemes[0].duration_ms == pytest.approx(100.0, abs=1e-6)
    assert result.total_duration_ms == pytest.approx(100.0, abs=1e-6)


def test_json_roundtrip_field_preservation():
    """JSON output preserves all fields correctly when re-parsed."""
    result = durations_to_timing([4.0, 8.0, 6.0], ["s", "t", "u"], 22050)
    json_str = timing_to_json(result)
    data = json.loads(json_str)

    assert data["sample_rate"] == 22050
    assert len(data["phonemes"]) == 3

    total_from_phonemes = sum(p["duration_ms"] for p in data["phonemes"])
    assert data["total_duration_ms"] == pytest.approx(total_from_phonemes, abs=0.001)

    names = [p["phoneme"] for p in data["phonemes"]]
    assert names == ["s", "t", "u"]


def test_tsv_numeric_values_parseable():
    """TSV data lines have parseable float values."""
    result = durations_to_timing([10.0, 20.0], ["a", "b"], 22050)
    tsv = timing_to_tsv(result)
    lines = tsv.strip().split("\n")

    for line in lines[1:]:
        cols = line.split("\t")
        assert len(cols) == 4
        start = float(cols[0])
        end = float(cols[1])
        dur = float(cols[2])
        assert start >= 0
        assert end >= start
        assert dur >= 0


# ---------------------------------------------------------------------------
# Multi-ID reverse map (first-wins semantics)
# ---------------------------------------------------------------------------


def test_build_reverse_map_multi_ids_first_wins():
    """When multiple IDs are assigned to the same phoneme, all map to the same name."""
    phoneme_id_map = {
        "a": [10, 11, 12],
        "k": [20],
    }
    rmap = build_phoneme_id_reverse_map(phoneme_id_map)

    assert rmap[10] == "a"
    assert rmap[11] == "a"
    assert rmap[12] == "a"
    assert rmap[20] == "k"


def test_build_reverse_map_conflicting_ids_first_wins():
    """When a single ID appears in multiple phonemes, the first occurrence wins.

    Python dict preserves insertion order; `build_phoneme_id_reverse_map`
    iterates in order and only assigns if the ID is not yet in the map.
    This matches the JS implementation in timing.js.
    """
    # "a" comes first, "b" comes second with the same ID 10.
    # The first occurrence ("a") wins.
    phoneme_id_map = {"a": [10], "b": [10]}
    rmap = build_phoneme_id_reverse_map(phoneme_id_map)
    assert rmap[10] == "a"


def test_build_reverse_map_empty_phoneme_id_map():
    """Empty phoneme_id_map produces an empty reverse map."""
    rmap = build_phoneme_id_reverse_map({})
    assert rmap == {}


def test_build_reverse_map_none_pua_mapping():
    """Passing None for pua_to_multi_char is equivalent to omitting it."""
    phoneme_id_map = {"a": [1], "\uE000": [2]}
    rmap_none = build_phoneme_id_reverse_map(phoneme_id_map, None)
    rmap_default = build_phoneme_id_reverse_map(phoneme_id_map)
    assert rmap_none == rmap_default


# ---------------------------------------------------------------------------
# TSV tab/newline escaping
# ---------------------------------------------------------------------------


def test_tsv_escapes_tab_in_phoneme_name():
    """Tabs in phoneme names are escaped to prevent TSV column corruption."""
    result = durations_to_timing([5.0], ["a\tb"], sample_rate=22050)
    tsv = timing_to_tsv(result)
    # Literal tab should be escaped to the two-character sequence \t
    assert "a\\tb" in tsv
    # The data row should have exactly 4 tab-separated columns
    data_line = tsv.strip().split("\n")[-1]
    cols = data_line.split("\t")
    assert len(cols) == 4


def test_tsv_escapes_newline_in_phoneme_name():
    """Newlines in phoneme names are escaped to keep one row per phoneme."""
    result = durations_to_timing([5.0], ["a\nb"], sample_rate=22050)
    tsv = timing_to_tsv(result)
    # Literal newline inside phoneme should be escaped
    assert "a\\nb" in tsv
    # We should still have exactly 2 non-empty lines (header + 1 data row)
    non_empty_lines = [l for l in tsv.split("\n") if l.strip()]
    assert len(non_empty_lines) == 2


# ---------------------------------------------------------------------------
# JSON roundtrip precision for extreme values
# ---------------------------------------------------------------------------


def test_json_roundtrip_precision_tiny_duration():
    """Very small duration values survive JSON roundtrip."""
    import json as json_mod

    result = durations_to_timing([0.001], ["x"], sample_rate=22050)
    parsed = json_mod.loads(timing_to_json(result))
    original_ms = result.phonemes[0].duration_ms
    parsed_ms = parsed["phonemes"][0]["duration_ms"]
    assert abs(parsed_ms - original_ms) < 1e-9


def test_json_roundtrip_precision_large_duration():
    """Very large duration values survive JSON roundtrip."""
    import json as json_mod

    result = durations_to_timing([1_000_000.0], ["x"], sample_rate=22050)
    parsed = json_mod.loads(timing_to_json(result))
    original_ms = result.phonemes[0].duration_ms
    parsed_ms = parsed["phonemes"][0]["duration_ms"]
    assert abs(parsed_ms - original_ms) < 1e-3  # Allow small relative error
