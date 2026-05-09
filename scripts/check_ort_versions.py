#!/usr/bin/env python3
"""C++ build pipeline / GitHub Actions の ORT バージョン整合性 lint.

Issue #383 follow-up で ORT 1.17.0 → 1.20.0 に上げた際、6 ファイル + sha256
を同時更新する必要があり、`build-piper.yml` の URL を取りこぼす実例が
あった。今後同じ取りこぼしを CI で検出するための gate。

正本 (Source of truth): ``cmake/OnnxRuntime.cmake`` の
``set(ONNXRUNTIME_VERSION "X.Y.Z")``。

検査対象 (canonical と一致するべき):

* ``cmake/find_onnxruntime_windows.cmake`` (Windows pre-built)
* ``.github/workflows/release-shared-lib.yml`` (iOS xcframework + Android release)
* ``.github/workflows/android-build.yml`` (Android PR CI)
* ``.github/workflows/release-kotlin-g2p.yml`` (Kotlin G2P AAR release)
* ``.github/workflows/kotlin-g2p-ci.yml`` (Kotlin G2P PR CI)
* ``.github/workflows/build-piper.yml`` (Linux/macOS source build)
* ``.github/workflows/_build-test-cpp.yml`` (Linux/macOS arm64/x86_64/Windows pre-built)

検査範囲外 (各ランタイムが独立にメンテ):

* Python ``pyproject.toml`` (`onnxruntime>=1.17.0` などの floor pin)
* C# ``*.csproj`` の ``Microsoft.ML.OnnxRuntime`` PackageReference
* Go ``go.mod`` の ``onnxruntime_go``
* Rust ``Cargo.toml`` の ``ort`` クレート
* JS/WASM ``package.json`` の ``onnxruntime-web``
* ``docs/`` (history を含むため自動検査せず、人間がレビューする)

これらは ``docs/spec/ort-versions.md`` のメンテナンスで担保。

Usage:

    python scripts/check_ort_versions.py            # check (CI 用)
    python scripts/check_ort_versions.py --verbose  # 抽出した全 version を表示

Exit codes:

* 0: すべて canonical と一致
* 1: 1 つ以上で drift / 取りこぼしを検出
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CMAKE_FILE = Path("cmake/OnnxRuntime.cmake")

TARGETS: list[Path] = [
    Path("cmake/find_onnxruntime_windows.cmake"),
    Path(".github/workflows/release-shared-lib.yml"),
    Path(".github/workflows/android-build.yml"),
    Path(".github/workflows/release-kotlin-g2p.yml"),
    Path(".github/workflows/kotlin-g2p-ci.yml"),
    Path(".github/workflows/build-piper.yml"),
    Path(".github/workflows/_build-test-cpp.yml"),
]

# Patterns that should always reference the canonical C++ ORT version.
# We scan generously and intersect against an "ORT context" check —
# isolated `1.20.0` strings unrelated to ORT (e.g. unrelated tool
# versions) are not matched because the patterns explicitly include
# `onnxruntime`, `ONNXRUNTIME_VERSION`, or the Microsoft download URLs.
VERSION_PATTERNS: list[re.Pattern[str]] = [
    # set(ONNXRUNTIME_VERSION "1.20.0") — CMake
    re.compile(r'set\s*\(\s*ONNXRUNTIME_VERSION\s+"(\d+\.\d+\.\d+)"\s*\)'),
    # ONNXRUNTIME_VERSION: "1.20.0" — GitHub Actions env
    re.compile(r'ONNXRUNTIME_VERSION\s*:\s*"(\d+\.\d+\.\d+)"'),
    # GitHub releases URL
    re.compile(
        r'github\.com/microsoft/onnxruntime/releases/download/v(\d+\.\d+\.\d+)/'
    ),
    # archive file names: onnxruntime-{linux,osx,win}-*-1.20.0.{tgz,zip}
    re.compile(r'onnxruntime-(?:linux|osx|win|android)-[a-z0-9_]+-(\d+\.\d+\.\d+)'),
    # Microsoft CDN pod-archive
    re.compile(r'download\.onnxruntime\.ai/pod-archive-onnxruntime-c-(\d+\.\d+\.\d+)'),
    # Maven Central onnxruntime-android/<version>/onnxruntime-android-<version>.aar
    re.compile(
        r'/onnxruntime-android/(\d+\.\d+\.\d+)/onnxruntime-android-(\d+\.\d+\.\d+)\.aar'
    ),
    # Cache keys like `onnxruntime-1.20.0-v3`
    re.compile(r'onnxruntime[-_](\d+\.\d+\.\d+)(?:[-_]|"|$|\s|/)'),
]


def extract_cmake_version(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"[FATAL] canonical file missing: {path}")
    text = path.read_text(encoding="utf-8")
    m = re.search(r'set\s*\(\s*ONNXRUNTIME_VERSION\s+"([^"]+)"\s*\)', text)
    if not m:
        raise SystemExit(f"[FATAL] ONNXRUNTIME_VERSION not found in {path}")
    return m.group(1)


def find_versions(text: str) -> dict[str, list[str]]:
    """Return {version: [matched_patterns]}."""
    found: dict[str, list[str]] = {}
    for pat in VERSION_PATTERNS:
        for m in pat.finditer(text):
            for grp in m.groups():
                if grp:
                    found.setdefault(grp, []).append(pat.pattern)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    canonical = extract_cmake_version(CMAKE_FILE)
    print(f"[info] canonical ORT version (from {CMAKE_FILE}): {canonical}")

    failures: list[str] = []
    for target in TARGETS:
        if not target.exists():
            print(f"[warn] target missing, skipping: {target}")
            continue
        text = target.read_text(encoding="utf-8")
        versions = find_versions(text)

        if args.verbose:
            print(f"[info] {target}: {sorted(versions.keys()) or '(no matches)'}")

        unexpected = {v: pats for v, pats in versions.items() if v != canonical}
        if unexpected:
            failures.append(
                f"{target}:\n  drift: {sorted(unexpected.keys())}\n"
                f"  expected: {canonical!r}"
            )

    if failures:
        print("\n[FAIL] ORT version drift detected:")
        for f in failures:
            print(f"  - {f}")
        print(
            "\nFix by aligning all targets with the canonical version, or "
            "update cmake/OnnxRuntime.cmake if the canonical itself should "
            "change. Run with --verbose for per-file detail."
        )
        return 1

    print("[OK] all ORT version references match canonical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
