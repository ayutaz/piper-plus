#!/usr/bin/env python3
"""docs/spec/*.toml の [meta] section schema validation (Wave 3).

全 spec TOML に対し以下を検査:
  1. [meta] section が存在する
  2. `forward_compat_policy` field がある (値は "strict" / "accept_unknown_fields"
     / "ignore_future_entries" のいずれか)

将来 spec TOML を新規追加するときに、 [meta] block の付与忘れを catch する
ための minimum schema gate。 Wave 3 で scripts/migrate_spec_meta.py により
既存 24 spec は全て統一済み。

`_implementation-map.auto.toml` のような auto-generated file は除外 (filename
が `_` で始まる)。

Usage:
  uv run python scripts/check_spec_meta.py

Exit codes:
  0 -- 全 spec が [meta] + forward_compat_policy を持つ
  1 -- drift 検出 (printed report)
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "docs" / "spec"

ALLOWED_POLICIES = {"strict", "accept_unknown_fields", "ignore_future_entries"}


def check_file(path: Path) -> list[str]:
    """Return list of failure messages for a single TOML file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{path.name}: TOML parse error: {exc}"]
    except OSError as exc:
        return [f"{path.name}: read error: {exc}"]

    failures: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict):
        failures.append(f"{path.name}: missing [meta] section")
        return failures
    policy = meta.get("forward_compat_policy")
    if policy is None:
        failures.append(
            f"{path.name}: missing meta.forward_compat_policy "
            f"(add `forward_compat_policy = \"strict\"`)"
        )
    elif policy not in ALLOWED_POLICIES:
        failures.append(
            f"{path.name}: invalid meta.forward_compat_policy={policy!r} "
            f"(must be one of {sorted(ALLOWED_POLICIES)})"
        )
    return failures


def main() -> int:
    if not SPEC_DIR.is_dir():
        print(f"error: {SPEC_DIR} not found", file=sys.stderr)
        return 1

    tomls = [p for p in sorted(SPEC_DIR.glob("*.toml")) if not p.name.startswith("_")]
    if not tomls:
        print("no spec TOML files; nothing to check")
        return 0

    all_failures: list[str] = []
    for path in tomls:
        all_failures.extend(check_file(path))

    if all_failures:
        print("spec [meta] schema gate: failures", file=sys.stderr)
        for line in all_failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"spec [meta] schema gate OK: {len(tomls)} spec(s) inspected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
