#!/usr/bin/env python3
"""Version manifest sync gate (Wave 3, S-4 Release 自動化).

`docs/spec/release-versions.toml` の `expected_prefix` と各 manifest の
実 version を比較し、 drift があれば warn/fail する。

mode (release-versions.toml の meta.mode):
  - "warn": drift があっても exit 0 (warning のみ、 初期 introduction 安全)
  - "fail": drift があれば exit 1 (post-hardening)

`--strict` flag を指定すると mode 設定を無視して "fail" 化 (pre-push hook
で tag push 時に強制 fail 用)。

CI 側の `.github/workflows/version-consistency.yml` と同等のロジック。
本 script は pre-push hook + /prepare-release skill から呼ばれる local 版。

Usage:
  uv run python scripts/check_version_manifest_sync.py
  uv run python scripts/check_version_manifest_sync.py --strict
  uv run python scripts/check_version_manifest_sync.py --verbose

Exit codes:
  0 -- 全 manifest が expected_prefix と一致 (または warn mode で drift)
  1 -- fail mode + drift / spec file 不在 / extract error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = REPO_ROOT / "docs" / "spec" / "release-versions.toml"


def read_text(rel: str) -> str:
    p = REPO_ROOT / rel
    if not p.exists():
        raise FileNotFoundError(rel)
    return p.read_text(encoding="utf-8")


def extract_version_file(rel: str) -> str:
    return read_text(rel).strip()


def extract_csproj(rel: str) -> str:
    text = read_text(rel)
    m = re.search(r"<Version>([^<]+)</Version>", text)
    if not m:
        raise ValueError(f"<Version> not found in {rel}")
    return m.group(1).strip()


def extract_cargo_workspace(rel: str) -> str:
    text = read_text(rel)
    for line in text.splitlines():
        m = re.match(r'^\s*version\s*=\s*"([^"]+)"\s*$', line)
        if m:
            return m.group(1)
    raise ValueError(f"version line not found in {rel}")


def extract_package_json(rel: str) -> str:
    data = json.loads(read_text(rel))
    return str(data["version"])


def extract_swift_let(rel: str, field: str) -> str:
    text = read_text(rel)
    pat = rf'^\s*let\s+{re.escape(field)}\s*=\s*"([^"]+)"'
    m = re.search(pat, text, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"`let {field}` not found in {rel}")
    return m.group(1)


def extract_gradle_property(rel: str, field: str) -> str:
    text = read_text(rel)
    pat = rf'^\s*{re.escape(field)}\s*=\s*([^\s#]+)'
    m = re.search(pat, text, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"property `{field}` not found in {rel}")
    return m.group(1).strip()


def detect_pyproject_dynamic(rel: str) -> bool:
    text = read_text(rel)
    return bool(re.search(r'dynamic\s*=\s*\[\s*"version"\s*\]', text))


def extract(manifest: str, field: str | None) -> str:
    """Dispatch by file extension / field name."""
    if manifest == "VERSION":
        return extract_version_file(manifest)
    if manifest.endswith(".csproj"):
        return extract_csproj(manifest)
    if manifest.endswith("Cargo.toml"):
        return extract_cargo_workspace(manifest)
    if manifest.endswith("package.json"):
        return extract_package_json(manifest)
    if manifest.endswith("Package.swift") and field:
        return extract_swift_let(manifest, field)
    if manifest.endswith("gradle.properties") and field:
        return extract_gradle_property(manifest, field)
    raise ValueError(f"no extractor for manifest={manifest}, field={field}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Version manifest sync gate")
    parser.add_argument("--strict", action="store_true",
                        help="force mode='fail' regardless of toml setting")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="print each manifest's comparison result")
    args = parser.parse_args()

    if not SPEC.exists():
        print(f"error: missing {SPEC}", file=sys.stderr)
        return 1

    with SPEC.open("rb") as fh:
        spec = tomllib.load(fh)

    mode_from_toml = spec.get("meta", {}).get("mode", "warn")
    mode = "fail" if args.strict else mode_from_toml
    if mode not in ("warn", "fail"):
        mode = "warn"

    failures: list[str] = []
    warnings_: list[str] = []
    ok_count = 0

    for section_name, body in spec.items():
        if section_name == "meta" or not isinstance(body, dict):
            continue
        entries: list[tuple[str, dict]] = []
        if "manifest" in body:
            entries.append((section_name, body))
        for sub_name, sub_body in body.items():
            if isinstance(sub_body, dict) and "manifest" in sub_body:
                entries.append((f"{section_name}.{sub_name}", sub_body))
        for label, entry in entries:
            manifest = entry["manifest"]
            expected = entry.get("expected_prefix")
            field = entry.get("field")
            dynamic = entry.get("dynamic", False)
            try:
                if dynamic and manifest.endswith("pyproject.toml"):
                    if detect_pyproject_dynamic(manifest):
                        if args.verbose:
                            print(f"OK    {label:30s}  manifest={manifest}  (dynamic)")
                        ok_count += 1
                    else:
                        msg = (f"{label}: pyproject.toml expected "
                               f"`dynamic = ['version']`")
                        (failures if mode == "fail" else warnings_).append(msg)
                    continue
                actual = extract(manifest, field)
                if expected and actual.startswith(expected):
                    if args.verbose:
                        print(f"OK    {label:30s}  manifest={manifest}  "
                              f"actual={actual} prefix={expected}")
                    ok_count += 1
                else:
                    msg = (f"{label}: {manifest} reports `{actual}` but "
                           f"expected_prefix is `{expected}`")
                    if mode == "fail":
                        failures.append(msg)
                    else:
                        warnings_.append(msg)
            except (FileNotFoundError, ValueError) as exc:
                msg = f"{label}: extract failed for {manifest}: {exc}"
                if mode == "fail":
                    failures.append(msg)
                else:
                    warnings_.append(msg)

    if warnings_:
        print("warning: version drift detected", file=sys.stderr)
        for line in warnings_:
            print(f"  {line}", file=sys.stderr)

    if failures:
        print("error: version drift detected (strict / fail mode)",
              file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"version-consistency gate OK: {ok_count} manifest(s) match "
          f"({len(warnings_)} warning(s), mode={mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
