#!/usr/bin/env python3
"""Custom dictionary JSON 同期チェッカー (canonical → WASM mirror).

Thin wrapper around `scripts/_mirror_check.py`. The actual mirror
declarations live in `docs/spec/dictionary-mirrors.toml` — edit the TOML
to add new dictionaries, this file should not need changes.

Why a shared helper: the byte-equal sync pattern is repeated across
dictionary / loanword / (potentially) PUA. Centralising it makes new
gates a 5-line wrapper + TOML spec instead of copy-pasting ~150 lines.

Usage:
    python scripts/check_dictionary_consistency.py        # check only
    python scripts/check_dictionary_consistency.py --fix  # canonical → mirror

Exit codes:
    0 -- all in sync (or --fix succeeded)
    1 -- mismatch / missing
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mirror_check import run_from_toml  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return run_from_toml(
        "docs/spec/dictionary-mirrors.toml",
        argv=argv if argv is not None else sys.argv[1:],
    )


if __name__ == "__main__":
    sys.exit(main())
