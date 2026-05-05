#!/usr/bin/env python3
"""Verify that every runtime's PUA mapping matches pua.json byte-for-byte.

This script is the CI gate that prevents the multi-codepoint regression
documented in docs/spec/pua-contract.toml. It parses each runtime's
hardcoded PUA table and compares it against the canonical pua.json.

Runtimes covered:
  - Python (src/python_run/piper/phonemize/token_mapper.py)
  - Python G2P (src/python/g2p/piper_plus_g2p/encode/pua.py -- loads pua.json)
  - Rust (src/rust/piper-plus-g2p/src/token_map.rs)
  - Go (src/go/phonemize/pua.go)
  - JavaScript / WASM (src/wasm/g2p/src/pua-map.js)
  - C# (src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs)

Exit codes:
  0 -- all runtimes match pua.json
  1 -- at least one mismatch (CI-fatal)

Usage:
  python scripts/check_pua_consistency.py [--verbose] [--check-version]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL = REPO_ROOT / "src/python/g2p/piper_plus_g2p/data/pua.json"

PYTHON_RUNTIME = REPO_ROOT / "src/python_run/piper/phonemize/token_mapper.py"
PYTHON_G2P_PUA = REPO_ROOT / "src/python/g2p/piper_plus_g2p/encode/pua.py"
RUST_TOKEN_MAP = REPO_ROOT / "src/rust/piper-plus-g2p/src/token_map.rs"
GO_PUA = REPO_ROOT / "src/go/phonemize/pua.go"
JS_PUA = REPO_ROOT / "src/wasm/g2p/src/pua-map.js"
CSHARP_PUA = REPO_ROOT / "src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs"


def load_canonical() -> tuple[int, dict[str, int]]:
    """Return (compat_version, {token: codepoint_int})."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    version = int(data["version"])
    mapping = {entry["token"]: int(entry["codepoint"], 16) for entry in data["entries"]}
    return version, mapping


# ---------------------------------------------------------------------------
# Per-runtime parsers
# ---------------------------------------------------------------------------

# Each parser returns (pua_version_or_None, {token: codepoint_int}).
# Token strings are returned with all backslash escapes resolved to the
# corresponding Unicode characters so they can be compared with pua.json.


_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9A-Fa-f]{4})")
_HEX_ESCAPE_RE = re.compile(r"\\x([0-9A-Fa-f]{2})")
_RUST_ESCAPE_RE = re.compile(r"\\u\{([0-9A-Fa-f]+)\}")


def _decode_string_literal(literal: str, *, rust: bool = False) -> str:
    """Decode a string literal body (between quotes) into the actual string.

    Handles \\uXXXX (Python/JS/C#/Go), \\u{XXXX} (Rust), and \\xXX. Native
    multi-byte UTF-8 characters are preserved as-is.
    """
    if rust:
        literal = _RUST_ESCAPE_RE.sub(
            lambda m: chr(int(m.group(1), 16)), literal
        )
    literal = _UNICODE_ESCAPE_RE.sub(
        lambda m: chr(int(m.group(1), 16)), literal
    )
    literal = _HEX_ESCAPE_RE.sub(
        lambda m: chr(int(m.group(1), 16)), literal
    )
    return literal


# Backward-compatible alias
_decode_python_string_literal = _decode_string_literal


def parse_python_runtime() -> tuple[int | None, dict[str, int]]:
    """Parse FIXED_PUA_MAPPING from token_mapper.py."""
    text = PYTHON_RUNTIME.read_text(encoding="utf-8")
    # match `"token": 0xE000,` or `"token": 0xE000  # comment`
    pattern = re.compile(
        r'^\s*"((?:[^"\\]|\\.)+)":\s*0x([0-9A-Fa-f]+)\s*,', re.MULTILINE
    )
    mapping: dict[str, int] = {}
    for m in pattern.finditer(text):
        token = _decode_string_literal(m.group(1))
        codepoint = int(m.group(2), 16)
        # Only include PUA range entries
        if 0xE000 <= codepoint <= 0xF8FF:
            mapping[token] = codepoint
    return None, mapping


def parse_python_g2p() -> tuple[int | None, dict[str, int]]:
    """pua.py loads pua.json at import time, so we read PUA_COMPAT_VERSION only."""
    text = PYTHON_G2P_PUA.read_text(encoding="utf-8")
    m = re.search(r"PUA_COMPAT_VERSION\s*:\s*int\s*=\s*(\d+)", text)
    version = int(m.group(1)) if m else None
    return version, {}  # mapping is loaded dynamically; canonical equals itself


def parse_rust() -> tuple[int | None, dict[str, int]]:
    """Parse FIXED_PUA_MAP from token_map.rs."""
    text = RUST_TOKEN_MAP.read_text(encoding="utf-8")
    m = re.search(
        r"PUA_COMPAT_VERSION\s*:\s*u32\s*=\s*(\d+)", text
    )
    version = int(m.group(1)) if m else None

    # Tokens look like ("a:", 0xE000),  or ("\u{025b}\u{0303}", 0xE056),
    pattern = re.compile(
        r'\(\s*"((?:[^"\\]|\\.)+)"\s*,\s*0x([0-9A-Fa-f]+)\s*\)', re.MULTILINE
    )
    mapping: dict[str, int] = {}
    for m2 in pattern.finditer(text):
        token = _decode_string_literal(m2.group(1), rust=True)
        codepoint = int(m2.group(2), 16)
        if 0xE000 <= codepoint <= 0xF8FF:
            mapping[token] = codepoint
    return version, mapping


