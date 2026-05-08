#!/usr/bin/env python3
"""Meta-tests for cross-runtime sync gate scripts.

Verifies that the gate scripts themselves correctly DETECT drift, i.e. they
exit non-zero when given an intentionally drifted input. Without this, a
silent regression in the gate (e.g. a regex that no longer matches the
runtime table) could let drift slip through unnoticed.

Tested gates:
    * scripts/check_loanword_consistency.py  (ZH-EN loanword JSON)
    * scripts/check_pua_consistency.py       (PUA mapping consistency)
    * scripts/check_ort_session_contract.py  (ORT session TOML <-> Python)
    * scripts/check_short_text_contract.py   (short-text TOML <-> Python)
    * scripts/check_text_splitter_contract.py
    * scripts/check_ssml_contract.py
    * scripts/check_language_id_map_contract.py

Each test:
    1. Snapshots a canonical file's bytes.
    2. Mutates it (single-byte append / version bump / similar).
    3. Runs the gate script and asserts exit code == 1.
    4. ALWAYS restores the original bytes in a `try / finally`.

Usage (CI mirrors):
    uv run python scripts/test_sync_gates_meta.py
    pytest scripts/test_sync_gates_meta.py -v

Exit codes:
    0 -- all gates correctly detected drift on a known-bad input
    1 -- one or more gates failed to detect drift (gate is broken)

Note: This is a local script that runs in-tree. It requires write access
to the repository (it temporarily mutates source files but always restores
them). DO NOT run it against a production / read-only checkout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent

LOANWORD_SOURCE = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json"
LOANWORD_FIRST_MIRROR = (
    REPO_ROOT / "src/python_run/piper/phonemize/data/zh_en_loanword.json"
)
PUA_SOURCE = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/pua.json"


@contextmanager
def temporarily_mutate_bytes(path: Path, suffix: bytes = b"\n") -> Iterator[None]:
    """Append ``suffix`` to ``path`` and restore on exit (always)."""
    backup = path.read_bytes()
    try:
        path.write_bytes(backup + suffix)
        yield
    finally:
        path.write_bytes(backup)


@contextmanager
def temporarily_mutate_json(path: Path, key: str, value: object) -> Iterator[None]:
    """Set ``data[key] = value`` in JSON file at ``path`` and restore on exit."""
    backup = path.read_bytes()
    try:
        data = json.loads(backup)
        data[key] = value
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yield
    finally:
        path.write_bytes(backup)


def run_gate(script: str) -> int:
    """Run a gate script and return exit code."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return result.returncode


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------


def test_loanword_gate_detects_source_drift() -> None:
    """Appending a byte to the canonical zh_en_loanword.json must fail the gate."""
    with temporarily_mutate_bytes(LOANWORD_SOURCE):
        rc = run_gate("check_loanword_consistency.py")
    assert rc == 1, (
        f"loanword gate failed to detect drift on canonical source "
        f"(expected rc=1, got rc={rc})"
    )


def test_loanword_gate_detects_mirror_drift() -> None:
    """Drifting any single mirror must also fail the gate (not just the source)."""
    with temporarily_mutate_bytes(LOANWORD_FIRST_MIRROR):
        rc = run_gate("check_loanword_consistency.py")
    assert rc == 1, (
        f"loanword gate failed to detect drift on a mirror (expected rc=1, got rc={rc})"
    )


def test_pua_gate_detects_version_drift() -> None:
    """Bumping pua.json version must fail the gate (with --check-version)."""
    with temporarily_mutate_json(PUA_SOURCE, "version", 999):
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "check_pua_consistency.py"),
                "--check-version",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        rc = result.returncode
    assert rc == 1, (
        f"pua gate failed to detect canonical version=999 vs runtime constants "
        f"(expected rc=1, got rc={rc})"
    )


def test_loanword_gate_passes_clean_tree() -> None:
    """Sanity check: gate must pass on a clean tree (catches false positives)."""
    rc = run_gate("check_loanword_consistency.py")
    assert rc == 0, (
        f"loanword gate failed on a clean tree -- bug in the gate or "
        f"unstaged drift in the working copy (got rc={rc})"
    )


def test_pua_gate_passes_clean_tree() -> None:
    """Sanity check: gate must pass on a clean tree."""
    rc = run_gate("check_pua_consistency.py")
    assert rc == 0, (
        f"pua gate failed on a clean tree -- bug in the gate or "
        f"unstaged drift in the working copy (got rc={rc})"
    )


# ---------------------------------------------------------------------------
# Standalone runner (also pytest-compatible)
# ---------------------------------------------------------------------------


def main() -> int:
    """Standalone entrypoint when not invoked via pytest."""
    tests = [
        test_loanword_gate_passes_clean_tree,
        test_pua_gate_passes_clean_tree,
        test_loanword_gate_detects_source_drift,
        test_loanword_gate_detects_mirror_drift,
        test_pua_gate_detects_version_drift,
    ]
    failures = 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"PASS  {name}")
        except AssertionError as e:
            print(f"FAIL  {name}: {e}", file=sys.stderr)
            failures += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {name}: {type(e).__name__}: {e}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"\n{failures}/{len(tests)} meta-test(s) failed", file=sys.stderr)
        return 1
    print(f"\nAll {len(tests)} meta-test(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
