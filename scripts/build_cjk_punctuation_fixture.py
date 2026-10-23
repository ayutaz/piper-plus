#!/usr/bin/env python3
"""Build the CJK punctuation fixture from docs/spec/cjk-punctuation-contract.toml.

Every G2P runtime reads tests/fixtures/g2p/cjk_punctuation_cases.json and
checks two things against it (Issue #823):

* ``neutral``: each code point is neutral for the Unicode language detector
  (configured with every G2P language and Latin default ``en``), and is
  replaced by ``latin`` when it appears in a Latin-script segment;
* ``fullwidth_latin``: the fullwidth Latin letters stay Latin (``en``), so the
  neutral ranges never swallow them.

The fixture is derived from the contract, not from a runtime, so a runtime
that drifts from the contract fails its own test.

Usage:
    uv run python scripts/build_cjk_punctuation_fixture.py          # write
    uv run python scripts/build_cjk_punctuation_fixture.py --check  # verify
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "spec" / "cjk-punctuation-contract.toml"
OUTPUT = REPO_ROOT / "tests" / "fixtures" / "g2p" / "cjk_punctuation_cases.json"

DETECTOR_LANGUAGES = ["en", "es", "fr", "ja", "ko", "pt", "sv", "zh"]
DEFAULT_LATIN = "en"


def _cp(text: str) -> int:
    if not text.startswith("U+"):
        raise ValueError(f"code point must be written U+XXXX: {text!r}")
    return int(text[2:], 16)


def _label(cp: int) -> str:
    return f"U+{cp:04X}"


def neutral_code_points(contract: dict) -> list[int]:
    cps: set[int] = set()
    for start, end in contract["neutral"]["ranges"]:
        cps.update(range(_cp(start), _cp(end) + 1))
    return sorted(cps)


def latin_replacement(cp: int, contract: dict) -> str:
    latin = contract["latin_segments"]
    lo, hi = (_cp(x) for x in latin["fullwidth_ascii"])
    if lo <= cp <= hi:
        return chr(cp - 0xFEE0)
    punctuation = {_cp(k): v for k, v in latin["punctuation"].items()}
    return punctuation.get(cp, " ")


def build() -> dict:
    contract = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
    neutral = neutral_code_points(contract)
    fullwidth_latin = [*range(0xFF21, 0xFF3B), *range(0xFF41, 0xFF5B)]
    overlap = set(neutral) & set(fullwidth_latin)
    if overlap:
        raise ValueError(
            f"neutral ranges include fullwidth Latin letters: {sorted(overlap)}"
        )
    return {
        "schema_version": 1,
        "description": (
            "CJK punctuation contract (Issue #823), generated from "
            "docs/spec/cjk-punctuation-contract.toml by "
            "scripts/build_cjk_punctuation_fixture.py. A detector built with "
            "'detector_languages' and Latin default 'default_latin' classifies every "
            "'neutral' code point as neutral and every 'fullwidth_latin' one as "
            "'default_latin'. In a segment of one of 'latin_languages', a neutral "
            "character is replaced by its 'latin' string."
        ),
        "detector_languages": DETECTOR_LANGUAGES,
        "default_latin": DEFAULT_LATIN,
        "latin_languages": contract["latin_segments"]["languages"],
        "neutral": [
            {
                "code_point": _label(cp),
                "char": chr(cp),
                "latin": latin_replacement(cp, contract),
            }
            for cp in neutral
        ],
        "fullwidth_latin": [
            {"code_point": _label(cp), "char": chr(cp)} for cp in fullwidth_latin
        ],
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the fixture is out of date"
    )
    args = parser.parse_args(argv)

    expected = render(build())
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if actual != expected:
            print(
                f"ERROR: {OUTPUT.relative_to(REPO_ROOT)} is out of date; run "
                "scripts/build_cjk_punctuation_fixture.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {OUTPUT.relative_to(REPO_ROOT)} is up to date")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