def parse_go() -> tuple[int | None, dict[str, int]]:
    """Parse fixedPUA from pua.go."""
    text = GO_PUA.read_text(encoding="utf-8")
    # Tokens look like:  "a:":       0xE000,  or  "ɛ̃":       0xE056,
    pattern = re.compile(
        r'^\s*"((?:[^"\\]|\\.)+)"\s*:\s*0x([0-9A-Fa-f]+)\s*,', re.MULTILINE
    )
    mapping: dict[str, int] = {}
    for m in pattern.finditer(text):
        token = _decode_string_literal(m.group(1))
        codepoint = int(m.group(2), 16)
        if 0xE000 <= codepoint <= 0xF8FF:
            mapping[token] = codepoint
    return None, mapping


def parse_js() -> tuple[int | None, dict[str, int]]:
    """Parse PUA_MAP from pua-map.js."""
    text = JS_PUA.read_text(encoding="utf-8")
    m = re.search(r"PUA_COMPAT_VERSION\s*=\s*(\d+)", text)
    version = int(m.group(1)) if m else None

    # Match keys/values inside the export const PUA_MAP = { ... }; block.
    body_match = re.search(r"export const PUA_MAP\s*=\s*\{(.*?)\};", text, re.DOTALL)
    if not body_match:
        return version, {}
    body = body_match.group(1)

    pattern = re.compile(
        r"^\s*'((?:[^'\\]|\\.)+)'\s*:\s*'((?:[^'\\]|\\.)+)'", re.MULTILINE
    )
    mapping: dict[str, int] = {}
    for m2 in pattern.finditer(body):
        token = _decode_string_literal(m2.group(1))
        value = _decode_string_literal(m2.group(2))
        if not value:
            continue
        codepoint = ord(value[0])
        if 0xE000 <= codepoint <= 0xF8FF:
            mapping[token] = codepoint
    return version, mapping


def parse_csharp() -> tuple[int | None, dict[str, int]]:
    """Parse TokenToChar from OpenJTalkToPiperMapping.cs."""
    text = CSHARP_PUA.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\["((?:[^"\\]|\\.)+)"\]\s*=\s*\'((?:[^\'\\]|\\.)+)\'', re.MULTILINE
    )
    mapping: dict[str, int] = {}
    for m in pattern.finditer(text):
        token = _decode_string_literal(m.group(1))
        value = _decode_string_literal(m.group(2))
        if not value:
            continue
        codepoint = ord(value[0])
        if 0xE000 <= codepoint <= 0xF8FF:
            mapping[token] = codepoint
    return None, mapping


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare(canonical: dict[str, int], runtime: dict[str, int], name: str) -> list[str]:
    """Return a list of human-readable error messages."""
    errors: list[str] = []

    canonical_tokens = set(canonical.keys())
    runtime_tokens = set(runtime.keys())

    missing = canonical_tokens - runtime_tokens
    extra = runtime_tokens - canonical_tokens

    for token in sorted(missing):
        cp = canonical[token]
        errors.append(
            f"  [{name}] MISSING token {token!r} (canonical: U+{cp:04X})"
        )
    for token in sorted(extra):
        cp = runtime[token]
        errors.append(
            f"  [{name}] EXTRA token {token!r} not in canonical (runtime: U+{cp:04X})"
        )
    for token in sorted(canonical_tokens & runtime_tokens):
        if canonical[token] != runtime[token]:
            errors.append(
                f"  [{name}] CODEPOINT MISMATCH for {token!r}: "
                f"canonical=U+{canonical[token]:04X}, runtime=U+{runtime[token]:04X}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 stdout for Windows consoles (cp932) so that error
    # messages containing IPA / PUA characters do not crash.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--check-version", action="store_true",
        help="Also verify PUA_COMPAT_VERSION constants match canonical version",
    )
    args = parser.parse_args(argv)

    canonical_version, canonical_map = load_canonical()
    print(f"Canonical pua.json: version={canonical_version}, entries={len(canonical_map)}")

    runtimes: list[tuple[str, tuple[int | None, dict[str, int]]]] = [
        ("Python runtime (token_mapper.py)", parse_python_runtime()),
        ("Python G2P (pua.py)", parse_python_g2p()),
        ("Rust (token_map.rs)", parse_rust()),
        ("Go (pua.go)", parse_go()),
        ("JavaScript (pua-map.js)", parse_js()),
        ("C# (OpenJTalkToPiperMapping.cs)", parse_csharp()),
    ]

    all_errors: list[str] = []
    for name, (version, mapping) in runtimes:
        if args.verbose:
            print(f"\n{name}: parsed {len(mapping)} entries, version={version}")

        if args.check_version and version is not None and version != canonical_version:
            all_errors.append(
                f"  [{name}] PUA_COMPAT_VERSION={version} != canonical={canonical_version}"
            )

        # Python G2P loads pua.json dynamically -- skip mapping comparison
        if not mapping:
            if args.verbose:
                print(f"  (skipping mapping comparison -- runtime loads pua.json dynamically)")
            continue

        errors = compare(canonical_map, mapping, name)
        all_errors.extend(errors)

    if all_errors:
        print("\nPUA CONSISTENCY ERRORS:")
        for err in all_errors:
            print(err)
        print(f"\nFAILED: {len(all_errors)} mismatch(es). Update runtime tables to match {CANONICAL.relative_to(REPO_ROOT)}")
        return 1

    print("\nAll runtimes are consistent with pua.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
