#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses aligned-table 2-space indent)
"""Inference-input contract verifier.

`docs/spec/inference-input-contract.toml` declares numeric constants and
error-prefix conventions that the canonical Python runtime is expected to
match. Without a CI gate, the contract drifts silently — a developer can
change ``MAX_TEXT_BYTES`` to 2 MiB without anyone touching the toml.

This script verifies the small set of constants that are *unambiguously*
locked between contract and implementation:

  toml [text].http_max_bytes              == python http_server.MAX_TEXT_BYTES
  toml [scales].default_noise_scale       == infer_onnx --noise-scale default
  toml [scales].default_length_scale      == infer_onnx --length-scale default
  toml [scales].default_noise_w           == infer_onnx --noise-scale-w default
  toml [speaker_embedding].emb_dim        == ecapa_tdnn ECAPA_TDNN(emb_dim=...)

Out of scope (informational only, not gated):
  - per-runtime error-prefix conformance (toml's `implementation_status`
    already says most runtimes pass-through to ORT; gating would block
    merges on a not-yet-implemented contract).
  - phoneme_ids range / scales range — runtimes do not currently validate
    these (per toml `implementation_status`).

Usage:
    python scripts/check_inference_input_contract.py

Exit codes:
    0 -- contract matches the canonical Python implementation
    1 -- drift detected
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/inference-input-contract.toml"

HTTP_SERVER = REPO_ROOT / "src/python_run/piper/http_server.py"
INFER_ONNX = REPO_ROOT / "src/python/piper_train/infer_onnx.py"
ECAPA = REPO_ROOT / "src/python/piper_train/speaker_encoder/ecapa_tdnn.py"


def _eval_simple_int(expr: str) -> int | None:
    """Evaluate a literal-only integer expression like '1 * 1024 * 1024'.

    The whitelist below permits digits, whitespace, ``+ - * / ( )`` only,
    but two consecutive ``*`` reads as the Python power operator — which
    a hostile PR could weaponise (``10**10000000`` exhausts memory on
    the CI runner). Reject any ``**`` substring explicitly so the
    operator is never reachable.
    """
    if not re.match(r"^[\d\s*+\-/()]+$", expr):
        return None
    if "**" in expr:
        return None
    try:
        return int(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 — sandboxed
    except Exception:
        # Non-numeric RHS (e.g. a string literal slipped through the
        # whitelist via parens) — caller treats this as "no constant
        # found" and reports a contract miss.
        return None


def grep_constant(path: Path, name_pattern: str) -> str | None:
    """Find ``NAME = <expr>`` and return the evaluated RHS as a string."""
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^\s*{name_pattern}\s*=\s*([^#]+?)\s*(?:#.*)?$", line)
        if not m:
            continue
        rhs = m.group(1).strip().rstrip(",").strip()
        if rhs.startswith(("'", '"')):
            return rhs.strip("'\"")
        ival = _eval_simple_int(rhs)
        if ival is not None:
            return str(ival)
        try:
            return str(float(rhs))
        except ValueError:
            return rhs
    return None


def grep_argparse_default(path: Path, flag: str) -> str | None:
    """For ``parser.add_argument('--foo', ..., default=X)``, return ``X``."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    pat = (
        rf'parser\.add_argument\(\s*"{re.escape(flag)}"[^)]*?'
        r"default\s*=\s*([^,)\s]+)"
    )
    m = re.search(pat, text)
    return m.group(1).strip() if m else None


def main(argv: list[str] | None = None) -> int:
    if not CONTRACT.exists():
        print(f"ERROR: contract missing: {CONTRACT}", file=sys.stderr)
        return 1

    with CONTRACT.open("rb") as f:
        spec = tomllib.load(f)

    expectations: list[tuple[str, str, str, str]] = []
    # (label, expected, actual, source-of-actual)

    expectations.append(
        (
            "http_max_bytes",
            str(spec["text"]["http_max_bytes"]),
            grep_constant(HTTP_SERVER, "MAX_TEXT_BYTES") or "<not found>",
            "http_server.py:MAX_TEXT_BYTES",
        )
    )

    for toml_key, cli_flag, label in [
        ("default_noise_scale", "--noise-scale", "default_noise_scale"),
        ("default_length_scale", "--length-scale", "default_length_scale"),
        ("default_noise_w", "--noise-scale-w", "default_noise_w"),
    ]:
        toml_val = str(float(spec["scales"][toml_key]))
        cli_val = grep_argparse_default(INFER_ONNX, cli_flag)
        actual = str(float(cli_val)) if cli_val else "<not found>"
        expectations.append(
            (label, toml_val, actual, f"infer_onnx.py:{cli_flag} default")
        )

    # PR #222 (Zero-Shot TTS): emb_dim is split by export mode.
    # legacy_ecapa_tdnn=256 (ECAPA-TDNN), zero_shot_cam_plus=192 (CAM++).
    # Validate the legacy ECAPA dim against ecapa_tdnn.py (CAM++ uses a
    # different file and is validated by speaker-encoder-contract checks).
    spk_emb_spec = spec["speaker_embedding"]
    if "export_modes" in spk_emb_spec:
        # New split-by-export-mode schema
        legacy_dim = str(
            spk_emb_spec["export_modes"]["legacy_ecapa_tdnn"]["emb_dim"]
        )
        expectations.append(
            (
                "speaker_embedding.export_modes.legacy_ecapa_tdnn.emb_dim",
                legacy_dim,
                grep_constant(ECAPA, "emb_dim: int") or "<not found>",
                "ecapa_tdnn.py:ECAPA_TDNN(emb_dim=...)",
            )
        )
    else:
        # Legacy flat schema (pre-PR-#222)
        expectations.append(
            (
                "speaker_embedding.emb_dim",
                str(spk_emb_spec["emb_dim"]),
                grep_constant(ECAPA, "emb_dim: int") or "<not found>",
                "ecapa_tdnn.py:ECAPA_TDNN(emb_dim=...)",
            )
        )

    failed: list[tuple[str, str, str, str]] = []
    print(f"Contract: {CONTRACT.relative_to(REPO_ROOT)}")
    print()
    for label, expected, actual, source in expectations:
        if expected == actual:
            print(f"  OK   {label}: {expected}  ({source})")
        else:
            print(
                f"  FAIL {label}: contract={expected} != actual={actual}  ({source})",
                file=sys.stderr,
            )
            failed.append((label, expected, actual, source))

    if failed:
        print(
            f"\n{len(failed)} contract drift(s) detected. "
            f"Update the spec or the implementation, not both.",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nOK contract matches canonical Python implementation "
        f"({len(expectations)} checks)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
