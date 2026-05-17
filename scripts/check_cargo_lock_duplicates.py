#!/usr/bin/env python3
# Wave 5-4 — Cargo.lock duplicate crate detection (regression-only ゲート).
#
# Why: workspace 5 member + feature gate の組み合わせで同一 crate の異なる
#   version が Cargo.lock に複数登録される。 binary size 増 + 異 ABI 併存
#   (e.g. ort 1.x vs 2.x) の risk。 transitive dep 起因の既存併存は
#   docs/spec/cargo-lock-duplicates-baseline.toml に allowlist 化済、
#   新規 duplicate のみ fail させる。
#
# How to apply: pre-commit / CI gate。 baseline TOML の count を ≤ として
#   扱い、 新 crate の duplicate 出現 / 既存 entry の count 増加で fail。
#   baseline は transitive update PR で必要に応じて更新する (review で説明)。

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output

force_utf8_output()

ROOT = Path(__file__).resolve().parent.parent
LOCKFILE = ROOT / "src" / "rust" / "Cargo.lock"
BASELINE = ROOT / "docs" / "spec" / "cargo-lock-duplicates-baseline.toml"


def _parse_lockfile_names(path: Path) -> dict[str, int]:
    """Cargo.lock を line-by-line parse、 crate name の出現回数 dict を返す。

    Cargo.lock は厳密 TOML だが size が大きく array-of-tables のみ
    必要なので regex 抽出で高速化。
    """
    name_pattern = re.compile(r'^\[\[package\]\]\s*$\nname\s*=\s*"([^"]+)"', re.MULTILINE)
    text = path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    for match in name_pattern.finditer(text):
        name = match.group(1)
        counts[name] = counts.get(name, 0) + 1
    return counts


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("allowlist", {}))


def main() -> int:
    if not LOCKFILE.exists():
        print(f"::error::{LOCKFILE} not found", file=sys.stderr)
        return 1

    counts = _parse_lockfile_names(LOCKFILE)
    baseline = _load_baseline(BASELINE)

    duplicates = {name: c for name, c in counts.items() if c > 1}

    violations: list[str] = []
    for name, count in sorted(duplicates.items()):
        allowed = baseline.get(name)
        if allowed is None:
            violations.append(
                f"  - {name}: {count} versions (NEW duplicate — not in baseline)"
            )
        elif count > allowed:
            violations.append(
                f"  - {name}: {count} versions (baseline allows ≤ {allowed})"
            )

    # Detect baseline-stale entries (allowlisted but no longer duplicated).
    stale = [
        name for name, allowed in baseline.items()
        if counts.get(name, 0) <= 1
    ]

    if violations:
        print("::error::Cargo.lock duplicate gate failed:")
        for v in violations:
            print(v)
        print()
        print(
            "If this duplicate is intentional (e.g. transitive dep upgrade),"
        )
        print(
            f"  update {BASELINE.relative_to(ROOT)} with the new count and"
        )
        print("  explain the change in the PR description.")
        return 1

    print(
        f"[check_cargo_lock_duplicates] OK — {len(duplicates)} crate(s) "
        f"duplicated, all within baseline limits."
    )
    if stale:
        print(
            f"[check_cargo_lock_duplicates] Note: {len(stale)} baseline "
            f"entry/entries no longer duplicated (could be removed from "
            f"baseline TOML on next refresh): {', '.join(stale)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
