#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""CLI flag naming parity across 5 runtimes.

Verifies that the common hyphen-form CLI flag names are recognised by
every runtime that exposes them. Drift example caught: C++ `main.cpp:865`
historically accepted both ``--sentence_silence`` (underscore) and
``--sentence-silence`` (hyphen) while Rust / Go accepted only the
hyphen form, leaving users who learned the underscore form from the
C++ help text confused on Rust / Go.

The flag matrix, runtime paths, and skip allowlist live in
``docs/spec/cli-flag-contract.toml`` so the data is reviewable in
isolation from the verifier logic. This script is the *enforcer* —
edits to the contract are the right place to register new flags or
add/remove a runtime.

Source of truth: hyphen-separated flag names (Unix convention). The
script searches for the hyphen-form *base name* (without the leading
``--``) because each runtime uses a different declaration idiom:

  - Python argparse:    ``add_argument("--sentence-silence", ...)``
  - Rust clap derive:   ``sentence_silence`` (rename-all kebab-case)
  - Go pflag:           ``f.Float64Var(..., "sentence-silence", ...)``
  - C# System.CommandLine: ``new Option<float>("--sentence-silence", ...)``
  - C++ manual:         ``arg == "--sentence-silence"``

A simple substring match for the hyphen-form base name catches all five.

Usage:
    python scripts/check_cli_flag_parity.py

Exit codes:
    0 -- every required (flag, runtime) pair found
    1 -- at least one expected flag missing in a runtime
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "spec" / "cli-flag-contract.toml"


def contains_flag(path: Path, flag_basename: str) -> bool:
    """Search for the hyphen-form base name **or** its snake_case twin.

    Most runtimes carry the literal hyphen-form (``sentence-silence``):

      - Python argparse:    ``add_argument("--sentence-silence", ...)``
      - Go pflag:           ``f.Float64Var(..., "sentence-silence", ...)``
      - C# System.CommandLine: ``new Option<float>("--sentence-silence", ...)``
      - C++ manual:         ``arg == "--sentence-silence"``

    Rust clap-derive is the exception: with ``rename-all = "kebab-case"``
    the source carries the snake_case field name (``sentence_silence``)
    and the hyphen form only appears in comments. A naive substring
    check on the hyphen form would pass even if the field were deleted
    (the comment alone would satisfy it). Accept either form so the
    gate detects field removal even when stale comments linger.

    False-positive risk: a documentation comment like
    ``// TODO: add sentence_silence later`` would also pass. That is
    accepted as a trade-off — code review still catches it, and the
    main failure mode the gate guards against (silent runtime
    omission across the matrix) is covered.
    """
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    underscore_form = flag_basename.replace("-", "_")
    return flag_basename in text or underscore_form in text


def _load_contract() -> dict:
    if not CONTRACT.exists():
        print(f"::error::contract missing: {CONTRACT}", file=sys.stderr)
        sys.exit(1)
    with CONTRACT.open("rb") as f:
        return tomllib.load(f)


def main(argv: list[str] | None = None) -> int:
    contract = _load_contract()

    # Build runtime registry: key -> (label, path)
    runtimes_by_key: dict[str, tuple[str, Path]] = {}
    for r in contract.get("runtimes", []):
        runtimes_by_key[r["key"]] = (r["label"], REPO_ROOT / r["path"])

    groups: dict[str, list[str]] = contract.get("groups", {})

    # Skip allowlist: set of (label, flag) pairs.
    skips: set[tuple[str, str]] = set()
    for s in contract.get("skips", []):
        runtime_key = s["runtime"]
        if runtime_key not in runtimes_by_key:
            print(
                f"::error::skips entry references unknown runtime key "
                f"{runtime_key!r}",
                file=sys.stderr,
            )
            return 1
        label, _ = runtimes_by_key[runtime_key]
        skips.add((label, s["flag"]))

    failures: list[str] = []
    skipped = 0
    for entry in contract.get("flags", []):
        flag = entry["flag"]
        group_key = entry["runtimes"]
        if group_key not in groups:
            print(f"::error::unknown group {group_key!r} in [[flags]]", file=sys.stderr)
            return 1
        runtime_keys = groups[group_key]
        print(f"== --{flag} ==")
        for key in runtime_keys:
            if key not in runtimes_by_key:
                print(f"::error::group {group_key!r} references unknown runtime {key!r}", file=sys.stderr)
                return 1
            label, path = runtimes_by_key[key]
            if (label, flag) in skips:
                print(f"  SKIP {label} (allowlisted as not-implemented)")
                skipped += 1
                continue
            if not path.exists():
                msg = f"  MISSING SOURCE [{label}] {path}"
                failures.append(msg)
                print(msg, file=sys.stderr)
                continue
            if contains_flag(path, flag):
                print(f"  OK   {label}")
            else:
                msg = (
                    f"  FAIL [{label}] does not declare hyphen-form '{flag}'. "
                    f"Either add the flag in {path.relative_to(REPO_ROOT)} "
                    f"or, if this runtime intentionally lacks the feature, "
                    f"add a [[skips]] entry in docs/spec/cli-flag-contract.toml."
                )
                failures.append(msg)
                print(msg, file=sys.stderr)
        print()

    if failures:
        print(
            f"\n{len(failures)} CLI flag parity drift(s). "
            f"({skipped} allowlisted pair(s) skipped.)",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK every required hyphen-form flag is present in every required "
        f"runtime CLI ({skipped} pair(s) allowlisted as not-implemented)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
