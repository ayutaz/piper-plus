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

A third pin site is also checked: ``src/python_run/requirements_webui.txt``.
Its rationale is **different** from the two above -- it is not part of the HF
Space build, so it cannot trigger the pip resolve failure. It is included
because leaving it out lets the security floor rot in exactly one place:

  * That file sat at ``gradio==6.14.0`` while carrying CVE-2026-48545
    (Cookie Injection via Shared Proxy Client, gradio < 6.15.0).
  * After it was brought to 6.21.0 to match the HF Space, the HF Space pair
    later moved to 6.26.0 -- and this file was left behind again, because the
    gate only covered the two HF files.

It is user-facing (all 8 README translations tell users to run
``uv pip install -r src/python_run/requirements_webui.txt``) and is COPYed by
``docker/webui/Dockerfile`` and ``docker/python-inference/Dockerfile``
(plus ``.cpu``), so one drift reaches both manual installs and the images.

This mirrors the existing ``scripts/check_ruff_version_sync.py`` convention:
several pin sites for one tool must agree exactly, and the gate names every
site so a removed pin cannot make the check silently pass.

Usage:
    python scripts/check_hf_space_gradio_sync.py

Exit codes:
    0 -- all three pin sites agree exactly
    1 -- any pair disagrees, or a file is missing / malformed /
         contains an empty pin
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "huggingface-space" / "README.md"
REQUIREMENTS = REPO_ROOT / "huggingface-space" / "requirements.txt"
# HF Space の build には関与しないが、 security floor の drift を防ぐため
# 同期対象に含める (上の docstring 参照)。
WEBUI_REQUIREMENTS = REPO_ROOT / "src" / "python_run" / "requirements_webui.txt"


def _extract_frontmatter_sdk_version(readme_path: Path) -> str | None:
    """Return the ``sdk_version`` value from the README YAML frontmatter.

    Returns None if no frontmatter / no ``sdk_version`` line / the value is
    empty (e.g. ``sdk_version:`` with nothing after the colon) so the caller
    can treat all "value absent" cases uniformly as malformed.
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
            value = line.split(":", 1)[1].strip().strip("\"'")
            return value or None
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
    webui_version = _extract_requirements_gradio(WEBUI_REQUIREMENTS)

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
    if webui_version is None:
        errors.append(
            f"{WEBUI_REQUIREMENTS.relative_to(REPO_ROOT)}: no `gradio==X.Y.Z` "
            "exact pin found. Do not drop this pin -- the file is what the "
            "README translations tell users to install and what the WebUI / "
            "python-inference images COPY, so an unpinned gradio there "
            "reintroduces the silent security-floor drift this gate exists "
            "to catch."
        )

    # HF Space 側の 2 サイトは build のハード要件なので、 専用の説明を出す。
    if sdk_version and req_version and sdk_version != req_version:
        errors.append(
            "HF Space gradio version drift detected:\n"
            f"  {README.relative_to(REPO_ROOT)} sdk_version: {sdk_version}\n"
            f"  {REQUIREMENTS.relative_to(REPO_ROOT)} gradio==        {req_version}\n"
            f"  These MUST match. HF Spaces injects gradio[oauth,mcp]=={sdk_version} "
            "into the pip install command alongside requirements.txt, and pip "
            "fails to resolve two different versions in one resolve pass "
            "(BUILD_ERROR with misleading 'cache miss' message)."
        )

    # 3 サイト目は build を壊さないぶん気付かれにくい。 失敗理由を分けて出す。
    if sdk_version and webui_version and sdk_version != webui_version:
        errors.append(
            "WebUI gradio version drift detected:\n"
            f"  {README.relative_to(REPO_ROOT)} sdk_version: {sdk_version}\n"
            f"  {WEBUI_REQUIREMENTS.relative_to(REPO_ROOT)} gradio==  {webui_version}\n"
            "  This pair does NOT break any build, which is exactly why it "
            "rots unnoticed: the file previously sat at 6.14.0 with "
            "CVE-2026-48545 open, and was left at 6.21.0 again when the HF "
            "Space pair moved to 6.26.0. Bump it together with the HF Space "
            "pin so the security floor cannot lag in one place."
        )

    if errors:
        print("gradio pin sync check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nTo fix: make all three pins agree --\n"
            "  huggingface-space/README.md          (frontmatter sdk_version)\n"
            "  huggingface-space/requirements.txt   (gradio==)\n"
            "  src/python_run/requirements_webui.txt (gradio==)"
        )
        return 1

    print(f"OK: all 3 gradio pin sites agree ({sdk_version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
