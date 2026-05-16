#!/usr/bin/env python3
"""Pre-commit config file: regex coverage gate.

Validates that each ``files:`` regex inside ``.pre-commit-config.yaml`` is
not silently mis-anchored. Two failure modes have been observed in past PRs:

  1. **basename-style alternation anchored at repo root** — PR #496 introduced
     a hook gated on ``^(CMakeLists\\.txt|...)$`` which only fires for
     repo-root files; every ``src/.../CMakeLists.txt`` slipped through.
     The fix was to prepend ``(^|/)``.
  2. **regex matches no tracked file** — the hook quietly never runs. Often a
     typo in the path (e.g. ``src/python_run/requirements.txt`` was missing
     from the ort-version-sync hook in PR #496).

This gate flags both classes by:

  - parsing each ``- id: ...`` block out of ``.pre-commit-config.yaml`` (text
    parse, no PyYAML dependency — the file uses unsafe-yaml-only features
    like ``!reference`` which PyYAML can't parse without ``--unsafe``)
  - extracting the ``files:`` regex (handles single-line and block forms)
  - running the regex against ``git ls-files`` output
  - reporting hooks whose regex matched zero files, and hooks that use
    basename alternation without a path-anchor escape

Exit codes:
    0  -- all hook regexes appear well-anchored and match at least one path
    1  -- drift detected (printed report)

Usage:
    python scripts/check_precommit_file_regex.py

The script is informational by default — known-good hooks that match zero
files in the current tree (e.g. CHANGELOG-cleanup gate when no release tag
is staged) can be allowlisted in ``ALLOW_ZERO_MATCH`` below.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"

ALLOW_ZERO_MATCH: set[str] = {
    # hooks whose regex intentionally fires only on rare paths
    "changelog-unreleased-cleanup",
}


def list_tracked_files() -> list[str]:
    """Return git-tracked files as repo-relative paths."""
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def parse_hooks(config_text: str) -> list[tuple[str, str, int]]:
    """Yield (hook_id, files_regex, line_number) for each local hook.

    Handles two regex forms:
        files: ^(a|b)$
        files: |
          (?x)^(
            a |
            b
          )$

    Block-style continuation stops at the next key (``entry:`` / ``language:``
    / ``- id:``) at the same or shallower indentation.
    """
    hooks: list[tuple[str, str, int]] = []
    lines = config_text.splitlines()
    i = 0
    current_id: str | None = None
    current_id_line = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        m_id = re.match(r"-\s+id:\s+([\w-]+)", stripped)
        if m_id:
            current_id = m_id.group(1)
            current_id_line = i + 1
            i += 1
            continue

        m_files = re.match(r"files:\s*(.*)", stripped)
        if m_files and current_id is not None:
            value = m_files.group(1).strip()
            if value in ("|", ">", "|-", ">-"):
                # block scalar — collect until indentation drops back to
                # the `files:` key's column (or shallower). Determine the
                # actual inner indent from the FIRST non-empty continuation
                # line rather than hard-coding `base_indent + 2` (4-space
                # styles, deeply nested hooks, or tab indentation made the
                # hard-coded slice produce mis-stripped fragments).
                base_indent = len(line) - len(line.lstrip())
                block: list[str] = []
                inner_indent: int | None = None
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if not next_line.strip():
                        block.append("")
                        i += 1
                        continue
                    indent = len(next_line) - len(next_line.lstrip())
                    if indent <= base_indent:
                        break
                    if inner_indent is None:
                        inner_indent = indent
                    # Strip the detected inner indent (or whichever is smaller
                    # in case YAML mixes deeper nesting inside the block).
                    strip_n = min(inner_indent, indent)
                    block.append(next_line[strip_n:])
                    i += 1
                regex = "\n".join(line for line in block if line.strip()).strip()
                hooks.append((current_id, regex, current_id_line))
                continue

            # single-line — strip trailing comment / quotes
            value = re.sub(r"\s+#.*$", "", value)
            if value.startswith(("'", '"')) and value.endswith(value[0]):
                value = value[1:-1]
            hooks.append((current_id, value, current_id_line))

        i += 1

    return hooks


def regex_is_root_only_basename_alternation(regex: str) -> bool:
    """Return True for ``^(name1|name2)$``-style alternations missing ``(^|/)``.

    The pattern that triggered PR #496: an alternation of bare filenames
    anchored only to repo root (``^(...)$``). Such a regex never fires for
    ``src/.../CMakeLists.txt``, defeating the intent. Adding ``(^|/)`` (or
    ``(?:^|/)``) before the alternation fixes it.
    """
    # Compact whitespace; verbose form is fine to inspect this way too.
    compact = re.sub(r"\s+", "", regex)
    # Strip verbose-mode flag
    compact = compact.removeprefix("(?x)")
    m = re.match(r"^\^\(([^)]+)\)\$$", compact)
    if not m:
        return False
    alternatives = m.group(1).split("|")
    # If every alternative looks like a bare filename (no path separator,
    # no anchor), we likely intended (^|/) prefix.
    bare = [alt for alt in alternatives if "/" not in alt and "^" not in alt]
    return len(bare) == len(alternatives) and len(bare) >= 2


def test_regex(regex: str, tracked: list[str]) -> int:
    """Count matches for a hook regex against tracked files."""
    flags = 0
    pattern = regex.strip()
    if pattern.startswith("(?x)"):
        flags |= re.VERBOSE
        pattern = pattern[len("(?x)") :]
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        print(f"  ! regex compile error: {exc}", file=sys.stderr)
        return -1
    return sum(1 for path in tracked if compiled.search(path))


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"error: {CONFIG_PATH} not found", file=sys.stderr)
        return 1

    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    hooks = parse_hooks(config_text)
    tracked = list_tracked_files()

    failures: list[str] = []
    warnings_: list[str] = []

    for hook_id, regex, line_no in hooks:
        if not regex:
            continue
        if regex_is_root_only_basename_alternation(regex):
            failures.append(
                f"  [{hook_id}] (line {line_no}): basename alternation anchored "
                f"only at repo root — nested files will not match.\n"
                f"    regex: {regex}\n"
                f"    fix:   prepend `(^|/)` so `src/.../CMakeLists.txt` matches"
            )
        matches = test_regex(regex, tracked)
        if matches == 0 and hook_id not in ALLOW_ZERO_MATCH:
            warnings_.append(
                f"  [{hook_id}] (line {line_no}): regex matches ZERO tracked files\n"
                f"    regex: {regex}"
            )
        elif matches == -1:
            failures.append(f"  [{hook_id}] (line {line_no}): regex failed to compile")

    if failures:
        print("file-path regex gate: errors", file=sys.stderr)
        for line in failures:
            print(line, file=sys.stderr)
    if warnings_:
        print("\nfile-path regex gate: zero-match warnings", file=sys.stderr)
        for line in warnings_:
            print(line, file=sys.stderr)
        print(
            "\nzero-match hooks never fire. either delete them, fix the path, "
            "or allowlist in ALLOW_ZERO_MATCH inside this script.",
            file=sys.stderr,
        )

    if failures or warnings_:
        return 1
    print(f"file-path regex gate OK: {len(hooks)} hook regex inspected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
