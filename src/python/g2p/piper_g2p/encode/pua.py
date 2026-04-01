"""PUA (Private Use Area) mapping for multi-character phoneme tokens.

Multi-character IPA tokens (e.g. ``"a:"``, ``"ch"``, ``"tɕʰ"``) are mapped
to single Unicode codepoints in the Private Use Area so that downstream
ID-map lookups work character-by-character.

The mapping table is loaded from ``piper_g2p/data/pua.json`` which is the
single source of truth shared across Python, Rust and JS implementations.
Codepoints are baked into trained models and **must not** be changed.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import warnings

__all__ = [
    "FIXED_PUA_MAPPING",
    "TOKEN2CHAR",
    "CHAR2TOKEN",
    "map_token",
    "PUA_COMPAT_VERSION",
    "check_pua_compat",
]

_log = logging.getLogger(__name__)


def _load_pua_mapping() -> dict[str, int]:
    """Load PUA mapping from the canonical JSON file."""
    data_files = importlib.resources.files("piper_g2p") / "data" / "pua.json"
    with (
        importlib.resources.as_file(data_files) as pua_path,
        open(pua_path, encoding="utf-8") as f,
    ):
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


# PUA compatibility version. Increment when new PUA mappings are added.
PUA_COMPAT_VERSION: int = 1


def check_pua_compat(config: dict) -> None:
    """Warn if the model's PUA version doesn't match the package version.

    Parameters
    ----------
    config : dict
        Model config (from config.json). May contain a
        ``pua_compat_version`` key.
    """
    model_version = config.get("pua_compat_version")
    if model_version is None:
        return
    if model_version != PUA_COMPAT_VERSION:
        warnings.warn(
            f"PUA version mismatch: model has pua_compat_version={model_version}, "
            f"but piper-g2p expects version {PUA_COMPAT_VERSION}. "
            "Some phoneme tokens may not encode correctly.",
            UserWarning,
            stacklevel=2,
        )


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
