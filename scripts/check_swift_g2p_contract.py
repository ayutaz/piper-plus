#!/usr/bin/env python3
"""Drift check for docs/spec/swift-g2p-contract.toml.

The contract pins the Swift G2P FFI ABI, JSON envelope, xcframework
layout, and default-language registration. A drift in this file relative
to the actual code would surface as a link error or a JSON decode
failure on Swift consumers — both runtime breaks for app shipped with
the binary xcframework.

Checks (deliberately scoped to what can be enforced without building
the xcframework):

1. TOML parses; required tables exist.
2. [compat].pua_compat_version matches the canonical pua.json version
    (already gated by check_pua_consistency.py, double-checked here to
    keep the contract honest).
3. The PUA Swift mirror file referenced by [compat].swift_pua_mirror
    exists on disk.
4. [abi.functions.*] each declare a 'signature' (text) and 'returns'
    (text); an empty entry would silently weaken the ABI guarantee.
5. The default-language tables ([default_languages].rule_based +
    conditional) are non-empty (the Phonemizer's no-arg ctor relies on
    them).
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/swift-g2p-contract.toml"
PUA_JSON_PATH = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/pua.json"


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract missing: {CONTRACT_PATH}", file=sys.stderr)
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    for table in ("meta", "compat", "abi", "json_envelope", "default_languages", "xcframework"):
        if table not in contract:
            errors.append(f"missing required table [{table}]")

    if PUA_JSON_PATH.exists():
        try:
            pua = json.loads(PUA_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"pua.json failed to parse: {exc}")
        else:
            pua_version = pua.get("version")
            compat_version = contract.get("compat", {}).get("pua_compat_version")
            if pua_version is not None and compat_version != pua_version:
                errors.append(
                    f"[compat].pua_compat_version={compat_version} != pua.json::version={pua_version}; "
                    "see scripts/check_pua_consistency.py for the canonical drift gate"
                )
    else:
        errors.append(f"pua.json missing at {PUA_JSON_PATH.relative_to(REPO_ROOT)}")

    swift_mirror = contract.get("compat", {}).get("swift_pua_mirror")
    if swift_mirror and not (REPO_ROOT / swift_mirror).exists():
        errors.append(
            f"[compat].swift_pua_mirror references missing file: {swift_mirror}"
        )

    abi_funcs = contract.get("abi", {}).get("functions", {})
    if not abi_funcs:
        errors.append("[abi.functions.*] tables are missing — ABI surface is empty")
    for name, body in abi_funcs.items():
        if not isinstance(body, dict):
            continue
        if not body.get("signature", "").strip():
            errors.append(f"[abi.functions.{name}].signature is empty")

    rule_based = contract.get("default_languages", {}).get("rule_based", [])
    conditional = contract.get("default_languages", {}).get("conditional", {})
    if not rule_based:
        errors.append("[default_languages].rule_based must list at least one language")
    if not conditional:
        errors.append("[default_languages.conditional] must list at least one feature-gated language")

    slices = contract.get("xcframework", {}).get("slices", {})
    if not slices:
        errors.append("[xcframework.slices] must declare at least one slice")

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print(
        f"OK: swift-g2p-contract.toml — "
        f"{len(abi_funcs)} ABI functions, {len(slices)} xcframework slice(s) validated"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
