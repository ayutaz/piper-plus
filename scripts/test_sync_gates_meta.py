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

ORT_SESSION_TOML = REPO_ROOT / "docs/spec/ort-session-contract.toml"
SHORT_TEXT_TOML = REPO_ROOT / "docs/spec/short-text-contract.toml"
TEXT_SPLITTER_TOML = REPO_ROOT / "docs/spec/text-splitter-contract.toml"
SSML_TOML = REPO_ROOT / "docs/spec/ssml-contract.toml"
LANGUAGE_ID_MAP_TOML = REPO_ROOT / "docs/spec/language-id-map-contract.toml"


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


@contextmanager
def temporarily_replace_in_file(path: Path, old: str, new: str) -> Iterator[None]:
    """Replace first ``old`` occurrence with ``new`` in ``path`` and restore on exit.

    Used to simulate **value drift** in TOML / Python source files (as opposed
    to structural corruption which only proves the parser fails). Raises if
    ``old`` is not present so the meta-test cannot silently no-op when the
    canonical value is renamed.
    """
    backup = path.read_bytes()
    text = backup.decode("utf-8")
    if old not in text:
        raise RuntimeError(
            f"pattern {old!r} not found in {path} -- meta-test target stale"
        )
    try:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        yield
    finally:
        path.write_bytes(backup)


@contextmanager
def temporarily_mutate_pua_entry(
    path: Path, token: str, new_codepoint: str
) -> Iterator[None]:
    """Mutate a single PUA entry's codepoint and restore on exit.

    Picks the entry whose ``token`` field matches ``token`` and rewrites
    its ``codepoint`` to ``new_codepoint``. This simulates the realistic
    drift scenario "someone renumbered a token" rather than the trivial
    version bump (which is already covered).
    """
    backup = path.read_bytes()
    try:
        data = json.loads(backup)
        target = next((e for e in data["entries"] if e.get("token") == token), None)
        if target is None:
            raise RuntimeError(f"token {token!r} not found in pua.json entries")
        target["codepoint"] = new_codepoint
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        yield
    finally:
        path.write_bytes(backup)


