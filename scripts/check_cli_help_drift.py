#!/usr/bin/env python3
"""CLI ``--help`` ↔ docs flag-table drift detector.

Catches the failure mode where a CLI flag is removed (or renamed) but the
markdown documentation continues to advertise it. Concrete v1.12.0 example:
``--mb-istft`` was dropped when HiFi-GAN was deleted, yet stale references
could easily linger in ``docs/guides/cli-usage.md`` flag tables and lead
users to invoke arguments the binary no longer accepts.

The gate scopes drift detection to *flag-table rows* of the form

    | `--flag` | description | default |

rather than every backtick occurrence in prose, because migration / changelog
docs legitimately reference removed flags (e.g. the
``docs/migration/v1.11-to-v1.12.md`` row pointing at ``--mb-istft``). Pass
only the *user-facing* CLI reference doc(s) to ``--docs``; pass migration
notes / changelogs via ``--ignore-docs`` or simply omit them.

Usage (CI invocation):

    # Capture --help, then diff against docs:
    uv run python -m piper --help > /tmp/piper.help 2>&1
    python scripts/check_cli_help_drift.py \\
        --help-file /tmp/piper.help \\
        --docs docs/guides/cli-usage.md

    # Or pass a command for the script to run itself:
    python scripts/check_cli_help_drift.py \\
        --help-cmd "uv run python -m piper --help" \\
        --docs docs/guides/cli-usage.md

Multiple docs are supported (`--docs a.md b.md`). The gate is one-sided
configurable:

  - ``--mode strict``         (default) drift in either direction fails.
  - ``--mode stale-only``     fail only on doc flags absent from --help
                              (i.e. removed / renamed CLI flags). Useful
                              when docs intentionally cover a subset.
  - ``--mode missing-only``   fail only on --help flags absent from docs
                              (i.e. undocumented new flags). Rarely useful.

Allowlist:
    Pass ``--allow=FLAG`` (repeatable, *equals form mandatory* — without
    the ``=``, argparse mis-parses the leading ``--`` as another option)
    for flags that the gate must ignore in *both* directions. Example:
    ``--allow=--help`` is auto-added because every argparse CLI surfaces it
    and few CLI doc tables list it explicitly.

    Alternative: ``--allow-file PATH`` reads one flag per line (``#`` for
    comments). Useful when a doc covers a different CLI surface and the
    baseline allowlist is large enough that inline ``--allow=`` gets noisy.

Exit codes:
    0 -- no drift (or only drift in directions excluded by --mode)
    1 -- drift detected
    2 -- usage / IO error
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches a leading flag in a markdown table cell:
#   | `--flag` | ...
#   | `--flag VAL` | ...
#   | `--flag/-f VAL` | ...
# Only captures the long-form (`--xxx`) so `-f` short aliases don't pollute the
# set. We require the backtick to start at column 0 of the cell (allowing one
# optional space after ``|``) so that mid-prose backticks (which would still
# match a naive ``--\S+`` regex) are not picked up.
_DOC_FLAG_RE = re.compile(
    r"""
    ^\|\s*           # row starts with a pipe (markdown table cell)
    `(--[A-Za-z][A-Za-z0-9_-]*)   # capture the long-form flag
    """,
    re.MULTILINE | re.VERBOSE,
)

# Matches a CLI flag inside argparse --help output. Argparse renders flags as
# ``--flag`` or ``--flag VALUE`` on indented option lines, optionally as part
# of a comma-separated alias group (``  -s, --speaker SPEAKER``). We anchor on
# *option lines* (whitespace + ``-`` at start) rather than scanning the whole
# blob so that stray ``--token`` inside help-prose or stderr warnings (e.g.
# uv's ``use --active to target…`` notice) doesn't pollute the flag set.
#
# We also intentionally accept the underscore alias variant argparse emits
# when a flag is registered with both hyphen and underscore forms (e.g.
# ``--output-file, --output_file``). Both forms are recorded so docs can use
# either spelling.
_HELP_OPTION_LINE_RE = re.compile(r"^\s+(-[A-Za-z]|--[A-Za-z])")
_HELP_FLAG_RE = re.compile(r"(--[A-Za-z][A-Za-z0-9_-]*)")


def extract_doc_flags(doc_paths: list[Path]) -> dict[str, list[Path]]:
    """Return {flag: [docs_that_mention_it]} from flag-table rows only."""
    found: dict[str, list[Path]] = {}
    for path in doc_paths:
        if not path.exists():
            print(f"error: docs file not found: {path}", file=sys.stderr)
            sys.exit(2)
        text = path.read_text(encoding="utf-8")
        for match in _DOC_FLAG_RE.finditer(text):
            flag = match.group(1)
            found.setdefault(flag, []).append(path)
    return found


def extract_help_flags(help_text: str) -> set[str]:
    """Return the set of long-form flags advertised by ``--help``.

    We only scan option-declaration lines (the indented ``-x, --foo`` rows
    argparse emits) — *not* arbitrary text — so stderr warnings or option-
    description prose can never inject a false-positive flag.
    """
    flags: set[str] = set()
    for line in help_text.splitlines():
        if _HELP_OPTION_LINE_RE.match(line):
            flags.update(_HELP_FLAG_RE.findall(line))
    return flags


def capture_help(help_cmd: str | None, help_file: Path | None) -> str:
    if help_file is not None:
        if not help_file.exists():
            print(f"error: --help-file not found: {help_file}", file=sys.stderr)
            sys.exit(2)
        return help_file.read_text(encoding="utf-8")
    assert help_cmd is not None  # argparse enforces one-of
    try:
        # Capture stdout + stderr together: argparse normally writes to stdout,
        # but startup warnings (the `tool.uv.dev-dependencies` deprecation
        # notice currently emitted by uv, for instance) land on stderr. Both
        # streams are run through the regex; warning text never matches the
        # ``--xxx`` flag pattern in practice, so the union is safe.
        proc = subprocess.run(
            shlex.split(help_cmd),
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except FileNotFoundError as exc:
        print(f"error: cannot run --help-cmd: {exc}", file=sys.stderr)
        sys.exit(2)
    # `--help` exits 0 on every well-formed CLI; tolerate nonzero (e.g. argparse
    # parse_known_args fallback) and still inspect output.
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect drift between a CLI's --help output and its markdown flag tables.",
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--help-cmd",
        help="Shell command whose stdout is the --help text (e.g. 'uv run python -m piper --help').",
    )
    src.add_argument(
        "--help-file",
        type=Path,
        help="Pre-captured --help output file. Mutually exclusive with --help-cmd.",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        nargs="+",
        required=True,
        help="One or more markdown files containing flag tables to validate.",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="Flag to ignore in both directions (repeatable). Must use equals form: --allow=--help (without `=`, argparse mis-parses the leading `--`).",
    )
    parser.add_argument(
        "--allow-file",
        type=Path,
        help=(
            "Path to a file with one flag per line (lines starting with # are "
            "comments). Used as the baseline allowlist when the docs cover a "
            "different CLI surface (e.g. C++ vs Python). Merged with --allow."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("strict", "stale-only", "missing-only"),
        default="strict",
        help=(
            "strict: fail on any drift. "
            "stale-only: fail only on doc flags missing from --help (removed CLI flags). "
            "missing-only: fail only on --help flags missing from docs."
        ),
    )
    args = parser.parse_args(argv)

    # Auto-allowlist: every argparse CLI surfaces --help / -h, but few CLI
    # reference docs bother listing it as a row. Adding it manually each time
    # would be tedious and not useful (it never disappears).
    allowlist = set(args.allow) | {"--help"}
    if args.allow_file is not None:
        if not args.allow_file.exists():
            print(f"error: --allow-file not found: {args.allow_file}", file=sys.stderr)
            return 2
        for line in args.allow_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            allowlist.add(stripped)

    help_text = capture_help(args.help_cmd, args.help_file)
    help_flags = extract_help_flags(help_text) - allowlist
    doc_flag_locations = extract_doc_flags(args.docs)
    doc_flags = set(doc_flag_locations.keys()) - allowlist

    stale = sorted(doc_flags - help_flags)  # in docs, removed from CLI
    missing = sorted(help_flags - doc_flags)  # in CLI, not in docs

    print(f"docs flags    : {len(doc_flags):3d}  (from {len(args.docs)} file(s))")
    print(f"--help flags  : {len(help_flags):3d}")
    print(f"intersect     : {len(doc_flags & help_flags):3d}")
    print()

    failed = False
    if stale and args.mode in ("strict", "stale-only"):
        failed = True
        print("STALE (documented but not in --help; likely removed/renamed):", file=sys.stderr)
        for flag in stale:
            paths: list[str] = []
            for p in doc_flag_locations[flag]:
                try:
                    paths.append(str(p.relative_to(REPO_ROOT)))
                except ValueError:
                    # Doc path lives outside the repo root (e.g. an ad-hoc
                    # path passed during local testing). Fall back to the
                    # absolute form rather than crashing.
                    paths.append(str(p))
            print(f"  {flag}  <- {', '.join(paths)}", file=sys.stderr)
        print(file=sys.stderr)

    if missing and args.mode in ("strict", "missing-only"):
        failed = True
        print("MISSING (in --help but not documented):", file=sys.stderr)
        for flag in missing:
            print(f"  {flag}", file=sys.stderr)
        print(file=sys.stderr)

    if failed:
        print(
            "CLI help / docs drift detected. Update the markdown flag table, "
            "remove stale rows, or pass --allow <flag> if intentional.",
            file=sys.stderr,
        )
        return 1

    # Non-fatal info: print direction-suppressed drift so it's visible in logs
    # without failing the build.
    if stale and args.mode == "missing-only":
        print(f"(info, suppressed by --mode) {len(stale)} stale doc flag(s): {stale}")
    if missing and args.mode == "stale-only":
        print(f"(info, suppressed by --mode) {len(missing)} undocumented flag(s): {missing}")

    print("OK no drift between --help and docs flag tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
