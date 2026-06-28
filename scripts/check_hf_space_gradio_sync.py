#!/usr/bin/env python3
"""HF Space gradio version sync gate.

Hugging Face Spaces (Gradio SDK) installs gradio twice during the Docker
build:

  1. From the README.md frontmatter ``sdk_version: X.Y.Z`` -- HF Spaces
     hardcodes this into the build step as ``gradio[oauth,mcp]==X.Y.Z``.
  2. From ``requirements.txt`` -- when the file pins ``gradio==A.B.C``.

If X.Y.Z != A.B.C, the two appear in a single ``pip install ...`` command and
pip resolves the conflict to exit code 1. The HF Space then shows
``BUILD_ERROR`` with the misleading message ``Reason: cache miss`` (the real
pip error is buried in the build log).

This script enforces ``X.Y.Z == A.B.C`` so Dependabot bumps that only touch
``requirements.txt`` cannot silently drift away from the SDK version pinned
in the README frontmatter.

Usage:
    python scripts/check_hf_space_gradio_sync.py

Exit codes:
    0 -- versions match (or both fields absent in the same way)
    1 -- versions disagree, or one of the files is missing/malformed
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "huggingface-space" / "README.md"
REQUIREMENTS = REPO_ROOT / "huggingface-space" / "requirements.txt"


def _extract_frontmatter_sdk_version(readme_path: Path) -> str | None:
    """Return the ``sdk_version`` value from the README YAML frontmatter.

    Returns None if no frontmatter / no ``sdk_version`` line.
    """
    if not readme_path.exists():
        return None
    text = readme_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter = text[3:end]
    for line in frontmatter.splitlines():
        line = line.strip()
        if line.startswith("sdk_version:"):
            value = line.split(":", 1)[1].strip()
            # strip optional quotes
            return value.strip("\"'")
    return None


_REQ_GRADIO_RE = re.compile(r"^\s*gradio\s*==\s*([^\s#;]+)")


def _extract_requirements_gradio(req_path: Path) -> str | None:
    """Return the pinned gradio version from requirements.txt.

    Only ``gradio==X`` (exact pin) is recognized. ``gradio`` / ``gradio>=X`` /
    ``gradio[extras]==X`` are NOT matched (the HF build always uses an exact
    SDK pin, so an inexact requirements pin is a separate problem to fix).
    """
    if not req_path.exists():
        return None
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        m = _REQ_GRADIO_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def main() -> int:
    sdk_version = _extract_frontmatter_sdk_version(README)
    req_version = _extract_requirements_gradio(REQUIREMENTS)

    errors: list[str] = []

    if sdk_version is None:
        errors.append(
            f"{README.relative_to(REPO_ROOT)}: no `sdk_version:` line in "
            "frontmatter (HF Space cannot determine the gradio runtime version)"
        )
    if req_version is None:
        errors.append(
            f"{REQUIREMENTS.relative_to(REPO_ROOT)}: no `gradio==X.Y.Z` exact "
            "pin found (HF build expects this to match the README sdk_version)"
        )

    if sdk_version and req_version and sdk_version != req_version:
        errors.append(
            "HF Space gradio version drift detected:\n"
            f"  {README.relative_to(REPO_ROOT)} sdk_version: {sdk_version}\n"
            f"  {REQUIREMENTS.relative_to(REPO_ROOT)} gradio==        {req_version}\n"
            "  These MUST match. HF Spaces injects gradio[oauth,mcp]=={sdk_version} "
            "into the pip install command alongside requirements.txt, and pip "
            "fails to resolve two different versions in one resolve pass "
            "(BUILD_ERROR with misleading 'cache miss' message)."
        )

    if errors:
        print("HF Space gradio sync check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nTo fix: edit either huggingface-space/README.md "
            "(sdk_version) or huggingface-space/requirements.txt (gradio==) "
            "so the two values agree."
        )
        return 1

    print(
        f"OK: gradio sdk_version ({sdk_version}) == requirements.txt pin "
        f"({req_version})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
