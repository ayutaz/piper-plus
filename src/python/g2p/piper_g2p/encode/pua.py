"""PUA (Private Use Area) mapping for multi-character phoneme tokens.

Multi-character IPA tokens (e.g. ``"a:"``, ``"ch"``, ``"tɕʰ"``) are mapped
to single Unicode codepoints in the Private Use Area so that downstream
ID-map lookups work character-by-character.

The mapping table is loaded from ``piper_g2p/data/pua.json`` which is the
single source of truth shared across Python, Rust and JS implementations.
Codepoints are baked into trained models and **must not** be changed.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

__all__ = ["FIXED_PUA_MAPPING", "TOKEN2CHAR", "CHAR2TOKEN", "map_token"]

_log = logging.getLogger(__name__)

_PUA_JSON = Path(__file__).parent.parent / "data" / "pua.json"


def _load_pua_mapping() -> dict[str, int]:
    """Load PUA mapping from the canonical JSON file."""
    with open(_PUA_JSON) as f:
        data = json.load(f)
    return {entry["token"]: int(entry["codepoint"], 16) for entry in data["entries"]}


# -------------------------------------------------------------------------
# Fixed PUA mapping table (87 entries)
# CRITICAL: Every codepoint here is baked into trained models.
# Do NOT change assigned codepoints.
# Loaded from data/pua.json — the single source of truth.
# -------------------------------------------------------------------------
FIXED_PUA_MAPPING: dict[str, int] = _load_pua_mapping()

# -------------------------------------------------------------------------
# Bidirectional mappings
# -------------------------------------------------------------------------
TOKEN2CHAR: dict[str, str] = {}
CHAR2TOKEN: dict[str, str] = {}

for _token, _codepoint in FIXED_PUA_MAPPING.items():
    _ch = chr(_codepoint)
    TOKEN2CHAR[_token] = _ch
    CHAR2TOKEN[_ch] = _token


def map_token(token: str) -> str:
    """Map a multi-character IPA token to a single PUA character.

    Single-character tokens are passed through unchanged.
    Multi-character tokens not in the fixed mapping emit a warning
    and are returned unchanged (no dynamic allocation).
    """
    if token in TOKEN2CHAR:
        return TOKEN2CHAR[token]

    if len(token) == 1:
        return token

    warnings.warn(
        f"Unknown multi-character token {token!r} has no PUA mapping; "
        "returning unchanged",
        stacklevel=2,
    )
    return token
