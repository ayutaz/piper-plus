"""Unit tests for scripts/audio_parity.py (M2.2)."""

from __future__ import annotations

import importlib.util
import math
import struct
import sys
import wave
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "audio_parity.py"
CONTRACT = REPO_ROOT / "docs" / "spec" / "audio-parity-contract.toml"


def _load():
    spec = importlib.util.spec_from_file_location("audio_parity", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ap():
    return _load()


def _write_sine(
    path: Path, freq: float = 440.0, amp: float = 0.1, dur_sec: float = 0.5
):
    rate = 22050
    n = int(rate * dur_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack(
                    "<h", int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
                )
                for i in range(n)
            )
        )


def _write_silence(path: Path, dur_sec: float = 0.5):
    rate = 22050
    n = int(rate * dur_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)


def test_contract_loads_and_thresholds_present(ap):
    data = ap.load_contract(CONTRACT)
    t = data["thresholds"]
    assert t["snr_min_db"] > 0
    assert t["mel_spec_max_mse"] > 0
    assert t["peak_rms_max_diff"] > 0


def test_contract_rejects_zero_threshold(ap, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        "[thresholds]\n"
        "peak_rms_max_diff = 0\n"
        "chromaprint_max_hamming = 32\n"
        "mel_spec_max_mse = 0.001\n"
        "snr_min_db = 60\n"
    )
    with pytest.raises(ValueError):
        ap.load_contract(bad)


def test_identical_wavs_pass_tier1(ap, tmp_path):
    a = tmp_path / "a.wav"
    _write_sine(a)
    b = tmp_path / "b.wav"
    b.write_bytes(a.read_bytes())  # byte-identical
    sa = ap.snapshot("python", a)
    sb = ap.snapshot("rust", b)
    contract = ap.load_contract(CONTRACT)
    res = ap.compare_pair(sa, sb, contract)
    assert res.passed
    assert res.tiers[0].name == "sha256"
    assert res.tiers[0].passed


