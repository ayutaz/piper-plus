#!/usr/bin/env python3
"""Drift check for docs/spec/streaming-api-contract.toml.

The contract requires every listed runtime to expose a streaming-synth
API with equivalent semantics (one AudioChunk per sentence, is_final
exactly once, etc.). This script verifies the cross-runtime surface
metadata, not the runtime behaviour itself (covered by per-runtime
tests).

Checks:

1. TOML parses; required tables exist.
2. Every runtime declared in [meta].applies_to has a matching
    [api_signatures.<runtime>] table. A missing entry = a runtime quietly
    dropped streaming support without contract-side acknowledgement.
3. Every runtime's signature carries a 'function' and 'return_type'
    field. Empty entries would let the contract claim coverage without
    any actual signature pinned.
4. The sentence-boundary source file referenced by
    [meta].sentence_boundary_source exists on disk.
5. [chunk] declares sample_rate / bit_depth / channels consistent with
    audio-format-contract (mono int16 @ 22050 Hz); a divergence here would
    produce playback artefacts at runtime.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/streaming-api-contract.toml"

# applies_to label -> [api_signatures.<key>] suffix used in TOML.
RUNTIME_KEY_MAP = {
    "python": "python",
    "rust": "rust",
    "csharp": "csharp",
    "go": "go",
    "wasm-js": "wasm_js",
    "c-api": "c_api",
}


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract missing: {CONTRACT_PATH}", file=sys.stderr)
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    for table in ("meta", "api_signatures", "chunk", "buffering", "is_final", "error_handling"):
        if table not in contract:
            errors.append(f"missing required table [{table}]")

    applies_to = contract.get("meta", {}).get("applies_to", [])
    api_signatures = contract.get("api_signatures", {})

    for runtime in applies_to:
        key = RUNTIME_KEY_MAP.get(runtime)
        if key is None:
            errors.append(
                f"[meta].applies_to includes unrecognised runtime label "
                f"{runtime!r}; update RUNTIME_KEY_MAP if intentional"
            )
            continue
        if key not in api_signatures:
            errors.append(
                f"[api_signatures.{key}] missing — every runtime in "
                f"[meta].applies_to must declare its streaming API surface"
            )
            continue
        sig = api_signatures[key]
        for required in ("function", "return_type"):
            if required not in sig or not str(sig[required]).strip():
                errors.append(f"[api_signatures.{key}].{required} is empty")

    sentence_source = contract.get("meta", {}).get("sentence_boundary_source")
    if sentence_source and not (REPO_ROOT / sentence_source).exists():
        errors.append(
            f"[meta].sentence_boundary_source references missing file: {sentence_source}"
        )

    chunk = contract.get("chunk", {})
    if chunk.get("sample_rate") != 22050:
        errors.append(
            f"[chunk].sample_rate must be 22050 (got {chunk.get('sample_rate')}) "
            "— cross-check with audio-format-contract.toml"
        )
    if chunk.get("bit_depth") != 16:
        errors.append(f"[chunk].bit_depth must be 16 (got {chunk.get('bit_depth')})")
    if chunk.get("channels") != 1:
        errors.append(f"[chunk].channels must be 1 (got {chunk.get('channels')})")
    if chunk.get("endianness") != "little":
        errors.append(f"[chunk].endianness must be 'little' (got {chunk.get('endianness')!r})")

    if not contract.get("is_final", {}).get("exactly_one_per_stream"):
        errors.append("[is_final].exactly_one_per_stream must be true")

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print(
        f"OK: streaming-api-contract.toml — "
        f"{len(applies_to)} runtimes' API signatures pinned"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
