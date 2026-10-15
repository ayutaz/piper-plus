#!/usr/bin/env python3
"""Update exact nested artifact hash/size fields without rewriting TOML comments.

Use --name MODEL --onnx FILE [--config FILE] [--force]. Local basenames must
match manifest artifact filenames; missing/ambiguous entries fail without any
partial write. Existing non-placeholder pins require --force.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "spec" / "model-sha256-manifest.toml"
PLACEHOLDER = "<computed-on-publish>"


def sha256_and_size(path: Path) -> tuple[str, int]:
    """Return (sha256_hex, byte_size)."""
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def artifact_range(text: str, name: str, filename: str) -> tuple[int, int]:
    """Find one exact artifact without crossing into a sibling model/table."""
    import tomllib

    lines = text.splitlines(keepends=True)
    current_model = None
    matches = []
    for i, line in enumerate(lines):
        if line.strip() == "[[models]]":
            end = next(
                (
                    j
                    for j in range(i + 1, len(lines))
                    if lines[j].strip().startswith("[")
                ),
                len(lines),
            )
            current_model = tomllib.loads("".join(lines[i:end]))["models"][0].get(
                "name"
            )
        if current_model == name and line.strip() == "[[models.artifacts]]":
            end = next(
                (
                    j
                    for j in range(i + 1, len(lines))
                    if lines[j].strip().startswith("[")
                ),
                len(lines),
            )
            artifact = tomllib.loads("".join(lines[i:end]))["models"]["artifacts"][0]
            if artifact.get("filename") == filename or (
                "/" not in filename
                and Path(artifact.get("filename", "")).name == filename
            ):
                matches.append((i, end))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous artifact basename: {name}/{filename}")
    raise ValueError(f"artifact not found: {name}/{filename}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update nested official artifact hashes and sizes"
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--onnx", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        default=[],
        help="Additional exact artifact file; repeat for checkpoints/encoders/config aliases",
    )
    args = parser.parse_args(argv)
    if not args.onnx and not args.config and not args.artifact:
        parser.error("provide at least --onnx or --config")
    try:
        text = MANIFEST.read_text(encoding="utf-8")
        for path in (args.onnx, args.config, *args.artifact):
            if path is None:
                continue
            digest, size = sha256_and_size(path)
            start, end = artifact_range(text, args.name, path.name)
            lines = text.splitlines(keepends=True)
            block = "".join(lines[start:end])
            for field, value in (("sha256", f'"{digest}"'), ("bytes", str(size))):
                pattern = re.compile(rf"^({field}\s*=\s*)([^#\n]+)(.*)$", re.MULTILINE)
                match = pattern.search(block)
                if match is None:
                    raise ValueError(f"{path.name}: required field {field} missing")
                old = match.group(2).strip()
                if not args.force and old not in (f'"{PLACEHOLDER}"', "0", value):
                    raise ValueError(f"{path.name}: {field} already set; use --force")
                block = pattern.sub(
                    lambda m, replacement=value: m[1] + replacement + m[3],
                    block,
                    count=1,
                )
            text = "".join(lines[:start]) + block + "".join(lines[end:])
        # No write occurs until every requested artifact has been validated.
        MANIFEST.write_text(text, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Updated artifact hashes and sizes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
