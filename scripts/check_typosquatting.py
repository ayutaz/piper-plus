#!/usr/bin/env python3
"""Typosquatting watch — 5-registry Levenshtein + homograph scan (M3.3).

PyPI / npm / crates.io / NuGet / Maven Central を週次 polling し、
``piper-plus`` の類似名 package が新規 publish された場合に GitHub Issue
を auto-create する supply-chain 監視 CLI。

判定の階層:

1. **canonical exact match** — canonical package そのもの (`piper-plus`,
   `@piper-plus/g2p` 等) は除外。
2. **allowlist** — `tests/fixtures/typosquatting-allowlist.json` に列挙された
   既知 false positive (`piper`, `piper-phonemize` 等) も除外。
3. **Levenshtein distance ≤ max_distance** — 1〜2 文字違いを suspicious と
   見なす。 default は 2。
4. **homograph attack** — `o↔0`, `l↔I`, ASCII↔Cyrillic 等を組合せで生成し、
   一致するものを別途検出。 距離計算より早く落とせる場合に短絡。

サブコマンド:

* ``scan``     — registry の API を呼ぶ。 ``--registry-fixture`` が渡されたら
                  そのファイルを read し offline scan に切り替える
                  (テスト・ローカル検証用)。
* ``classify`` — 候補 package 名 list (改行区切り) を読み、 typosquat か否か
                  だけを判定する純粋ロジック (test 容易性)。

stdlib only。 PyPI / npm 等の REST 呼び出しは ``--registry-fixture`` 不使用
時にしか走らないため unit テスト時は遅延 import の手前で済む。
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALLOWLIST = REPO_ROOT / "tests/fixtures/typosquatting-allowlist.json"

# Package names we are responsible for (across the 5 registries).
CANONICAL_NAMES = frozenset(
    {
        "piper-plus",
        "piper_plus",
        "@piper-plus/g2p",
        "piper-plus-cli",
        "piper-plus-g2p",
        "piper-plus-g2p-android",
        "piperplus.core",
        "piperplus.cli",
        "io.github.ayutaz:piper-plus-g2p-android",
    }
)

# ASCII / leet / Cyrillic homograph pairs.
HOMOGRAPH_PAIRS = (
    ("l", "1"),
    ("l", "i"),
    ("i", "l"),
    ("o", "0"),
    ("e", "3"),
    ("i", "1"),
    ("p", "р"),  # ASCII p ↔ Cyrillic ер (U+0440)
    ("e", "е"),  # ASCII e ↔ Cyrillic ie (U+0435)
    ("a", "а"),  # ASCII a ↔ Cyrillic a (U+0430)
    ("s", "ѕ"),  # ASCII s ↔ Cyrillic dze (U+0455)
    ("c", "с"),  # ASCII c ↔ Cyrillic es (U+0441)
)


@dataclass(frozen=True)
class Suspect:
    name: str
    registry: str
    reason: str
    distance: int


def levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    previous = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current = [i + 1]
        for j, c2 in enumerate(s2):
            current.append(
                min(
                    previous[j + 1] + 1,
                    current[j] + 1,
                    previous[j] + (c1 != c2),
                )
            )
        previous = current
    return previous[-1]


def homograph_candidates(canonical: str) -> set[str]:
    """Generate every name that arises by applying one or more
    `HOMOGRAPH_PAIRS` substitutions to `canonical`.

    The function caps the combinatorial explosion at 2^16 candidates which
    is plenty for any name we publish (longest is 14 chars).
    """
    options: list[set[str]] = []
    for ch in canonical:
        opts = {ch}
        for a, b in HOMOGRAPH_PAIRS:
            if ch == a:
                opts.add(b)
            elif ch == b:
                opts.add(a)
        options.append(opts)
    total = 1
    for o in options:
        total *= len(o)
        if total > 65536:
            # Fall back to a no-substitution result so we never run away.
            return {canonical}
    result: set[str] = set()
    for combo in itertools.product(*options):
        result.add("".join(combo))
    result.discard(canonical)
    return result


def load_allowlist(path: Path = DEFAULT_ALLOWLIST) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s.lower() for s in data.get("allowed", [])}


def is_canonical(name: str) -> bool:
    return name.lower() in {c.lower() for c in CANONICAL_NAMES}


def classify(
    candidates: list[tuple[str, str]],
    *,
    canonical: str = "piper-plus",
    max_distance: int = 2,
    allowlist: set[str] | None = None,
) -> list[Suspect]:
    """candidates is a list of (registry, package_name) pairs.

    Returns the suspects in order, deduplicated by (registry, name).
    """
    allowlist = allowlist or set()
    homographs = homograph_candidates(canonical)
    seen: set[tuple[str, str]] = set()
    out: list[Suspect] = []
    for registry, name in candidates:
        key = (registry, name.lower())
        if key in seen:
            continue
        seen.add(key)
        lower = name.lower()
        if is_canonical(name):
            continue
        if lower in allowlist:
            continue
        if lower in homographs:
            out.append(
                Suspect(name=name, registry=registry, reason="homograph", distance=0)
            )
            continue
        dist = levenshtein(lower, canonical)
        if 0 < dist <= max_distance:
            out.append(
                Suspect(
                    name=name,
                    registry=registry,
                    reason="levenshtein",
                    distance=dist,
                )
            )
    return out


def render_markdown(suspects: list[Suspect], scanned: int) -> str:
    lines = [
        "## Typosquatting watch",
        "",
        f"Packages scanned: **{scanned}**, suspects: **{len(suspects)}**.",
        "",
    ]
    if not suspects:
        lines.append("No suspicious package names this cycle.")
        return "\n".join(lines).rstrip() + "\n"
    lines.append("| Registry | Package | Reason | Distance |")
    lines.append("|----------|---------|--------|----------|")
    for s in suspects:
        lines.append(f"| `{s.registry}` | `{s.name}` | {s.reason} | {s.distance} |")
    return "\n".join(lines).rstrip() + "\n"


def cmd_classify(args: argparse.Namespace) -> int:
    text = (
        args.input.read_text(encoding="utf-8")
        if args.input
        else sys.stdin.read()
    )
    candidates: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            registry, name = line.split("\t", 1)
        else:
            registry, name = "stdin", line
        candidates.append((registry.strip(), name.strip()))
    allowlist = load_allowlist(args.allowlist)
    suspects = classify(
        candidates,
        canonical=args.canonical,
        max_distance=args.max_distance,
        allowlist=allowlist,
    )
    md = render_markdown(suspects, scanned=len(candidates))
    print(md)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    if args.fail_on_suspect and suspects:
        return 1
    return 0


def cmd_scan(args: argparse.Namespace) -> int:  # pragma: no cover (network)
    """Polling 用 entrypoint (CI 専用)。 fixture 渡し時は network を叩かず
    そのファイルに含まれる候補だけを classify する。"""
    if not args.registry_fixture:
        print(
            "scan requires --registry-fixture for now; network polling is "
            "implemented in the CI workflow that wraps this script.",
            file=sys.stderr,
        )
        return 2
    raw = json.loads(args.registry_fixture.read_text(encoding="utf-8"))
    candidates = [(entry["registry"], entry["name"]) for entry in raw.get("entries", [])]
    allowlist = load_allowlist(args.allowlist)
    suspects = classify(
        candidates,
        canonical=args.canonical,
        max_distance=args.max_distance,
        allowlist=allowlist,
    )
    md = render_markdown(suspects, scanned=len(candidates))
    print(md)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    return 1 if (suspects and args.fail_on_suspect) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, func in (("classify", cmd_classify), ("scan", cmd_scan)):
        s = sub.add_parser(name)
        s.add_argument("--canonical", default="piper-plus")
        s.add_argument("--max-distance", type=int, default=2)
        s.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
        s.add_argument("--output", type=Path, default=None)
        s.add_argument("--fail-on-suspect", action="store_true")
        if name == "classify":
            s.add_argument(
                "--input",
                type=Path,
                default=None,
                help="One package per line; optional 'registry\\tname'.",
            )
        else:
            s.add_argument("--registry-fixture", type=Path, default=None)
        s.set_defaults(func=func)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
