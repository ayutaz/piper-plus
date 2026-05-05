#!/usr/bin/env python3
"""Regenerate the PUA-related sections of `tests/fixtures/g2p/phoneme_test_cases.json`
from the canonical source (`src/python/g2p/piper_plus_g2p/data/pua.json`).

Why this script exists
----------------------
The fixture is consumed by all 6 runtime test suites (Python/Rust/Go/JS/C#/C++),
and its `pua_map_count` + `pua_map` block must always agree with `pua.json`.
A drift here is exactly what broke Windows CI in PR #389 — the `pua_map_count`
was bumped to 99 while the `pua_map` dict still carried 96 entries, so the Rust
`test_pua_map_individual` assertion fired.

Re-emitting the full JSON via `json.dump` would reflow every inline array
(e.g. `expected_contains: ["k", "o", "n", "i", "a"]`) into 6 lines, producing
hundreds of spurious diff lines. We instead update the two PUA-related fields
**in place** with a small regex pass, leaving all hand-curated test cases
untouched.

Usage
-----
    python scripts/regenerate_test_fixture.py            # writes back in place
    python scripts/regenerate_test_fixture.py --check    # exit 1 on drift (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "g2p" / "phoneme_test_cases.json"


def _build_pua_map_block(entries: list[dict], indent: str = "  ") -> str:
    """Format the `pua_map` dict body matching the fixture's existing style.

    The fixture writes one entry per line with 4-space indentation under the
    top-level key (i.e. `    "token": "0xE000",`). Returns the inner body only —
    the surrounding `"pua_map": {` / `}` is preserved by the caller.
    """
    body_indent = indent * 2  # top-level key has 2-space indent → entries 4-space
    lines = []
    for e in entries:
        # ensure_ascii=True keeps the existing fixture style: non-ASCII glyphs
        # become \uXXXX escapes (e.g. "pʰ" rather than "pʰ").
        token = json.dumps(e["token"])
        codepoint = json.dumps(e["codepoint"])
        lines.append(f"{body_indent}{token}: {codepoint}")
    return ",\n".join(lines)


def regenerate(text: str, pua_data: dict) -> str:
    """Return the fixture JSON text with `pua_map_count` and `pua_map` updated.

    Idempotent: running the function twice on its output yields the same string.
    """
    entries = pua_data["entries"]
    pua_map_count = len(entries)

    # 1) Replace pua_map_count
    text = re.sub(
        r'"pua_map_count":\s*\d+',
        f'"pua_map_count": {pua_map_count}',
        text,
        count=1,
    )

    # 2) Replace pua_map dict body. The fixture has no nested {} inside this
    #    block, so a non-greedy match between `{` and the matching closing `}`
    #    on its own line is unambiguous.
    new_body = _build_pua_map_block(entries)
    text = re.sub(
        r'("pua_map":\s*\{)[^}]*(\n  \})',
        lambda m: f"{m.group(1)}\n{new_body}{m.group(2)}",
        text,
        count=1,
        flags=re.DOTALL,
    )

    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if regeneration would change the fixture "
        "(used by CI to detect drift). Does not write anything.",
    )
    args = parser.parse_args()

    pua_data = json.loads(PUA_JSON.read_text(encoding="utf-8"))
    original = FIXTURE.read_text(encoding="utf-8")
    updated = regenerate(original, pua_data)

    if updated == original:
        print(f"OK: {FIXTURE.relative_to(REPO_ROOT)} already in sync with pua.json")
        return 0

    if args.check:
        print(
            f"DRIFT: {FIXTURE.relative_to(REPO_ROOT)} is out of sync with "
            f"{PUA_JSON.relative_to(REPO_ROOT)}.\n"
            "Run `python scripts/regenerate_test_fixture.py` to refresh.",
            file=sys.stderr,
        )
        return 1

    FIXTURE.write_text(updated, encoding="utf-8")
    print(
        f"Updated {FIXTURE.relative_to(REPO_ROOT)} "
        f"({len(pua_data['entries'])} pua_map entries)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