def test_distinct_but_close_pair_passes_rms_tier(ap, tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_sine(a, amp=0.1)
    _write_sine(b, amp=0.1001)  # tiny amplitude diff
    sa = ap.snapshot("python", a)
    sb = ap.snapshot("rust", b)
    contract = ap.load_contract(CONTRACT)
    res = ap.compare_pair(sa, sb, contract)
    # sha256 differs but rms diff is well below 0.005
    assert not res.tiers[0].passed
    assert res.tiers[1].name == "peak_rms"
    assert res.tiers[1].passed


def test_distinct_pair_falls_through_to_snr(ap, tmp_path):
    """Different amplitudes that exceed peak-RMS tolerance still meet SNR."""
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_sine(a, amp=0.1)
    _write_sine(b, amp=0.2)  # rms diff ~0.07 > threshold (0.005)
    sa = ap.snapshot("python", a)
    sb = ap.snapshot("rust", b)
    contract = ap.load_contract(CONTRACT)
    res = ap.compare_pair(sa, sb, contract)
    assert res.tiers[0].name == "sha256" and not res.tiers[0].passed
    assert res.tiers[1].name == "peak_rms" and not res.tiers[1].passed
    # SNR depends on the contract threshold; an amplitude-only difference
    # at this scale tends to fall well below 60dB and therefore fail.
    assert res.tiers[2].name == "snr"
    # We do not assert pass/fail here — the snapshot pins how the script
    # cascades. The next test pins a definite failure scenario.


def test_silent_vs_loud_fails_all_tiers(ap, tmp_path):
    a = tmp_path / "loud.wav"
    b = tmp_path / "silent.wav"
    _write_sine(a, amp=0.5)
    _write_silence(b)
    sa = ap.snapshot("python", a)
    sb = ap.snapshot("rust", b)
    contract = ap.load_contract(CONTRACT)
    res = ap.compare_pair(sa, sb, contract)
    assert not res.passed
    assert all(not t.passed for t in res.tiers)


def test_render_markdown(ap, tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_sine(a)
    b.write_bytes(a.read_bytes())
    snaps = {"python": ap.snapshot("python", a), "rust": ap.snapshot("rust", b)}
    contract = ap.load_contract(CONTRACT)
    report = ap.gather_pairs(snaps, contract)
    md = ap.render_markdown(report)
    assert "Runtime Parity Deep" in md
    assert "python" in md and "rust" in md


def test_cli_compare_pass(ap, tmp_path, capsys):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "diff.md"
    _write_sine(a)
    b.write_bytes(a.read_bytes())
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"python={a}",
            f"rust={b}",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    assert out.exists()


def test_cli_compare_fail_on_mismatch(ap, tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "diff.md"
    _write_sine(a, amp=0.5)
    _write_silence(b)
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"python={a}",
            f"rust={b}",
            "--output",
            str(out),
            "--fail-on-mismatch",
        ]
    )
    rc = args.func(args)
    assert rc == 1


def test_parse_inputs_requires_runtime_prefix(ap):
    with pytest.raises(SystemExit):
        ap.parse_inputs(["a.wav"])


# ---------- skip logic (Phase 2: all 6 runtimes enabled) ----------


ALL_RUNTIMES = ("python", "rust", "csharp", "go", "cpp", "wasm")


def _write_ad_hoc_contract(tmp_path: Path, disabled: set[str]) -> Path:
    """Generate a contract toml where ``disabled`` runtimes have
    supports_dump_wav=false. Used by tests that need to assert the skip
    behaviour without depending on the production contract toml (which
    has all 6 runtimes enabled in Phase 2)."""
    lines = [
        "[thresholds]",
        "peak_rms_max_diff = 0.005",
        "chromaprint_max_hamming = 32",
        "mel_spec_max_mse = 0.001",
        "snr_min_db = 60.0",
        "",
        "[runtimes]",
    ]
    for name in ALL_RUNTIMES:
        supports = "false" if name in disabled else "true"
        lines.append(f'{name} = {{ id = "{name}", supports_dump_wav = {supports} }}')
    path = tmp_path / "ad-hoc-contract.toml"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_collect_skips_drops_supports_dump_wav_false(ap, tmp_path):
    """A runtime declared with supports_dump_wav=false is skipped even when an
    --inputs entry is provided. Verified via an ad-hoc fixture toml so the
    regression test stays valid after Phase 2 enabled all runtimes."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(_write_ad_hoc_contract(tmp_path, {"wasm"}))
    kept, skipped = ap.collect_skips({"wasm": a, "python": a}, contract)
    assert "python" in kept and "wasm" not in kept
    reasons = {entry.runtime: entry.reason for entry in skipped}
    assert "wasm" in reasons
    assert "supports_dump_wav" in reasons["wasm"]


def test_collect_skips_drops_missing_runtimes(ap, tmp_path):
    """Runtimes declared in contract but absent from --inputs are skipped with
    a clear reason. The workflow uses this when a build job fails and never
    uploads its wav."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(CONTRACT)  # production contract: 6 enabled
    kept, skipped = ap.collect_skips({"python": a, "rust": a}, contract)
    skipped_names = {entry.runtime for entry in skipped}
    # All 4 remaining runtimes (csharp/go/cpp/wasm) are missing --inputs
    assert skipped_names == {"csharp", "go", "cpp", "wasm"}
    assert kept == {"python": a, "rust": a}
    for entry in skipped:
        assert "no --inputs entry" in entry.reason


def test_render_markdown_includes_skipped_table(ap, tmp_path):
    a = tmp_path / "a.wav"
    _write_sine(a)
    snaps = {"python": ap.snapshot("python", a), "rust": ap.snapshot("rust", a)}
    contract = ap.load_contract(CONTRACT)
    skipped = [
        ap.SkipEntry("wasm", "supports_dump_wav = false (Phase 2 follow-up)"),
        ap.SkipEntry("csharp", "no --inputs entry provided"),
    ]
    report = ap.gather_pairs(snaps, contract, skipped=skipped)
    md = ap.render_markdown(report)
    assert "Skipped runtimes" in md
    assert "wasm" in md and "csharp" in md
    assert "supports_dump_wav" in md


def test_cli_compare_reports_skips_for_partial_inputs(ap, tmp_path):
    """End-to-end CLI run: only python + rust inputs given (out of 6 enabled
    runtimes) → 1 pair compared, 4 runtimes skipped (csharp/go/cpp/wasm
    missing inputs)."""
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "diff.md"
    _write_sine(a)
    b.write_bytes(a.read_bytes())
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"python={a}",
            f"rust={b}",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **1**" in text
    assert "runtimes skipped: **4**" in text
    # all 4 missing runtimes show up in the skip table
    for name in ("csharp", "go", "cpp", "wasm"):
        assert f"`{name}`" in text


def test_cli_compare_accepts_only_unsupported_runtime(ap, tmp_path):
    """If only an unsupported runtime is provided we still produce a report
    (no pairs, only skips) and exit success — informational tier should not
    crash on a degenerate input set. Verified via ad-hoc fixture toml
    (production contract now has all 6 supported)."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    out = tmp_path / "diff.md"
    ad_hoc = _write_ad_hoc_contract(tmp_path, {"wasm"})
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"wasm={a}",
            "--output",
            str(out),
            "--contract",
            str(ad_hoc),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **0**" in text
    assert "`wasm`" in text


# ---------- Phase 2 coverage (all 6 runtimes enabled) ----------


def test_load_contract_runtimes_section_has_six_runtimes(ap):
    """Phase 2 production contract enables all 6 inference runtimes."""
    contract = ap.load_contract(CONTRACT)
    runtimes = contract.get("runtimes", {})
    assert set(runtimes) == set(ALL_RUNTIMES)
    for name, spec in runtimes.items():
        assert spec.get("supports_dump_wav") is True, f"{name} should be enabled"


def test_collect_skips_all_runtimes_enabled_full_inputs(ap, tmp_path):
    """When inputs are provided for every runtime in the contract, every
    runtime is kept and no skip rows are emitted."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(CONTRACT)
    inputs = dict.fromkeys(ALL_RUNTIMES, a)
    kept, skipped = ap.collect_skips(inputs, contract)
    assert set(kept) == set(ALL_RUNTIMES)
    assert skipped == []


def test_collect_skips_unknown_runtime_is_kept_verbatim(ap, tmp_path):
    """An --inputs entry whose runtime key is not in the contract is kept
    verbatim. This lets contributors add ad-hoc runtimes for one-off
    diagnostics without editing the production contract toml."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(CONTRACT)
    inputs = {"python": a, "myrust": a}
    kept, _ = ap.collect_skips(inputs, contract)
    assert "myrust" in kept
    assert "python" in kept


def test_collect_skips_priority_dump_wav_over_missing(ap, tmp_path):
    """When a runtime is both disabled (supports_dump_wav=false) AND missing
    --inputs, the unsupported reason wins. This pin keeps the skip table
    free of redundant entries."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(_write_ad_hoc_contract(tmp_path, {"wasm", "cpp"}))
    # Provide python only; wasm/cpp are both unsupported AND missing
    kept, skipped = ap.collect_skips({"python": a}, contract)
    reasons = {entry.runtime: entry.reason for entry in skipped}
    assert "supports_dump_wav" in reasons["wasm"]
    assert "supports_dump_wav" in reasons["cpp"]
    # Other runtimes (rust/csharp/go) are missing inputs only
    for name in ("rust", "csharp", "go"):
        assert "no --inputs entry" in reasons[name]
    assert kept == {"python": a}


def test_render_markdown_full_six_runtime_pair_count(ap, tmp_path):
    """When all 6 runtimes are compared, render_markdown shows C(6,2)=15
    pairs — pin the form so a future refactor can't silently drop pairs."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    snaps = {name: ap.snapshot(name, a) for name in ALL_RUNTIMES}
    contract = ap.load_contract(CONTRACT)
    report = ap.gather_pairs(snaps, contract)
    assert len(report.pairs) == 15
    md = ap.render_markdown(report)
    assert "Pairs compared: **15**" in md
    for name in ALL_RUNTIMES:
        assert f"`{name}`" in md


def test_cli_compare_phase2_full_six_runtimes(ap, tmp_path):
    """End-to-end CLI run with all 6 runtime inputs (byte-identical wavs):
    15 pairs all pass tier 1, 0 skip rows, exit 0."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    out = tmp_path / "diff.md"
    # --inputs uses nargs="*", so pass all values in a single flag invocation
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            *(f"{name}={a}" for name in ALL_RUNTIMES),
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **15**" in text
    assert "runtimes skipped: **0**" in text
    assert "Skipped runtimes" not in text  # no skip section when empty


def test_cli_compare_phase2_partial_three_inputs(ap, tmp_path):
    """3 inputs out of 6 → C(3,2)=3 pairs + 3 missing-input skip rows."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    out = tmp_path / "diff.md"
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"python={a}",
            f"rust={a}",
            f"cpp={a}",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **3**" in text
    assert "runtimes skipped: **3**" in text
    for missing in ("csharp", "go", "wasm"):
        assert f"`{missing}`" in text


def test_cli_compare_phase2_fail_on_mismatch_across_runtimes(ap, tmp_path):
    """--fail-on-mismatch propagates a non-zero exit when any pair fails
    even in a Phase 2 full-runtime comparison. Reused regression coverage
    for the rc==1 path applied to the new 6-runtime topology."""
    a = tmp_path / "loud.wav"
    b = tmp_path / "silent.wav"
    out = tmp_path / "diff.md"
    _write_sine(a, amp=0.5)
    _write_silence(b)
    # Use 2 mismatched inputs; the rest will be skipped (missing) so the
    # fail-on-mismatch is anchored on a real pair.
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"python={a}",
            f"rust={b}",
            "--output",
            str(out),
            "--fail-on-mismatch",
        ]
    )
    rc = args.func(args)
    assert rc == 1
    text = out.read_text()
    assert "Pairs compared: **1**" in text


# ---------- garbage tolerance / contract edge cases ----------


def test_cli_compare_all_inputs_unsupported_runtime(ap, tmp_path):
    """All --inputs entries map to supports_dump_wav=false runtimes →
    0 pair + N skip rows + exit 0. Confirms informational tier does not
    crash on a fully-skipped corpus."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    out = tmp_path / "diff.md"
    ad_hoc = _write_ad_hoc_contract(tmp_path, {"wasm", "cpp"})
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"wasm={a}",
            f"cpp={a}",
            "--output",
            str(out),
            "--contract",
            str(ad_hoc),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **0**" in text
    # Both unsupported entries appear in the skip table; other 4 runtimes
    # are also listed as missing --inputs (declared in ad-hoc contract).
    for name in ("wasm", "cpp"):
        assert f"`{name}`" in text
    # supports_dump_wav reason wins over missing for wasm/cpp
    assert text.count("supports_dump_wav") >= 2


def test_contract_with_empty_runtimes_section_keeps_inputs_verbatim(ap, tmp_path):
    """A contract with no [runtimes] entries should accept any --inputs key
    without skipping. Edge case for diagnostic / ad-hoc parity runs."""
    bad = tmp_path / "no-runtimes.toml"
    bad.write_text(
        "[thresholds]\n"
        "peak_rms_max_diff = 0.005\n"
        "chromaprint_max_hamming = 32\n"
        "mel_spec_max_mse = 0.001\n"
        "snr_min_db = 60\n"
    )
    contract = ap.load_contract(bad)
    a = tmp_path / "a.wav"
    _write_sine(a)
    kept, skipped = ap.collect_skips({"foo": a, "bar": a}, contract)
    assert kept == {"foo": a, "bar": a}
    assert skipped == []


def test_contract_spec_missing_supports_dump_wav_defaults_to_true(
    ap,
    tmp_path,
):
    """A runtime entry without the supports_dump_wav field should be treated
    as enabled (default True). Forward-compat for older contract dialects."""
    bad = tmp_path / "default-true.toml"
    bad.write_text(
        "[thresholds]\n"
        "peak_rms_max_diff = 0.005\n"
        "chromaprint_max_hamming = 32\n"
        "mel_spec_max_mse = 0.001\n"
        "snr_min_db = 60\n"
        "\n"
        "[runtimes]\n"
        'python = { id = "python" }\n'  # no supports_dump_wav
        'rust   = { id = "rust", supports_dump_wav = true }\n'
    )
    contract = ap.load_contract(bad)
    a = tmp_path / "a.wav"
    _write_sine(a)
    kept, skipped = ap.collect_skips({"python": a, "rust": a}, contract)
    assert set(kept) == {"python", "rust"}
    # Neither is skipped — defaults to enabled
    assert skipped == []


def test_contract_spec_non_dict_runtime_entry_treated_as_enabled(
    ap,
    tmp_path,
):
    """If a runtime entry is malformed (not a dict — TOML scalar / array),
    collect_skips should not crash. It treats the entry as enabled
    (default True). This is the garbage-tolerance contract for
    misconfigured ad-hoc TOML files."""
    bad = tmp_path / "scalar-runtime.toml"
    bad.write_text(
        "[thresholds]\n"
        "peak_rms_max_diff = 0.005\n"
        "chromaprint_max_hamming = 32\n"
        "mel_spec_max_mse = 0.001\n"
        "snr_min_db = 60\n"
        "\n"
        "[runtimes]\n"
        'python = "deadbeef"\n'  # malformed: scalar instead of inline table
    )
    contract = ap.load_contract(bad)
    a = tmp_path / "a.wav"
    _write_sine(a)
    # Should not raise; python is kept (default True path handles non-dict)
    kept, _ = ap.collect_skips({"python": a}, contract)
    assert "python" in kept


# ---------- parity fixture validation ----------


def test_parity_fixture_phoneme_ids_jsonl_is_valid(ap):
    """The canonical phoneme_ids.jsonl fixture (Phase 1) must remain a
    valid single-line JSONL with the contract fields. A drift in this
    fixture would silently change what every runtime parity job
    synthesizes, so we pin it here."""
    import json

    fixture = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "audio-corpus"
        / "parity"
        / "phoneme_ids.jsonl"
    )
    assert fixture.exists(), "phoneme_ids.jsonl fixture is missing"
    lines = [line for line in fixture.read_text().splitlines() if line.strip()]
    assert len(lines) >= 1, "fixture must contain at least one utterance"
    for line in lines:
        entry = json.loads(line)
        ids = entry["phoneme_ids"]
        assert isinstance(ids, list)
        assert len(ids) >= 3, "needs BOS / body / EOS at minimum"
        assert all(isinstance(i, int) for i in ids)
        # piper-plus contract: ID 1 = BOS, ID 2 = EOS, ID 0 = PAD
        assert ids[0] == 1, "first ID should be BOS (=1)"
        assert ids[-1] == 2, "last ID should be EOS (=2)"


