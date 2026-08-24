#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""GitHub Actions pin safety gate (sliding-tag regression prevention).

PR #414 fixed a multi-job CI failure where ``sigstore/cosign-installer@v4``
was a sliding major tag that the upstream had deleted, causing 7 jobs to
fail simultaneously. Memory entry ``feedback_pin_actions_sha.md`` records
the rule: pin actions by full SemVer (``@v1.2.3``) or 40-hex SHA, never by
sliding ``@v<major>`` alone.

The original migration (Phase 3) moved all 39 grandfathered sliding-tag
references to SemVer pins (37 entries) or SHA pins (2 entries —
``dawidd6/action-download-artifact`` and ``mymindstorm/setup-emsdk`` had
no SemVer releases). New entries should only be added with a justification
comment when an action *exclusively* publishes ``@v<major>``-style tags
and SHA pinning is impractical — the codespell-baseline pattern is
preserved so a future regression doesn't require a mega-migration again.

Scanning (see ``iter_target_files`` / ``iter_uses_refs``):
  - ``.github/workflows/*.yml`` and ``*.yaml``
  - ``.github/actions/**/action.yml`` and ``action.yaml`` (composite actions —
    the pre-commit hook's ``files:`` pattern always claimed to cover these)
  - Both YAML spellings of a step ref are matched::

        - uses: actions/checkout@v4.2.2     # list form (the common one)
          uses: actions/checkout@v4.2.2     # plain form (mapping continuation)

    Historically only the plain form was matched, which silently skipped
    52% of the ``uses:`` lines in this repo (388 of 806 seen) and hid 38
    sliding-major references across 17 workflows.
  - Lines inside a YAML block scalar (``run: |`` / ``script: >``) are skipped
    so an example ``uses:`` embedded in a shell heredoc is not mistaken for a
    real step reference.

Allowed pin forms (per `uses:` line):
  - 40-hex SHA:               ``actions/checkout@abcd1234...abcd1234``
  - Full SemVer:              ``actions/checkout@v4.2.2``
  - Pre-release SemVer:       ``foo/bar@v1.0.0-rc.1``
  - Local action / workflow:  ``./.github/actions/...``
  - Versioned ref like        ``pypa/gh-action-pypi-publish@release/v1``
    (treated as opaque release branch, warned only)

Forbidden (unless in baseline):
  - Sliding major tag:        ``actions/checkout@v6``
  - Branch ref:               ``dtolnay/rust-toolchain@stable``  (warn only)
  - Symbolic tag:             ``foo/bar@master``                 (warn only)

Workflow:
  1. Collect all ``uses:`` refs from the files above.
  2. Classify each into one of (OK / BASELINED / NEW-VIOLATION).
  3. Exit 1 if any NEW-VIOLATION found.

Migration path (out of scope for this gate):
  - To remove an entry from the baseline, pin the action to SemVer or SHA
    and delete that line from ``action_pins_baseline.txt``.
  - Dependabot will then propose Patch/Minor SemVer bumps.

Usage:
    python scripts/check_action_pins.py
    python scripts/check_action_pins.py --update-baseline  # rare: refresh after batch migration
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "scripts/action_pins_baseline.txt"

# Files scanned, relative to the repo root. Kept in sync with the `files:`
# pattern of the `action-pin-gate` pre-commit hook and with the `paths:`
# filter of .github/workflows/action-pin-gate.yml.
TARGET_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**/action.yml",
    ".github/actions/**/action.yaml",
)

# Matches both `uses: foo/bar@v1` and the far more common list form
# `- uses: foo/bar@v1`. `\s*` cannot consume a leading letter, so `reuses:`
# and comment lines (`# uses: ...`) do not match. YAML allows the value to be
# quoted; the quotes must be stripped before classification, otherwise the
# version reads as `v6'` and a sliding major tag silently degrades from FAIL
# to WARN.
USES_RE = re.compile(r"""^\s*(?:-\s*)?uses:\s*['"]?([^\s#'"]+)""")
# `run: |`, `- run: >-`, `script: |2` … everything indented deeper than the
# key is literal text, not YAML structure.
BLOCK_SCALAR_RE = re.compile(r"^(\s*)(?:-\s*)?[\w.\-]+:\s*[|>][-+]?\d*\s*(?:#.*)?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.+-]+)?$")
SLIDING_MAJOR_RE = re.compile(r"^v\d+$")


def classify(ref: str) -> str:
    """Return one of: 'local', 'ok-sha', 'ok-semver', 'sliding-major', 'other'."""
    if ref.startswith("./"):
        return "local"
    if "@" not in ref:
        return "other"
    _, _, version = ref.partition("@")
    if SHA_RE.match(version):
        return "ok-sha"
    if SEMVER_RE.match(version):
        return "ok-semver"
    if SLIDING_MAJOR_RE.match(version):
        return "sliding-major"
    return "other"


def iter_target_files(repo_root: Path) -> list[Path]:
    """Return every workflow / composite-action YAML file, de-duplicated."""
    seen: dict[Path, None] = {}
    for pattern in TARGET_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file():
                seen[path] = None
    return sorted(seen)


