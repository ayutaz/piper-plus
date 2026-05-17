#!/usr/bin/env python3
# Wave 5-9 — Rust panic/unwrap density gate (crate-level budget).
#
# Why: 1973 件の unwrap/expect/panic が Rust source 全体に散在。 production
#   経路 (piper-core / piper-cli / piper-python) は低密度を維持し、 WASM の
#   ような relaxed 領域とは別 budget で track。 既存 clippy lint
#   (unwrap_used / expect_used) は per-occurrence gate で全件 suppression が
#   必要だが、 本 gate は crate ごとの density budget で「許容上限」 を pin
#   する regression-only ゲート。
#
# How to apply: docs/spec/unwrap-density-budget.toml の max_pct を超えたら
#   fail。 budget 緩和は PR で本 TOML を更新 + justification 必須。

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output

force_utf8_output()

ROOT = Path(__file__).resolve().parent.parent
BUDGET = ROOT / "docs" / "spec" / "unwrap-density-budget.toml"

UNWRAP_PATTERN = re.compile(r"\.unwrap\(\)|\.expect\(|panic!\(")


def _scan_crate(crate_root: Path) -> tuple[int, int]:
    """Return (unwrap_count, total_lines) for a crate's src/ tree.

    tests/ ディレクトリは除外 (test では unwrap が許容される)。
    """
    src_root = crate_root / "src"
    if not src_root.exists():
        return (0, 0)

    total_lines = 0
    unwrap_count = 0
    for path in src_root.rglob("*.rs"):
        if "tests" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        total_lines += text.count("\n") + 1
        unwrap_count += len(UNWRAP_PATTERN.findall(text))
    return (unwrap_count, total_lines)


def main() -> int:
    if not BUDGET.exists():
        print(f"::error::budget TOML missing: {BUDGET}", file=sys.stderr)
        return 1

    spec = tomllib.loads(BUDGET.read_text(encoding="utf-8"))
    crates = spec.get("crates", {})
    if not crates:
        print("::error::no [crates.*] entries in budget TOML", file=sys.stderr)
        return 1

    violations: list[str] = []
    warnings: list[str] = []
    ok_count = 0

    for crate_name, entry in sorted(crates.items()):
        crate_root = ROOT / "src" / "rust" / crate_name
        if not crate_root.exists():
            warnings.append(f"  - {crate_name}: src/rust/{crate_name} missing, skipped")
            continue

        unwraps, lines = _scan_crate(crate_root)
        if lines == 0:
            continue
        pct = unwraps / lines * 100.0
        max_pct = entry.get("max_pct", 5.0)

        if pct > max_pct:
            violations.append(
                f"  - {crate_name}: {unwraps} unwrap/expect/panic / "
                f"{lines} lines = {pct:.2f}% (budget ≤ {max_pct}%)"
            )
        else:
            ok_count += 1
            # 80% 以上消費している場合は warning (early signal)
            if pct > max_pct * 0.8:
                warnings.append(
                    f"  - {crate_name}: {pct:.2f}% / budget {max_pct}% "
                    f"({pct / max_pct * 100:.0f}% consumed)"
                )

    for w in warnings:
        print(f"::warning::Unwrap density nearing budget:{w[4:]}")

    if violations:
        print("::error::Unwrap density budget exceeded:")
        for v in violations:
            print(v)
        print()
        print(
            f"Update {BUDGET.relative_to(ROOT)} with the new budget and "
            f"justify in the PR description (intentional invariant pin via "
            f"expect, or refactor to Result+? propagation)."
        )
        return 1

    print(
        f"[check_unwrap_density] OK — {ok_count} crate(s) within budget, "
        f"{len(warnings)} approaching limits."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
