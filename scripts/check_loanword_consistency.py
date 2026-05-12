#!/usr/bin/env python3
"""ZH-EN loanword JSON 同期チェッカー (thin wrapper).

The actual mirror declarations live in `docs/spec/loanword-mirrors.toml`;
this wrapper registers a loanword-specific JSON schema validator and
delegates to `scripts/_mirror_check.run_from_toml`.

Why a wrapper (not pure TOML driven): Python `_load_loanword_data` has
forward-compat behaviour (silently accepts `version` field absence,
unknown top-level fields, `schema_version: 2`) that can't be encoded in
TOML. The validator stays here so the helper remains generic.

Source of truth: src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json

Usage:
    python scripts/check_loanword_consistency.py              # check
    python scripts/check_loanword_consistency.py --fix         # canonical → 10 mirrors + 8 fixtures
    python scripts/check_loanword_consistency.py --schema-only # schema only
    python scripts/check_loanword_consistency.py --diff        # dry-run diff
    python scripts/check_loanword_consistency.py --allow-missing  # Phase 6a

Exit codes:
    0 -- すべて同期済 (または --allow-missing で missing が warn 扱い)
    1 -- 1 つ以上の mismatch / schema 違反
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mirror_check import register_schema_validator, run_from_toml  # noqa: E402


def validate_loanword_schema(p: Path) -> None:
    """Mirror of `_load_loanword_data` validation behaviour.

    Error message format matches the original loader exactly:
        f"{p}: '{section}.{key}' must be list[str], got {value!r}"

    Forward-compat (YELLOW-5): silently accept `version` absence / type
    mismatch and unknown top-level fields so `schema_version: 2`-shaped
    canonicals are not rejected at runtime.
    """
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level must be a JSON object")
    for section in ("acronyms", "loanwords", "letter_fallback"):
        m = data.get(section, {})
        if not isinstance(m, dict):
            raise ValueError(
                f"{p}: section '{section}' must be a mapping, got "
                f"{type(m).__name__}"
            )
        for k, v in m.items():
            if not isinstance(v, list) or not all(isinstance(e, str) for e in v):
                raise ValueError(
                    f"{p}: '{section}.{k}' must be list[str], got {v!r}"
                )


# Keyed by the TOML [[groups]].name of the *runtime data* group (not the
# fixture group — fixtures intentionally use a different schema).
register_schema_validator(
    "zh_en_loanword runtime data (10 mirrors)",
    validate_loanword_schema,
)


def main(argv: list[str] | None = None) -> int:
    return run_from_toml(
        "docs/spec/loanword-mirrors.toml",
        argv=argv if argv is not None else sys.argv[1:],
    )


if __name__ == "__main__":
    sys.exit(main())
