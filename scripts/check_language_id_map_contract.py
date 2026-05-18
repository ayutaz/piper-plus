#!/usr/bin/env python3
"""Drift check for LANGUAGE_ID_MAP across all 6 runtimes.

The contract toml (`docs/spec/language-id-map-contract.toml`) lists a canonical
language code -> integer ID mapping that ALL trained piper-plus checkpoints
agree on. This script verifies:

    1. Python canonical (`prepare_multilingual_dataset.py:LANGUAGE_ID_MAP`,
        `ALL_LANGUAGES`) matches the toml exactly.
    2. Each per-runtime literal listed under `[[runtime_sources.entries]]`
        contains the expected mapping (7-lang or 6-lang form), byte-for-byte.
    3. C# / C++ entries (kind = "none") still point at existing files but are
        intentionally NOT compared (they are data-driven from config JSON).

Drift here is catastrophic — see `docs/spec/language-id-map-contract.toml` for
the rationale. A change to LANGUAGE_ID_MAP requires editing every runtime
listed in the toml and updating this script's expectations.

Usage:
    python scripts/check_language_id_map_contract.py            # CI mode
    python scripts/check_language_id_map_contract.py --verbose  # show all values
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
CONTRACT_PATH = REPO_ROOT / "docs/spec/language-id-map-contract.toml"


# ---------------------------------------------------------------------------
# Source extractors — one per `kind` listed in the toml's runtime_sources.
# ---------------------------------------------------------------------------


def _extract_python_dict_literal(path: Path, name: str) -> dict[str, int] | None:
    """Find `NAME = {"ja": 0, ...}` and return the parsed dict.

    The literal MUST be on a single line (we don't run a Python parser) and
    only contain string -> int pairs. Returns None if not found.
    """
    text = path.read_text(encoding="utf-8")
    pat = re.compile(
        rf"^{re.escape(name)}\s*(?::\s*[^=]+)?=\s*(\{{[^}}]*\}})\s*(?:#.*)?$",
        flags=re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return None
    body = m.group(1)
    try:
        # The literal looks like Python-and-also-JSON: convert single quotes
        # to double quotes to make json.loads happy (we already filtered to
        # str -> int pairs).
        normalized = body.replace("'", '"')
        return json.loads(normalized)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_python_list_literal(path: Path, name: str) -> list[str] | None:
    """Find `NAME = [...]` (single-line, str-only) and return the list."""
    text = path.read_text(encoding="utf-8")
    pat = re.compile(
        rf"^{re.escape(name)}\s*(?::\s*[^=]+)?=\s*(\[[^\]]*\])\s*(?:#.*)?$",
        flags=re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return None
    body = m.group(1)
    try:
        return json.loads(body.replace("'", '"'))
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_inline_python_list(path: Path, expected: list[str]) -> bool:
    """Verify the file contains the inline 6-lang list literal verbatim.

    voice.py:479 has the literal as part of a conditional expression with no
    top-level binding, so we just substring-search for the rendered form.
    """
    text = path.read_text(encoding="utf-8")
    # Render both quote styles to be tolerant of formatter changes.
    rendered_double = "[" + ", ".join(f'"{x}"' for x in expected) + "]"
    rendered_single = "[" + ", ".join(f"'{x}'" for x in expected) + "]"
    return rendered_double in text or rendered_single in text


def _extract_inline_substring_map(path: Path, expected_map: dict[str, int]) -> bool:
    """Check that an inline JSON-shaped literal exists in the source file.

    Used for Rust source files where `language_id_map` appears as an embedded
    JSON literal inside a `serde_json::json!()` macro or `r#"..."#` raw
    string. The braces may live on separate lines from the body; what we
    verify is that the *ordered key-value sequence* appears as a single line
    inside the file (with one of two common spacings).
    """
    text = path.read_text(encoding="utf-8")
    # Variant 1: comma-space separated, full `"k": v` form.
    body1 = ", ".join(f'"{k}": {v}' for k, v in expected_map.items())
    if body1 in text:
        return True
    # Variant 2: comma + no-space form (`"k":v`).
    body2 = ", ".join(f'"{k}":{v}' for k, v in expected_map.items())
    return body2 in text


def _extract_json_field(path: Path, field: str) -> object:
    """Read a top-level JSON field from a file."""
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get(field)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print all checked values"
    )
    args = parser.parse_args()

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    canonical_7 = dict(contract["canonical"]["language_id_map"])
    canonical_7_list = list(contract["canonical"]["all_languages"])
    canonical_6 = dict(contract["canonical"]["trained_language_id_map"])
    canonical_6_list = list(contract["canonical"]["trained_languages"])
    canonical_8 = dict(contract["canonical"]["extended_language_id_map"])
    canonical_8_list = list(contract["canonical"]["extended_languages"])

    # Map of expected-name -> resolved value used by per-entry checks.
    expected_resolvers: dict[str, object] = {
        "language_id_map": canonical_7,
        "all_languages": canonical_7_list,
        "trained_language_id_map": canonical_6,
        "trained_languages": canonical_6_list,
        "extended_language_id_map": canonical_8,
        "extended_languages": canonical_8_list,
    }

    errors: list[str] = []

    # ---- 1. Invariants on the canonical map itself --------------------------
    invariants = contract["invariants"]
    for name, mapping in (
        ("language_id_map", canonical_7),
        ("trained_language_id_map", canonical_6),
        ("extended_language_id_map", canonical_8),
    ):
        keys = list(mapping.keys())
        values = list(mapping.values())
        if invariants["keys_lowercase"] and any(k != k.lower() for k in keys):
            errors.append(f"  {name}: keys_lowercase invariant violated ({keys!r})")
        if invariants["values_consecutive_from_zero"] and sorted(values) != list(
            range(len(values))
        ):
            errors.append(
                f"  {name}: values_consecutive_from_zero invariant violated "
                f"(values={values!r})"
            )
        if invariants["values_unique"] and len(set(values)) != len(values):
            errors.append(f"  {name}: values_unique invariant violated ({values!r})")
        if invariants["ja_is_zero"] and mapping.get("ja") != 0:
            errors.append(
                f"  {name}: ja_is_zero invariant violated (ja={mapping.get('ja')!r})"
            )
        if invariants["en_is_one"] and mapping.get("en") != 1:
            errors.append(
                f"  {name}: en_is_one invariant violated (en={mapping.get('en')!r})"
            )
    if invariants["values_consecutive_from_zero"]:
        # Cross-form: every shared key must agree across the 6/7/8-lang forms.
        # (Adding sv or ko must NEVER renumber an existing language.)
        for k, v in canonical_6.items():
            if canonical_7.get(k) != v:
                errors.append(
                    f"  trained_language_id_map[{k!r}]={v!r} disagrees with "
                    f"language_id_map[{k!r}]={canonical_7.get(k)!r}"
                )
        for k, v in canonical_7.items():
            if canonical_8.get(k) != v:
                errors.append(
                    f"  language_id_map[{k!r}]={v!r} disagrees with "
                    f"extended_language_id_map[{k!r}]={canonical_8.get(k)!r}"
                )

    # ---- 2. Per-runtime source extraction ----------------------------------
    for entry in contract["runtime_sources"]["entries"]:
        runtime = entry["runtime"]
        rel_path = entry["path"]
        kind = entry["kind"]
        path = REPO_ROOT / rel_path
        if not path.exists():
            errors.append(f"  [{runtime}] path missing: {rel_path}")
            continue

        if kind == "none":
            # Data-driven runtimes — only verify the file still exists.
            if args.verbose:
                print(f"  SKIP [{runtime}] {rel_path} (data-driven, kind=none)")
            continue

        expected_key = entry["expected"]
        expected = expected_resolvers[expected_key]

        if kind == "python_dict_literal":
            actual = _extract_python_dict_literal(path, entry["symbol"])
            if actual is None:
                errors.append(
                    f"  [{runtime}] could not extract {entry['symbol']!r} "
                    f"from {rel_path}"
                )
            elif actual != expected:
                errors.append(
                    f"  [{runtime}] {entry['symbol']} in {rel_path}: "
                    f"actual={actual!r} != expected={expected!r}"
                )
            elif args.verbose:
                print(f"  OK [{runtime}] {entry['symbol']} = {actual!r}")

        elif kind == "python_list_literal":
            actual = _extract_python_list_literal(path, entry["symbol"])
            if actual is None:
                errors.append(
                    f"  [{runtime}] could not extract {entry['symbol']!r} "
                    f"from {rel_path}"
                )
            elif actual != expected:
                errors.append(
                    f"  [{runtime}] {entry['symbol']} in {rel_path}: "
                    f"actual={actual!r} != expected={expected!r}"
                )
            elif args.verbose:
                print(f"  OK [{runtime}] {entry['symbol']} = {actual!r}")

        elif kind == "python_list_literal_inline":
            ok = _extract_inline_python_list(path, expected)  # type: ignore[arg-type]
            if not ok:
                errors.append(
                    f"  [{runtime}] inline list literal {expected!r} not found in "
                    f"{rel_path} (expected one of double-quoted or single-quoted form)"
                )
            elif args.verbose:
                print(f"  OK [{runtime}] inline list {expected!r} present")

        elif kind in (
            "inline_substring_6lang",
            "inline_substring_7lang",
            "inline_substring_8lang",
        ):
            target_map = {
                "inline_substring_6lang": canonical_6,
                "inline_substring_7lang": canonical_7,
                "inline_substring_8lang": canonical_8,
            }[kind]
            ok = _extract_inline_substring_map(path, target_map)
            if not ok:
                errors.append(
                    f"  [{runtime}] inline {kind} literal not found in {rel_path} "
                    f"(expected map={target_map!r})"
                )
            elif args.verbose:
                print(f"  OK [{runtime}] inline {kind} literal present")

        elif kind == "json_field":
            actual = _extract_json_field(path, entry["field"])
            if actual != expected:
                errors.append(
                    f"  [{runtime}] {rel_path}.{entry['field']}: "
                    f"actual={actual!r} != expected={expected!r}"
                )
            elif args.verbose:
                print(f"  OK [{runtime}] {rel_path}.{entry['field']} = {actual!r}")

        else:
            errors.append(f"  [{runtime}] unknown extractor kind={kind!r}")

    # ---- 3. Forbidden patterns elsewhere -----------------------------------
    # Lightweight allowlist sweep: forbidden_outside_sources should not appear
    # in any source file under src/. We constrain to a fixed extension list
    # and prune noisy directories so the sweep runs in <1 s on CI.
    allowlisted_paths = {
        REPO_ROOT / "docs/spec/language-id-map-contract.toml",
        Path(__file__).resolve(),
        REPO_ROOT / "tests/fixtures/language_id_map/contract.json",
        REPO_ROOT / "scripts/regenerate_language_id_map_fixture.py",
    }
    # Source-code-ish extensions only — skip binaries, generated files, models.
    sweep_extensions = {
        ".py",
        ".rs",
        ".go",
        ".cs",
        ".cpp",
        ".cc",
        ".c",
        ".h",
        ".hpp",
        ".js",
        ".ts",
        ".mjs",
        ".cjs",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".kt",
        ".swift",
    }
    # Directory names to prune entirely (anywhere in path).
    skip_dirs = {
        "node_modules",
        "target",
        "build",
        "dist",
        "bin",
        "obj",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "vendor",
        "pkg",  # Go module cache
        # Tests legitimately exercise edge cases including non-canonical
        # language_id_map literals (e.g. http_server fallback paths). The
        # contract verifies SOURCE drift, not test fixture diversity.
        "tests",
        "test",
        "testdata",
        "TestData",
        "fixtures",
    }
    forbidden = contract["expected_not_found"]["forbidden_outside_sources"]
    sweep_root = REPO_ROOT / "src"
    files_to_scan: list[Path] = []
    for path in sweep_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in sweep_extensions:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        # Explicit per-file skip: any file whose name starts with `test_` or
        # ends with `_test.<ext>` / `Test.<ext>` / `Tests.<ext>` is a test.
        name = path.name
        if (
            name.startswith("test_")
            or name.endswith("_test.go")
            or name.endswith(".test.js")
            or name.endswith(".test.ts")
            or name.endswith(".spec.ts")
            or name.endswith(".spec.js")
            or name.endswith("Test.cs")
            or name.endswith("Tests.cs")
        ):
            continue
        if path in allowlisted_paths:
            continue
        files_to_scan.append(path)

    for path in files_to_scan:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for forbidden_pat in forbidden:
            if forbidden_pat in content:
                errors.append(
                    f"  forbidden pattern {forbidden_pat!r} found in "
                    f"{path.relative_to(REPO_ROOT)} (would silently break "
                    f"trained-model emb_lang lookups)"
                )

    if errors:
        print("ERROR: LANGUAGE_ID_MAP cross-runtime drift detected:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            f"Update {CONTRACT_PATH.relative_to(REPO_ROOT)} OR the listed "
            f"runtime source(s) so they agree. Drift here breaks every "
            f"trained multilingual checkpoint — review carefully.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: LANGUAGE_ID_MAP contract ({CONTRACT_PATH.relative_to(REPO_ROOT)}) "
        f"matches Python canonical and 6 runtime sources."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
