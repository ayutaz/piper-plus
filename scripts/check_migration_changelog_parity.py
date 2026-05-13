#!/usr/bin/env python3
"""CHANGELOG <-> code <-> migration-doc triangulation gate.

This script enforces three invariants between the three sources of truth
that document a release:

  1. CHANGELOG.md   -- bullet-level Breaking changes (what changed)
  2. docs/migration/v*.md -- how users migrate (per-version migration guide)
  3. VERSION / pyproject.toml -- the actual shipped version string

For every released `## [X.Y.Z]` section in CHANGELOG.md, the script scans
the `### Changed (Breaking)` / `### Breaking changes` / `### BREAKING
CHANGES` heading family. Each bullet line and `####` sub-heading inside
that section is treated as a "breaking item". For each breaking item, the
script extracts notable keywords (back-ticked identifiers, file paths,
flag names) and verifies that at least one keyword appears somewhere in
`docs/migration/v<prev>-to-v<curr>.md` (substring match, case-insensitive
for ASCII tokens).

If a breaking item has no corresponding migration coverage, the script
fails with a list of orphaned items. Optionally `--verbose` prints the
keyword set that was searched for.

In addition:
  * VERSION file is parsed and compared with the most-recent released
    `## [X.Y.Z]` header in CHANGELOG.md. Drift fails.
  * `pyproject.toml`'s `version = {file = "VERSION"}` (or literal
    `version = "X.Y.Z"`) is compared with the VERSION file.

`## [Unreleased]` is intentionally skipped -- pre-release churn happens
there and migration docs are produced at release time.

Exit codes:
    0 -- all invariants hold
    1 -- drift detected (missing migration entry / version mismatch)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
VERSION_FILE = REPO_ROOT / "VERSION"
PYPROJECT = REPO_ROOT / "pyproject.toml"
MIGRATION_DIR = REPO_ROOT / "docs" / "migration"

# Heading family that signals a breaking-changes section.
# We match `### Foo` (level 3) but also accept `**Breaking changes:**` style
# bold-paragraph markers because some CHANGELOG entries (e.g. v1.12.0's
# Decoder section) put the bullets under a bold inline label instead of a
# level-3 heading.
BREAKING_HEADING_PATTERNS = [
    re.compile(r"^###\s+(?:Changed\s*\(Breaking\)|Breaking(?:\s+changes?|\s+Changes?)?|BREAKING\s+CHANGES?)\s*$", re.IGNORECASE),
]
BREAKING_BOLD_PATTERNS = [
    re.compile(r"^\*\*Breaking changes?:?\*\*\s*$", re.IGNORECASE),
    re.compile(r"^\*\*BREAKING CHANGES?:?\*\*\s*$", re.IGNORECASE),
]
# A bold-paragraph marker like **影響を受ける呼び出しパターン:** -- any
# bold line ending in a colon. When we see one of these and it is NOT a
# breaking marker, we stop attributing subsequent bullets to the prior
# breaking sub-heading (they're descriptive scaffolding, not breaking items).
ANY_BOLD_MARKER_RE = re.compile(r"^\*\*[^*\n]+[:：]\*\*\s*$")

VERSION_HEADER_RE = re.compile(r"^##\s+\[(?P<ver>\d+\.\d+\.\d+)\](?:\s+-\s+\S+)?\s*$")
UNRELEASED_HEADER_RE = re.compile(r"^##\s+\[Unreleased\]\s*$", re.IGNORECASE)
ANY_LEVEL2_RE = re.compile(r"^##\s+")
ANY_LEVEL3_RE = re.compile(r"^###\s+")
SUBSECTION_HEADER_RE = re.compile(r"^####\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^-\s+(.+?)\s*$")

# Tokens worth using as migration-doc lookup keys.
BACKTICK_RE = re.compile(r"`([^`]{2,})`")
FLAG_RE = re.compile(r"(--[a-z][a-z0-9_-]+)")
PATH_RE = re.compile(r"([A-Za-z_][\w./-]*\.(?:py|rs|cs|go|js|ts|toml|md|json|yml|yaml|cpp|h|kt))")
ISSUE_RE = re.compile(r"#(\d+)")


@dataclass
class BreakingItem:
    """A single bullet or sub-heading inside a Breaking section."""

    version: str
    raw: str
    kind: str  # "subheading" | "bullet"
    line_no: int
    keywords: list[str] = field(default_factory=list)


def parse_version_file() -> str | None:
    if not VERSION_FILE.exists():
        return None
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    return text or None


def parse_pyproject_version() -> tuple[str | None, str]:
    """Return (version, kind) where kind is 'literal' or 'file' or 'missing'."""
    if not PYPROJECT.exists():
        return None, "missing"
    text = PYPROJECT.read_text(encoding="utf-8")
    # literal: version = "X.Y.Z"
    m = re.search(r'^\s*version\s*=\s*"(?P<v>\d+\.\d+\.\d+[^"\s]*)"', text, re.MULTILINE)
    if m:
        return m.group("v"), "literal"
    # file pointer: version = {file = "VERSION"}
    m = re.search(r'^\s*version\s*=\s*\{\s*file\s*=\s*"(?P<f>[^"]+)"\s*\}', text, re.MULTILINE)
    if m:
        return m.group("f"), "file"
    return None, "missing"


def extract_keywords(raw: str) -> list[str]:
    """Pick out distinctive tokens that should appear in a migration doc.

    Priority order (most discriminating first):
      1. Backticked identifiers (`Generator`, `--mb-istft`, ...)
      2. CLI flags (--foo-bar) outside backticks
      3. File paths (something.py)

    Falls back to the lowercase ASCII alphabetic words of length >= 4 if
    nothing else is found, which catches plain-English breaking change
    descriptions.
    """
    keywords: list[str] = []
    for m in BACKTICK_RE.finditer(raw):
        token = m.group(1).strip()
        if token:
            keywords.append(token)
    for m in FLAG_RE.finditer(raw):
        keywords.append(m.group(1))
    for m in PATH_RE.finditer(raw):
        keywords.append(m.group(1))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    if unique:
        return unique

    # Fallback: ASCII alphabetic words of length >= 4 (avoid noise like "the").
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", raw)
    stop = {"this", "that", "with", "from", "into", "have", "been", "when", "will", "Breaking", "breaking", "changes", "Changes"}
    return [w for w in words if w not in stop][:5]


def iter_changelog_sections(text: str):
    """Yield (version, start_line, end_line) tuples for each released ## [X.Y.Z] block.

    `## [Unreleased]` is skipped.
    """
    lines = text.splitlines()
    headers: list[tuple[int, str | None]] = []
    for i, line in enumerate(lines):
        if UNRELEASED_HEADER_RE.match(line):
            headers.append((i, None))
        else:
            m = VERSION_HEADER_RE.match(line)
            if m:
                headers.append((i, m.group("ver")))
    headers.append((len(lines), "__sentinel__"))
    for idx in range(len(headers) - 1):
        start, ver = headers[idx]
        end = headers[idx + 1][0]
        if ver is None or ver == "__sentinel__":
            continue
        yield ver, start, end


def collect_breaking_items(text: str) -> list[BreakingItem]:
    lines = text.splitlines()
    items: list[BreakingItem] = []

    for version, start, end in iter_changelog_sections(text):
        i = start + 1
        in_breaking_section = False   # inside `### Changed (Breaking)` heading
        bullets_active = False        # current bullet group is breaking
        last_subheading: str | None = None

        while i < end:
            line = lines[i]
            if ANY_LEVEL2_RE.match(line):
                break

            is_breaking_heading = any(p.match(line) for p in BREAKING_HEADING_PATTERNS)
            is_bold_breaking = any(p.match(line) for p in BREAKING_BOLD_PATTERNS)
            is_other_bold_marker = (
                ANY_BOLD_MARKER_RE.match(line) is not None and not is_bold_breaking
            )

            if is_breaking_heading:
                in_breaking_section = True
                bullets_active = True
                last_subheading = None
                i += 1
                continue

            # Another ### heading ends the breaking region.
            if ANY_LEVEL3_RE.match(line):
                in_breaking_section = False
                bullets_active = False
                last_subheading = None
                i += 1
                continue

            if not in_breaking_section:
                i += 1
                continue

            # Sub-heading inside breaking region -- record it as a breaking item
            # AND reset bullet tracking (bullets immediately after a #### are
            # treated as breaking by default until a non-breaking bold marker
            # appears).
            m_sub = SUBSECTION_HEADER_RE.match(line)
            if m_sub:
                raw = m_sub.group(1)
                items.append(BreakingItem(
                    version=version,
                    raw=raw,
                    kind="subheading",
                    line_no=i + 1,
                    keywords=extract_keywords(raw),
                ))
                last_subheading = raw
                bullets_active = True
                i += 1
                continue

            if is_bold_breaking:
                bullets_active = True
                i += 1
                continue

            if is_other_bold_marker:
                # Descriptive scaffolding marker like **保持される CLI:** or
                # **影響を受ける呼び出しパターン:**. Suppress bullet attribution
                # until the next sub-heading / breaking marker resets it.
                bullets_active = False
                i += 1
                continue

            m_bullet = BULLET_RE.match(line)
            if m_bullet and bullets_active:
                raw = m_bullet.group(1)
                # Skip purely descriptive lead-in bullets that just frame
                # the "before vs after" contrast (e.g. starting with
                # "**v1.11" or "**v1.12"). These are not standalone
                # breaking items -- they pair with the surrounding sub-heading.
                if not re.match(r"^\*\*v?\d+\.\d+", raw):
                    items.append(BreakingItem(
                        version=version,
                        raw=raw,
                        kind="bullet",
                        line_no=i + 1,
                        keywords=extract_keywords(raw),
                    ))
            i += 1

    return items


def find_migration_doc(version: str) -> Path | None:
    """Find docs/migration/v<prev>-to-v<version>.md for given version.

    Falls back to a glob that ends with '-to-v<X.Y>.md' (without patch).
    """
    major_minor = ".".join(version.split(".")[:2])
    candidates = sorted(MIGRATION_DIR.glob("*.md")) if MIGRATION_DIR.exists() else []
    # Exact major.minor match first.
    for p in candidates:
        if p.name.endswith(f"-to-v{major_minor}.md"):
            return p
        if p.name.endswith(f"-to-v{version}.md"):
            return p
    # Any file containing the version anywhere in the name.
    for p in candidates:
        if version in p.name or major_minor in p.name:
            return p
    return None


def check_item_covered(item: BreakingItem, doc_text_lower: str) -> tuple[bool, list[str]]:
    """Return (covered, matched_keywords)."""
    if not item.keywords:
        # If we extracted nothing, treat as covered iff the raw line text
        # itself appears somewhere in the doc.
        if item.raw.lower() in doc_text_lower:
            return True, [item.raw]
        return False, []
    matched = [kw for kw in item.keywords if kw.lower() in doc_text_lower]
    return bool(matched), matched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--verbose", action="store_true", help="Print keyword sets matched per item.")
    args = parser.parse_args()

    failures: list[str] = []
    info: list[str] = []

    if not CHANGELOG.exists():
        print(f"ERROR: {CHANGELOG} not found", file=sys.stderr)
        return 1

    changelog_text = CHANGELOG.read_text(encoding="utf-8")

    # ---- 1. Version consistency: VERSION <-> pyproject.toml <-> latest CHANGELOG ----
    version_str = parse_version_file()
    py_value, py_kind = parse_pyproject_version()

    if version_str is None:
        failures.append("VERSION file is missing or empty")
    if py_kind == "missing":
        failures.append("pyproject.toml has no `version = ...` line")
    elif py_kind == "literal" and version_str and py_value != version_str:
        failures.append(
            f"pyproject.toml literal version {py_value!r} != VERSION {version_str!r}"
        )
    elif py_kind == "file":
        # pyproject points at VERSION file -- ensure it matches.
        resolved = (REPO_ROOT / py_value).resolve()
        if resolved != VERSION_FILE.resolve():
            failures.append(
                f"pyproject.toml `version = {{file = {py_value!r}}}` "
                f"does not resolve to {VERSION_FILE}"
            )

    # Latest released CHANGELOG version.
    latest_release: str | None = None
    for ver, _start, _end in iter_changelog_sections(changelog_text):
        latest_release = ver
        break

    if latest_release is None:
        failures.append("CHANGELOG.md has no released `## [X.Y.Z]` section")
    elif version_str and latest_release != version_str:
        # Allow VERSION to be ahead of CHANGELOG (release-in-progress) but
        # never behind. Behind means we shipped without updating CHANGELOG.
        from_v = tuple(int(x) for x in version_str.split("."))
        to_v = tuple(int(x) for x in latest_release.split("."))
        if from_v < to_v:
            failures.append(
                f"VERSION {version_str!r} is behind latest CHANGELOG entry {latest_release!r}"
            )
        else:
            info.append(
                f"VERSION {version_str!r} is ahead of latest CHANGELOG entry "
                f"{latest_release!r} (release in progress, OK)"
            )

    # ---- 2. Breaking-change <-> migration-doc parity ----
    items = collect_breaking_items(changelog_text)

    # Group items by version for clearer reporting.
    by_version: dict[str, list[BreakingItem]] = {}
    for it in items:
        by_version.setdefault(it.version, []).append(it)

    total_items = 0
    covered_items = 0
    for version, vitems in sorted(by_version.items()):
        doc = find_migration_doc(version)
        if doc is None or not doc.exists():
            failures.append(
                f"v{version} has {len(vitems)} breaking item(s) but no migration doc "
                f"found under {MIGRATION_DIR.relative_to(REPO_ROOT)}/"
            )
            total_items += len(vitems)
            continue
        doc_text_lower = doc.read_text(encoding="utf-8").lower()
        for it in vitems:
            total_items += 1
            covered, matched = check_item_covered(it, doc_text_lower)
            if covered:
                covered_items += 1
                if args.verbose:
                    info.append(
                        f"  [OK] v{version} L{it.line_no} ({it.kind}): matched {matched!r}"
                    )
            else:
                preview = it.raw if len(it.raw) <= 100 else it.raw[:97] + "..."
                failures.append(
                    f"v{version} CHANGELOG L{it.line_no} ({it.kind}) NOT covered in "
                    f"{doc.relative_to(REPO_ROOT)}: {preview!r} "
                    f"(searched keywords: {it.keywords[:6]})"
                )

    # ---- Report ----
    print(f"CHANGELOG <-> migration parity gate")
    print(f"  VERSION:        {version_str!r}")
    print(f"  pyproject.toml: {py_value!r} ({py_kind})")
    print(f"  latest CHANGELOG release: {latest_release!r}")
    print(f"  breaking items: {covered_items}/{total_items} covered")
    if info:
        for line in info:
            print(line)

    if failures:
        print()
        print("FAIL: parity gate detected drift:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
