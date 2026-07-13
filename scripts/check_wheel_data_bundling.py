#!/usr/bin/env python3
"""Gate 2 — piper-plus wheel data bundling smoke test.

Why this gate exists (Issue #590 rename design §9)
--------------------------------------------------

v2.0 renamed the top-level Python package ``piper`` → ``piper_plus`` in a
single clean-break commit (b86df3f9). Two regression classes threaten that
rename and are silently invisible to unit tests (they only bite downstream
users at pip-install time):

1. **Package-data drift.** ``piper_plus/voices.json`` and the two JSON
   language-data files (``phonemize/data/zh_en_loanword.json`` /
   ``phonemize/data/sv_function_words.json``) MUST be present inside the
   built ``.whl`` archive; otherwise ``pip install piper-plus`` gives users
   an import-time ``FileNotFoundError`` the first time they call
   ``synthesize()``. The three paths live in three places at once —
   ``src/python_run/pyproject.toml`` ``[tool.setuptools.package-data]``,
   the on-disk file layout, and (implicitly) the runtime import path —
   and any of them can drift independently. Existing lint/format gates
   do not open the wheel.

2. **Co-install safety after the piper→piper_plus rename.** If a stray
   top-level ``piper/`` directory ever gets repackaged into the wheel
   (e.g. an editable-install leftover, an accidental ``packages.find``
   pattern change, or a symlink into the source tree), that wheel will
   silently overwrite the legacy ``piper`` package on PyPI when a user
   has both installed. The v2.0 rename design mandates a clean break —
   the built wheel must contain **only** ``piper_plus/`` and its
   sibling ``piper_plus-<ver>.dist-info/`` metadata.

This script opens the built wheel with ``zipfile.ZipFile`` and asserts
both invariants against the raw member name list. False-positive risks
are minimized by the exact-match check for the three required files and
the ``startswith("piper/")`` prefix (with the literal ``/``) for the
forbidden check — ``piper_plus/`` does not match (``_`` != ``/``) and
``piper_plus-<ver>.dist-info/`` does not match (``-`` != ``/``).

Usage
-----

    # CI mode: point at the wheel produced by an earlier build step
    python scripts/check_wheel_data_bundling.py --wheel dist/piper_plus-2.0.0-py3-none-any.whl

    # Local mode: auto-discover the newest wheel in dist/, or build if missing
    python scripts/check_wheel_data_bundling.py

Exit codes
----------

* ``0`` — all three required files present, no top-level ``piper/`` member.
* ``0`` — wheel could not be built locally within 120 s (skip with a
  ``::warning::`` annotation; CI runs the gate against a pre-built wheel).
* ``1`` — any required file missing OR any forbidden ``piper/`` member found.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent

# The three required package-data files. Exact zipfile-member string match.
# Keep in sync with src/python_run/pyproject.toml [tool.setuptools.package-data].
REQUIRED_FILES: tuple[str, ...] = (
    "piper_plus/voices.json",
    "piper_plus/phonemize/data/zh_en_loanword.json",
    "piper_plus/phonemize/data/sv_function_words.json",
)

# Anchor the glob to piper_plus-<digit> so sibling wheels
# (piper_plus_g2p-*.whl) are not accidentally picked up. This matches the
# convention in check_bundle_size.py where every distribution glob uses
# a trailing "-[0-9]*" to exclude packages whose name shares the prefix.
DIST_GLOB = "dist/piper_plus-[0-9]*.whl"

# Local dev fallback: try to build the wheel once. Wall-clock 120 s is
# generous — a warm src/python_run wheel build is ~10-20 s, a cold build
# with a full uv resolver run is ~60 s. If we exceed this budget we
# skip with a warning (CI is the authoritative gate).
BUILD_TIMEOUT_SECONDS = 120


def _resolve_wheel(explicit: str | None) -> Path | None:
    """Return the wheel to inspect, or None if we should skip.

    Resolution order:
      1. ``--wheel`` if given.
      2. Newest matching wheel in ``dist/`` by mtime.
      3. Try ``uv build --wheel src/python_run --out-dir dist`` once, then
         re-glob. On timeout / uv missing / build failure, return None so
         the caller can print a skip warning and exit 0.
    """
    if explicit is not None:
        candidates = sorted(glob.glob(explicit))
        if not candidates:
            print(
                f"::error::--wheel path did not match any file: {explicit}",
                file=sys.stderr,
            )
            return None
        # If a glob was passed (e.g. dist/piper_plus-*.whl) prefer newest.
        candidates.sort(key=os.path.getmtime)
        chosen = Path(candidates[-1])
        print(f"[check_wheel_data_bundling] using wheel: {chosen}", file=sys.stderr)
        return chosen

    matches = sorted(glob.glob(str(REPO_ROOT / DIST_GLOB)))
    if matches:
        matches.sort(key=os.path.getmtime)
        chosen = Path(matches[-1])
        print(
            f"[check_wheel_data_bundling] auto-discovered wheel: {chosen}",
            file=sys.stderr,
        )
        return chosen

    # No wheel on disk — try one build. If uv is missing or the build
    # exceeds the timeout, skip cleanly (this script is meant to be a fast
    # sanity check; producing the wheel is CI's job).
    print(
        "[check_wheel_data_bundling] no wheel in dist/, attempting "
        f"'uv build --wheel src/python_run --out-dir dist' (timeout "
        f"{BUILD_TIMEOUT_SECONDS}s)...",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [
                "uv",
                "build",
                "--wheel",
                "src/python_run",
                "--out-dir",
                "dist",
            ],
            cwd=REPO_ROOT,
            timeout=BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        print(
            "::warning::uv not installed locally; skipping wheel bundling "
            "check. CI will run this gate against a fresh build.",
            file=sys.stderr,
        )
        return None
    except subprocess.TimeoutExpired:
        print(
            f"::warning::wheel not built within {BUILD_TIMEOUT_SECONDS}s; "
            "skipping wheel bundling check. CI will run this gate against "
            "a fresh build.",
            file=sys.stderr,
        )
        return None

    matches = sorted(glob.glob(str(REPO_ROOT / DIST_GLOB)))
    if not matches:
        print(
            "::warning::wheel build completed but produced no matching "
            f"{DIST_GLOB!s}; skipping. CI will run this gate against a "
            "fresh build.",
            file=sys.stderr,
        )
        return None
    matches.sort(key=os.path.getmtime)
    chosen = Path(matches[-1])
    print(f"[check_wheel_data_bundling] built wheel: {chosen}", file=sys.stderr)
    return chosen


def _inspect_wheel(wheel_path: Path) -> tuple[list[str], list[str]]:
    """Return (missing_required, unexpected_piper_members).

    Uses zipfile member NAMES only — never inspects RECORD text or file
    bodies. PKZIP guarantees forward slashes in member names, so no
    OS-specific normalization is required.
    """
    with zipfile.ZipFile(wheel_path) as zf:
        names = set(zf.namelist())

    missing = [path for path in REQUIRED_FILES if path not in names]

    # Forbidden: any member whose top-level directory is literally ``piper``.
    # ``piper_plus/...`` and ``piper_plus-<ver>.dist-info/...`` do NOT
    # match this prefix because both the underscore and the hyphen fail
    # the ``startswith("piper/")`` literal-slash test.
    unexpected = sorted(n for n in names if n.startswith("piper/"))

    return missing, unexpected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--wheel",
        type=str,
        default=None,
        help=(
            "Path (or glob) to a built .whl. If omitted, the newest "
            f"{DIST_GLOB!s} is used; if none exists, one build attempt "
            "is made via 'uv build --wheel src/python_run'."
        ),
    )
    args = parser.parse_args(argv)

    wheel_path = _resolve_wheel(args.wheel)
    if wheel_path is None:
        # A resolution warning (or explicit ::error::) has already been
        # printed. For the explicit --wheel-not-found case we still want
        # to fail; for the local skip case we want to exit 0. Distinguish
        # by whether --wheel was passed.
        if args.wheel is not None:
            return 1
        return 0

    missing, unexpected = _inspect_wheel(wheel_path)

    for path in missing:
        print(f"::error::MISSING: {path}")
    for member in unexpected:
        print(f"::error::UNEXPECTED: piper/ found in wheel: {member}")

    if missing or unexpected:
        print(
            f"\nERROR: {wheel_path.name} failed wheel bundling smoke — "
            f"{len(missing)} missing required file(s), "
            f"{len(unexpected)} unexpected piper/ member(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"[check_wheel_data_bundling] OK — {wheel_path.name}: "
        f"{len(REQUIRED_FILES)}/{len(REQUIRED_FILES)} required files "
        "present, 0 top-level piper/ members"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
