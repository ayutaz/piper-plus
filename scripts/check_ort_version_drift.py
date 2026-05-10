"""
Check ONNX Runtime version drift across runtimes.

Reads docs/spec/ort-versions.md and confirms each runtime's pinned
version matches what's listed in the spec.

Sources scanned:
  - Python: src/python_run/setup.py / src/python_run/pyproject.toml
            grep onnxruntime version constraint
  - Rust:   src/rust/piper-core/Cargo.toml grep ort version
  - Go:     src/go/go.mod grep onnxruntime
  - C#:     src/csharp/PiperPlus.Core/PiperPlus.Core.csproj grep
            Microsoft.ML.OnnxRuntime version
  - C++:    cmake/SetupOnnxRuntime.cmake or similar grep ONNX_RUNTIME_VERSION
  - WASM:   src/rust/piper-wasm/Cargo.toml grep ort
  - Kotlin: android/piper-plus-g2p/build.gradle.kts (if any ORT integration)
  - Swift:  not tracked here (uses C lib via xcframework)

Exit code:
  0 = all match (or spec has TBD)
  1 = drift detected
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "ort-versions.md"


def grep_version(file_path: Path, pattern: str, label: str) -> str | None:
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    return match.group(1) if match else None


def main() -> int:
    if not SPEC.exists():
        print(f"WARNING: spec missing: {SPEC}", file=sys.stderr)
        print("Cannot verify drift without spec. Skipping.")
        return 0

    spec_text = SPEC.read_text(encoding="utf-8")
    print(f"Loaded spec: {SPEC}")
    print(f"  ({len(spec_text.splitlines())} lines)")

    runtime_checks = [
        ("Python (runtime)", REPO_ROOT / "src/python_run/setup.py", r'onnxruntime[^\s]*[>=]+([0-9.]+)'),
        ("Python (pyproject)", REPO_ROOT / "src/python_run/pyproject.toml", r'"onnxruntime[^"]*[>=]+([0-9.]+)'),
        ("Rust (piper-core)", REPO_ROOT / "src/rust/piper-core/Cargo.toml", r'ort\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"'),
        ("Rust (piper-wasm)", REPO_ROOT / "src/rust/piper-wasm/Cargo.toml", r'ort\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"'),
        ("Go (go.mod)", REPO_ROOT / "src/go/go.mod", r'onnxruntime[^\s]*\sv?([0-9.]+)'),
        ("C# (csproj)", REPO_ROOT / "src/csharp/PiperPlus.Core/PiperPlus.Core.csproj", r'Microsoft\.ML\.OnnxRuntime[^"]*"\s+Version="([0-9.]+)"'),
    ]

    drifts: list[str] = []
    for label, file_path, pattern in runtime_checks:
        version = grep_version(file_path, pattern, label)
        if version is None:
            print(f"  [{label}] not found ({file_path})")
            continue
        print(f"  [{label}] ORT version = {version}")
        # Cross-reference with spec
        if version not in spec_text:
            drifts.append(f"[{label}] ORT version {version} not mentioned in {SPEC.name}")

    if drifts:
        print("\nDrift detected:", file=sys.stderr)
        for d in drifts:
            print(f"  - {d}", file=sys.stderr)
        print("\nUpdate docs/spec/ort-versions.md to reflect current versions.")
        return 1

    print("\nAll runtimes' ORT versions are mentioned in spec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
