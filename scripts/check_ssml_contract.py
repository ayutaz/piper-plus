#!/usr/bin/env python3
"""Three-way drift check for the SSML subset contract.

Verifies byte-for-byte agreement across the three sources of truth:
    1. ``docs/spec/ssml-contract.toml``                        — human-edited spec
    2. ``src/python/g2p/piper_plus_g2p/ssml.py``               — Python canonical
    3. ``tests/fixtures/ssml/contract.json``                   — JSON fixture
                                                                consumed by
                                                                Rust/Go/C# tests

If any of the three drifts from the others, this script exits non-zero. The
JSON fixture is checked via ``regenerate_ssml_fixture.py --check`` (which
also performs an internal toml ↔ Python comparison before writing); this
script duplicates the toml ↔ Python comparison so a missing/stale fixture
does not mask a Python ↔ toml drift.

Usage:
    python scripts/check_ssml_contract.py            # CI mode
    python scripts/check_ssml_contract.py --verbose  # show all checked values
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from platform_utils import force_utf8_output

force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/ssml-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/ssml/contract.json"
SSML_PY_PATH = REPO_ROOT / "src/python/g2p/piper_plus_g2p/ssml.py"
SSML_WASM_PATH = REPO_ROOT / "src/wasm/g2p/src/ssml.js"
REGEN_SCRIPT = REPO_ROOT / "scripts/regenerate_ssml_fixture.py"


def _load_python_canonical() -> dict[str, Any]:
    """Load the Python ``SSMLParser`` and ``_MAX_SSML_SIZE`` directly from the
    .py file so this checker has no third-party dependency.
    """
    mod_name = "_piper_plus_g2p_ssml_check"
    spec = importlib.util.spec_from_file_location(mod_name, SSML_PY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec from {SSML_PY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(mod_name, None)
    parser_cls = module.SSMLParser
    return {
        "BREAK_STRENGTH_MS": dict(parser_cls.BREAK_STRENGTH_MS),
        "RATE_NAMES": dict(parser_cls.RATE_NAMES),
        "RE_SSML_PATTERN": parser_cls._RE_SSML.pattern,
        "RE_SSML_FLAGS_DOTALL": bool(parser_cls._RE_SSML.flags & re.DOTALL),
        "MAX_SSML_SIZE": int(module._MAX_SSML_SIZE),
    }


def _load_wasm_canonical() -> dict[str, Any]:
    """Extract SSML constants from `src/wasm/g2p/src/ssml.js` via regex.

    Why parse JS with regex instead of evaluating it? The CI runners that
    invoke this script have Python but not necessarily Node; the JS file
    only uses literal-only constants (`Object.freeze({...})` with string
    keys and numeric values) so regex extraction is safe and avoids adding
    a `node` dependency to the contract gate.
    """
    src = SSML_WASM_PATH.read_text(encoding="utf-8")

    def _parse_frozen_object(name: str, value_kind: str) -> dict[str, Any]:
        # name = "BREAK_STRENGTH_MS" → matches:
        #   const BREAK_STRENGTH_MS = Object.freeze({  ...  });
        block = re.search(
            rf"const\s+{name}\s*=\s*Object\.freeze\s*\(\s*\{{([^}}]*)\}}\s*\)\s*;",
            src,
            flags=re.DOTALL,
        )
        if not block:
            raise RuntimeError(f"could not locate {name} in {SSML_WASM_PATH}")
        body = block.group(1)
        out: dict[str, Any] = {}
        # Each line: optional-quoted key : value,
        for entry in re.finditer(r"""['"]?([\w-]+)['"]?\s*:\s*([-\d.]+)""", body):
            key, raw = entry.group(1), entry.group(2)
            out[key] = int(raw) if value_kind == "int" else float(raw)
        return out

    max_size_m = re.search(r"const\s+MAX_SSML_SIZE\s*=\s*([\d_]+)\s*;", src)
    if not max_size_m:
        raise RuntimeError(f"could not locate MAX_SSML_SIZE in {SSML_WASM_PATH}")
    max_size = int(max_size_m.group(1).replace("_", ""))

    # RE_SSML regex literal: `/^\s*<speak[\s>]/s` → pattern + flags.
    re_m = re.search(r"const\s+RE_SSML\s*=\s*/(.+?)/([a-z]*)\s*;", src)
    if not re_m:
        raise RuntimeError(f"could not locate RE_SSML in {SSML_WASM_PATH}")
    regex_pattern, regex_flags = re_m.group(1), re_m.group(2)

    return {
        "BREAK_STRENGTH_MS": _parse_frozen_object("BREAK_STRENGTH_MS", "int"),
        "RATE_NAMES": _parse_frozen_object("RATE_NAMES", "float"),
        "RE_SSML_PATTERN": regex_pattern,
        "RE_SSML_FLAGS_DOTALL": "s" in regex_flags,
        "MAX_SSML_SIZE": max_size,
    }


