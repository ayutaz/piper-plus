#!/usr/bin/env python3
"""Drift check between docs/spec/short-text-contract.toml and Python canonical.

The contract toml lists canonical constants (min_phoneme_ids,
min_body_for_strategy_a, short_text_chars, silence_pad_ms, threshold_rms,
noise_scale_min_ratio, noise_w_min_ratio) that all 7 runtimes must agree on.
This script verifies the Python canonical implementations match the contract.

Two source files are checked:
  - src/python_run/piper_plus/voice.py (runtime — Strategy A/B/C)
  - src/python/piper_train/infer_onnx.py (training — Strategy A/B)

Usage:
    python scripts/check_short_text_contract.py            # CI mode
    python scripts/check_short_text_contract.py --verbose  # show all values
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/short-text-contract.toml"
VOICE_PATH = REPO_ROOT / "src/python_run/piper_plus/voice.py"
INFER_ONNX_PATH = REPO_ROOT / "src/python/piper_train/infer_onnx.py"


def _read_constant(path: Path, name: str) -> str | None:
    """Extract a top-level module constant by name via regex (no import).

    Returns the literal as a string, or None if not found. Importing
    voice.py / infer_onnx.py at check-time pulls heavy dependencies
    (torch, onnxruntime), so we read the source directly.
    """
    text = path.read_text(encoding="utf-8")
    m = re.search(
        rf"^{re.escape(name)}\s*[:=][^=].*?=\s*([^\s#]+)",
        text,
        flags=re.MULTILINE,
    )
    if m is None:
        m = re.search(rf"^{re.escape(name)}\s*=\s*([^\s#]+)", text, flags=re.MULTILINE)
    return m.group(1).rstrip(",") if m else None


def _coerce(literal: str | None) -> int | float | None:
    if literal is None:
        return None
    try:
        return int(literal)
    except ValueError:
        try:
            return float(literal)
        except ValueError:
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true", help="Print all checked values")
    args = parser.parse_args()

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    expectations: list[tuple[str, str, str, object]] = [
        # (label, source path, constant name, expected value)
        ("voice.py MIN_PHONEME_IDS", VOICE_PATH, "MIN_PHONEME_IDS", contract["padding"]["min_phoneme_ids"]),
        ("voice.py MIN_BODY_FOR_STRATEGY_A", VOICE_PATH, "MIN_BODY_FOR_STRATEGY_A", contract["padding"]["min_body_for_strategy_a"]),
        ("voice.py SHORT_TEXT_CHARS", VOICE_PATH, "SHORT_TEXT_CHARS", contract["ssml_injection"]["short_text_chars"]),
        ("voice.py SILENCE_PAD_MS", VOICE_PATH, "SILENCE_PAD_MS", contract["ssml_injection"]["silence_pad_ms"]),
        ("voice.py TRIM_THRESHOLD_RMS", VOICE_PATH, "TRIM_THRESHOLD_RMS", contract["trim"]["threshold_rms"]),
        ("voice.py NOISE_SCALE_MIN_RATIO", VOICE_PATH, "NOISE_SCALE_MIN_RATIO", contract["scales"]["noise_scale_min_ratio"]),
        ("voice.py NOISE_W_MIN_RATIO", VOICE_PATH, "NOISE_W_MIN_RATIO", contract["scales"]["noise_w_min_ratio"]),
        ("infer_onnx.py MIN_PHONEME_IDS", INFER_ONNX_PATH, "MIN_PHONEME_IDS", contract["padding"]["min_phoneme_ids"]),
        ("infer_onnx.py MIN_BODY_FOR_STRATEGY_A", INFER_ONNX_PATH, "MIN_BODY_FOR_STRATEGY_A", contract["padding"]["min_body_for_strategy_a"]),
        ("infer_onnx.py TRIM_THRESHOLD_RMS", INFER_ONNX_PATH, "TRIM_THRESHOLD_RMS", contract["trim"]["threshold_rms"]),
        ("infer_onnx.py NOISE_SCALE_MIN_RATIO", INFER_ONNX_PATH, "NOISE_SCALE_MIN_RATIO", contract["scales"]["noise_scale_min_ratio"]),
        ("infer_onnx.py NOISE_W_MIN_RATIO", INFER_ONNX_PATH, "NOISE_W_MIN_RATIO", contract["scales"]["noise_w_min_ratio"]),
    ]

    errors: list[str] = []

    # Strategy C must be applied to the AUDIO, not by handing SSML text to a
    # phonemizer.
    #
    # `[ssml_injection].silence_pad_ms` is defined as silence "prepended and
    # appended to short text audio". The Rust synthesis path instead called
    # `wrap_short_text_ssml(text)` and passed the resulting string to
    # `phonemize_with_prosody`, which does not parse SSML -- so `<speak>`,
    # `<break` and `time=` were phonemised and SPOKEN (issue #694, visible in
    # `--timing json` as `s p ˈ i ː k` / `b ɹ ˈ e ɪ k` / `t ˈ a ɪ m`). The
    # text wrapper stays available for pipelines that do parse SSML, which is
    # why its mere existence cannot be the check; what matters is that the
    # synthesis path does not use it.
    rust_voice = REPO_ROOT / "src/rust/piper-core/src/voice.rs"
    if not rust_voice.is_file():
        errors.append(f"  rust voice.rs not found at {rust_voice}")
    else:
        source = rust_voice.read_text(encoding="utf-8", errors="replace")
        code = re.sub(r"//[^\n]*", "", source)
        if "wrap_short_text_ssml(" in code:
            errors.append(
                "  rust voice.rs: synthesis path calls wrap_short_text_ssml(); "
                "Strategy C must pad the AUDIO (pad_silence_for_short_text) -- "
                "passing the SSML string to the phonemizer makes the markup "
                "audible (issue #694)"
            )
        if "pad_silence_for_short_text(" not in code:
            errors.append(
                "  rust voice.rs: synthesis path does not call "
                "pad_silence_for_short_text(); short-text silence padding is "
                "not being applied at all"
            )

    for label, path, name, expected in expectations:
        literal = _read_constant(path, name)
        actual = _coerce(literal)
        if actual is None:
            errors.append(f"  {label}: not found in {path.relative_to(REPO_ROOT)}")
        elif actual != expected:
            errors.append(
                f"  {label}: source={actual!r} (raw={literal!r}) != contract={expected!r}"
            )
        elif args.verbose:
            print(f"  OK {label} = {actual!r}")

    if errors:
        print("ERROR: short-text contract drift detected:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            f"Update {CONTRACT_PATH.relative_to(REPO_ROOT)} or the Python source so they agree.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: short-text contract ({CONTRACT_PATH.relative_to(REPO_ROOT)}) matches "
        "Python canonical implementations (voice.py, infer_onnx.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
