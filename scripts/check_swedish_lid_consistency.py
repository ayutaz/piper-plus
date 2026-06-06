#!/usr/bin/env python3
"""Swedish per-word LID function-word JSON 同期チェッカー (thin wrapper).

The actual mirror declarations live in `docs/spec/swedish-lid-mirrors.toml`;
this wrapper registers a Swedish-LID-specific JSON schema validator and
delegates to `scripts/_mirror_check.run_from_toml`.

Why a wrapper (not pure TOML driven): the Swedish function-word loader has
forward-compat behaviour (silently accepts `schema_version` absence/extra
and unknown top-level fields) that can't be encoded in TOML. The validator
stays here so the helper remains generic.

Source of truth: src/python/g2p/piper_plus_g2p/data/sv_function_words.json

Usage:
    python scripts/check_swedish_lid_consistency.py              # check
    python scripts/check_swedish_lid_consistency.py --fix         # canonical → 7 mirrors
    python scripts/check_swedish_lid_consistency.py --schema-only # schema only
    python scripts/check_swedish_lid_consistency.py --diff        # dry-run diff

Exit codes:
    0 -- すべて同期済
    1 -- 1 つ以上の mismatch / schema 違反
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mirror_check import register_schema_validator, run_from_toml  # noqa: E402


def validate_swedish_lid_schema(p: Path) -> None:
    """Validate the Swedish per-word LID function-word JSON shape.

    Contract:
      * top-level must be a JSON object;
      * `function_words` (if present) must be list[str];
      * `strong_chars` (if present) must be list[str].

    Forward-compat: silently accept `schema_version` absence/extra and any
    unknown top-level fields so a future `schema_version: 2`-shaped canonical
    is not rejected at runtime (matching the ZH-EN loanword loader stance).
    """
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level must be a JSON object")
    for key in ("function_words", "strong_chars"):
        if key not in data:
            continue
        v = data[key]
        if not isinstance(v, list) or not all(isinstance(e, str) for e in v):
            raise ValueError(f"{p}: '{key}' must be list[str], got {v!r}")


# Keyed by the TOML [[groups]].name of the runtime data group.
register_schema_validator(
    "sv_function_words runtime data (7 mirrors)",
    validate_swedish_lid_schema,
)


def main(argv: list[str] | None = None) -> int:
    return run_from_toml(
        "docs/spec/swedish-lid-mirrors.toml",
        argv=argv if argv is not None else sys.argv[1:],
    )


if __name__ == "__main__":
    sys.exit(main())
