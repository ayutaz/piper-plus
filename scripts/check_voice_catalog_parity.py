#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented lists)
"""Voice catalog parity checker across 5 runtimes.

`test/model_resolution_vectors.json` の `voice_catalog` を canonical source
として、5 ランタイム (Python / C++ / Rust / C# / Go) の voice catalog
mirror が同じ `repo_id` / `onnx_file` / `aliases` を持っているか確認する。

Why: voice catalog は各ランタイムで「JSON ファイル」または「ハードコード」
の形で分散しており、Python と C++ は JSON、Rust/C#/Go はソース内ハード
コード。drift すると `--model tsukuyomi` がランタイムによって違う ONNX を
引いたり、alias 解決に失敗したりする。`model-resolution.md` + golden
vector は既に存在するが CI gate がなかった (本 PR で追加)。

検証粒度: 各 catalog entry について以下を assert
  - canonical の `repo_id` / `onnx_file` が各ランタイムソースに出現
  - canonical の `aliases` のうち少なくとも 1 つが各ランタイムソースに出現

これは完全な byte-for-byte 比較ではなく、「**同じモデルを指している**」
を保証する subset 比較。フィールド名や hard-code 表現は言語固有でよい。

Source of truth: test/model_resolution_vectors.json (voice_catalog section)

Usage:
    python scripts/check_voice_catalog_parity.py

Exit codes:
    0 -- all runtime mirrors carry the canonical aliases / files
    1 -- drift detected
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL = REPO_ROOT / "test/model_resolution_vectors.json"

# Runtime mirrors. Each maps a label to the source file we will text-search.
# Python and C++ are JSON; Rust/C#/Go are source code. The check is identical
# (substring presence) for all five.
MIRRORS: dict[str, Path] = {
    # NOTE: `src/python_run/piper/voices.json` contains the 97-language
    # rhasspy upstream catalog only; piper-plus-specific models live in
    # `download.py`'s `PIPER_PLUS_MODELS` registry instead.
    "Python download.py": REPO_ROOT / "src/python_run/piper/download.py",
    "C++ piper_plus_voices.json": REPO_ROOT / "src/cpp/piper_plus_voices.json",
    "Rust model_download.rs": REPO_ROOT / "src/rust/piper-core/src/model_download.rs",
    "C# VoiceCatalog.cs": REPO_ROOT
    / "src/csharp/PiperPlus.Core/Config/VoiceCatalog.cs",
    "Go voice_catalog.go": REPO_ROOT / "src/go/piperplus/voice_catalog.go",
}


def load_canonical() -> dict[str, dict]:
    """Return canonical `voice_catalog` section keyed by catalog key."""
    if not CANONICAL.exists():
        print(f"ERROR: canonical missing: {CANONICAL}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    catalog = data.get("voice_catalog", {})
    if not catalog:
        print(
            f"ERROR: canonical {CANONICAL} has empty voice_catalog section",
            file=sys.stderr,
        )
        sys.exit(1)
    # Filter out keys starting with underscore (e.g. `_comment`).
    return {k: v for k, v in catalog.items() if not k.startswith("_")}


def check_entry(
    entry_key: str, entry: dict, mirror_label: str, mirror_path: Path
) -> list[str]:
    """Return a list of failure messages for this (entry, mirror) pair."""
    if not mirror_path.exists():
        return [f"  MISSING {mirror_label}: {mirror_path}"]

    text = mirror_path.read_text(encoding="utf-8")
    failures: list[str] = []

    repo = entry.get("repo_id")
    if repo and repo not in text:
        failures.append(f"  [{mirror_label}] {entry_key}: repo_id '{repo}' not found")

    onnx = entry.get("onnx_file")
    if onnx and onnx not in text:
        failures.append(f"  [{mirror_label}] {entry_key}: onnx_file '{onnx}' not found")

    aliases = entry.get("aliases", [])
    if aliases:
        # At least one alias must appear in the mirror. Rust uses a
        # synthetic name like `tsukuyomi-6lang-v2` and relies on partial
        # match; requiring all aliases would be too strict.
        if not any(alias in text for alias in aliases):
            failures.append(
                f"  [{mirror_label}] {entry_key}: none of aliases {aliases} found"
            )

    return failures


def main(argv: list[str] | None = None) -> int:
    canonical = load_canonical()
    print(f"Canonical: {CANONICAL.relative_to(REPO_ROOT)}")
    print(f"  {len(canonical)} catalog entries: {', '.join(canonical.keys())}")
    print()

    all_failures: list[str] = []

    for entry_key, entry in canonical.items():
        print(f"== {entry_key} ==")
        for mirror_label, mirror_path in MIRRORS.items():
            entry_failures = check_entry(entry_key, entry, mirror_label, mirror_path)
            if entry_failures:
                all_failures.extend(entry_failures)
                for f in entry_failures:
                    print(f, file=sys.stderr)
            else:
                print(f"  OK   {mirror_label}")
        print()

    if all_failures:
        print(
            f"\n{len(all_failures)} drift(s) detected. "
            f"Reconcile mirrors against {CANONICAL.relative_to(REPO_ROOT)}.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK all {len(canonical)} canonical entries present in all "
        f"{len(MIRRORS)} runtime mirrors"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
