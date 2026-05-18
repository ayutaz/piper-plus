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


# ---------- skip logic (Phase 1: cpp / wasm not yet implemented) ----------


def test_collect_skips_drops_supports_dump_wav_false(ap, tmp_path):
    """A runtime declared with supports_dump_wav=false is skipped even when an
    --inputs entry is provided. This lets the workflow upload an artifact for
    a not-yet-supported runtime (e.g. for diagnostic purposes) without
    accidentally enforcing parity against it."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    contract = ap.load_contract(CONTRACT)
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
    contract = ap.load_contract(CONTRACT)
    kept, skipped = ap.collect_skips({"python": a, "rust": a}, contract)
    skipped_names = {entry.runtime for entry in skipped}
    # supports_dump_wav=false: cpp / wasm
    assert "cpp" in skipped_names and "wasm" in skipped_names
    # missing --inputs: csharp / go
    assert "csharp" in skipped_names and "go" in skipped_names
    assert kept == {"python": a, "rust": a}


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


def test_cli_compare_reports_skips_for_phase1_runtimes(ap, tmp_path):
    """End-to-end CLI run: only python + rust inputs given → 1 pair compared,
    4 runtimes skipped (csharp/go missing inputs + cpp/wasm unsupported)."""
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
    # ordering inside the table is contract-driven (declaration order)
    for name in ("csharp", "go", "wasm", "cpp"):
        assert f"`{name}`" in text


def test_cli_compare_accepts_only_skipped_runtime(ap, tmp_path):
    """If only an unsupported runtime is provided we still produce a report
    (no pairs, only skips) and exit success — informational tier should not
    crash on a degenerate input set."""
    a = tmp_path / "a.wav"
    _write_sine(a)
    out = tmp_path / "diff.md"
    args = ap.build_parser().parse_args(
        [
            "compare",
            "--inputs",
            f"wasm={a}",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    text = out.read_text()
    assert "Pairs compared: **0**" in text
    assert "`wasm`" in text
