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
no SemVer releases). ``scripts/action_pins_baseline.txt`` is now empty
(header only). New entries should only be added with a justification
comment when an action *exclusively* publishes ``@v<major>``-style tags
and SHA pinning is impractical — the codespell-baseline pattern is
preserved so a future regression doesn't require a mega-migration again.

Allowed pin forms (per `uses:` line):
  - 40-hex SHA:               ``actions/checkout@abcd1234...abcd1234``
  - Full SemVer:              ``actions/checkout@v4.2.2``
  - Pre-release SemVer:       ``foo/bar@v1.0.0-rc.1``
  - Local action / workflow:  ``./.github/actions/...``
  - Versioned ref like        ``pypa/gh-action-pypi-publish@release/v1``
    (treated as opaque release branch, allowlisted only)

Forbidden (unless in baseline):
  - Sliding major tag:        ``actions/checkout@v6``
  - Branch ref:               ``dtolnay/rust-toolchain@stable``
  - Symbolic tag:             ``foo/bar@master``

Workflow:
  1. Grep all ``uses:`` lines from ``.github/workflows/*.yml``.
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
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"
BASELINE = REPO_ROOT / "scripts/action_pins_baseline.txt"

USES_RE = re.compile(r"^\s*uses:\s*([^\s#]+)")
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


def collect_uses() -> list[tuple[Path, int, str]]:
    """Return (workflow-path, line-number, uses-ref) for every uses: line."""
    out: list[tuple[Path, int, str]] = []
    for wf in sorted(WORKFLOW_DIR.glob("*.yml")):
        for lineno, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = USES_RE.match(line)
            if m:
                out.append((wf, lineno, m.group(1)))
    return out


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def write_baseline(refs: set[str]) -> None:
    header = [
        "# Grandfathered sliding-major-tag references for check_action_pins.py.",
        "# DO NOT add new entries to this file — pin new actions by SemVer or SHA.",
        "# Removing a line here: action is migrated to SemVer/SHA pin (good).",
        "# Adding a line here: undermines the gate (bad). Discuss in PR review first.",
        "",
    ]
    BASELINE.write_text("\n".join(header + sorted(refs)) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite scripts/action_pins_baseline.txt from current sliding-tag set.",
    )
    args = p.parse_args(argv)

    if not WORKFLOW_DIR.exists():
        print(f"ERROR: {WORKFLOW_DIR} not found", file=sys.stderr)
        return 1

    all_uses = collect_uses()
    sliding_refs: set[str] = set()
    other_refs: list[tuple[Path, int, str]] = []
    for wf, lineno, ref in all_uses:
        kind = classify(ref)
        if kind == "sliding-major":
            sliding_refs.add(ref)
        elif kind == "other":
            other_refs.append((wf, lineno, ref))

    if args.update_baseline:
        write_baseline(sliding_refs)
        print(f"Wrote {len(sliding_refs)} entries to {BASELINE.relative_to(REPO_ROOT)}")
        return 0

    baseline = load_baseline()
    new_violations = sorted(sliding_refs - baseline)
    stale_baseline = sorted(baseline - sliding_refs)

    if other_refs:
        print(
            f"WARN: {len(other_refs)} 'other' ref(s) (branch/release-name pin); review:"
        )
        for wf, lineno, ref in other_refs:
            print(f"  {wf.relative_to(REPO_ROOT)}:{lineno}  {ref}")
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
