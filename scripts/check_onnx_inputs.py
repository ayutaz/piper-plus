#!/usr/bin/env python3
"""Validate the input graph of a Piper-Plus ONNX model before distribution.

This is the gate that would have prevented Issue #385 — the v1.12.0
tsukuyomi 6lang model was accidentally exported in voice-cloning mode
(`speaker_embedding` + `speaker_embedding_mask` listed as required inputs),
so Python CLI inference rejects it with::

    ValueError: Required inputs (['speaker_embedding', 'speaker_embedding_mask'])
    are missing from input feed (...).

Pipeline runtimes (Python `voice.py`, Rust, Go, ...) do not feed those
tensors. Any model that requires them is unusable through normal CLI flow.

Usage
-----
    # Validate a single .onnx
    python scripts/check_onnx_inputs.py path/to/model.onnx

    # Allow voice-cloning models explicitly (e.g. Reference-Audio releases)
    python scripts/check_onnx_inputs.py --allow-voice-cloning path/to/model.onnx

    # Strict mode: require an exact input set
    python scripts/check_onnx_inputs.py --strict --expected input,input_lengths,scales,lid,prosody_features model.onnx

Exit codes
----------
    0 — model is fine for distribution
    1 — model has unexpected input set (e.g. voice-cloning leaked in)
    2 — bad invocation / file not found
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# The set of inputs that mainline CLI runtimes *can* feed today. Anything
# outside this set means the model needs a special caller (and is therefore
# not safe to drop into a generic distribution slot).
KNOWN_OPTIONAL_INPUTS = {
    "input",
    "input_lengths",
    "scales",
    "sid",  # multispeaker
    "lid",  # multilingual
    "prosody_features",  # OpenJTalk A1/A2/A3 features
}

# Inputs that mark voice-cloning-mode export. CLI runtimes cannot feed
# these; a normal-distribution model must NOT list them as required.
VOICE_CLONING_INPUTS = {
    "speaker_embedding",
    "speaker_embedding_mask",
}


def get_input_names(onnx_path: Path) -> list[str]:
    """Return the model's required input names (in graph order)."""
    try:
        import onnxruntime as ort
    except ImportError as e:
        raise RuntimeError(
            "onnxruntime is required. Install with `uv pip install onnxruntime`."
        ) from e

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return [inp.name for inp in session.get_inputs()]


def check(
    onnx_path: Path,
    *,
    allow_voice_cloning: bool,
    strict_expected: set[str] | None,
) -> tuple[bool, str]:
    """Return (ok, message)."""
    inputs = get_input_names(onnx_path)
    inputs_set = set(inputs)

    if strict_expected is not None:
        if inputs_set != strict_expected:
            extra = inputs_set - strict_expected
            missing = strict_expected - inputs_set
            return False, (
                f"Strict mismatch. Got: {sorted(inputs)}. "
                f"Expected: {sorted(strict_expected)}. "
                f"Extra: {sorted(extra)}. Missing: {sorted(missing)}."
            )
        return True, f"OK (strict): {sorted(inputs)}"

    leaked_vc = inputs_set & VOICE_CLONING_INPUTS
    if leaked_vc and not allow_voice_cloning:
        return False, (
            f"Voice-cloning input(s) leaked into a distribution model: "
            f"{sorted(leaked_vc)}. CLI runtimes cannot feed these and will "
            f"fail with `Required inputs (...) are missing from input feed`. "
            f"Re-export the model without --speaker-embedding / --reference-audio "
            f"flags, or pass --allow-voice-cloning if this model is intentionally "
            f"voice-cloning-only. (Issue #385 / docs/spec/pua-contract.toml)"
        )

    unknown = inputs_set - KNOWN_OPTIONAL_INPUTS - VOICE_CLONING_INPUTS
    if unknown:
        return False, (
            f"Unknown input name(s): {sorted(unknown)}. "
            f"Known: {sorted(KNOWN_OPTIONAL_INPUTS | VOICE_CLONING_INPUTS)}. "
            f"Update KNOWN_OPTIONAL_INPUTS in scripts/check_onnx_inputs.py "
            f"if the export now legitimately produces this input."
        )

    return True, f"OK: {sorted(inputs)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "onnx_paths",
        nargs="+",
        type=Path,
        help="Path(s) to ONNX model file(s) to validate",
    )
    parser.add_argument(
        "--allow-voice-cloning",
        action="store_true",
        help="Permit speaker_embedding/speaker_embedding_mask as required inputs. "
        "Use only for intentional voice-cloning-only releases.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require the input set to exactly match --expected (no extras, no missing).",
    )
    parser.add_argument(
        "--expected",
        type=lambda s: {x.strip() for x in s.split(",") if x.strip()},
        default=None,
        help="Comma-separated expected input names (used with --strict). "
        "Example: input,input_lengths,scales,lid,prosody_features",
    )
    args = parser.parse_args()

    if args.strict and args.expected is None:
        parser.error("--strict requires --expected")

    any_failed = False
    for path in args.onnx_paths:
        if not path.exists():
            print(f"ERROR: {path} does not exist", file=sys.stderr)
            return 2
        try:
            ok, msg = check(
                path,
                allow_voice_cloning=args.allow_voice_cloning,
                strict_expected=args.expected if args.strict else None,
            )
        except RuntimeError as e:
            print(f"ERROR: {path}: {e}", file=sys.stderr)
            return 2
        prefix = "OK  " if ok else "FAIL"
        print(f"{prefix}  {path}: {msg}")
        if not ok:
            any_failed = True

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