def iter_uses_refs(text: str) -> list[tuple[int, str]]:
    """Return (line-number, uses-ref) for every step reference in `text`.

    Block-scalar bodies (`run: |`) are skipped: a `uses:` line inside a shell
    heredoc is documentation, not a step reference.
    """
    out: list[tuple[int, str]] = []
    block_indent: int | None = None
    for lineno, line in enumerate(text.splitlines(), 1):
        if block_indent is not None:
            if not line.strip():
                continue
            if len(line) - len(line.lstrip()) > block_indent:
                continue
            block_indent = None
        block = BLOCK_SCALAR_RE.match(line)
        if block:
            block_indent = len(block.group(1))
            continue
        m = USES_RE.match(line)
        if m:
            out.append((lineno, m.group(1)))
    return out


def collect_uses(repo_root: Path | None = None) -> list[tuple[Path, int, str]]:
    """Return (path, line-number, uses-ref) for every uses: line."""
    root = repo_root or REPO_ROOT
    out: list[tuple[Path, int, str]] = []
    for path in iter_target_files(root):
        text = path.read_text(encoding="utf-8")
        for lineno, ref in iter_uses_refs(text):
            out.append((path, lineno, ref))
    return out


def load_baseline(baseline: Path | None = None) -> set[str]:
    path = baseline or BASELINE
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def write_baseline(refs: set[str], baseline: Path | None = None) -> None:
    path = baseline or BASELINE
    header = [
        "# Grandfathered sliding-major-tag references for check_action_pins.py.",
        "# DO NOT add new entries to this file — pin new actions by SemVer or SHA.",
        "# Removing a line here: action is migrated to SemVer/SHA pin (good).",
        "# Adding a line here: undermines the gate (bad). Discuss in PR review first.",
        "",
    ]
    path.write_text("\n".join(header + sorted(refs)) + "\n", encoding="utf-8")


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite scripts/action_pins_baseline.txt from current sliding-tag set.",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Scan this tree instead of the repo the script lives in (tests).",
    )
    p.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline file to read/write instead of the repo default (tests).",
    )
    args = p.parse_args(argv)

    root = (args.repo_root or REPO_ROOT).resolve()
    baseline_path = args.baseline or BASELINE
    workflow_dir = root / ".github/workflows"
    if not workflow_dir.is_dir():
        print(f"ERROR: {workflow_dir} not found", file=sys.stderr)
        return 1

    all_uses = collect_uses(root)
    if not all_uses:
        # 0 件は「違反なし」ではなく「探索が壊れた」。 このゲートが塞ごうと
        # している欠陥そのもの (盲目を成功として報告する) を再現しないよう
        # fail-closed にする。
        print(
            "ERROR: discovery found 0 uses: lines — TARGET_GLOBS or USES_RE is broken",
            file=sys.stderr,
        )
        return 1

    sliding_refs: set[str] = set()
    other_refs: list[tuple[Path, int, str]] = []
    for wf, lineno, ref in all_uses:
        kind = classify(ref)
        if kind == "sliding-major":
            sliding_refs.add(ref)
        elif kind == "other":
            other_refs.append((wf, lineno, ref))

    if args.update_baseline:
        write_baseline(sliding_refs, baseline_path)
        print(f"Wrote {len(sliding_refs)} entries to {_display(baseline_path, root)}")
        return 0

    baseline = load_baseline(baseline_path)
    new_violations = sorted(sliding_refs - baseline)
    stale_baseline = sorted(baseline - sliding_refs)

    if other_refs:
        # Grouped by ref: dtolnay/rust-toolchain@stable alone accounts for 37
        # lines, and a 40-line wall of WARN trains people to ignore the gate.
        grouped: dict[str, list[str]] = defaultdict(list)
        for wf, lineno, ref in other_refs:
            grouped[ref].append(f"{_display(wf, root)}:{lineno}")
        print(
            f"WARN: {len(grouped)} 'other' ref(s) (branch/release-name pin) "
            f"on {len(other_refs)} line(s); review:"
        )
        for ref in sorted(grouped):
            locations = grouped[ref]
            shown = ", ".join(locations[:3])
            more = f", +{len(locations) - 3} more" if len(locations) > 3 else ""
            print(f"  {ref}  ({len(locations)}x: {shown}{more})")
        print()

    if stale_baseline:
        print(
            f"INFO: {len(stale_baseline)} baseline entry(ies) no longer in tree "
            f"(action migrated or removed — please delete from baseline):"
        )
        for ref in stale_baseline:
            print(f"  - {ref}")
        print()

    if new_violations:
        print(
            f"FAIL: {len(new_violations)} new sliding-major-tag reference(s) not "
            f"in baseline. Pin by full SemVer (@v1.2.3) or 40-hex SHA — never "
            f"@v<major> alone (PR #414 incident: cosign-installer@v4 was deleted "
            f"upstream and crashed 7 jobs).",
            file=sys.stderr,
        )
        for ref in new_violations:
            print(f"  + {ref}", file=sys.stderr)
        print(
            "\nIf this is a deliberate addition (e.g., adopting a brand-new action "
            "that only ships major tags), add the entry to "
            "scripts/action_pins_baseline.txt with a justification comment.",
            file=sys.stderr,
        )
        return 1

    sha_count = sum(1 for _, _, r in all_uses if classify(r) == "ok-sha")
    semver_count = sum(1 for _, _, r in all_uses if classify(r) == "ok-semver")
    print(
        f"OK no new sliding-tag references. "
        f"({len(all_uses)} total uses: {sha_count} SHA, {semver_count} SemVer, "
        f"{len(sliding_refs)} baselined-sliding, {len(other_refs)} other)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
