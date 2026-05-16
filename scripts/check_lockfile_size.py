#!/usr/bin/env python3
# Wave 5-4 — Lockfile size regression gate.
#
# Why: transitive dep 爆発 (1 dep 追加 → 30 sub-dep を pull) は CI cache /
#   build wall time / supply-chain attack surface を悪化させる。 lockfile
#   size の急増 (+50% in 1 PR) は早期 signal だが既存 gate は存在しない。
#   既存 lockfile-consistency gate は「9 runtime に lock があるか」 だけを
#   見ており、 size 増加は通知されない。
#
# How to apply: docs/spec/lockfile-size-baseline.toml の bytes 値と比較。
#   warn_pct (+20%) で stderr warning、 fail_pct (+50%) で fail。 意図的
#   bloat (e.g. PyTorch major upgrade) は baseline の bytes を update して
#   PR で justification を書く。 optional=true entry は monitor 対象外。

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "docs" / "spec" / "lockfile-size-baseline.toml"


def main() -> int:
    if not BASELINE.exists():
        print(f"::error::baseline TOML missing: {BASELINE}", file=sys.stderr)
        return 1

    spec = tomllib.loads(BASELINE.read_text(encoding="utf-8"))
    meta = spec.get("meta", {})
    warn_pct = meta.get("warn_pct", 20)
    fail_pct = meta.get("fail_pct", 50)

    lockfiles = spec.get("lockfiles", {})
    if not lockfiles:
        print("::error::no [lockfiles.*] entries in baseline TOML", file=sys.stderr)
        return 1

    warnings: list[str] = []
    errors: list[str] = []
    ok_count = 0

    for rel_path, entry in sorted(lockfiles.items()):
        path = ROOT / rel_path
        baseline_bytes = entry.get("bytes", 0)
        optional = entry.get("optional", False)

        if not path.exists():
            if optional:
                continue
            errors.append(f"  - {rel_path}: lockfile missing (baseline expected)")
            continue

        actual_bytes = path.stat().st_size
        if baseline_bytes == 0:
            # baseline 未設定 (optional/initial state) — skip
            if optional:
                continue
            warnings.append(
                f"  - {rel_path}: baseline=0 (uninitialized); actual={actual_bytes}"
            )
            continue

        delta = actual_bytes - baseline_bytes
        pct = (delta / baseline_bytes) * 100.0

        if pct >= fail_pct:
            errors.append(
                f"  - {rel_path}: {actual_bytes} bytes "
                f"(baseline {baseline_bytes}, {pct:+.1f}% ≥ fail threshold {fail_pct}%)"
            )
        elif pct >= warn_pct:
            warnings.append(
                f"  - {rel_path}: {actual_bytes} bytes "
                f"(baseline {baseline_bytes}, {pct:+.1f}% ≥ warn threshold {warn_pct}%)"
            )
        elif pct <= -warn_pct:
            warnings.append(
                f"  - {rel_path}: {actual_bytes} bytes "
                f"(baseline {baseline_bytes}, {pct:+.1f}% — baseline may be stale)"
            )
        else:
            ok_count += 1

    for w in warnings:
        print(f"::warning::{w[4:]}")  # strip leading "  - " for GHA annotation

    if errors:
        print("::error::Lockfile size regression detected:")
        for e in errors:
            print(e)
        print()
        print(
            f"Update {BASELINE.relative_to(ROOT)} with new bytes and justify "
            f"in the PR description (transitive dep update / intentional bloat)."
        )
        return 1

    print(
        f"[check_lockfile_size] OK — {ok_count} lockfile(s) within ±{warn_pct}%, "
        f"{len(warnings)} warning(s), 0 errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
