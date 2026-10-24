#!/usr/bin/env python3
"""Security floor gate for Python dependencies (Issue #709).

`docs/spec/dependency-floors.toml` lists, per package, the lowest version
outside the affected range of the advisories it was raised for. This gate
fails when:

  - a `<package>>=X` declaration (pyproject.toml, requirements*.txt, or a
    workflow `pip install`) has X below the minimum,
  - a uv.lock resolves the package below the minimum,
  - no declaration of the package is found (a gate that checks nothing must
    not pass), or
  - a workflow still suppresses one of the fixed advisories
    (`--ignore-vuln <id>` / `allow-ghsas: <id>`).

The last check exists because of #588: the floor `nltk>=3.9.4` sat inside the
affected range `<= 3.9.4`, and the pip-audit suppression kept the audit green
while a resolution could pick the vulnerable version.

Usage:
    python scripts/check_dependency_floors.py

Exit codes:
    0 -- every floor is satisfied
    1 -- a violation was found (each one is listed)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.version import Version
from platform_utils import force_utf8_output


REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "dependency-floors.toml"

DECLARATION_FILE_RE = re.compile(
    r"(^|/)(pyproject\.toml|requirements[^/]*\.txt)$|^\.github/workflows/[^/]+\.ya?ml$",
)
LOCK_FILE_RE = re.compile(r"(^|/)uv\.lock$")
WORKFLOW_RE = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")


def load_floors(path: Path) -> list[dict]:
    with path.open("rb") as f:
        return tomllib.load(f)["floor"]


def collect_files(repo_root: Path) -> dict[str, str]:
    """Return {repo-relative path: text} for every tracked file the gate reads."""
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files: dict[str, str] = {}
    for rel in out.splitlines():
        if DECLARATION_FILE_RE.search(rel) or LOCK_FILE_RE.search(rel):
            files[rel] = (repo_root / rel).read_text(encoding="utf-8")
    return files


def _floor_re(package: str) -> re.Pattern[str]:
    # Comment lines are skipped: history notes name old floors on purpose.
    return re.compile(
        rf"^(?!\s*#).*?(?<![\w.-]){re.escape(package)}(?:\[[^\]]*\])?\s*>=\s*"
        rf"([0-9][0-9A-Za-z.]*)",
        re.IGNORECASE | re.MULTILINE,
    )


def _lock_re(package: str) -> re.Pattern[str]:
    return re.compile(
        rf'^name = "{re.escape(package)}"\nversion = "([^"]+)"',
        re.MULTILINE,
    )


def _suppression_re(advisory: str) -> re.Pattern[str]:
    # Only live YAML / shell, not comments: the line must not start with `#`.
    return re.compile(
        rf"^(?!\s*#).*(--ignore-vuln\s+|allow-ghsas:.*)\b{re.escape(advisory)}\b",
        re.MULTILINE,
    )


def check(files: dict[str, str], floors: list[dict]) -> list[str]:
    errors: list[str] = []
    for floor in floors:
        package = floor["package"]
        minimum = Version(floor["minimum"])
        found = 0
        for rel, text in sorted(files.items()):
            if DECLARATION_FILE_RE.search(rel):
                for m in _floor_re(package).finditer(text):
                    found += 1
                    if Version(m.group(1)) < minimum:
                        line = text.count("\n", 0, m.start()) + 1
                        errors.append(
                            f"{rel}:{line}: {package}>={m.group(1)} is below the "
                            f"security floor {minimum} (issue #{floor['issue']})",
                        )
            if LOCK_FILE_RE.search(rel):
                for m in _lock_re(package).finditer(text):
                    if Version(m.group(1)) < minimum:
                        errors.append(
                            f"{rel}: resolves {package} {m.group(1)}, below the "
                            f"security floor {minimum} (issue #{floor['issue']})",
                        )
            if WORKFLOW_RE.search(rel):
                for advisory in floor.get("fixed_advisories", []):
                    for m in _suppression_re(advisory).finditer(text):
                        line = text.count("\n", 0, m.start()) + 1
                        errors.append(
                            f"{rel}:{line}: still suppresses {advisory}, which "
                            f"the {package}>={minimum} floor already fixes; "
                            f"remove the suppression",
                        )
        if found == 0:
            errors.append(
                f"no floor declaration of {package} was found; the spec lists "
                f"it, so a declaration was renamed or removed",
            )
    return errors


def main() -> int:
    force_utf8_output()
    errors = check(collect_files(REPO_ROOT), load_floors(SPEC))
    if errors:
        print("Dependency security floor violations:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nSpec: {SPEC.relative_to(REPO_ROOT).as_posix()}")
        return 1
    print("All dependency security floors are satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
