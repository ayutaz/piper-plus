#!/usr/bin/env python3
# Wave 5-13 — uv workspace member requires-python parity gate.
#
# Why: uv workspace の member pyproject (root / src/python / src/python_run /
#   src/python_stub / src/rust/piper-python / src/python/g2p) で requires-python
#   が drift すると、 一部 member だけ古い Python で動作 → import 時に
#   silent failure / type error が発生する。 既存 ruff version sync gate と
#   同パターンで「全 pyproject の requires-python が一致」 を pin する。
#
# How to apply: pre-commit / CI gate。 全 pyproject.toml を tomllib parse、
#   requires-python 値の unique 集合が 1 でない場合 fail。

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 監視対象 pyproject.toml (uv workspace member + 主要 sub-project)。
# build artifacts (build/, build-full/, build-shared/) と venv は除外。
TARGETS = [
    "pyproject.toml",
    "src/python/pyproject.toml",
    "src/python_run/pyproject.toml",
    "src/python_stub/pyproject.toml",
    "src/rust/piper-python/pyproject.toml",
    "src/python/g2p/pyproject.toml",
    # src/piper_phonemize_bundled は HiFi-GAN legacy bundle なので除外
]


def main() -> int:
    found: dict[str, str | None] = {}
    missing: list[str] = []

    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            print(f"::error file={rel}::TOML parse failed: {e}")
            return 1

        project = data.get("project") or {}
        req = project.get("requires-python")
        found[rel] = req

    if missing:
        print(f"::warning::Workspace members missing: {', '.join(missing)}")

    if not found:
        print("::error::No pyproject.toml files found", file=sys.stderr)
        return 1

    # None (unspecified) は library 用 sub-project では valid のため warning に降格。
    with_value = {rel: v for rel, v in found.items() if v is not None}
    without_value = [rel for rel, v in found.items() if v is None]

    if without_value:
        for rel in without_value:
            print(
                f"::warning file={rel}::requires-python not set "
                f"(library sub-project may inherit from workspace, but explicit is preferred)"
            )

    unique_values = set(with_value.values())
    if len(unique_values) > 1:
        print("::error::Workspace requires-python drift detected:")
        for rel, value in sorted(with_value.items()):
            print(f"  - {rel}: {value}")
        print()
        print(
            "All workspace members should pin the same requires-python to "
            "prevent silent import-time failures on lower Python versions."
        )
        return 1

    canonical = next(iter(unique_values))
    print(
        f"[check_workspace_python_parity] OK — {len(with_value)} member(s) "
        f"all pinned to requires-python={canonical}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
