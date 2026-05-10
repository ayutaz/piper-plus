#!/usr/bin/env python3
"""Drift check between docs/spec/text-splitter-contract.toml and Python canonical.

The contract toml lists canonical closing-punctuation + sentence-terminator
codepoints. This script verifies the Python canonical implementation
(``src/python_run/piper/text_splitter.py``) matches the *python* runtime row
projected by ``regenerate_text_splitter_fixture.py``.

Per-runtime divergences (Rust / Go / C# / C++) are tracked in
``regenerate_text_splitter_fixture.py``'s RUNTIME_*_OMITS tables and validated
by per-runtime tests, not here.

Usage:
    python scripts/check_text_splitter_contract.py            # CI mode
    python scripts/check_text_splitter_contract.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLITTER_PATH = REPO_ROOT / "src/python_run/piper/text_splitter.py"

# Lazy import so this script doesn't need the runtime in PYTHONPATH.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from regenerate_text_splitter_fixture import (  # noqa: E402  (intentional sys.path)
    build_fixture,
)


def _extract_set(text: str, name: str) -> set[str]:
    """Extract a frozenset literal '{...}' assigned to *name* in *text*.

    Returns the set of single-character string elements. Comments after each
    element are tolerated. We only support string literals (single or double
    quoted) — non-string elements raise.
    """
    # Match: NAME: frozenset[str] = frozenset(\n    {\n      ...,\n    }\n)
    # or:    NAME = frozenset({...})
    pat = re.compile(
        rf"^{re.escape(name)}\s*(?::\s*\S+\s*)?=\s*frozenset\(\s*\{{(.*?)\}}\s*\)",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        raise ValueError(f"could not find frozenset assignment for {name!r}")

    body = m.group(1)
    # Strip line comments
    body = re.sub(r"#[^\n]*", "", body)
    # Each element: '"x"' or "'x'" — extract them
    elements: set[str] = set()
    for tok in re.finditer(r"(?:'((?:\\.|[^'\\])*)'|\"((?:\\.|[^\"\\])*)\")", body):
        s = tok.group(1) if tok.group(1) is not None else tok.group(2)
        # Decode python escape sequences only if the literal contains them.
        # Already-decoded UTF-8 source chars are passed through unchanged.
        if "\\" in s:
            try:
                decoded = s.encode("utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                decoded = s
        else:
            decoded = s
        if len(decoded) != 1:
            raise ValueError(
                f"element {s!r} in {name} is not a single character "
                f"(decoded={decoded!r})"
            )
        elements.add(decoded)
    return elements


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    fixture = build_fixture()
    py_expected_close = {chr(cp) for cp in fixture["runtimes"]["python"]["closing_punctuation"]}
    py_expected_term = {chr(cp) for cp in fixture["runtimes"]["python"]["sentence_terminators"]}

    text = SPLITTER_PATH.read_text(encoding="utf-8")
    actual_close = _extract_set(text, "_CLOSING_PUNCTUATION")
    actual_term = _extract_set(text, "_SENTENCE_TERMINATORS")

    errors: list[str] = []
    if actual_close != py_expected_close:
        missing = py_expected_close - actual_close
        extra = actual_close - py_expected_close
        if missing:
            errors.append(
                f"  _CLOSING_PUNCTUATION missing chars (codepoints): "
                f"{sorted(ord(c) for c in missing)}"
            )
        if extra:
            errors.append(
                f"  _CLOSING_PUNCTUATION has unexpected chars (codepoints): "
                f"{sorted(ord(c) for c in extra)}"
            )
    elif args.verbose:
        print(f"  OK _CLOSING_PUNCTUATION: {len(actual_close)} chars")

    if actual_term != py_expected_term:
        missing = py_expected_term - actual_term
        extra = actual_term - py_expected_term
        if missing:
            errors.append(
                f"  _SENTENCE_TERMINATORS missing chars (codepoints): "
                f"{sorted(ord(c) for c in missing)}"
            )
        if extra:
            errors.append(
                f"  _SENTENCE_TERMINATORS has unexpected chars (codepoints): "
                f"{sorted(ord(c) for c in extra)}"
            )
    elif args.verbose:
        print(f"  OK _SENTENCE_TERMINATORS: {len(actual_term)} chars")

    if errors:
        print("ERROR: text-splitter contract drift detected:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            "Update docs/spec/text-splitter-contract.toml or text_splitter.py "
            "(or scripts/regenerate_text_splitter_fixture.py's RUNTIME_*_OMITS) so they agree.",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: text-splitter contract (docs/spec/text-splitter-contract.toml) "
        "matches Python canonical (src/python_run/piper/text_splitter.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
