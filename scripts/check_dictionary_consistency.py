#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented numbered list)
"""Custom dictionary JSON 同期チェッカー (canonical → WASM mirror).

`data/dictionaries/*.json` を canonical source として、
`src/wasm/openjtalk-web/assets/*.json` の mirror が byte-for-byte 一致
しているか確認する。

Why: default_common_dict.json は 2026-05 時点で canonical 443 行 vs
WASM mirror 124 行で drift していた (ブラウザ向け配布だけ語彙が古い)。
default_tech_dict / additional_tech_dict は同期済だったが、CI gate が
無いため次の更新で同じ drift が起きるリスクが残っていた。

Source of truth: data/dictionaries/<name>.json
Mirror:          src/wasm/openjtalk-web/assets/<name>.json

Usage:
    python scripts/check_dictionary_consistency.py        # check only
    python scripts/check_dictionary_consistency.py --fix  # canonical → mirror

Exit codes:
    0 -- all in sync (or --fix succeeded)
    1 -- mismatch / missing
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# (canonical, mirror) pairs. Add new pairs here when a dictionary is
# bundled in additional runtime distributions.
PAIRS: list[tuple[Path, Path]] = [
    (
        REPO_ROOT / "data/dictionaries/default_common_dict.json",
        REPO_ROOT / "src/wasm/openjtalk-web/assets/default_common_dict.json",
    ),
    (
        REPO_ROOT / "data/dictionaries/default_tech_dict.json",
        REPO_ROOT / "src/wasm/openjtalk-web/assets/default_tech_dict.json",
    ),
    (
        REPO_ROOT / "data/dictionaries/additional_tech_dict.json",
        REPO_ROOT / "src/wasm/openjtalk-web/assets/additional_tech_dict.json",
    ),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def show_diff(src: Path, dst: Path) -> None:
    src_lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    dst_lines = (
        dst.read_text(encoding="utf-8").splitlines(keepends=True)
        if dst.exists()
        else []
    )
    diff = difflib.unified_diff(
        dst_lines,
        src_lines,
        fromfile=str(dst.relative_to(REPO_ROOT)),
        tofile=str(src.relative_to(REPO_ROOT)),
        n=1,
    )
    sys.stdout.writelines(diff)


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="canonical → mirror 一方向コピー"
    )
    parser.add_argument(
        "--diff", action="store_true", help="--fix 前の dry-run 差分表示"
    )
    args = parser.parse_args(argv)

    failed: list[str] = []
    fixed: list[str] = []

    for canonical, mirror in PAIRS:
        rel_c = canonical.relative_to(REPO_ROOT)
        rel_m = mirror.relative_to(REPO_ROOT)

        if not canonical.exists():
            print(f"ERROR: canonical missing: {rel_c}", file=sys.stderr)
            return 1

        if not mirror.exists():
            if args.fix:
                mirror.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(canonical, mirror)
                fixed.append(f"created {rel_m}")
                continue
            failed.append(f"MIRROR MISSING {rel_m}")
            continue

        if sha256(canonical) == sha256(mirror):
            print(f"  OK    {rel_m}")
            continue

        if args.diff:
            show_diff(canonical, mirror)
        if args.fix:
            shutil.copy2(canonical, mirror)
            fixed.append(f"synced {rel_m}")
            continue
        failed.append(f"MISMATCH {rel_m} (canonical: {rel_c})")

    for f in fixed:
        print(f"  FIXED {f}")

    if failed:
        print("", file=sys.stderr)
        for f in failed:
            print(f"  FAIL  {f}", file=sys.stderr)
        print(
            f"\n{len(failed)} file(s) out of sync. "
            "Run with --fix to copy from data/dictionaries/.",
            file=sys.stderr,
        )
        return 1

    if not fixed:
        print(f"\nOK All {len(PAIRS)} mirror(s) in sync with data/dictionaries/")
    else:
        print(f"\nOK applied {len(fixed)} fix(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
