#!/usr/bin/env python3
"""Regenerate the LANGUAGE_ID_MAP cross-runtime contract JSON fixture.

Source of truth: ``docs/spec/language-id-map-contract.toml``
Output:          ``tests/fixtures/language_id_map/contract.json``

Each runtime (Python training, Python runtime, Rust core, Rust WASM, Go,
WASM/openjtalk-web) loads this JSON in its parity test suite and asserts that
its own literal mapping (or runtime config it ships) matches the canonical
map projected here. C# and C++ are data-driven (no literal mapping in source)
and listed in the fixture for completeness only.

Using a JSON projection avoids a TOML parser dependency in five different
languages, and pins forward-compat behaviour: future readers must accept
unknown top-level fields and an unknown ``schema_version`` greater than 1.

Usage:
    python scripts/regenerate_language_id_map_fixture.py            # regenerate
    python scripts/regenerate_language_id_map_fixture.py --check    # CI mode: drift check
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/language-id-map-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/language_id_map/contract.json"


def build_fixture() -> dict:
    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    canonical = contract["canonical"]
    invariants = contract["invariants"]

    # Project per-runtime entries into a portable JSON form.
    runtime_sources: list[dict] = []
    for entry in contract["runtime_sources"]["entries"]:
        # Drop None-valued keys so the JSON stays minimal/stable.
        runtime_sources.append({k: v for k, v in entry.items() if v is not None})

    return {
        "schema_version": 1,
        "comment": (
            "LANGUAGE_ID_MAP cross-runtime contract fixture. Regenerate via "
            "`python scripts/regenerate_language_id_map_fixture.py`. "
            "Source: docs/spec/language-id-map-contract.toml. "
            "Each runtime (Python train/runtime, Rust core/wasm, Go, "
            "WASM/openjtalk-web) asserts its literal language_id_map matches "
            "either `canonical.language_id_map` (7-lang) or "
            "`canonical.trained_language_id_map` (6-lang)."
        ),
        "canonical": {
            "language_id_map": canonical["language_id_map"],
            "all_languages": canonical["all_languages"],
            "trained_language_id_map": canonical["trained_language_id_map"],
            "trained_languages": canonical["trained_languages"],
            "extended_language_id_map": canonical["extended_language_id_map"],
            "extended_languages": canonical["extended_languages"],
        },
        "invariants": {
            "keys_lowercase": invariants["keys_lowercase"],
            "values_consecutive_from_zero": invariants["values_consecutive_from_zero"],
            "values_unique": invariants["values_unique"],
            "ja_is_zero": invariants["ja_is_zero"],
            "en_is_one": invariants["en_is_one"],
        },
        "runtime_sources": runtime_sources,
        "expected_not_found": {
            "forbidden_outside_sources": list(
                contract["expected_not_found"]["forbidden_outside_sources"]
            ),
        },
    }


def _serialize(fixture: dict) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: verify that the in-tree fixture is up-to-date with the toml",
    )
    args = parser.parse_args()

    fixture = build_fixture()
    serialized = _serialize(fixture)
    rel = FIXTURE_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not FIXTURE_PATH.exists():
            print(
                f"ERROR: {rel} does not exist. "
                f"Run `python scripts/regenerate_language_id_map_fixture.py`.",
                file=sys.stderr,
            )
            return 1
        existing = FIXTURE_PATH.read_text(encoding="utf-8")
        if existing != serialized:
            print(
                f"ERROR: {rel} is out of sync with "
                f"{CONTRACT_PATH.relative_to(REPO_ROOT)}.",
                file=sys.stderr,
            )
            print(
                "Run `python scripts/regenerate_language_id_map_fixture.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel} is up-to-date.")
        return 0

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(serialized, encoding="utf-8")
    print(f"Wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
