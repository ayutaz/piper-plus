#!/usr/bin/env python3
"""Validate the input graph of a Piper-Plus ONNX model before distribution.

History
-------
- Issue #385 (v1.12.0 era): the tsukuyomi 6lang model was accidentally
    exported in voice-cloning mode and CLI runtimes did not yet know how
    to feed `speaker_embedding` / `speaker_embedding_mask`, so the model
    failed with `Required inputs missing`. The gate originally rejected
    those inputs outright.
- PR #320 / Issue #426: MB-iSTFT-VITS2 + Voice Cloning support makes
    `speaker_embedding` / `speaker_embedding_mask` *always-declared*
    inputs. Mainline CLI runtimes (`src/python_run/piper/voice.py`,
    `docker/python-inference/inference.py`, Rust, Go, C#) now feed zero
    embedding + mask=0 so the model falls back to `emb_g(sid)`
    (`src/python/piper_train/vits/models.py`). The two tensors are
    therefore normal optional inputs, not leakage.

Usage
-----
    # Validate a single .onnx
    python scripts/check_onnx_inputs.py path/to/model.onnx

    # Strict mode: require an exact input set (e.g. CI gate per release)
    python scripts/check_onnx_inputs.py --strict \
        --expected input,input_lengths,scales,lid,prosody_features,speaker_embedding,speaker_embedding_mask \
        model.onnx

Exit codes
----------
    0 — model is fine for distribution
    1 — model has unexpected / unknown input(s)
    2 — bad invocation / file not found
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# The set of inputs that mainline CLI runtimes know how to feed today.
# Anything outside this set means the model needs a special caller (and
# is therefore not safe to drop into a generic distribution slot).
# speaker_embedding / speaker_embedding_mask are listed here because PR #320
# made them always-declared by `export_onnx.py:505-515`; runtimes feed
# zero+mask=0 to route through emb_g(sid).
KNOWN_OPTIONAL_INPUTS = {
    "input",
    "input_lengths",
    "scales",
    "sid",  # multispeaker
    "lid",  # multilingual
    "prosody_features",  # OpenJTalk A1/A2/A3 features
    "speaker_embedding",  # PR #320 — zero+mask=0 fallback via emb_g(sid)
    "speaker_embedding_mask",
}

# Retained for the deprecated --allow-voice-cloning flag so existing CI
# invocations keep working. The flag is now a no-op (kept as a name only).
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
    """Return (ok, message).

    Output messages preserve graph order for the actual input list (so the
    user can correlate output with what export_onnx.py produced). Set-diff
    fields (extra/missing) are sorted because set ordering is undefined.
    """
    inputs = get_input_names(onnx_path)
    inputs_set = set(inputs)

    if strict_expected is not None:
        if inputs_set != strict_expected:
            extra = inputs_set - strict_expected
            missing = strict_expected - inputs_set
            return False, (
                f"Strict mismatch. Got: {inputs}. "
                f"Expected: {sorted(strict_expected)}. "
                f"Extra: {sorted(extra)}. Missing: {sorted(missing)}."
            )
        return True, f"OK (strict): {inputs}"

    # `allow_voice_cloning` is preserved for backward compatibility with CI
    # scripts that still pass --allow-voice-cloning; after PR #320 the flag
    # is a no-op because speaker_embedding / speaker_embedding_mask are
    # ordinary optional inputs.
    del allow_voice_cloning

    unknown = inputs_set - KNOWN_OPTIONAL_INPUTS
    if unknown:
        return False, (
            f"Unknown input name(s): {sorted(unknown)}. "
            f"Known: {sorted(KNOWN_OPTIONAL_INPUTS)}. "
            f"Update KNOWN_OPTIONAL_INPUTS in scripts/check_onnx_inputs.py "
            f"if the export now legitimately produces this input."
        )

    return True, f"OK: {inputs}"


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
        help="Deprecated since PR #320: speaker_embedding / speaker_embedding_mask "
        "are now ordinary optional inputs that mainline runtimes feed as "
        "zero+mask=0. Kept as a no-op for CI backward compatibility.",
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
        except Exception as e:
            # InferenceSession can raise onnxruntime.capi exceptions for
            # corrupt/incompatible ONNX, plus IOError, ValueError, etc.
            # Treat any unexpected exception as a hard failure (Copilot review
            # on PR #395) — don't let it leak as a Python traceback to CI.
            print(f"ERROR: {path}: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        prefix = "OK  " if ok else "FAIL"
        print(f"{prefix}  {path}: {msg}")
        if not ok:
            any_failed = True

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