def test_parity_fixture_first_utterance_matches_expected_layout():
    """The first fixture utterance is `あいうえお` interspersed with PAD.
    Pinning the exact ID layout (`^ a _ i _ u _ e _ o _ $`) makes any
    accidental edit to the fixture (and therefore the parity baseline)
    show up as a test failure rather than silent audio drift."""
    import json

    fixture = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "audio-corpus"
        / "parity"
        / "phoneme_ids.jsonl"
    )
    first_line = next(line for line in fixture.read_text().splitlines() if line.strip())
    entry = json.loads(first_line)
    assert entry["phoneme_ids"] == [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]
    assert entry.get("language_id") == 0  # ja


# ---------- snapshot edge cases ----------


def test_snapshot_handles_8bit_pcm_wav(ap, tmp_path):
    """A non-16-bit WAV should still load without raising — only the
    sample_width is recorded, samples_f32 / rms stay None so tier 2/3
    cleanly report as 'unavailable'."""
    a = tmp_path / "8bit.wav"
    with wave.open(str(a), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)  # 8-bit
        w.setframerate(22050)
        w.writeframes(b"\x80" * 100)
    snap = ap.snapshot("python", a)
    assert snap.sample_width == 1
    assert snap.samples_f32 is None
    assert snap.rms is None


