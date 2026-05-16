#!/usr/bin/env python3
"""docs/spec/model-sha256-manifest.toml の sha256 / bytes 自動更新 (Wave 3, T10).

`<computed-on-publish>` placeholder を、 引数で指定した artifact の
実 SHA-256 / size に置換する。 /publish-model skill のフェーズ 5b
(HF upload 直前) に呼ばれる想定。

verify_model_checksums.py の逆向き (read → 検証 ではなく compute → 書き込み)。

Usage:
  uv run python scripts/auto_update_model_manifest.py \
    --name "multilingual-6lang-mb-istft" \
    --onnx /path/to/model.onnx
  # config.json も同時に更新する場合
  uv run python scripts/auto_update_model_manifest.py \
    --name "multilingual-6lang-mb-istft" \
    --onnx /path/to/model.onnx \
    --config /path/to/model.onnx.json

  # 既存 sha256 を上書きする場合
  uv run python scripts/auto_update_model_manifest.py --name ... --force

Exit codes:
  0 -- 更新成功
  1 -- artifact 不在 / placeholder が既に置換済 (--force 必要)
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


def find_model_block(text: str, name: str) -> tuple[int, int] | None:
    """Locate the [[models]] block matching `name = "<name>"`.

    Returns (start_line, end_line_exclusive) of the block, or None.
    """
    lines = text.splitlines()
    start: int | None = None
    found_name = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[[models]]":
            if start is not None and not found_name:
                # passed an unmatched block — keep searching
                pass
            start = i
            found_name = False
            continue
        if start is not None and stripped == f'name = "{name}"':
            found_name = True
        if found_name and stripped.startswith("[[") and stripped != "[[models]]":
            # next block header — end of our match
            return (start, i)
    if found_name and start is not None:
        return (start, len(lines))
    return None


def update_block(
    text: str,
    block_range: tuple[int, int],
    field: str,
    value: str,
    force: bool,
) -> tuple[str, str]:
    """Replace `field = <PLACEHOLDER>` (or any existing value if --force) with new value.

    Returns (new_text, action_msg).
    """
    start, end = block_range
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^(\s*{re.escape(field)}\s*=\s*)(.+?)(\s*(?:#.*)?\n?)$")
    for i in range(start, end):
        m = pattern.match(lines[i])
        if not m:
            continue
        current = m.group(2).strip()
        is_placeholder = current in (f'"{PLACEHOLDER}"', PLACEHOLDER, "0")
        if not is_placeholder and not force:
            return (text, f"skip: {field}={current} (already set, use --force)")
        prefix = m.group(1)
        suffix = m.group(3).rstrip("\n")
        if field == "sha256":
            new_line = f'{prefix}"{value}"{suffix}\n'
        else:
            new_line = f"{prefix}{value}{suffix}\n"
        lines[i] = new_line
        return ("".join(lines), f"updated: {field}={value} (line {i + 1})")
    return (text, f"field {field}= not found in block")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-update model-sha256-manifest.toml"
    )
    parser.add_argument(
        "--name", required=True, help='model `name = "..."` value to match'
    )
    parser.add_argument(
        "--onnx",
        type=Path,
        help="path to .onnx file (computes onnx_sha256 / onnx_bytes)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="path to .onnx.json file (computes config_sha256 / config_bytes)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite already-filled sha256 / bytes fields",
    )
    args = parser.parse_args()

    if not MANIFEST.exists():
        print(f"error: {MANIFEST} not found", file=sys.stderr)
        return 1
    if not args.onnx and not args.config:
        print("error: provide at least --onnx or --config", file=sys.stderr)
        return 1

    text = MANIFEST.read_text(encoding="utf-8")
    block = find_model_block(text, args.name)
    if block is None:
        print(
            f'error: [[models]] block with name="{args.name}" not found',
            file=sys.stderr,
        )
        return 1

    actions: list[str] = []

    # The manifest uses generic `sha256` / `bytes` fields per model block.
    # For onnx-only updates we touch those; for config we also assume the
    # block contains a separate subtable `[models.config]` (current spec)
    # — adjust here once the schema settles.
    if args.onnx:
        if not args.onnx.exists():
            print(f"error: onnx file not found: {args.onnx}", file=sys.stderr)
            return 1
        digest, size = sha256_and_size(args.onnx)
        text, msg = update_block(text, block, "sha256", digest, args.force)
        actions.append(msg)
        # re-locate block (line offsets shifted)
        block = find_model_block(text, args.name)
        if block:
            text, msg = update_block(text, block, "bytes", str(size), args.force)
            actions.append(msg)

    if args.config:
        if not args.config.exists():
            print(f"error: config file not found: {args.config}", file=sys.stderr)
            return 1
        # config_sha256 / config_bytes are best-effort; skip if fields missing.
        digest, size = sha256_and_size(args.config)
        block = find_model_block(text, args.name)
        if block:
            text, msg = update_block(text, block, "config_sha256", digest, args.force)
            actions.append(msg)
            block = find_model_block(text, args.name)
            if block:
                text, msg = update_block(
                    text, block, "config_bytes", str(size), args.force
                )
                actions.append(msg)

    MANIFEST.write_text(text, encoding="utf-8")
    for msg in actions:
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
