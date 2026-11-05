#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented lists)
"""Voice catalog parity checker across the runtime catalog mirrors.

`test/model_resolution_vectors.json` の `voice_catalog` を canonical source
として、5 ランタイム (Python / C++ / Rust / C# / Go) の voice catalog
mirror の `repo_id` / `onnx_file` / `config_file` / `revision` / `aliases` と、
利用案内 (`notice` / `notice_files`) を確認する。

Why: voice catalog は各ランタイムで「JSON ファイル」または「ハードコード」
の形で分散しており、Python と C++ は JSON、Rust/C#/Go はソース内ハード
コード。drift すると `--model tsukuyomi` がランタイムによって違う ONNX を
引いたり、alias 解決に失敗したり、利用案内の文面がランタイムごとに
食い違ったりする。

検証粒度: 各 catalog entry について以下を assert
  - full mirror (catalog を持つランタイム):
      - canonical の `repo_id` / `onnx_file` / `config_file` と任意の `revision` が出現
      - canonical の `aliases` のうち少なくとも 1 つが出現
      - canonical の `notice` の各行と `notice_files` の各要素が出現
  - notice mirror (catalog の形が違うが利用案内を出すもの: WASM と学習側 Python):
      - `notice` を持つ entry についてだけ、`repo_id`、`notice` の各行、
        `notice_files` の各要素が出現

これは完全な byte-for-byte 比較ではなく、「**同じモデルを指し、同じ
案内を持っている**」を保証する subset 比較。フィールド名や hard-code 表現は
言語固有でよい。mirror 側の `\\uXXXX` エスケープは照合前に文字へ戻す。
案内文の行には `"` と `\\` を入れない規則なので、各言語の文字列リテラル
にそのまま書ける (docs/reference/model-resolution.md §9)。

Source of truth: test/model_resolution_vectors.json (voice_catalog section)

Usage:
    python scripts/check_voice_catalog_parity.py

Exit codes:
    0 -- all runtime mirrors carry the canonical aliases / files / notices
    1 -- drift detected
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL = REPO_ROOT / "test/model_resolution_vectors.json"

# Runtime mirrors that hold a full catalog. Each maps a label to the source
# file we will text-search. Python and C++ are JSON; Rust/C#/Go are source
# code. The check is identical (substring presence) for all of them.
MIRRORS: dict[str, Path] = {
    # NOTE: `src/python_run/piper_plus/voices.json` contains the 97-language
    # rhasspy upstream catalog only; piper-plus-specific models live in
    # `download.py`'s `PIPER_PLUS_VOICES` registry instead.
    "Python download.py": REPO_ROOT / "src/python_run/piper_plus/download.py",
    "C++ piper_plus_voices.json": REPO_ROOT / "src/cpp/piper_plus_voices.json",
    "C++ embedded catalog": REPO_ROOT / "src/cpp/model_manager.cpp",
    "Rust model_download.rs": REPO_ROOT / "src/rust/piper-core/src/model_download.rs",
    "C# VoiceCatalog.cs": REPO_ROOT
    / "src/csharp/PiperPlus.Core/Config/VoiceCatalog.cs",
    "Go voice_catalog.go": REPO_ROOT / "src/go/piperplus/voice_catalog.go",
}

# Mirrors that only carry the usage notice for the entries that have one.
# Their catalogs are shaped differently (WASM maps alias -> repo only; the
# training-side Python catalog is a separate registry), so only the repo and
# the notice are compared.
NOTICE_MIRRORS: dict[str, Path] = {
    "WASM model-manager.js": REPO_ROOT / "src/wasm/openjtalk-web/src/model-manager.js",
    "Python piper_train model_manager.py": REPO_ROOT
    / "src/python/piper_train/model_manager.py",
}

_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def normalize_mirror_text(text: str) -> str:
    """Turn `\\uXXXX` escapes into characters so escaped mirrors still match."""
    return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def load_canonical(path: Path = CANONICAL) -> dict[str, dict]:
    """Return canonical `voice_catalog` section keyed by catalog key."""
    if not path.exists():
        print(f"ERROR: canonical missing: {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    catalog = data.get("voice_catalog", {})
    if not catalog:
        print(
            f"ERROR: canonical {path} has empty voice_catalog section",
            file=sys.stderr,
        )
        sys.exit(1)
    # Filter out keys starting with underscore (e.g. `_comment`).
    return {k: v for k, v in catalog.items() if not k.startswith("_")}


def validate_canonical_notice(entry_key: str, entry: dict) -> list[str]:
    """Notice lines must be literal-safe in every runtime's source."""
    failures: list[str] = []
    for line in entry.get("notice", []):
        if not line.strip():
            failures.append(f"  [canonical] {entry_key}: notice has an empty line")
        if '"' in line or "\\" in line:
            failures.append(
                f"  [canonical] {entry_key}: notice line must not contain '\"' or "
                f"'\\\\': {line!r}"
            )
    if entry.get("notice") and not entry.get("notice_files"):
        failures.append(f"  [canonical] {entry_key}: notice without notice_files")
    return failures


