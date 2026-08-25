#!/usr/bin/env python3
"""Check G2P dictionary versions against docs/spec/dictionary-versions.toml.

Why this was rewritten (all measured 2026-08-26)
------------------------------------------------
The previous implementation checked nothing. It grepped four targets:

    pyopenjtalk-plus / g2p-en / pypinyin  <- src/python_run/setup.py
    jpreprocess (Rust)                    <- src/rust/piper-core/Cargo.toml

and **all four matched nothing**::

    [pyopenjtalk-plus] not found in src/python_run/setup.py
    [g2p-en]           not found in src/python_run/setup.py
    [pypinyin]         not found in src/python_run/setup.py
    [jpreprocess]      not found in src/rust/piper-core/Cargo.toml

    [OK] All discoverable dictionary versions are referenced in spec
    exit 0

Two independent causes:

* ``src/python_run/setup.py`` stopped carrying pins in Issue #418 — it now
  reads ``requirements.txt`` into ``install_requires``. The three Python
  pins live in ``src/python_run/requirements.txt``.
* The Rust pattern ``jpreprocess\\s*=\\s*"..."`` never matched the actual
  declaration, which is ``jpreprocess = { version = "0.9", optional = true }``.

Because the drift loop iterates over ``found``, an empty ``found`` means the
loop body never runs and the gate prints ``[OK]`` — it went green *precisely
because* it had lost every target. The same class as #628 / #629 / #632.

Behind that sat a real drift: the spec pinned ``pyopenjtalk-plus 0.4.1.post7``
while ``requirements.txt`` required ``>=0.4.1.post8``.

The comparison was unsound too. It asked ``version not in spec_text`` — a
bare substring test over the whole document — so a version belonging to a
different package's row would satisfy it. This module reads the spec as TOML
and compares each pin against **its own** declared value.

Failure modes (all exit 1 — there is no ``return 0`` escape hatch)
------------------------------------------------------------------
* spec file missing
* a target file missing
* a pattern matching nothing (i.e. the pin it guards disappeared)
* a spec key path that does not resolve
* ``len(CHECKS) != EXPECTED_CHECK_COUNT``
* an extracted version differing from the spec's declared version

Usage
-----
    python scripts/check_dictionary_versions.py
    python scripts/check_dictionary_versions.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "dictionary-versions.toml"

# (label, repo-relative file, capture pattern, spec key path, spec field, mode).
#
# The spec field differs per entry: Python packages declare `version`, while
# the Rust crate declares `crates_io_version` (the published crate release).
#
# `mode` selects how the code's pin is compared to the spec's declared value:
#
#   "exact"  — the two must be identical. Used where the code states a
#              concrete version (a `>=X` floor that is meant to track the
#              spec's pinned release).
#   "prefix" — the spec version must sit inside the code's caret range.
#              `jpreprocess = { version = "0.9" }` is Cargo caret syntax
#              meaning `>=0.9.0, <0.10.0`, so the spec's `0.9.1` satisfies it.
#              Comparing those for equality would be a category error and
#              would report drift on a perfectly consistent pair.
CHECKS: list[tuple[str, str, str, tuple[str, ...], str, str]] = [
    (
        "pyopenjtalk-plus",
        "src/python_run/requirements.txt",
        r"^pyopenjtalk-plus>=([0-9][0-9a-z.]*)",
        ("japanese", "pyopenjtalk_plus"),
        "version",
        "exact",
    ),
    (
        "g2p-en",
        "src/python_run/requirements.txt",
        r"^g2p-en>=([0-9][0-9.]*)",
        ("english", "g2p_en"),
        "version",
        "exact",
    ),
    (
        "pypinyin",
        "src/python_run/requirements.txt",
        r"^pypinyin>=([0-9][0-9.]*)",
        ("chinese", "pypinyin"),
        "version",
        "exact",
    ),
    (
        "jpreprocess (Rust)",
        "src/rust/piper-core/Cargo.toml",
        r'jpreprocess\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"',
        ("japanese", "jpreprocess"),
        "crates_io_version",
        "prefix",
    ),
]

# A silent shrink of CHECKS would make this gate cover less while still
# reporting success -- the exact failure mode being fixed.
EXPECTED_CHECK_COUNT = 4


class DriftError(RuntimeError):
    """Raised on a broken setup; the caller turns this into exit 1."""


def spec_get(spec: dict[str, Any], path: tuple[str, ...], field: str, label: str) -> str:
    node: Any = spec
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise DriftError(
                f"[{label}] spec key path {'.'.join(path)!r} does not resolve in "
                f"{SPEC.relative_to(REPO_ROOT)}. Update CHECKS rather than leaving a "
                "lookup that can never match."
            )
        node = node[key]
    if not isinstance(node, dict) or field not in node:
        raise DriftError(
            f"[{label}] spec table {'.'.join(path)!r} has no {field!r} field "
            f"(keys: {', '.join(sorted(node)) if isinstance(node, dict) else type(node).__name__})."
        )
    return str(node[field])


def extract_version(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise DriftError(
            f"[{label}] pattern {pattern!r} matched nothing in "
            f"{path.relative_to(REPO_ROOT)}. The pin this gate guards has "
            "disappeared -- failing rather than skipping, which is how the "
            "previous implementation went green with all four targets empty."
        )
    return match.group(1)


def check(*, verbose: bool = False) -> list[str]:
    """Return a list of drift messages. Raises DriftError on a broken setup."""
    if len(CHECKS) != EXPECTED_CHECK_COUNT:
        raise DriftError(
            f"CHECKS has {len(CHECKS)} entr(ies) but EXPECTED_CHECK_COUNT is "
            f"{EXPECTED_CHECK_COUNT}. Adjust the constant deliberately -- a silent "
            "shrink would make this gate cover less while still passing."
        )

    if not SPEC.exists():
        raise DriftError(
            f"spec missing: {SPEC}. The gate cannot verify drift without it; "
            "failing rather than skipping."
        )

    with SPEC.open("rb") as handle:
        spec = tomllib.load(handle)
    if verbose:
        print(f"Loaded {SPEC.relative_to(REPO_ROOT)}")

    drifts: list[str] = []
    for label, rel_path, pattern, key_path, field, mode in CHECKS:
        if mode not in ("exact", "prefix"):
            raise DriftError(f"[{label}] unknown comparison mode {mode!r}")

        path = REPO_ROOT / rel_path
        if not path.exists():
            raise DriftError(
                f"[{label}] target file missing: {rel_path}. Update CHECKS instead "
                "of leaving a target that can never match."
            )

        actual = extract_version(path, pattern, label)
        declared = spec_get(spec, key_path, field, label)

        if mode == "exact":
            ok = actual == declared
            detail = f"declares {declared}"
        else:  # prefix: spec version must fall inside the caret range
            ok = declared == actual or declared.startswith(actual + ".")
            detail = f"declares {declared}, which is outside the caret range ^{actual}"

        if ok:
            if verbose:
                print(f"  [{label}] {actual} <-> spec {declared}  ({rel_path})")
            continue
        drifts.append(
            f"[{label}] {rel_path} pins {actual}, but "
            f"{'.'.join(key_path)}.{field} in {SPEC.name} {detail}"
        )
    return drifts


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", action="store_true", help="print every pin checked")
    args = parser.parse_args(argv)

    try:
        drifts = check(verbose=args.verbose)
    except DriftError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if drifts:
        print("\nDrift detected:", file=sys.stderr)
        for drift in drifts:
            print(f"  - {drift}", file=sys.stderr)
        print(
            f"\nUpdate {SPEC.relative_to(REPO_ROOT)} to match the pins, or fix the "
            "pin if the spec is right. Bumping a pinned version has the process "
            "requirements listed in the spec's [meta] section.",
            file=sys.stderr,
        )
        return 1

    print(f"OK spec matches all {EXPECTED_CHECK_COUNT} dictionary pin(s)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