def run_gate(script: str, *args: str) -> int:
    """Run a gate script (with optional CLI args) and return exit code."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
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


def test_pua_gate_detects_mapping_drift() -> None:
    """Renumbering a PUA token's codepoint must fail the gate (without --check-version).

    Until this test existed, only the version constant was exercised. A real
    bug like "U+E000 (a:) silently renamed to U+E099" would slip through if
    the gate's mirror-comparison code path broke.
    """
    # 'a:' is the very first ja entry (U+E000) — drifting it is the most
    # representative case for "single-token renumbering".
    with temporarily_mutate_pua_entry(PUA_SOURCE, "a:", "0xEFFF"):
        rc = run_gate("check_pua_consistency.py")
    assert rc == 1, (
        f"pua gate failed to detect codepoint drift on token 'a:' "
        f"(expected rc=1, got rc={rc}) -- mirror comparison may be broken"
    )


# ---------------------------------------------------------------------------
# Contract-TOML drift gates (5 gates added by PR #401)
# Until these existed, the gates could silently no-op (e.g. a regex that
# stops matching the runtime constant) and CI would pass forever.
# ---------------------------------------------------------------------------


def test_short_text_gate_detects_drift() -> None:
    """Mutating short-text-contract.toml min_phoneme_ids must fail the gate."""
    with temporarily_replace_in_file(
        SHORT_TEXT_TOML,
        "min_phoneme_ids = 15",
        "min_phoneme_ids = 999",
    ):
        rc = run_gate("check_short_text_contract.py")
    assert rc == 1, (
        f"short-text gate failed to detect min_phoneme_ids drift "
        f"(expected rc=1, got rc={rc})"
    )


def test_short_text_gate_passes_clean_tree() -> None:
    rc = run_gate("check_short_text_contract.py")
    assert rc == 0, f"short-text gate failed on clean tree (rc={rc})"


def test_ort_session_gate_detects_drift() -> None:
    """Mutating ort-session-contract.toml max_intra_threads must fail the gate."""
    with temporarily_replace_in_file(
        ORT_SESSION_TOML,
        "max_intra_threads = 4",
        "max_intra_threads = 999",
    ):
        rc = run_gate("check_ort_session_contract.py")
    assert rc == 1, (
        f"ort-session gate failed to detect max_intra_threads drift "
        f"(expected rc=1, got rc={rc})"
    )


def test_ort_session_gate_passes_clean_tree() -> None:
    rc = run_gate("check_ort_session_contract.py")
    assert rc == 0, f"ort-session gate failed on clean tree (rc={rc})"


def test_text_splitter_gate_detects_drift() -> None:
    """Removing a sentence terminator from the canonical TOML must fail the gate."""
    # `。` (U+3002) is the canonical Japanese sentence terminator. Renaming
    # it to "X" simulates "someone changed a terminator codepoint in the
    # contract"; runtimes still terminate on `。` → drift detected.
    with temporarily_replace_in_file(
        TEXT_SPLITTER_TOML,
        'char = "\\u3002"\ncodepoint = "U+3002"',
        'char = "X"\ncodepoint = "U+0058"',
    ):
        rc = run_gate("check_text_splitter_contract.py")
    assert rc == 1, (
        f"text-splitter gate failed to detect terminator drift "
        f"(expected rc=1, got rc={rc})"
    )


def test_text_splitter_gate_passes_clean_tree() -> None:
    rc = run_gate("check_text_splitter_contract.py")
    assert rc == 0, f"text-splitter gate failed on clean tree (rc={rc})"


def test_ssml_gate_detects_drift() -> None:
    """Mutating a break_strength.map entry must fail the gate.

    The SSML gate compares Python ``SSMLParser.BREAK_STRENGTH_MS`` against
    the canonical TOML ``[break_strength.map]`` values. Drifting the toml
    entry simulates "someone changed the medium-break duration in the
    contract" while Python still uses 400ms.
    """
    with temporarily_replace_in_file(
        SSML_TOML,
        "medium   = 400",
        "medium   = 99",
    ):
        rc = run_gate("check_ssml_contract.py")
    assert rc == 1, (
        f"ssml gate failed to detect break_strength.map drift "
        f"(expected rc=1, got rc={rc})"
    )


def test_ssml_gate_passes_clean_tree() -> None:
    rc = run_gate("check_ssml_contract.py")
    assert rc == 0, f"ssml gate failed on clean tree (rc={rc})"


def test_language_id_map_gate_detects_drift() -> None:
    """Renumbering a language code in language-id-map-contract.toml must fail."""
    with temporarily_replace_in_file(
        LANGUAGE_ID_MAP_TOML,
        "ja = 0,",
        "ja = 99,",
    ):
        rc = run_gate("check_language_id_map_contract.py")
    assert rc == 1, (
        f"language-id-map gate failed to detect ja=0→99 drift "
        f"(expected rc=1, got rc={rc})"
    )


def test_language_id_map_gate_passes_clean_tree() -> None:
    rc = run_gate("check_language_id_map_contract.py")
    assert rc == 0, f"language-id-map gate failed on clean tree (rc={rc})"


# ---------------------------------------------------------------------------
# Standalone runner (also pytest-compatible)
# ---------------------------------------------------------------------------


def main() -> int:
    """Standalone entrypoint when not invoked via pytest."""
    tests = [
        # Sanity (clean-tree) checks
        test_loanword_gate_passes_clean_tree,
        test_pua_gate_passes_clean_tree,
        test_short_text_gate_passes_clean_tree,
        test_ort_session_gate_passes_clean_tree,
        test_text_splitter_gate_passes_clean_tree,
        test_ssml_gate_passes_clean_tree,
        test_language_id_map_gate_passes_clean_tree,
        # Drift detection
        test_loanword_gate_detects_source_drift,
        test_loanword_gate_detects_mirror_drift,
        test_pua_gate_detects_version_drift,
        test_pua_gate_detects_mapping_drift,
        test_short_text_gate_detects_drift,
        test_ort_session_gate_detects_drift,
        test_text_splitter_gate_detects_drift,
        test_ssml_gate_detects_drift,
        test_language_id_map_gate_detects_drift,
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
