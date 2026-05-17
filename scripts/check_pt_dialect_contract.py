#!/usr/bin/env python3
"""Drift check for docs/spec/pt-dialect-contract.toml.

The contract pins (a) the language-code aliasing pt -> pt-BR and
pt-PT / pt-pt -> pt-PT, (b) the canonical 5 BR↔EU phonological
differences, and (c) the 8 runtime mirror files that must implement
them. This script catches the cheapest class of drift — file deletion
or contract-side schema breakage — without re-running the per-runtime
fixture tests.

Checks:

1. TOML parses and required tables exist.
2. [language_codes] declares both `pt` (BR alias) and `pt-PT` (EU)
    targets; removing either is a backwards-compat break.
3. [[implementation.differences]] contains exactly the 5 documented
    phenomena (palatalisation / final-e / final-s / coda-l / r). Adding
    a 6th here without test updates leaves the gate stale; this script
    forces an intentional bump.
4. [implementation.phoneme_inventory].new_phonemes lists the EU-only IPA
    characters (ɨ, ɫ) and the PUA contract path resolves.
5. All 8 runtime mirror files referenced by [runtimes] exist on disk.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from platform_utils import force_utf8_output

force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/pt-dialect-contract.toml"

# Canonical 5 phenomena, in the order they appear in v2 of the spec.
EXPECTED_PHENOMENA = {
    "t/d palatalisation before unstressed final /e/",
    "Final unstressed -e",
    "Final -s / -z and pre-consonantal -s",
    "Coda /l/",
    "Strong /r/ and word-final r",
}

# EU-only IPA characters that round-trip via PUA mapping.
EXPECTED_NEW_PHONEMES = {"ɨ", "ɫ"}

PARITY_FIXTURE = REPO_ROOT / "tests/fixtures/g2p/pt_dialect_parity.json"


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract missing: {CONTRACT_PATH}", file=sys.stderr)
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    for table in ("meta", "language_codes", "implementation", "runtimes"):
        if table not in contract:
            errors.append(f"missing required table [{table}]")

    codes = contract.get("language_codes", {})
    if codes.get("pt") != "pt-BR":
        errors.append(f"[language_codes].pt must resolve to 'pt-BR' (got {codes.get('pt')!r})")
    if codes.get("pt-PT") != "pt-PT":
        errors.append(f"[language_codes].pt-PT must resolve to 'pt-PT' (got {codes.get('pt-PT')!r})")
    if codes.get("pt-pt") != "pt-PT":
        errors.append(
            f"[language_codes].pt-pt must resolve to 'pt-PT' for case insensitivity "
            f"(got {codes.get('pt-pt')!r})"
        )

    impl = contract.get("implementation", {})
    differences = impl.get("differences", [])
    phenomena = {d.get("phenomenon") for d in differences if isinstance(d, dict)}
    missing = EXPECTED_PHENOMENA - phenomena
    extra = phenomena - EXPECTED_PHENOMENA
    if missing:
        errors.append(
            f"[[implementation.differences]] missing canonical phenomenon/phenomena: {sorted(missing)}"
        )
    if extra:
        errors.append(
            f"[[implementation.differences]] introduces undocumented phenomenon/phenomena: "
            f"{sorted(extra)} — bump EXPECTED_PHENOMENA in scripts/check_pt_dialect_contract.py "
            "if intentional"
        )
    for i, diff in enumerate(differences):
        if not isinstance(diff, dict):
            continue
        for field in ("phenomenon", "br", "eu", "mechanism"):
            if field not in diff:
                errors.append(f"differences[{i}] missing required field {field!r}")

    new_phonemes = set(impl.get("phoneme_inventory", {}).get("new_phonemes", []))
    if new_phonemes != EXPECTED_NEW_PHONEMES:
        errors.append(
            f"[implementation.phoneme_inventory].new_phonemes={sorted(new_phonemes)} "
            f"!= expected {sorted(EXPECTED_NEW_PHONEMES)} — these are required for the "
            "PUA contract to round-trip EU phonology"
        )

    pua_path = impl.get("phoneme_inventory", {}).get("pua_contract")
    if pua_path and not (REPO_ROOT / pua_path).exists():
        errors.append(
            f"[implementation.phoneme_inventory].pua_contract references missing file: {pua_path}"
        )

    runtimes = contract.get("runtimes", {})
    if not runtimes:
        errors.append("[runtimes] table is empty — must list all runtime mirror files")
    for key, rel_path in runtimes.items():
        if not isinstance(rel_path, str):
            continue
        if not (REPO_ROOT / rel_path).exists():
            errors.append(
                f"[runtimes].{key} references missing file: {rel_path} "
                "(if the file was intentionally moved, update both this contract "
                "and the corresponding fixture-driven runtime test)"
            )

    # Cross-check that the parity fixture (consumed by per-runtime tests)
    # covers exactly the 5 contracted phenomena. Without this gate a
    # phenomenon could be added to the contract but the fixture would
    # silently lag behind, producing zero coverage for the new rule.
    if PARITY_FIXTURE.exists():
        import json as _json

        try:
            parity = _json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as exc:
            errors.append(f"parity fixture failed to parse: {exc}")
        else:
            fixture_phenomena = {tc.get("phenomenon") for tc in parity.get("test_cases", [])}
            if fixture_phenomena != EXPECTED_PHENOMENA:
                errors.append(
                    f"parity fixture phenomena drift: "
                    f"missing={sorted(EXPECTED_PHENOMENA - fixture_phenomena)}, "
                    f"extra={sorted(fixture_phenomena - EXPECTED_PHENOMENA)} "
                    f"(fixture: {PARITY_FIXTURE.relative_to(REPO_ROOT)})"
                )
    else:
        errors.append(
            f"parity fixture missing: {PARITY_FIXTURE.relative_to(REPO_ROOT)} "
            "(required by per-runtime BR/EU tests, e.g. "
            "src/python_run/tests/test_pt_dialect_parity.py)"
        )

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print(
        f"OK: pt-dialect-contract.toml — "
        f"{len(EXPECTED_PHENOMENA)} phenomena, {len(runtimes)} runtime mirror(s), "
        f"parity fixture validated"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
