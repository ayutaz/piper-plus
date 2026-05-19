#!/usr/bin/env python3
"""Chinese (Mandarin) tone symbol cross-runtime contract gate.

5 つの tone marker (tone1 / tone2 / tone3 / tone4 / tone5) が全 G2P
ランタイム (Python canonical / Rust / Go / C# / WASM / C++) で同じ表記
かつ同じ PUA mapping を持っているかを検証する。

drift = silent embedding ID shift = wrong pitch contour for Mandarin
audio (catastrophic; ピッチが完全に違う発音となる)。

検証内容:

  1. contract toml が parse でき、 [tones] / [[tone_definitions]] /
     [runtime_sources] が揃う
  2. 5 つの tone symbol が canonical Python (chinese.py) に literal 出現
  3. canonical 関数 `_pinyin_to_ipa` が `f"tone{tone}"` 形式で tone を
     emit している (regex 検証)
  4. 各 runtime source に 5 つの tone symbol が string literal として出現
  5. PUA codepoint が pua.json (canonical) と一致 (check_pua_consistency.py
     との二重 gate)

Usage:
    python scripts/check_chinese_tone_contract.py
    python scripts/check_chinese_tone_contract.py --verbose

Exit codes:
    0 -- drift なし
    1 -- 欠落 / 不一致
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/chinese-tone-contract.toml"
PUA_JSON = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/pua.json"


def load_contract() -> dict:
    with CONTRACT.open("rb") as fh:
        return tomllib.load(fh)


def _normalize_codepoint(cp: object) -> str | None:
    """Normalize a codepoint value of any common shape into canonical "U+XXXX".

    Accepted inputs: int (e.g. 0xE046), hex string with `0x` prefix
    (`"0xE046"`), `U+`-prefixed string (`"U+E046"`), or a bare hex string
    (`"E046"`). Returns None when the value cannot be coerced — keeps the
    caller's drift report explicit rather than silently passing through.
    """
    if cp is None:
        return None
    if isinstance(cp, int):
        return f"U+{cp:04X}"
    if isinstance(cp, str):
        s = cp.strip()
        if s.lower().startswith("u+"):
            try:
                return f"U+{int(s[2:], 16):04X}"
            except ValueError:
                return None
        if s.lower().startswith("0x"):
            try:
                return f"U+{int(s, 16):04X}"
            except ValueError:
                return None
        # Bare hex — interpret as base-16.
        if all(c in "0123456789abcdefABCDEF" for c in s) and s:
            try:
                return f"U+{int(s, 16):04X}"
            except ValueError:
                return None
    return None


def load_pua_codepoints() -> dict[str, str]:
    """Return mapping token -> canonical "U+XXXX" string for pua.json entries."""
    with PUA_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    out: dict[str, str] = {}
    entries = data.get("entries") or data.get("mappings") or []
    if isinstance(entries, dict):
        entries = [
            {"token": k, **(v if isinstance(v, dict) else {"codepoint": v})}
            for k, v in entries.items()
        ]
    for entry in entries:
        token = entry.get("token") or entry.get("name")
        cp = (
            entry.get("codepoint")
            or entry.get("pua_codepoint")
            or entry.get("codepoint_hex")
        )
        if token is None:
            continue
        normalized = _normalize_codepoint(cp)
        if normalized is None:
            continue
        out[token] = normalized
    return out


PUA_CODEPOINT_BY_SYMBOL = {
    "tone1": "0xE046",
    "tone2": "0xE047",
    "tone3": "0xE048",
    "tone4": "0xE049",
    "tone5": "0xE04A",
}


def verify_runtime_has_symbols(source_path: Path, symbols: list[str]) -> list[str]:
    """Symbol を string literal OR PUA codepoint hex の何れかで持っているか確認。"""
    if not source_path.exists():
        return [f"<missing file: {source_path}>"]
    text = source_path.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for s in symbols:
        cp = PUA_CODEPOINT_BY_SYMBOL.get(s, "")
        if s in text:
            continue
        if cp and cp.lower() in text.lower():
            continue
        missing.append(s)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    contract = load_contract()
    symbols: list[str] = contract["tones"]["all"]
    runtime_sources = contract["runtime_sources"]
    canonical_path = REPO_ROOT / contract["meta"]["canonical_source"]
    canonical_function = contract["meta"]["canonical_function"]

    errors: list[str] = []

    if not canonical_path.exists():
        print(f"error: canonical source not found: {canonical_path}", file=sys.stderr)
        return 1

    py_src = canonical_path.read_text(encoding="utf-8")

    # 2. symbols are emitted by canonical source
    # canonical Python uses f"tone{tone}" to generate tone1-5 dynamically;
    # accept either explicit literal OR the f-string pattern.
    has_fstring = 'f"tone{' in py_src or "f'tone{" in py_src
    for symbol in symbols:
        if symbol in py_src:
            continue
        if has_fstring:
            continue
        errors.append(f"  canonical Python missing tone symbol: {symbol}")

    # 3. canonical function uses f"tone{tone}" formatting
    fn_re = re.compile(
        rf"def {re.escape(canonical_function)}\b.*?(?=\ndef |\Z)",
        re.DOTALL,
    )
    fn_match = fn_re.search(py_src)
    if not fn_match:
        errors.append(f"  function {canonical_function} not found in canonical source")
    else:
        fn_body = fn_match.group(0)
        if 'f"tone{' not in fn_body and "f'tone{" not in fn_body:
            errors.append(
                f"  canonical function {canonical_function} does not use "
                f'`f"tone{{tone}}"` formatting — drift risk.'
            )

    # 4. symbol literals in each runtime source
    for runtime_label, rel_path in runtime_sources.items():
        if runtime_label == "python":
            continue
        src_path = REPO_ROOT / rel_path
        missing = verify_runtime_has_symbols(src_path, symbols)
        if missing:
            errors.append(
                f"  runtime [{runtime_label}] ({rel_path}) missing tone symbols: {missing}"
            )

    # 5. PUA codepoints agree with contract
    if PUA_JSON.exists():
        pua_map = load_pua_codepoints()
        for tone_def in contract["tone_definitions"]:
            sym = tone_def["symbol"]
            contract_cp = tone_def["pua_codepoint"]
            pua_cp = pua_map.get(sym)
            if pua_cp is None:
                errors.append(
                    f"  PUA mapping for {sym} missing from pua.json "
                    f"(contract says {contract_cp})"
                )
            elif pua_cp.upper() != contract_cp.upper():
                errors.append(
                    f"  PUA mismatch for {sym}: contract={contract_cp} pua.json={pua_cp}"
                )

    if errors:
        print("Chinese tone contract drift:", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
        print(
            "\nFix: align docs/spec/chinese-tone-contract.toml + pua.json + "
            "canonical Python (chinese.py) + missing runtimes.",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        print(f"verified tones: {symbols}")
        for td in contract["tone_definitions"]:
            print(f"  {td['symbol']} ({td['description']}) → {td['pua_codepoint']}")
    print(
        f"OK Chinese tone contract: {len(symbols)} tones × "
        f"{len(runtime_sources)} runtime sources"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