def _notice_failures(
    entry_key: str, entry: dict, mirror_label: str, text: str
) -> list[str]:
    failures: list[str] = []
    for line in entry.get("notice", []):
        if line not in text:
            failures.append(
                f"  [{mirror_label}] {entry_key}: notice line not found: {line!r}"
            )
    for file_name in entry.get("notice_files", []):
        if file_name not in text:
            failures.append(
                f"  [{mirror_label}] {entry_key}: notice_files entry '{file_name}' "
                "not found"
            )
    return failures


def check_entry(
    entry_key: str, entry: dict, mirror_label: str, mirror_path: Path
) -> list[str]:
    """Return a list of failure messages for this (entry, full mirror) pair."""
    if not mirror_path.exists():
        return [f"  MISSING {mirror_label}: {mirror_path}"]

    text = normalize_mirror_text(mirror_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    repo = entry.get("repo_id")
    if repo and repo not in text:
        failures.append(f"  [{mirror_label}] {entry_key}: repo_id '{repo}' not found")

    onnx = entry.get("onnx_file")
    if onnx and onnx not in text:
        failures.append(f"  [{mirror_label}] {entry_key}: onnx_file '{onnx}' not found")

    for field in ("config_file", "revision"):
        value = entry.get(field)
        if value and value not in text:
            failures.append(
                f"  [{mirror_label}] {entry_key}: {field} '{value}' not found"
            )

    aliases = entry.get("aliases", [])
    if aliases:
        # At least one alias must appear in the mirror. Rust uses a
        # synthetic name like `tsukuyomi-6lang-v2` and relies on partial
        # match; requiring all aliases would be too strict.
        if not any(alias in text for alias in aliases):
            failures.append(
                f"  [{mirror_label}] {entry_key}: none of aliases {aliases} found"
            )

    failures.extend(_notice_failures(entry_key, entry, mirror_label, text))
    return failures


def check_notice_entry(
    entry_key: str, entry: dict, mirror_label: str, mirror_path: Path
) -> list[str]:
    """Return failures for a notice-only mirror (entries with a notice only)."""
    if not entry.get("notice"):
        return []
    if not mirror_path.exists():
        return [f"  MISSING {mirror_label}: {mirror_path}"]

    text = normalize_mirror_text(mirror_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    repo = entry.get("repo_id")
    if repo and repo not in text:
        failures.append(f"  [{mirror_label}] {entry_key}: repo_id '{repo}' not found")
    failures.extend(_notice_failures(entry_key, entry, mirror_label, text))
    return failures


def main(
    argv: list[str] | None = None,
    *,
    canonical_path: Path = CANONICAL,
    mirrors: dict[str, Path] | None = None,
    notice_mirrors: dict[str, Path] | None = None,
) -> int:
    mirrors = MIRRORS if mirrors is None else mirrors
    notice_mirrors = NOTICE_MIRRORS if notice_mirrors is None else notice_mirrors
    canonical = load_canonical(canonical_path)
    print(f"Canonical: {canonical_path}")
    print(f"  {len(canonical)} catalog entries: {', '.join(canonical.keys())}")
    print()

    all_failures: list[str] = []

    for entry_key, entry in canonical.items():
        print(f"== {entry_key} ==")
        canonical_failures = validate_canonical_notice(entry_key, entry)
        all_failures.extend(canonical_failures)
        for f in canonical_failures:
            print(f, file=sys.stderr)

        checks = [(label, path, check_entry) for label, path in mirrors.items()]
        checks += [
            (label, path, check_notice_entry) for label, path in notice_mirrors.items()
        ]
        for mirror_label, mirror_path, check in checks:
            if check is check_notice_entry and not entry.get("notice"):
                continue
            entry_failures = check(entry_key, entry, mirror_label, mirror_path)
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
            f"Reconcile mirrors against {canonical_path}.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK all {len(canonical)} canonical entries present in all "
        f"{len(mirrors)} runtime mirrors and {len(notice_mirrors)} notice mirrors"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