def _check_python_vs_wasm(
    py: dict[str, Any], wasm: dict[str, Any], verbose: bool
) -> list[str]:
    """Verify the WASM SSML parser carries the same constants as Python.

    The existing ssml-parity workflow gates Python / toml / JSON fixture
    triples per-runtime, but the npm `@piper-plus/g2p` package's SSML.js
    was previously not gated. Browser callers could silently see different
    `<break strength>` durations or `<prosody rate>` multipliers.
    """
    errors: list[str] = []

    def cmp(label: str, py_val: Any, wasm_val: Any) -> None:
        if py_val == wasm_val:
            if verbose:
                print(f"  OK python ↔ wasm {label} = {py_val!r}")
        else:
            errors.append(f"python ↔ wasm {label}: python={py_val!r} wasm={wasm_val!r}")

    cmp("BREAK_STRENGTH_MS", py["BREAK_STRENGTH_MS"], wasm["BREAK_STRENGTH_MS"])
    cmp(
        "RATE_NAMES",
        {k: float(v) for k, v in py["RATE_NAMES"].items()},
        {k: float(v) for k, v in wasm["RATE_NAMES"].items()},
    )
    cmp("MAX_SSML_SIZE", int(py["MAX_SSML_SIZE"]), int(wasm["MAX_SSML_SIZE"]))
    cmp(
        "RE_SSML pattern",
        py["RE_SSML_PATTERN"],
        wasm["RE_SSML_PATTERN"],
    )
    cmp(
        "RE_SSML DOTALL flag",
        py["RE_SSML_FLAGS_DOTALL"],
        wasm["RE_SSML_FLAGS_DOTALL"],
    )
    return errors


def _check_toml_vs_python(
    contract: dict[str, Any],
    py: dict[str, Any],
    verbose: bool,
) -> list[str]:
    errors: list[str] = []

    def cmp(label: str, toml_val: Any, py_val: Any) -> None:
        if toml_val == py_val:
            if verbose:
                print(f"  OK toml ↔ python {label} = {toml_val!r}")
        else:
            errors.append(f"toml ↔ python {label}: toml={toml_val!r} python={py_val!r}")

    cmp(
        "break_strength.map",
        {k: int(v) for k, v in contract["break_strength"]["map"].items()},
        py["BREAK_STRENGTH_MS"],
    )
    cmp(
        "break_strength.default_ms",
        int(contract["break_strength"]["default_ms"]),
        int(py["BREAK_STRENGTH_MS"]["medium"]),
    )
    cmp(
        "break_strength.unknown_strength_fallback_ms",
        int(contract["break_strength"]["unknown_strength_fallback_ms"]),
        int(py["BREAK_STRENGTH_MS"]["medium"]),
    )
    cmp(
        "prosody_rate.named_map",
        {k: float(v) for k, v in contract["prosody_rate"]["named_map"].items()},
        {k: float(v) for k, v in py["RATE_NAMES"].items()},
    )
    cmp(
        "detection.regex",
        str(contract["detection"]["regex"]),
        py["RE_SSML_PATTERN"],
    )
    cmp(
        "detection.flags=DOTALL",
        contract["detection"]["flags"] == "DOTALL",
        py["RE_SSML_FLAGS_DOTALL"],
    )
    cmp(
        "size_limit.python_max_ssml_bytes",
        int(contract["size_limit"]["python_max_ssml_bytes"]),
        py["MAX_SSML_SIZE"],
    )

    return errors


