#!/usr/bin/env python3
"""Public ABI snapshot diff (M3.1).

各 surface (C / Swift / Kotlin) の現行 snapshot と baseline JSON を比較し、
**削除 / 型変更 (breaking)** を fail に、 **追加のみ (compatible)** を pass に
分類する CLI。 snapshot 抽出 (nm / abi-dumper / swift symbolgraph /
binary-compatibility-validator) は workflow 側に分離し、 本 script は
「JSON in / JSON out + markdown 差分」 という pure な比較レイヤだけ持つ
(test 容易性 + 抽出ツール差し替え柔軟性)。

判定ロジック:

* C: ``symbols`` / ``structs`` / ``enums`` / ``constants`` の各 element を
  ``name`` で identify。 baseline にあって current に無い → ``removed``。
  ``name`` 一致だが signature / fields / values が変わった → ``changed``。
  current 側にだけ新規 → ``added``。
* Swift / Kotlin: ``declarations`` を identifier (``usr`` or normalized
  signature) で identify、 同様の add / remove / change を判定。

``removed`` または ``changed`` が 1 件でもあれば exit 1 (informational tier
時は ``--no-fail`` で OK)。 ``--allow-breaking`` フラグは
``update-abi-baseline`` label が付いた PR で workflow から渡される。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class DiffSection:
    surface: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class DiffReport:
    sections: list[DiffSection] = field(default_factory=list)
    bootstrap: bool = False

    @property
    def has_breaking(self) -> bool:
        return any(s.removed or s.changed for s in self.sections)


def _normalize(items: list[dict], key: str) -> dict[str, dict]:
    """Index a list of dicts by ``key`` (e.g., ``name``)."""
    out: dict[str, dict] = {}
    for item in items:
        if key not in item:
            continue
        out[item[key]] = item
    return out


def _signature_of(item: dict) -> str:
    """Best-effort canonical signature for a single declaration.

    The exact key depends on the surface (`signature` for C functions,
    `usr` for Swift, `declaration` for Kotlin). We pin the field
    preferences here so all three surfaces share one comparison code path.
    """
    for k in ("signature", "usr", "declaration", "fields", "values", "type", "value"):
        if k in item:
            return json.dumps(item[k], sort_keys=True, ensure_ascii=False)
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def diff_collection(
    surface: str,
    baseline_items: list[dict],
    current_items: list[dict],
    key: str = "name",
) -> DiffSection:
    base = _normalize(baseline_items, key)
    cur = _normalize(current_items, key)
    section = DiffSection(surface=surface)
    for name in cur:
        if name not in base:
            section.added.append(name)
    for name in base:
        if name not in cur:
            section.removed.append(name)
    for name in base:
        if name in cur:
            b_sig = _signature_of(base[name])
            c_sig = _signature_of(cur[name])
            if b_sig != c_sig:
                section.changed.append((name, b_sig[:80], c_sig[:80]))
    return section


def diff_c(baseline: dict, current: dict) -> list[DiffSection]:
    return [
        diff_collection(
            "c-symbols", baseline.get("symbols", []), current.get("symbols", [])
        ),
        diff_collection(
            "c-structs", baseline.get("structs", []), current.get("structs", [])
        ),
        diff_collection("c-enums", baseline.get("enums", []), current.get("enums", [])),
        diff_collection(
            "c-constants", baseline.get("constants", []), current.get("constants", [])
        ),
    ]


def diff_swift(baseline: dict, current: dict) -> list[DiffSection]:
    return [
        diff_collection(
            "swift-declarations",
            baseline.get("declarations", []),
            current.get("declarations", []),
            key="usr",
        )
    ]


def diff_kotlin(baseline: dict, current: dict) -> list[DiffSection]:
    return [
        diff_collection(
            "kotlin-declarations",
            baseline.get("declarations", []),
            current.get("declarations", []),
            key="declaration",
        )
    ]


SURFACE_DIFFS = {
    "c": diff_c,
    "swift": diff_swift,
    "kotlin": diff_kotlin,
}


def is_bootstrap(baseline: dict) -> bool:
    """A baseline is in bootstrap mode when all of its collections are empty.

    Bootstrap baselines never produce ``removed`` / ``changed`` rows, so the
    diff is always pass; the first real snapshot landing seeds the baseline
    via the update-abi-baseline label workflow.
    """
    return all(not (isinstance(v, list) and v) for v in baseline.values())


def render_markdown(report: DiffReport) -> str:
    lines = ["## Public ABI snapshot diff", ""]
    if report.bootstrap:
        lines.append(
            "_Bootstrap mode: baseline is empty, recording first observation._"
        )
        lines.append("")
    for section in report.sections:
        if not (section.added or section.removed or section.changed):
            continue
        lines.append(f"### {section.surface}")
        if section.removed:
            lines.append("- **removed (breaking):**")
            for name in section.removed:
                lines.append(f"  - `{name}`")
        if section.changed:
            lines.append("- **changed (breaking):**")
            for name, b, c in section.changed:
                lines.append(f"  - `{name}`: was `{b}`, now `{c}`")
        if section.added:
            lines.append("- **added (compatible):**")
            for name in section.added:
                lines.append(f"  - `{name}`")
        lines.append("")
    if all(not (s.added or s.removed or s.changed) for s in report.sections):
        lines.append("No ABI changes detected.")
    return "\n".join(lines).rstrip() + "\n"


def cmd_diff(args: argparse.Namespace) -> int:
    surface = args.surface
    if surface not in SURFACE_DIFFS:
        print(f"unknown surface: {surface}", file=sys.stderr)
        return 2
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    sections = SURFACE_DIFFS[surface](baseline, current)
    report = DiffReport(sections=sections, bootstrap=is_bootstrap(baseline))
    md = render_markdown(report)
    print(md)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    if report.has_breaking and not (report.bootstrap or args.allow_breaking):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff")
    d.add_argument("--surface", choices=list(SURFACE_DIFFS), required=True)
    d.add_argument("--baseline", type=Path, required=True)
    d.add_argument("--current", type=Path, required=True)
    d.add_argument("--output", type=Path, default=None)
    d.add_argument(
        "--allow-breaking",
        action="store_true",
        help="Pass even if breaking changes exist (`update-abi-baseline` label).",
    )
    d.set_defaults(func=cmd_diff)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
