#!/usr/bin/env python3
"""Japanese N-variant cross-runtime contract gate.

「ん」の 4 つの allophone (N_m / N_n / N_ng / N_uvular) が同一の同化規則で
全 G2P ランタイムに実装されているかを検証する。 drift = silent acoustic
regression for Japanese audio.

検証内容:

  1. contract toml が parse でき、 [rules.*] / [runtime_sources] が揃う
  2. 4 つの variant symbol が canonical Python 実装に出現する
  3. canonical Python 実装の trigger_phonemes tuple が contract と一致
  4. 各 runtime source に 4 つの variant symbol が string literal として
     出現する (G2P-only と inference-only で別パスを許容)

完全 byte-for-byte byte 比較は要求しない (HashSet vs tuple の表現差を許容)。
変更が必要な場合は contract toml と canonical Python 実装の両方を更新し、
他 runtime には grep ベースの存在確認を行う。

Usage:
    python scripts/check_japanese_n_variant_contract.py
    python scripts/check_japanese_n_variant_contract.py --verbose

Exit codes:
    0 -- drift なし
    1 -- variant 欠落 / trigger 不一致
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/japanese-n-variant-contract.toml"


def load_contract() -> dict:
    with CONTRACT.open("rb") as fh:
        return tomllib.load(fh)


def extract_python_trigger_phonemes(py_src: str) -> dict[str, list[str]]:
    """Parse `_apply_n_phoneme_rules` and return variant -> trigger list mapping.

    Looks for the Python source's literal tuples after each ``elif next_phoneme in``
    line. Conservative regex; if the Python source is refactored this needs
    updating, which is intentional — refactors should land with a contract bump.
    """
    triggers: dict[str, list[str]] = {}
    pattern = re.compile(
        r'elif next_phoneme in \(([^)]+)\):\s*\n\s*result\[i\]\s*=\s*"(N_[a-z]+)"',
        re.MULTILINE,
    )
    for m in pattern.finditer(py_src):
        items_raw = m.group(1)
        variant = m.group(2)
        items = re.findall(r'"([^"]+)"', items_raw)
        triggers[variant] = items
    return triggers


def verify_runtime_has_variants(source_path: Path, variants: list[str]) -> list[str]:
    """Return the subset of ``variants`` that do NOT appear in ``source_path``."""
    if not source_path.exists():
        return [f"<missing file: {source_path}>"]
    text = source_path.read_text(encoding="utf-8", errors="replace")
    return [v for v in variants if v not in text]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    contract = load_contract()
    variants: list[str] = contract["variants"]["all"]
    rules = contract["rules"]
    runtime_sources = contract["runtime_sources"]
    canonical_path = REPO_ROOT / contract["meta"]["canonical_source"]

    errors: list[str] = []

    if not canonical_path.exists():
        print(f"error: canonical source not found: {canonical_path}", file=sys.stderr)
        return 1

    py_src = canonical_path.read_text(encoding="utf-8")
    py_triggers = extract_python_trigger_phonemes(py_src)

    # 2. variant symbols appear in canonical source
    for variant in variants:
        if variant not in py_src:
            errors.append(f"  canonical Python missing variant string: {variant}")

    # 3. trigger lists match contract
    for variant in variants:
        contract_triggers = list(rules[variant]["trigger_phonemes"])
        if not contract_triggers:
            continue  # N_uvular is the default; no explicit trigger list
        py_t = py_triggers.get(variant, [])
        if set(py_t) != set(contract_triggers):
            errors.append(
                f"  trigger mismatch for {variant}:\n"
                f"    contract: {sorted(contract_triggers)}\n"
                f"    python:   {sorted(py_t)}"
            )

    # 4. variant symbols present in each runtime source
    for runtime_label, rel_path in runtime_sources.items():
        if runtime_label == "python":
            continue  # already canonical
        src_path = REPO_ROOT / rel_path
        missing = verify_runtime_has_variants(src_path, variants)
        if missing:
            errors.append(
                f"  runtime [{runtime_label}] ({rel_path}) missing variants: {missing}"
            )

    if errors:
        print("Japanese N-variant contract drift:", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
        print(
            "\nFix: update docs/spec/japanese-n-variant-contract.toml + Python "
            "canonical (japanese.py:_apply_n_phoneme_rules) + missing runtimes.",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        print(f"verified variants: {variants}")
        for variant in variants:
            print(f"  {variant}: trigger={rules[variant]['trigger_phonemes']}")
    print(
        f"OK Japanese N-variant contract: {len(variants)} variants × "
        f"{len(runtime_sources)} runtime sources"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
