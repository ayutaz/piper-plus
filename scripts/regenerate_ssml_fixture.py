#!/usr/bin/env python3
"""Regenerate the SSML contract JSON fixture used by per-runtime parity tests.

Source of truth: ``docs/spec/ssml-contract.toml``  (canonical text)
                 ``src/python/g2p/piper_plus_g2p/ssml.py``  (canonical Python)
Output:          ``tests/fixtures/ssml/contract.json``

Each non-Python runtime (Rust, Go, C#) loads this JSON in its test suite and
asserts its own constants match. Using JSON avoids a toml dependency in three
different languages.

The fixture is built by reading the toml AND comparing against the live Python
``SSMLParser`` constants — if the toml drifts from the Python source the script
exits non-zero, before any fixture is written. This makes the toml the
human-edited spec while the Python module remains the runtime canonical.

Usage:
    python scripts/regenerate_ssml_fixture.py            # regenerate
    python scripts/regenerate_ssml_fixture.py --check    # CI mode: drift check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/ssml-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/ssml/contract.json"
SSML_PY_PATH = REPO_ROOT / "src/python/g2p/piper_plus_g2p/ssml.py"


def _load_python_canonical() -> dict[str, Any]:
    """Load the Python ``SSMLParser`` and ``_MAX_SSML_SIZE`` without importing
    the whole ``piper_plus_g2p`` package (which would require all its runtime
    deps installed). We use an isolated importlib spec on the single .py file.
    """
    mod_name = "_piper_plus_g2p_ssml"
    spec = importlib.util.spec_from_file_location(mod_name, SSML_PY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec from {SSML_PY_PATH}")
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves type hints via sys.modules[<__module__>], so the
    # module must be registered before exec_module runs.
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # Don't pollute sys.modules for subsequent calls (e.g. test runs).
        sys.modules.pop(mod_name, None)
    parser_cls = module.SSMLParser
    return {
        "BREAK_STRENGTH_MS": dict(parser_cls.BREAK_STRENGTH_MS),
        "RATE_NAMES": dict(parser_cls.RATE_NAMES),
        "RE_SSML_PATTERN": parser_cls._RE_SSML.pattern,
        "RE_SSML_FLAGS_DOTALL": bool(parser_cls._RE_SSML.flags & 16),  # re.DOTALL == 16
        "MAX_SSML_SIZE": int(module._MAX_SSML_SIZE),
    }


def _verify_toml_matches_python(
    contract: dict[str, Any], py: dict[str, Any]
) -> list[str]:
    """Return a list of mismatch messages (empty list = OK)."""
    errors: list[str] = []

    # break_strength.map
    toml_break = {k: int(v) for k, v in contract["break_strength"]["map"].items()}
    if toml_break != py["BREAK_STRENGTH_MS"]:
        errors.append(
            f"break_strength.map drift: toml={toml_break} python={py['BREAK_STRENGTH_MS']}"
        )

    # default + unknown_strength fallback should match python's "medium"
    if (
        int(contract["break_strength"]["default_ms"])
        != py["BREAK_STRENGTH_MS"]["medium"]
    ):
        errors.append(
            f"break_strength.default_ms ({contract['break_strength']['default_ms']}) "
            f"!= python medium ({py['BREAK_STRENGTH_MS']['medium']})"
        )
    if (
        int(contract["break_strength"]["unknown_strength_fallback_ms"])
        != py["BREAK_STRENGTH_MS"]["medium"]
    ):
        errors.append(
            "break_strength.unknown_strength_fallback_ms drift vs python medium"
        )

    # prosody_rate.named_map
    toml_rate = {k: float(v) for k, v in contract["prosody_rate"]["named_map"].items()}
    py_rate = {k: float(v) for k, v in py["RATE_NAMES"].items()}
    if toml_rate != py_rate:
        errors.append(
            f"prosody_rate.named_map drift: toml={toml_rate} python={py_rate}"
        )

    # detection regex
    if contract["detection"]["regex"] != py["RE_SSML_PATTERN"]:
        errors.append(
            f"detection.regex drift: toml={contract['detection']['regex']!r} "
            f"python={py['RE_SSML_PATTERN']!r}"
        )

    # detection flags — python uses re.DOTALL
    if (contract["detection"]["flags"] == "DOTALL") != py["RE_SSML_FLAGS_DOTALL"]:
        errors.append(
            f"detection.flags drift: toml={contract['detection']['flags']!r} "
            f"python DOTALL={py['RE_SSML_FLAGS_DOTALL']}"
        )

    # size_limit
    if int(contract["size_limit"]["python_max_ssml_bytes"]) != py["MAX_SSML_SIZE"]:
        errors.append(
            f"size_limit.python_max_ssml_bytes drift: "
            f"toml={contract['size_limit']['python_max_ssml_bytes']} "
            f"python={py['MAX_SSML_SIZE']}"
        )

    return errors


def build_fixture() -> dict[str, Any]:
    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    py = _load_python_canonical()

    drift = _verify_toml_matches_python(contract, py)
    if drift:
        msg = (
            "ERROR: toml ↔ Python canonical drift detected before fixture write:\n"
            + "\n".join(f"  - {e}" for e in drift)
        )
        raise SystemExit(msg)

    # Stable, language-neutral projection. Keys are sorted within each table
    # so the JSON is deterministic. Numeric types preserved (int vs float).
    return {
        "schema_version": 1,
        "comment": (
            "SSML contract fixture. Regenerate via "
            "`python scripts/regenerate_ssml_fixture.py`. "
            "Sources: docs/spec/ssml-contract.toml + "
            "src/python/g2p/piper_plus_g2p/ssml.py. "
            "Each non-Python runtime (Rust/Go/C#) asserts its own constants "
            "match these values byte-for-byte."
        ),
        "break_strength": {
            "case_insensitive": bool(contract["break_strength"]["case_insensitive"]),
            "default_strength": str(contract["break_strength"]["default_strength"]),
            "default_ms": int(contract["break_strength"]["default_ms"]),
            "unknown_strength_fallback_ms": int(
                contract["break_strength"]["unknown_strength_fallback_ms"]
            ),
            "map": {
                k: int(v) for k, v in sorted(contract["break_strength"]["map"].items())
            },
        },
        "prosody_rate": {
            "default_rate": float(contract["prosody_rate"]["default_rate"]),
            "case_insensitive_named": bool(
                contract["prosody_rate"]["case_insensitive_named"]
            ),
            "named_map": {
                k: float(v)
                for k, v in sorted(contract["prosody_rate"]["named_map"].items())
            },
            "parsing": {
                "percent_formula": str(
                    contract["prosody_rate"]["parsing"]["percent_formula"]
                ),
                "percent_min_exclusive": float(
                    contract["prosody_rate"]["parsing"]["percent_min_exclusive"]
                ),
                "bare_float_min_exclusive": float(
                    contract["prosody_rate"]["parsing"]["bare_float_min_exclusive"]
                ),
                "fallback_rate": float(
                    contract["prosody_rate"]["parsing"]["fallback_rate"]
                ),
            },
        },
        "break_time": {
            "ms_suffix": str(contract["break_time"]["ms_suffix"]),
            "seconds_suffix": str(contract["break_time"]["seconds_suffix"]),
            "bare_number_assumes": str(contract["break_time"]["bare_number_assumes"]),
            "case_insensitive_suffix": bool(
                contract["break_time"]["case_insensitive_suffix"]
            ),
            "unparseable_fallback_ms": int(
                contract["break_time"]["unparseable_fallback_ms"]
            ),
        },
        "detection": {
            "regex": str(contract["detection"]["regex"]),
            "flags": str(contract["detection"]["flags"]),
            "matches_at": str(contract["detection"]["matches_at"]),
            "case_sensitive": bool(contract["detection"]["case_sensitive"]),
        },
        "fallback": {
            "strip_regex": str(contract["fallback"]["strip_regex"]),
            "strip_then_trim": bool(contract["fallback"]["strip_then_trim"]),
            "empty_strip_yields_original_text": bool(
                contract["fallback"]["empty_strip_yields_original_text"]
            ),
        },
        "size_limit": {
            "python_max_ssml_bytes": int(
                contract["size_limit"]["python_max_ssml_bytes"]
            ),
            "python_only": bool(contract["size_limit"]["python_only"]),
            "on_exceed": str(contract["size_limit"]["on_exceed"]),
        },
        "segment_defaults": {
            "text": str(contract["segment_defaults"]["text"]),
            "break_ms": int(contract["segment_defaults"]["break_ms"]),
            "rate": float(contract["segment_defaults"]["rate"]),
        },
        "walk_semantics": {
            "tail_inherits_parent_rate": bool(
                contract["walk_semantics"]["tail_inherits_parent_rate"]
            ),
            "merge_drops_empty_zero_break": bool(
                contract["walk_semantics"]["merge_drops_empty_zero_break"]
            ),
            "empty_result_replacement": str(
                contract["walk_semantics"]["empty_result_replacement"]
            ),
            "strip_xml_namespace_for_tag_match": bool(
                contract["walk_semantics"]["strip_xml_namespace_for_tag_match"]
            ),
        },
    }


def _serialize(fixture: dict[str, Any]) -> str:
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
                f"Run `python scripts/regenerate_ssml_fixture.py`.",
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
                "Run `python scripts/regenerate_ssml_fixture.py` to regenerate.",
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
