#!/usr/bin/env python3
"""ZH-EN loanword forward-compatibility check.

The canonical schema is `version: 1`. The loader contract (documented in
docs/reference/zh-en-loanword/README.md) requires every runtime to
silently accept future fields that v1 loaders did not know about — both
top-level keys, per-section unknowns, and a bumped `schema_version`.

This script validates the Python-side loader against a synthetic fixture
that exercises that contract:

- top-level: extra keys (`future_top_level_field`)
- top-level: bumped `schema_version` to 2
- per-section: extra sections (`future_per_entry_extension`)
- per-entry: extra metadata keys

A successful run means the Python loader returns a usable dictionary and
does not crash, mirroring what each non-Python runtime is expected to do.
The other runtimes have their own loader tests that load this same
fixture (added incrementally as Phase 6c rollout progresses).

Exit codes:
    0 -- forward-compat fixture loads cleanly into the Python runtime
    1 -- loader rejected the fixture or returned an empty dictionary
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests/fixtures/g2p/zh_en_loanword_forward_compat.json"


def main() -> int:
    if not FIXTURE.exists():
        print(f"ERROR: fixture missing: {FIXTURE}", file=sys.stderr)
        return 1

    with FIXTURE.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    schema_version = raw.get("schema_version", raw.get("version", 1))
    if schema_version < 2:
        print(
            f"ERROR: fixture must declare schema_version >= 2 to exercise "
            f"forward-compat (got {schema_version})",
            file=sys.stderr,
        )
        return 1

    if "future_top_level_field" not in raw:
        print(
            "ERROR: fixture must include `future_top_level_field` to "
            "exercise unknown top-level key tolerance",
            file=sys.stderr,
        )
        return 1

    if "future_per_entry_extension" not in raw:
        print(
            "ERROR: fixture must include `future_per_entry_extension` to "
            "exercise unknown section tolerance",
            file=sys.stderr,
        )
        return 1

    try:
        from piper_plus_g2p.chinese import _load_loanword_data
    except ImportError as exc:
        print(
            f"ERROR: cannot import piper_plus_g2p.chinese: {exc}\n"
            "Run from a checkout where piper_plus_g2p is installed "
            "(e.g. uv run python scripts/check_loanword_forward_compat.py).",
            file=sys.stderr,
        )
        return 1

    loaded = _load_loanword_data(FIXTURE)
    if not loaded:
        print(
            "ERROR: loader returned empty dict for forward-compat fixture",
            file=sys.stderr,
        )
        return 1

    if "GPS" not in loaded.get("acronyms", {}):
        print(
            "ERROR: GPS acronym missing from loaded dict — loader may have "
            "rejected the fixture instead of ignoring unknown fields",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: forward-compat fixture loaded; "
        f"{len(loaded.get('acronyms', {}))} acronyms, "
        f"{len(loaded.get('loanwords', {}))} loanwords, "
        f"{len(loaded.get('letter_fallback', {}))} letter_fallback entries."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
