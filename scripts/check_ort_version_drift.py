#!/usr/bin/env python3
"""Check that the ORT version table in the docs matches the real pins.

Scope
-----
This gate has exactly one job: keep the ``## Current versions`` table in
``docs/reference/ort-versions.md`` honest. It does **not** check that the
pins satisfy the canonical floor -- ``scripts/check_ort_versions.py``
already does that with real ``parse_version`` comparisons over
``EXACT_TARGETS`` / ``FLOOR_TARGETS``, gated by ``ort-version-sync.yml``.
Duplicating it here would put the same contract behind a weaker check.

Rows deliberately not covered:

* ``Rust`` -- ``docs/reference/ort-versions.md`` declares
  ``src/rust/piper-core/Cargo.toml`` out of scope so the gate is not
  coupled to the upstream ``ort`` RC cadence. Honour that.
* ``C++`` / ``iOS`` / ``Android`` / ``Kotlin G2P`` -- covered by
  ``check_ort_versions.py``'s exact-match group.

Why this was rewritten (all measured 2026-08-25)
------------------------------------------------
The previous implementation never once failed a job:

1. ``SPEC`` pointed at ``docs/spec/ort-versions.md``; the file was renamed
   to ``docs/reference/`` in ``ea994a2c`` (#493). Running it printed
   ``WARNING: spec missing`` and returned **0**.
2. Even with the path fixed, a target whose pattern did not match was
   ``continue``d silently. Two of the six targets had nothing to match:
   ``src/python_run/setup.py`` lost its pin in Issue #418, and
   ``src/rust/piper-wasm/Cargo.toml`` does not depend on ``ort`` at all.
3. ``model-quality-gate.yml`` also carried ``continue-on-error: true`` on
   this step -- present since the workflow's first commit ``692cb3f6``
   (#401), so the step could not fail the job even in principle.

Behind those three layers sat a real drift: the doc claimed ``>=1.20.0``
for both Python rows while the actual pins were ``>=1.26.0``. The string
``1.26.0`` appeared **zero** times in the doc.

The comparison itself was also unsound. It asked ``version not in
spec_text`` -- a bare substring test against the whole 140-line document:

===========================  =======  ==================================
expression                   result   what it means
===========================  =======  ==================================
``'2.0.0-rc.1' in doc``      True     an rc.13 -> rc.1 downgrade passes
``'1.20.0' in doc``          True     *any* runtime dropped to 1.20.0
                                      passes (six C++ rows carry it)
``'1.24.3' in doc``          True     Go set to the C# value passes
``'1.2' in doc``             True     a truncated version passes
===========================  =======  ==================================

So the check only ever asserted "this string occurs somewhere in the
file". This module compares **per row**: a version must appear as a
whole token inside its own row's ``ORT Version`` cell.

Failure modes (all exit 1 -- there is no ``return 0`` escape hatch)
-------------------------------------------------------------------
* spec file missing
* ``## Current versions`` table missing or unparseable
* a declared row label absent from the table
* a target file missing
* a pattern matching nothing (i.e. the pin it guards disappeared)
* ``len(ROW_CHECKS) != EXPECTED_CHECK_COUNT``
* any extracted version absent from its row's cell

Usage
-----
    python scripts/check_ort_version_drift.py
    python scripts/check_ort_version_drift.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "reference" / "ort-versions.md"

TABLE_HEADING = "## Current versions"

# (doc row label, repo-relative file, pattern capturing the version).
# Several entries may share a row label; every version found across that
# label's entries must appear in the row's cell.
#
# Patterns are matched with re.MULTILINE unconditionally. This is not
# optional: `src/python_run/requirements.txt` opens with two comment
# lines, so `^onnxruntime` anchored to the string start finds nothing and
# -- since a non-matching pattern is now a hard failure -- the gate would
# be permanently red without it.
ROW_CHECKS: list[tuple[str, str, str]] = [
    ("Python (training)", "src/python/pyproject.toml", r'"onnxruntime>=([0-9][0-9.]*)"'),
    (
        "Python (training)",
        "src/python/pyproject.toml",
        r'"onnxruntime-gpu>=([0-9][0-9.]*)',
    ),
    ("Python (runtime)", "src/python_run/requirements.txt", r"^onnxruntime>=([0-9][0-9.]*)"),
    (
        "Python (runtime)",
        "src/python_run/requirements_gpu.txt",
        r"^onnxruntime-gpu>=([0-9][0-9.]*)",
    ),
    (
        "C#",
        "src/csharp/PiperPlus.Core/PiperPlus.Core.csproj",
        r'Microsoft\.ML\.OnnxRuntime\.Managed"\s+Version="([0-9][0-9.]*)"',
    ),
    ("Go", "src/go/go.mod", r"onnxruntime_go\s+v([0-9][0-9.]*)"),
    (
        "JS/WASM",
        "src/wasm/openjtalk-web/package.json",
        r'"onnxruntime-web"\s*:\s*"[^"0-9]*([0-9][0-9.]*)"',
    ),
]

# A silent shrink of ROW_CHECKS would make this gate quietly cover less
# while still reporting success -- the exact failure mode being fixed.
EXPECTED_CHECK_COUNT = 7

# Version-ish tokens inside a table cell: 1.20.0, 1.2, 2.0.0-rc.13.
VERSION_TOKEN_RE = re.compile(r"\d+(?:\.\d+)+(?:-rc\.\d+)?")


class DriftError(RuntimeError):
    """Raised on any failure; the caller turns this into exit 1."""


def parse_current_versions(spec_text: str) -> dict[str, str]:
    """Return ``{row label: ORT Version cell}`` from the doc's table.

    Reads the markdown table under ``## Current versions`` up to the next
    ``##`` heading, skipping the header and separator rows.
    """
    lines = spec_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == TABLE_HEADING)
    except StopIteration:
        raise DriftError(
            f"{TABLE_HEADING!r} heading not found in {SPEC}. "
            "The gate parses that table; if the doc was restructured, update "
            "TABLE_HEADING in scripts/check_ort_version_drift.py."
        ) from None

    rows: dict[str, str] = {}
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = cells[0]
        if not label or label.lower() == "runtime" or set(label) <= set("-: "):
            continue  # header or separator row
        rows[label] = cells[1]
    if not rows:
        raise DriftError(
            f"no data rows parsed from the {TABLE_HEADING!r} table in {SPEC}. "
            "Refusing to report success on an empty table."
        )
    return rows


def extract_versions(path: Path, pattern: str) -> list[str]:
    """All versions captured by ``pattern`` in ``path``, in order, deduped."""
    text = path.read_text(encoding="utf-8")
    found = [m.group(1) for m in re.finditer(pattern, text, re.MULTILINE)]
    seen: dict[str, None] = {}
    for v in found:
        seen.setdefault(v, None)
    return list(seen)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", action="store_true", help="print every row checked")
    args = parser.parse_args(argv)

    try:
        drifts = check(verbose=args.verbose)
    except DriftError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if drifts:
        print("\nDrift detected:", file=sys.stderr)
        for d in drifts:
            print(f"  - {d}", file=sys.stderr)
        print(
            f"\nUpdate the '{TABLE_HEADING}' table in {SPEC.relative_to(REPO_ROOT)} "
            "so it matches the pins, or fix the pin if the doc is right.",
            file=sys.stderr,
        )
        return 1

    print(f"OK doc table matches all {EXPECTED_CHECK_COUNT} pin site(s)")
    return 0


def check(*, verbose: bool = False) -> list[str]:
    """Return a list of drift messages. Raises DriftError on a broken setup."""
    if len(ROW_CHECKS) != EXPECTED_CHECK_COUNT:
        raise DriftError(
            f"ROW_CHECKS has {len(ROW_CHECKS)} entr(ies) but EXPECTED_CHECK_COUNT "
            f"is {EXPECTED_CHECK_COUNT}. Adjust the constant deliberately -- a "
            "silent shrink would make this gate cover less while still passing."
        )

    if not SPEC.exists():
        raise DriftError(
            f"spec missing: {SPEC}. The gate cannot verify drift without it; "
            "failing rather than skipping (the previous implementation returned "
            "0 here and went unnoticed for three months)."
        )

    rows = parse_current_versions(SPEC.read_text(encoding="utf-8"))
    if verbose:
        print(f"Loaded {SPEC.relative_to(REPO_ROOT)} ({len(rows)} table row(s))")

    drifts: list[str] = []
    for label, rel_path, pattern in ROW_CHECKS:
        path = REPO_ROOT / rel_path
        if not path.exists():
            raise DriftError(
                f"[{label}] target file missing: {rel_path}. Update ROW_CHECKS "
                "instead of leaving a target that can never match."
            )
        if label not in rows:
            raise DriftError(
                f"[{label}] no such row in the '{TABLE_HEADING}' table "
                f"(rows: {', '.join(sorted(rows))}). "
                "Row labels are matched exactly."
            )

        versions = extract_versions(path, pattern)
        if not versions:
            raise DriftError(
                f"[{label}] pattern {pattern!r} matched nothing in {rel_path}. "
                "The pin this gate guards has disappeared -- failing rather than "
                "skipping, which is how the previous implementation went green "
                "precisely when a target lost its pin."
            )

        cell = rows[label]
        cell_tokens = set(VERSION_TOKEN_RE.findall(cell))
        for version in versions:
            if version in cell_tokens:
                if verbose:
                    print(f"  [{label}] {version} <- {rel_path}")
                continue
            drifts.append(
                f"[{label}] {rel_path} pins {version}, but the doc row reads "
                f"{cell!r} (tokens: {', '.join(sorted(cell_tokens)) or 'none'})"
            )
    return drifts


if __name__ == "__main__":
    sys.exit(run())