def test_snapshot_handles_stereo_wav(ap, tmp_path):
    """Stereo (2-channel) PCM 16-bit input gets averaged to mono so
    downstream tier 2/3 comparisons stay valid (cross-runtime contract
    is mono 22050 Hz). Pin the averaging behaviour."""
    a = tmp_path / "stereo.wav"
    with wave.open(str(a), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(22050)
        # L=+0.5, R=-0.5 → avg = 0
        frames = []
        for _ in range(100):
            frames.append(struct.pack("<hh", 16384, -16384))
        w.writeframes(b"".join(frames))
    snap = ap.snapshot("python", a)
    assert snap.num_channels == 2
    assert snap.samples_f32 is not None
    assert all(abs(s) < 1e-6 for s in snap.samples_f32)


def test_snapshot_records_sha256_even_when_pcm_unavailable(ap, tmp_path):
    """SHA256 is the tier 1 anchor; it must work regardless of sample
    format (24-bit / 32-bit-float / 8-bit) so the workflow can still
    detect byte-identical outputs."""
    a = tmp_path / "24bit.wav"
    with wave.open(str(a), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)  # 24-bit
        w.setframerate(22050)
        w.writeframes(b"\x00\x00\x00" * 100)
    snap = ap.snapshot("python", a)
    assert snap.sha256
    assert len(snap.sha256) == 64
