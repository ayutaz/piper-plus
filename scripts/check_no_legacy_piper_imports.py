#!/usr/bin/env python3
"""Detect legacy ``import piper`` / ``from piper import`` references in sources.

Background:
    piper-plus v2.0 renamed the Python runtime module from ``piper`` to
    ``piper_plus`` (see ``docs/design/piper-plus-module-rename-v2.md`` §9,
    "co-install fallback risk", tracked in Issue #590). The bare top-level
    ``piper`` module now belongs to upstream ``piper-tts`` on PyPI. If our
    own sources still contain ``from piper import ...`` or ``import piper``
    while both packages are installed in the same environment, Python
    silently resolves the name to whichever wheel happens to win the
    ``sys.path`` race — most often upstream ``piper-tts``. The failure
    is silent, produces subtly different audio (different phonemizer,
    different Voice class), and only surfaces when users open a bug
    against us for behaviour that is actually upstream's.

    §9 of the rename design flags this as the highest-severity carryover
    risk from the rename. This gate is the static (compile-time) half of
    the mitigation; a runtime co-install detection test is planned in
    Phase 8.

Detection rule (conservative — prefer false-negative over false-positive):

- Matches ``import piper`` (with optional alias / comma / EOL / trailing
  ``#comment``) but NOT ``import piper_train`` / ``import piper_plus`` /
  ``import piper_plus_g2p`` / ``import piper_phonemize`` /
  ``import piper_wyoming``.
- Matches ``from piper import X`` and ``from piper.<submod> import X``
  but NOT ``from piper_train import ...``.
- Scope: repo-wide ``*.py`` files (executable Python only). Non-Python
  formats — Markdown docs, TOML/JSON configs — are exempt; they may
  legitimately quote ``import piper`` as prose (e.g., a migration guide
  showing the deprecated form).
- Skipped path prefixes: ``tests/fixtures/`` (synthetic parser fixtures)
  and ``src/piper_phonemize_bundled/`` (vendored upstream mirror — outside
  the rename contract). Gitignored trees (``.venv/``, ``target/``,
  ``build/``, ``node_modules/``, ``__pycache__/``, ``dist/``) are
  naturally excluded by ``git ls-files``.

False-positive risks (documented so future contributors know when to
extend ALLOWLIST vs. change the source):

1. Docstrings / string literals that quote the legacy import form
   (e.g., a migration-guide example embedded in a ``.py`` source). This
   regex is line-based and cannot tell code from a string. Preferred
   fix: extract the example into a Markdown file (docs/ is not scanned).
   Fallback: add the file to ALLOWLIST with a justification comment.
2. Tests that intentionally exercise co-install detection (planned in
   Phase 8, ``tests/**/test_coinstall_*.py``). Add to ALLOWLIST when
   introduced, not preemptively.
3. This script itself: the regex source is a raw string, not a real
   ``import piper`` statement, and does not match its own pattern
   (branch 2 requires ``import\\s+piper`` at line start after optional
   whitespace, while the source line here has the token embedded in a
   quoted string). Verified by a full-repo dry run.

Exit codes:
    0  -- no legacy references found
    1  -- references found; offending file:line printed to stderr

Override:
    Add the offending file to ALLOWLIST below with a justification.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


# Local import: shared UTF-8 stdout/stderr reconfiguration for Windows consoles
# so gate output (arrows, dashes) doesn't UnicodeEncodeError on cp932/cp1252.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_utils import force_utf8_output  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent

# Single compiled regex; two branches OR'd together.
#
# Branch 1: ``from piper import X`` and ``from piper.<submod> import X``.
#   ``piper`` must be followed by either ``.`` (submodule) or whitespace
#   before ``import`` — a following ``_`` would make it ``piper_train``
#   etc., which is what we want to ALLOW, so ``\s+`` (not ``\w``) after
#   the optional submodule tail rejects that case naturally.
#
# Branch 2: ``import piper`` (with optional ``as alias`` / ``, other`` /
#   comment / EOL).
#   Negative lookahead ``(?![A-Za-z0-9_])`` after literal ``piper``
#   rejects ``piper_train`` / ``piper_plus`` / ``piperclip`` / etc.
LEGACY_IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"from\s+piper(?:\.[A-Za-z_][A-Za-z0-9_.]*)?\s+import\b"
    r"|"
    r"import\s+piper(?![A-Za-z0-9_])"
    r")"
)

# Path prefixes (POSIX-normalized) that are exempt from the check.
# Add entries with a justification comment. Kept minimal on purpose —
# broad skip lists silently accumulate escape hatches.
SKIP_PREFIXES: tuple[str, ...] = (
    # Synthetic Python fixtures for parser/lint testing may contain
    # deliberately malformed or legacy import lines.
    "tests/fixtures/",
    # Vendored upstream mirror. This tree is not under the rename
    # contract — it's a byte-for-byte copy of an external project.
    "src/piper_phonemize_bundled/",
)

# Files explicitly allowed to keep the legacy import form. Document why
# each entry exists. Additions should require code review.
#
# NOTE: Empty at introduction time. The repo-wide `git grep` sweep at
# gate-authoring time returned zero hits, so no bootstrap entries were
# needed. Future entries are expected to fall into the categories listed
# in the module docstring under "False-positive risks".
ALLOWLIST: frozenset[str] = frozenset()


def _is_python_file(path: Path) -> bool:
    """Return True if ``path`` is a ``.py`` source file."""
    return path.suffix == ".py"


def _should_skip(rel_posix: str) -> bool:
    """Return True if ``rel_posix`` matches a SKIP_PREFIX or ALLOWLIST entry."""
    if rel_posix in ALLOWLIST:
        return True
    return any(rel_posix.startswith(p) for p in SKIP_PREFIXES)


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of ``(line_no, matched_line)`` legacy-import hits."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # Rare binary-ish .py (generated resource files) — skip, matching
        # the check_secret_path_reference.py convention.
        return []
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if LEGACY_IMPORT_RE.match(line):
            hits.append((i, line.rstrip()))
    return hits


def _iter_repo_python_files() -> list[Path]:
    """Enumerate tracked ``*.py`` files via ``git ls-files``.

    Falls back to ``rglob`` with explicit ignore dirs when not in a git
    checkout (e.g., release tarball), mirroring
    ``scripts/check_secret_path_reference.py``.
    """
    try:
        tracked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="replace")
        return [REPO_ROOT / p for p in tracked.split("\0") if p and p.endswith(".py")]
    except (OSError, subprocess.CalledProcessError):
        _IGNORE_DIRS = {
            "build",
            ".venv",
            "venv",
            "node_modules",
            "target",
            "dist",
            ".git",
            "__pycache__",
            ".mypy_cache",
        }
        return [
            p
            for p in REPO_ROOT.rglob("*.py")
            if p.is_file()
            and not _IGNORE_DIRS.intersection(p.relative_to(REPO_ROOT).parts)
        ]


def main(argv: list[str]) -> int:
    force_utf8_output()

    # pre-commit passes staged file paths as argv; if none given, do a
    # full-repo sweep (manual invocation / release-time audit).
    if argv:
        paths = [Path(p) for p in argv]
    else:
        paths = _iter_repo_python_files()

    failures: list[tuple[str, int, str]] = []
    scanned = 0
    for path in paths:
        if not path.is_file():
            continue
        if not _is_python_file(path):
            continue
        try:
            # as_posix() — forward slashes on every OS so SKIP_PREFIXES /
            # ALLOWLIST entries (which use "/") match on Windows too.
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        if _should_skip(rel):
            continue
        scanned += 1
        for line_no, content in _check_file(path):
            failures.append((rel, line_no, content))

    if not failures:
        print(
            f"OK: scanned {scanned} *.py file(s); no legacy `import piper` / "
            f"`from piper import` references found "
            f"({len(ALLOWLIST)} files allowlisted, "
            f"{len(SKIP_PREFIXES)} path prefix(es) skipped)."
        )
        return 0

    print(
        f"ERROR: {len(failures)} legacy `piper` import reference(s) found:",
        file=sys.stderr,
    )
    for rel, line_no, content in failures:
        print(f"  {rel}:{line_no}: {content}", file=sys.stderr)
    print(
        "\nWhy this fails: piper-plus v2.0 renamed the runtime module from "
        "`piper` to `piper_plus`. The bare top-level `piper` module now "
        "belongs to upstream `piper-tts` on PyPI. When both packages are "
        "installed in the same environment (co-install), `from piper "
        "import ...` silently resolves to whichever wheel wins the sys.path "
        "race — typically upstream — and users see subtly wrong behaviour "
        "that they attribute to piper-plus.",
        file=sys.stderr,
    )
    print(
        "\nSee: docs/design/piper-plus-module-rename-v2.md §9 "
        "(silent fallback to upstream `piper-tts` PiperVoice) and "
        "Issue #590.",
        file=sys.stderr,
    )
    print(
        "\nFix options:",
        file=sys.stderr,
    )
    print(
        "  - Rename to `piper_plus` (canonical): "
        "`from piper_plus import PiperVoice`, `import piper_plus`.",
        file=sys.stderr,
    )
    print(
        "  - If the import is inside a docstring / string literal "
        "(migration example, changelog snippet), extract it to a Markdown "
        "file under `docs/` — Markdown is not scanned.",
        file=sys.stderr,
    )
    print(
        "  - If the file legitimately needs the legacy form (e.g., a "
        "co-install detection test), add its repo-relative POSIX path to "
        "ALLOWLIST in scripts/check_no_legacy_piper_imports.py with a "
        "justification comment.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
