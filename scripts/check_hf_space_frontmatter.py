#!/usr/bin/env python3
"""HF Space README frontmatter schema gate.

Hugging Face Spaces parses the YAML frontmatter at the top of ``README.md``
to decide how to build and run the Space. A typo or missing field there is
a common BUILD_ERROR cause that the build log surfaces as a misleading
"cache miss" / generic error (the real reason is often only visible in the
Space settings page).

This gate catches the four most common drift patterns BEFORE the bundle is
shipped to HF:

  F1. A required field is missing
      (HF rejects the build with no useful error)
  F2. ``app_file:`` points to a file not present in ``huggingface-space/``
      (HF returns NO_APP_FILE)
  F3. The YAML itself is unparseable
      (HF rejects with "could not parse README")
  F4. ``sdk:`` is not one of the supported values
      (HF returns CONFIG_ERROR)

The gate is intentionally narrow: it does NOT enforce ``license:`` against
HF's accepted list (HF updates that list independently of our repo and we
do not want to false-positive a Dependabot-style license bump). It also
does NOT cross-check ``sdk_version`` against ``requirements.txt`` -- that
is handled by ``check_hf_space_gradio_sync.py``.

Usage:
    python scripts/check_hf_space_frontmatter.py

Exit codes:
    0 -- frontmatter is well-formed and self-consistent
    1 -- one or more required fields missing, malformed, or inconsistent
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HF_SPACE_DIR = REPO_ROOT / "huggingface-space"
README = HF_SPACE_DIR / "README.md"

REQUIRED_FIELDS = ("title", "sdk", "sdk_version", "app_file")

VALID_SDKS = ("gradio", "streamlit", "docker", "static")


def _extract_frontmatter(readme_path: Path) -> tuple[dict | None, list[str]]:
    """Return parsed frontmatter dict + list of errors.

    A None dict + non-empty errors means the file is missing, has no
    frontmatter delimiters, or fails YAML parse. Callers should treat both
    cases the same way (gate must fail).
    """
    errors: list[str] = []
    if not readme_path.exists():
        errors.append(f"{readme_path.relative_to(REPO_ROOT)}: file does not exist")
        return None, errors

    text = readme_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append(
            f"{readme_path.relative_to(REPO_ROOT)}: file does not start with "
            "`---` delimiter (HF Space requires YAML frontmatter at the top)"
        )
        return None, errors

    end = text.find("\n---", 3)
    if end < 0:
        errors.append(
            f"{readme_path.relative_to(REPO_ROOT)}: opening `---` found but no "
            "closing `---` (frontmatter block is unterminated)"
        )
        return None, errors

    frontmatter_text = text[3:end]
    try:
        data = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        errors.append(
            f"{readme_path.relative_to(REPO_ROOT)}: frontmatter is not valid "
            f"YAML: {e}"
        )
        return None, errors

    if not isinstance(data, dict):
        errors.append(
            f"{readme_path.relative_to(REPO_ROOT)}: frontmatter parses to "
            f"{type(data).__name__}, expected a mapping (key: value pairs)"
        )
        return None, errors

    return data, errors


def main() -> int:
    data, errors = _extract_frontmatter(README)

    if data is None:
        # Parse failure -- emit the parse error(s) and stop. No point checking
        # required fields if we could not parse the YAML at all.
        print("HF Space frontmatter check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    # F1: required fields present and non-empty
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(
                f"frontmatter is missing required field `{field}:` (HF Space "
                "cannot build without it)"
            )

    # F4: sdk must be one of HF's supported values
    sdk = data.get("sdk")
    if isinstance(sdk, str) and sdk not in VALID_SDKS:
        errors.append(
            f"`sdk: {sdk}` is not a recognized HF Space SDK. Allowed: "
            f"{', '.join(VALID_SDKS)} (HF rejects unknown values with "
            "CONFIG_ERROR)"
        )

    # F2: app_file must point to a file that exists in the Space directory
    # (this directory is what `Prepare Space files` copies from). If it is
    # missing here, the deploy bundle will be missing app.py and HF returns
    # NO_APP_FILE at runtime.
    app_file = data.get("app_file")
    if isinstance(app_file, str) and app_file.strip():
        target = HF_SPACE_DIR / app_file.strip()
        if not target.exists():
            errors.append(
                f"`app_file: {app_file}` does not exist at "
                f"{target.relative_to(REPO_ROOT)} -- HF Space will fail with "
                "NO_APP_FILE after deploy"
            )

    if errors:
        print("HF Space frontmatter check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nTo fix: edit huggingface-space/README.md so the YAML "
            "frontmatter has every required field and `app_file:` points to "
            "an existing file."
        )
        return 1

    print("OK: HF Space frontmatter is well-formed")
    print(
        f"     title={data.get('title')!r} sdk={data.get('sdk')} "
        f"sdk_version={data.get('sdk_version')} app_file={data.get('app_file')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
