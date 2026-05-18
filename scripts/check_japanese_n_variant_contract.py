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

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/japanese-n-variant-contract.toml"


def load_contract() -> dict:
    with CONTRACT.open("rb") as fh:
        return tomllib.load(fh)


def extract_python_trigger_phonemes(py_src: str) -> dict[str, list[str]]:
    """Parse `_apply_n_phoneme_rules` and return variant -> trigger list mapping.

    Strategy: locate the body of `_apply_n_phoneme_rules`, then scan it for
    any line that assigns a phoneme variant (``result[i] = "N_x"``) and walk
    *upwards* a few lines to find the nearest ``in (...)``/``in [...]`` /
    ``in {...}`` literal collection plus the contents of any tuple/list/set
    assigned to a module-level constant referenced by the condition. This is
    robust to refactors such as:

      - tuple → list → set literal swaps
      - hoisting trigger collections to module-level constants
      - splitting the ``in (...)`` literal onto multiple lines
      - single-quoted vs double-quoted strings
      - ``match/case`` rewrites (case heads carry the literal)

    If the body cannot be located we return ``{}`` and let the contract check
    flag the missing variant — better an explicit failure than silently
    accepting drift.
    """
    triggers: dict[str, list[str]] = {}

    # 1. Locate the function body. Capture up to the next top-level `def`.
    body_re = re.compile(
        r"def\s+_apply_n_phoneme_rules\b.*?(?=\ndef |\nclass |\Z)",
        re.DOTALL,
    )
    body_match = body_re.search(py_src)
    if not body_match:
        return triggers
    body = body_match.group(0)
    body_lines = body.splitlines()

    # 2. Module-level constant references: collect mapping name -> [items].
    const_re = re.compile(
        r"^\s*(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*[\(\[\{](?P<items>[^)\]\}]+)[\)\]\}]",
        re.MULTILINE,
    )
    const_lookup: dict[str, list[str]] = {}
    for m in const_re.finditer(py_src):
        const_name = m.group("name")
        items_raw = m.group("items")
        items = re.findall(r"['\"]([^'\"]+)['\"]", items_raw)
        if items:
            const_lookup[const_name] = items

    # 3. For each assignment to result[i] = "N_*", walk back ≤8 lines to find
    #    the controlling `if/elif/case` literal (parenthesised list / set
    #    / tuple) or a constant reference. Tolerate multi-line ``in (...)``
    #    by accumulating until the brackets balance.
    bracket_pairs = {"(": ")", "[": "]", "{": "}"}
    assign_re = re.compile(r'result\[i\]\s*=\s*[\'"](N_[a-z]+)[\'"]')
    in_literal_start_re = re.compile(r"in\s*([\(\[\{])(?P<rest>.*)$")
    in_constant_re = re.compile(r"in\s+([A-Z_][A-Z0-9_]*)\b")
    case_literal_re = re.compile(r"case\s*[\(\[\{](?P<body>[^)\]\}]*)[\)\]\}]")
    case_constant_re = re.compile(r"case\s+([A-Z_][A-Z0-9_]*)\b")

    for idx, line in enumerate(body_lines):
        am = assign_re.search(line)
        if not am:
            continue
        variant = am.group(1)
        triggers.setdefault(variant, [])
        # Walk back to find the controlling literal/constant.
        for look_back in range(idx - 1, max(idx - 9, -1), -1):
            up = body_lines[look_back]
            # Match `in CONST_NAME`
            cm = in_constant_re.search(up)
            if cm:
                triggers[variant] = list(const_lookup.get(cm.group(1), []))
                break
            # Match `case CONST_NAME`
            ccm = case_constant_re.search(up)
            if ccm:
                triggers[variant] = list(const_lookup.get(ccm.group(1), []))
                break
            # Match `case (...)` / `case [...]` / `case {...}`
            cl = case_literal_re.search(up)
            if cl:
                triggers[variant] = re.findall(r"['\"]([^'\"]+)['\"]", cl.group("body"))
                break
            # Match `in (...)` possibly multi-line; accumulate until balanced.
            ilm = in_literal_start_re.search(up)
            if ilm:
                open_bracket = ilm.group(1)
                close_bracket = bracket_pairs[open_bracket]
                accum = ilm.group("rest")
                depth = accum.count(open_bracket) + 1 - accum.count(close_bracket)
                j = look_back + 1
                while depth > 0 and j < len(body_lines):
                    accum += "\n" + body_lines[j]
                    depth += body_lines[j].count(open_bracket)
                    depth -= body_lines[j].count(close_bracket)
                    j += 1
                inner = accum.rsplit(close_bracket, 1)[0]
                triggers[variant] = re.findall(r"['\"]([^'\"]+)['\"]", inner)
                break
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
