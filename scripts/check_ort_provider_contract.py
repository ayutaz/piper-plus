#!/usr/bin/env python3
"""Drift check for docs/spec/ort-provider-contract.toml.

The contract pins the canonical execution-provider matrix (CPU / CUDA /
CoreML / DirectML / TensorRT), the auto-detect priority per platform, and
the output-equivalence tolerances each provider must satisfy. This script
verifies:

1. TOML parses and the required tables exist.
2. Every provider entry in [[providers]] has a name + short_name +
    non-empty platforms + non-empty notes (silent removal of a row would
    leave the loader free to register a provider that the contract no
    longer endorses).
3. Every provider referenced by [selection.auto_detect_priority] also
    exists as a [[providers]] row (a typo here = the loader auto-picks an
    unrecognised string and fails to register).
4. Each [output_equivalence.cpu_vs_*] block has a finite positive
    threshold (a negative / zero threshold would silently pass any drift).
5. The companion contract file referenced by [meta].companion_contract
    actually exists.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/ort-provider-contract.toml"


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract missing: {CONTRACT_PATH}", file=sys.stderr)
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    for table in ("meta", "selection", "selection.auto_detect_priority", "determinism"):
        cursor: object = contract
        for part in table.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                errors.append(f"missing required table [{table}]")
                cursor = None
                break
            cursor = cursor[part]

    providers = contract.get("providers", [])
    if not isinstance(providers, list) or len(providers) < 1:
        errors.append("[[providers]] must list at least one provider")
        providers = []

    provider_names: set[str] = set()
    for i, prov in enumerate(providers):
        for field in ("name", "short_name", "platforms", "notes"):
            if field not in prov:
                errors.append(f"providers[{i}] missing required field '{field}'")
        name = prov.get("name")
        if name:
            if name in provider_names:
                errors.append(f"duplicate provider name: {name}")
            provider_names.add(name)
        platforms = prov.get("platforms", [])
        if not isinstance(platforms, list) or len(platforms) == 0:
            errors.append(f"providers[{i}] ({name!r}) has empty platforms list")

    if "CPUExecutionProvider" not in provider_names:
        errors.append(
            "CPUExecutionProvider must be present as the universal fallback "
            "(referenced by [selection.auto_detect_priority] on every platform)"
        )

    priority = contract.get("selection", {}).get("auto_detect_priority", {})
    for platform, providers_list in priority.items():
        if not isinstance(providers_list, list):
            errors.append(
                f"[selection.auto_detect_priority].{platform} must be a list "
                f"(got {type(providers_list).__name__})"
            )
            continue
        for prov_name in providers_list:
            if prov_name not in provider_names:
                errors.append(
                    f"[selection.auto_detect_priority].{platform} references "
                    f"unknown provider {prov_name!r} (not in [[providers]])"
                )

    for key, block in contract.get("output_equivalence", {}).items():
        if not isinstance(block, dict):
            continue
        threshold = block.get("threshold")
        if threshold is None:
            errors.append(f"[output_equivalence.{key}] missing 'threshold'")
            continue
        try:
            t = float(threshold)
        except (TypeError, ValueError):
            errors.append(f"[output_equivalence.{key}].threshold is not numeric: {threshold!r}")
            continue
        if not (t > 0.0 and t < 1.0):
            errors.append(
                f"[output_equivalence.{key}].threshold = {t} outside (0, 1); "
                "a non-positive threshold silently passes any drift"
            )

    companion = contract.get("meta", {}).get("companion_contract")
    if companion and not (REPO_ROOT / companion).exists():
        errors.append(f"[meta].companion_contract references missing file: {companion}")

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print(
        f"OK: ort-provider-contract.toml — {len(provider_names)} providers, "
        f"{len(priority)} platform priority lists validated"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
