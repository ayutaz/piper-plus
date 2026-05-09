#!/usr/bin/env python3
"""C++ build pipeline / GitHub Actions / 各ランタイム依存ファイルの ORT
バージョン整合性 lint。

Issue #383 follow-up で ORT 1.17.0 → 1.20.0 に上げた際、6 ファイル + sha256
を同時更新する必要があり、`build-piper.yml` の URL を取りこぼす実例が
あった。Issue #372 follow-up で、各ランタイム ecosystem (Python / C# / Go
/ WASM) の floor pin が canonical を下回らないことも CI gate に組み込む。

正本 (Source of truth): ``cmake/OnnxRuntime.cmake`` の
``set(ONNXRUNTIME_VERSION "X.Y.Z")``。

検査対象 (2 種類):

1. **Exact-match group** — canonical と完全一致するべき (C++ パイプライン
   の hard-coded URL / env / cache key / Dockerfile)。drift があれば fail。

   * ``cmake/find_onnxruntime_windows.cmake`` (Windows pre-built)
   * ``.github/workflows/release-shared-lib.yml`` (iOS xcframework + Android release)
   * ``.github/workflows/android-build.yml`` (Android PR CI)
   * ``.github/workflows/release-kotlin-g2p.yml`` (Kotlin G2P AAR release)
   * ``.github/workflows/kotlin-g2p-ci.yml`` (Kotlin G2P PR CI)
   * ``.github/workflows/build-piper.yml`` (Linux/macOS source build)
   * ``.github/workflows/_build-test-cpp.yml`` (Linux/macOS arm64/x86_64/Windows pre-built)
   * ``docker/cpp-dev/Dockerfile`` (CPU-only dev image; Issue #372)

2. **Floor-check group** — canonical より低い floor pin は禁止 (Issue
   #372 Option C 方針)。pinned version の場合も canonical 以上を要求。

   * ``src/python/pyproject.toml`` (train / inference / inference-gpu extras)
   * ``src/python_run/requirements.txt`` (runtime CPU)
   * ``src/python_run/requirements_gpu.txt`` (runtime GPU)
   * ``src/python_run/setup.py`` (runtime extras_require)
   * ``src/csharp/PiperPlus.{Core,Cli,Cli.Tests,Core.Tests,Bench}.csproj``
   * ``src/go/go.mod``
   * ``src/wasm/openjtalk-web/package.json`` (peerDependencies)

検査範囲外:

* Rust ``src/rust/piper-core/Cargo.toml`` の ``ort`` crate
  — ``ort`` のバージョンは upstream ORT と 1:1 対応せず (RC 系列の
  ``2.0.0-rc.X`` は ORT 1.20 系をラップ)、また stable 版が未公開
  (2026-05 時点)。``docs/spec/ort-versions.md`` で別途トラッキング。
* ``docs/`` (history を含むため自動検査せず、人間がレビューする)

Usage:

    python scripts/check_ort_versions.py            # check (CI 用)
    python scripts/check_ort_versions.py --verbose  # 抽出した全 version を表示

Exit codes:

* 0: すべて canonical / floor を満たす
* 1: 1 つ以上で drift / floor 違反を検出
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CMAKE_FILE = Path("cmake/OnnxRuntime.cmake")

# ---------------------------------------------------------------------------
# Exact-match group: canonical と完全一致を要求 (C++ パイプライン)
# ---------------------------------------------------------------------------

TARGETS: list[Path] = [
    Path("cmake/find_onnxruntime_windows.cmake"),
    Path(".github/workflows/release-shared-lib.yml"),
    Path(".github/workflows/android-build.yml"),
    Path(".github/workflows/release-kotlin-g2p.yml"),
    Path(".github/workflows/kotlin-g2p-ci.yml"),
    Path(".github/workflows/build-piper.yml"),
    Path(".github/workflows/_build-test-cpp.yml"),
    Path("docker/cpp-dev/Dockerfile"),
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
        r"github\.com/microsoft/onnxruntime/releases/download/v(\d+\.\d+\.\d+)/"
    ),
    # archive file names: onnxruntime-{linux,osx,win}-*-1.20.0.{tgz,zip}
    # The arch segment allows hyphens (e.g. ``x64-gpu``) so suffix variants
    # such as ``onnxruntime-linux-x64-gpu-1.20.0.tgz`` (GPU build) or
    # ``onnxruntime-win-x64-cuda-1.20.0.zip`` are still picked up by the
    # gate; otherwise a workflow could drift on a GPU/CUDA archive name
    # while keeping the surrounding ``vX.Y.Z`` URL aligned.
    re.compile(r"onnxruntime-(?:linux|osx|win|android)-[a-z0-9_-]+-(\d+\.\d+\.\d+)"),
    # Microsoft CDN pod-archive
    re.compile(r"download\.onnxruntime\.ai/pod-archive-onnxruntime-c-(\d+\.\d+\.\d+)"),
    # Maven Central onnxruntime-android/<version>/onnxruntime-android-<version>.aar
    re.compile(
        r"/onnxruntime-android/(\d+\.\d+\.\d+)/onnxruntime-android-(\d+\.\d+\.\d+)\.aar"
    ),
    # Cache keys like `onnxruntime-1.20.0-v3`
    re.compile(r'onnxruntime[-_](\d+\.\d+\.\d+)(?:[-_]|"|$|\s|/)'),
]

# ---------------------------------------------------------------------------
# Floor-check group: canonical 以上を要求 (Issue #372 Option C)
# ---------------------------------------------------------------------------

# Each ecosystem has its own version-spec syntax. Regex captures
# (package, version) so the floor check can attribute violations to a
# specific dependency line.
FLOOR_PATTERNS_BY_ECOSYSTEM: dict[str, list[re.Pattern[str]]] = {
    # PEP 508 / pip requirements: onnxruntime>=1.20.0 / onnxruntime-gpu>=1.20.0,<2
    # Also matches setup.py extras_require strings like "onnxruntime-gpu>=1.20.0,<2".
    "python": [
        re.compile(r"\b(onnxruntime(?:-gpu)?)\s*>=\s*(\d+(?:\.\d+){0,2})"),
    ],
    # C# csproj: <PackageReference Include="Microsoft.ML.OnnxRuntime[.Managed]" Version="X.Y.Z" />
    "csharp": [
        re.compile(
            r'Include="(Microsoft\.ML\.OnnxRuntime(?:\.Managed)?)"\s+Version="(\d+\.\d+\.\d+)"'
        ),
    ],
    # Go go.mod: github.com/yalue/onnxruntime_go vX.Y.Z
    "go": [
        re.compile(r"(github\.com/yalue/onnxruntime_go)\s+v(\d+\.\d+\.\d+)"),
    ],
    # npm package.json peerDependencies: "onnxruntime-web": ">=X.Y.Z"
    "npm": [
        re.compile(r'"(onnxruntime-web)"\s*:\s*">=(\d+\.\d+\.\d+)"'),
    ],
}

FLOOR_TARGETS: list[tuple[Path, str]] = [
    # Python (training + runtime)
    (Path("src/python/pyproject.toml"), "python"),
    (Path("src/python_run/requirements.txt"), "python"),
    (Path("src/python_run/requirements_gpu.txt"), "python"),
    (Path("src/python_run/setup.py"), "python"),
    # C# (Core + CLI + tests + bench)
    (Path("src/csharp/PiperPlus.Core/PiperPlus.Core.csproj"), "csharp"),
    (Path("src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj"), "csharp"),
    (Path("src/csharp/PiperPlus.Cli.Tests/PiperPlus.Cli.Tests.csproj"), "csharp"),
    (Path("src/csharp/PiperPlus.Core.Tests/PiperPlus.Core.Tests.csproj"), "csharp"),
    (Path("src/csharp/PiperPlus.Bench/PiperPlus.Bench.csproj"), "csharp"),
    # Go
    (Path("src/go/go.mod"), "go"),
    # JS/WASM
    (Path("src/wasm/openjtalk-web/package.json"), "npm"),
]


def parse_version(v: str) -> tuple[int, ...]:
    """Parse a SemVer-ish string into a tuple for ordered comparison.

    Strips a leading ``v`` and any pre-release / build-metadata suffix.
    Pads short versions (e.g. ``1.20`` → ``(1, 20, 0)``) so they compare
    consistently against three-segment canonical versions.
    """
    v = v.lstrip("v")
    v = re.split(r"[-+]", v, maxsplit=1)[0]
    parts = [int(x) for x in v.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def extract_cmake_version(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"[FATAL] canonical file missing: {path}")
    text = path.read_text(encoding="utf-8")
    m = re.search(r'set\s*\(\s*ONNXRUNTIME_VERSION\s+"([^"]+)"\s*\)', text)
    if not m:
        raise SystemExit(f"[FATAL] ONNXRUNTIME_VERSION not found in {path}")
    return m.group(1)


def find_versions(text: str) -> dict[str, list[str]]:
    """Return {version: [matched_patterns]} for the exact-match group."""
    found: dict[str, list[str]] = {}
    for pat in VERSION_PATTERNS:
        for m in pat.finditer(text):
            for grp in m.groups():
                if grp:
                    found.setdefault(grp, []).append(pat.pattern)
    return found


def find_floor_violations(
    text: str, ecosystem: str, floor: str
) -> list[tuple[str, str]]:
    """Return [(package, version), ...] entries that fail the floor check.

    A floor violation is any matched (package, version) pair whose version
    sorts strictly below ``floor``. Equal-or-greater versions pass (this
    permits C# 1.24.3 / Go 1.27.0 to coexist with C++ canonical 1.20.0
    under Option C).
    """
    floor_tuple = parse_version(floor)
    violations: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pat in FLOOR_PATTERNS_BY_ECOSYSTEM[ecosystem]:
        for m in pat.finditer(text):
            pkg, ver = m.group(1), m.group(2)
            key = (pkg, ver)
            if key in seen:
                continue
            seen.add(key)
            if parse_version(ver) < floor_tuple:
                violations.append(key)
    return violations


def find_floor_versions(text: str, ecosystem: str) -> list[tuple[str, str]]:
    """Return [(package, version), ...] for verbose reporting (no filtering)."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for pat in FLOOR_PATTERNS_BY_ECOSYSTEM[ecosystem]:
        for m in pat.finditer(text):
            key = (m.group(1), m.group(2))
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    canonical = extract_cmake_version(CMAKE_FILE)
    print(f"[info] canonical ORT version (from {CMAKE_FILE}): {canonical}")

    # ----- Exact-match group ------------------------------------------------
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

    # ----- Floor-check group ------------------------------------------------
    floor_failures: list[str] = []
    for target, ecosystem in FLOOR_TARGETS:
        if not target.exists():
            print(f"[warn] floor target missing, skipping: {target}")
            continue
        text = target.read_text(encoding="utf-8")

        if args.verbose:
            found = find_floor_versions(text, ecosystem)
            pretty = ", ".join(f"{p}={v}" for p, v in found) or "(no matches)"
            print(f"[info] {target} ({ecosystem}): {pretty}")

        violations = find_floor_violations(text, ecosystem, canonical)
        if violations:
            pretty = ", ".join(f"{p}={v}" for p, v in violations)
            floor_failures.append(
                f"{target} ({ecosystem}):\n  below floor: {pretty}\n"
                f"  required: >= {canonical}"
            )

    # ----- Report -----------------------------------------------------------
    if failures or floor_failures:
        if failures:
            print("\n[FAIL] ORT version drift detected (exact-match group):")
            for f in failures:
                print(f"  - {f}")
        if floor_failures:
            print("\n[FAIL] ORT floor violation detected (floor-check group):")
            for f in floor_failures:
                print(f"  - {f}")
        print(
            "\nFix by aligning all targets with the canonical version, or "
            "update cmake/OnnxRuntime.cmake if the canonical itself should "
            "change. Run with --verbose for per-file detail."
        )
        return 1

    print("[OK] all ORT version references match canonical / floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
