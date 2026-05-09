#!/usr/bin/env python3
"""Drift check between docs/spec/ort-session-contract.toml and Python canonical.

The contract toml lists canonical ORT session/warmup/cache/env_vars constants
that all 4 runtimes (Python / Rust / Go / C#) must agree on. This script
verifies the Python canonical implementation in
``src/python/piper_train/ort_utils.py`` matches the contract.

(Per-runtime drift detection for Rust/Go/C# happens in their own test suites
via the ``tests/fixtures/ort_session/contract.json`` fixture.)

Usage:
    python scripts/check_ort_session_contract.py            # CI mode
    python scripts/check_ort_session_contract.py --verbose  # show all values
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/ort-session-contract.toml"
ORT_UTILS_PATH = REPO_ROOT / "src/python/piper_train/ort_utils.py"


def _read_constant(path: Path, name: str) -> str | None:
    """Extract a top-level module constant by name via regex (no import).

    Importing ort_utils.py at check-time pulls onnxruntime + numpy, so we
    read the source directly.
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


def _coerce(literal: str | None) -> int | float | str | None:
    if literal is None:
        return None
    if literal.startswith('"') and literal.endswith('"'):
        return literal[1:-1]
    try:
        return int(literal)
    except ValueError:
        try:
            return float(literal)
        except ValueError:
            return literal


def _has_substring(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true", help="Print all checked values")
    args = parser.parse_args()

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    expectations: list[tuple[str, str, object]] = [
        # (label, ort_utils.py constant name, expected value)
        ("MAX_INTRA_THREADS", "MAX_INTRA_THREADS", contract["session"]["max_intra_threads"]),
        ("WARMUP_PHONEME_LENGTH", "WARMUP_PHONEME_LENGTH", contract["warmup"]["phoneme_length"]),
        ("DEFAULT_WARMUP_RUNS", "DEFAULT_WARMUP_RUNS", contract["warmup"]["default_runs"]),
    ]

    errors: list[str] = []
    for label, name, expected in expectations:
        literal = _read_constant(ORT_UTILS_PATH, name)
        actual = _coerce(literal)
        if actual is None:
            errors.append(f"  {label}: not found in {ORT_UTILS_PATH.relative_to(REPO_ROOT)}")
        elif actual != expected:
            errors.append(
                f"  {label}: source={actual!r} (raw={literal!r}) != contract={expected!r}"
            )
        elif args.verbose:
            print(f"  OK {label} = {actual!r}")

    # Substring checks: env_vars and dynamic_block_base do not appear as
    # top-level constants but as inline literals. Verify they exist.
    substring_checks: list[tuple[str, str]] = [
        ("PIPER_DISABLE_WARMUP env var", contract["env_vars"]["disable_warmup"]),
        ("PIPER_DISABLE_CACHE env var", contract["env_vars"]["disable_cache"]),
        ("PIPER_INTRA_THREADS env var", contract["env_vars"]["intra_threads"]),
        ("dynamic_block_base config key", "session.dynamic_block_base"),
        ("dynamic_block_base value", f'"{contract["session"]["dynamic_block_base"]}"'),
    ]
    for label, needle in substring_checks:
        if not _has_substring(ORT_UTILS_PATH, needle):
            errors.append(f"  {label}: substring {needle!r} not found in ort_utils.py")
        elif args.verbose:
            print(f"  OK {label} (substring {needle!r} present)")

    if errors:
        print("ERROR: ORT session contract drift detected:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            f"Update {CONTRACT_PATH.relative_to(REPO_ROOT)} or "
            f"{ORT_UTILS_PATH.relative_to(REPO_ROOT)} so they agree.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: ORT session contract ({CONTRACT_PATH.relative_to(REPO_ROOT)}) "
        "matches Python canonical (ort_utils.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
