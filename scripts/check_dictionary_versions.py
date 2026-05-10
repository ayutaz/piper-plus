"""
Check G2P dictionary versions against docs/spec/dictionary-versions.toml.

Sources scanned (best-effort):
  - Python: src/python_run/setup.py / pyproject.toml
            grep pyopenjtalk-plus / g2p-en / pypinyin / g2pk2
  - Rust:   src/rust/piper-plus-g2p/Cargo.toml grep jpreprocess
  - Other:  TBD (mirror snapshots in JSON form)

Exit code:
  0 = compliant (or pin says <unverified>)
  1 = drift detected
"""
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "dictionary-versions.toml"


def grep_version(file_path: Path, pattern: str) -> str | None:
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    return match.group(1) if match else None


def main() -> int:
    if not SPEC.exists():
        print(f"WARNING: spec missing: {SPEC}", file=sys.stderr)
        return 0

    with SPEC.open("rb") as f:
        spec = tomllib.load(f)

    print(f"Loaded {SPEC.name}")

    checks = [
        ("pyopenjtalk-plus", REPO_ROOT / "src/python_run/setup.py", r'pyopenjtalk-plus[^"]*[>=]+([0-9.]+)'),
        ("g2p-en", REPO_ROOT / "src/python_run/setup.py", r'g2p-en[^"]*[>=]+([0-9.]+)'),
        ("pypinyin", REPO_ROOT / "src/python_run/setup.py", r'pypinyin[^"]*[>=]+([0-9.]+)'),
        ("jpreprocess (Rust)", REPO_ROOT / "src/rust/piper-core/Cargo.toml", r'jpreprocess\s*=\s*"([^"]+)"'),
    ]

    found: dict[str, str] = {}
    for label, file_path, pattern in checks:
        version = grep_version(file_path, pattern)
        if version:
            found[label] = version
            print(f"  [{label}] {version}  ({file_path.relative_to(REPO_ROOT)})")
        else:
            print(f"  [{label}] not found in {file_path.relative_to(REPO_ROOT) if file_path.exists() else '(missing file)'}")

    # Cross-reference with spec content as text scan
    spec_text = SPEC.read_text(encoding="utf-8")
    drifts = []
    for label, version in found.items():
        if version not in spec_text:
            drifts.append(f"[{label}] version {version} not mentioned in {SPEC.name}")

    if drifts:
        print("\nDrift detected:", file=sys.stderr)
        for d in drifts:
            print(f"  - {d}", file=sys.stderr)
        return 1

    print("\n[OK] All discoverable dictionary versions are referenced in spec")
    _ = spec  # parsed for validation; future: deeper structural checks
    return 0


if __name__ == "__main__":
    sys.exit(main())
