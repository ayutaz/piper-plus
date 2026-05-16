#!/usr/bin/env python3
"""Detect host-specific secret-path references in committed sources.

Background:
    CLAUDE.md's training template shows
    ``export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2)``
    as an instruction for the maintainer's environment. That path is safe in
    documentation, but if it leaks into Python / shell scripts / workflows
    that downstream users run, every fresh clone will hit:

    1. A confusing ``grep: /data/piper/.env: No such file or directory``
       error in CI or contributor environments.
    2. A working assumption that a private filesystem location exists
       cross-machine, encouraging future code to hardcode the same path.

This hook flags those references early. Documentation files (``CLAUDE.md``,
``README*.md``, ``docs/**``) are intentionally exempt because they describe
the maintainer's setup; the rule targets *executable* code (sources,
workflows, configs that get executed) only.

Detection rule (conservative — prefer false-negative over false-positive):

- Path: literal string ``/data/piper/`` (with trailing slash, ie. the
  maintainer's filesystem mount, not the broader ``/data/`` namespace).
- Hosts: any file under tracked directories matching the EXECUTABLE_GLOBS
  list below.
- Skip: comments-only references are still flagged — comments leak into
  shell history when copy-pasted, so they're not safer than code.

Exit codes:
    0  -- no references found
    1  -- references found; offending file:line printed to stderr

Override:
    Add the offending file to ALLOWLIST below. Document why.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Path pattern that means "the maintainer's training-machine layout".
# Keep the trailing slash so we don't flag legitimate references to
# ``/data/`` (e.g., dataset README prose about generic data directories).
SECRET_PATH_PATTERNS: tuple[str, ...] = (
    "/data/piper/.env",
    "/data/piper/",
)

# Files whose JOB is to describe the maintainer's environment. Refs are
# documentation, not executable instructions — exempt.
DOC_PATH_PREFIXES: tuple[str, ...] = (
    "CLAUDE.md",
    "README",  # README.md / README_EN.md / README.*.md
    "docs/",
    "CHANGELOG.md",
    "CHANGELOG-archive.md",
    "CONTRIBUTING",
)

# Files explicitly allowed to keep the reference. Document why each entry
# exists. Additions should require a code review.
ALLOWLIST: frozenset[str] = frozenset({
    # This script defines the pattern itself; literal strings here are
    # detection rules, not actual references.
    "scripts/check_secret_path_reference.py",
    # Guard hook: defines patterns to BLOCK at exec time. The path literals
    # are part of the deny-list, not a usage of the path.
    ".claude/hooks/guard-bash.sh",
    # Training data-preparation scripts: docstring usage examples documenting
    # the maintainer's actual dataset layout. The scripts themselves accept
    # arbitrary --paths via argparse; example paths are not hardcoded
    # behaviour. Pre-existing as of the hook's introduction.
    "src/python/piper_train/tools/prepare_multilingual_dataset.py",
    "src/python/piper_train/tools/prepare_bilingual_dataset.py",
})

# File extensions / globs of *executable* artifacts. References here are
# the ones we want to catch.
EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".rs",
    ".go",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".js",
    ".ts",
    ".mjs",
    ".cjs",
    ".kt",
    ".kts",
    ".swift",
    ".gradle",
    ".cmake",
    "CMakeLists.txt",
    "Dockerfile",
    "Makefile",
})


def _is_executable_file(path: Path) -> bool:
    """Return True if ``path``'s suffix/name is in the EXECUTABLE list."""
    if path.suffix in EXECUTABLE_EXTENSIONS:
        return True
    return path.name in EXECUTABLE_EXTENSIONS


def _is_doc_file(rel_path: str) -> bool:
    """Return True if ``rel_path`` is documentation (exempt)."""
    return any(rel_path.startswith(p) for p in DOC_PATH_PREFIXES)


def _check_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of ``(line_no, pattern, line_content)`` matches."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pat in SECRET_PATH_PATTERNS:
            if pat in line:
                hits.append((i, pat, line.rstrip()))
                break  # one hit per line is enough
    return hits


def main(argv: list[str]) -> int:
    # pre-commit passes staged file paths as argv; if none given, scan all
    # tracked files via the `git ls-files` equivalent (limited to executable
    # extensions) — but only when run manually.
    if argv:
        paths = [Path(p) for p in argv]
    else:
        # Manual full-repo scan fallback. pre-commit always passes paths,
        # so this branch is only hit when developer runs the script directly.
        paths = []
        for ext in EXECUTABLE_EXTENSIONS:
            if ext.startswith("."):
                paths.extend(REPO_ROOT.rglob(f"*{ext}"))
            else:
                paths.extend(REPO_ROOT.rglob(ext))

    failures: list[tuple[str, int, str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        if rel in ALLOWLIST:
            continue
        if _is_doc_file(rel):
            continue
        if not _is_executable_file(path):
            continue
        for line_no, pat, content in _check_file(path):
            failures.append((rel, line_no, pat, content))

    if not failures:
        print(
            f"OK: scanned {len(paths)} file(s); no host-specific secret path "
            f"references found ({len(ALLOWLIST)} files allowlisted)."
        )
        return 0

    print(
        f"ERROR: {len(failures)} reference(s) to host-specific secret path(s) "
        "found in *executable* files:",
        file=sys.stderr,
    )
    for rel, line_no, pat, content in failures:
        print(f"  {rel}:{line_no}: matched '{pat}'", file=sys.stderr)
        print(f"    {content}", file=sys.stderr)
    print(
        "\nWhy this fails: paths like /data/piper/.env are specific to the "
        "maintainer's training machine. References in *executable* code "
        "(scripts/workflows/sources) will break for any other user.",
        file=sys.stderr,
    )
    print(
        "\nFix options:",
        file=sys.stderr,
    )
    print(
        "  - Use an env var (e.g., WANDB_API_KEY) and document the source "
        "in CLAUDE.md / docs/, not in code.",
        file=sys.stderr,
    )
    print(
        "  - Move the reference into a documentation file (README, "
        "CLAUDE.md, docs/), which is exempt from this check.",
        file=sys.stderr,
    )
    print(
        "  - If the file genuinely needs this path, add an entry to "
        "ALLOWLIST in scripts/check_secret_path_reference.py with a "
        "justification comment.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