def _check_fixture_vs_toml(
    contract: dict[str, Any],
    fixture: dict[str, Any],
    verbose: bool,
) -> list[str]:
    """Spot-check that fixture values are consistent with the toml.

    The byte-for-byte fixture verification is delegated to
    ``regenerate_ssml_fixture.py --check``; here we only assert a few
    cross-references so that a fixture-only edit is also caught when this
    checker runs without the regenerate script.
    """
    errors: list[str] = []

    def cmp(label: str, toml_val: Any, fix_val: Any) -> None:
        if toml_val == fix_val:
            if verbose:
                print(f"  OK toml ↔ fixture {label} = {toml_val!r}")
        else:
            errors.append(
                f"toml ↔ fixture {label}: toml={toml_val!r} fixture={fix_val!r}"
            )

    cmp(
        "break_strength.map",
        {k: int(v) for k, v in contract["break_strength"]["map"].items()},
        {k: int(v) for k, v in fixture["break_strength"]["map"].items()},
    )
    cmp(
        "prosody_rate.named_map",
        {k: float(v) for k, v in contract["prosody_rate"]["named_map"].items()},
        {k: float(v) for k, v in fixture["prosody_rate"]["named_map"].items()},
    )
    cmp(
        "detection.regex",
        str(contract["detection"]["regex"]),
        str(fixture["detection"]["regex"]),
    )
    cmp(
        "size_limit.python_max_ssml_bytes",
        int(contract["size_limit"]["python_max_ssml_bytes"]),
        int(fixture["size_limit"]["python_max_ssml_bytes"]),
    )
    cmp(
        "schema_version",
        1,
        int(fixture["schema_version"]),
    )

    return errors


def _check_fixture_byte_for_byte(verbose: bool) -> list[str]:
    """Delegate the byte-for-byte fixture check to the regenerate script."""
    proc = subprocess.run(
        [sys.executable, str(REGEN_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        if verbose:
            print(f"  OK fixture byte-for-byte: {proc.stdout.strip()}")
        return []
    return [
        "fixture byte-for-byte: regenerate_ssml_fixture.py --check failed:\n"
        + (proc.stdout or "")
        + (proc.stderr or "")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print all checked values"
    )
    args = parser.parse_args()

    if not CONTRACT_PATH.exists():
        print(f"ERROR: missing {CONTRACT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    if not SSML_PY_PATH.exists():
        print(f"ERROR: missing {SSML_PY_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    if not FIXTURE_PATH.exists():
        print(
            f"ERROR: missing {FIXTURE_PATH.relative_to(REPO_ROOT)}. "
            f"Run `python scripts/regenerate_ssml_fixture.py`.",
            file=sys.stderr,
        )
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    py = _load_python_canonical()

    all_errors: list[str] = []
    all_errors.extend(_check_toml_vs_python(contract, py, args.verbose))
    all_errors.extend(_check_fixture_vs_toml(contract, fixture, args.verbose))
    all_errors.extend(_check_fixture_byte_for_byte(args.verbose))

    if SSML_WASM_PATH.exists():
        wasm = _load_wasm_canonical()
        all_errors.extend(_check_python_vs_wasm(py, wasm, args.verbose))
    else:
        print(
            f"WARNING: {SSML_WASM_PATH.relative_to(REPO_ROOT)} missing — "
            "skipping python ↔ wasm comparison",
            file=sys.stderr,
        )

    if all_errors:
        print("ERROR: SSML contract drift detected:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            f"\nUpdate {CONTRACT_PATH.relative_to(REPO_ROOT)}, "
            f"{SSML_PY_PATH.relative_to(REPO_ROOT)}, or rerun "
            f"`python scripts/regenerate_ssml_fixture.py` so all three agree.",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: SSML contract toml ↔ Python canonical (ssml.py) ↔ JSON fixture "
        "(tests/fixtures/ssml/contract.json) all agree."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
