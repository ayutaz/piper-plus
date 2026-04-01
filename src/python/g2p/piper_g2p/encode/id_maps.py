"""Language-specific phoneme-to-ID maps for Piper TTS.

Phase 0 ships a built-in ID map for Japanese only.  Other languages
require the ``phoneme_id_map`` from the model's ``config.json`` and
will raise ``ValueError`` here.
"""

from __future__ import annotations

from functools import lru_cache

from .pua import map_token

__all__ = ["get_phoneme_id_map"]

# -------------------------------------------------------------------------
# Japanese phoneme inventory (identical ordering to piper_train)
# -------------------------------------------------------------------------
_SPECIAL_TOKENS: list[str] = [
    "_",   # short pause (pad, id=0)
    "^",   # BOS
    "$",   # EOS (declarative)
    "?",   # EOS (interrogative - generic)
    "?!",  # EOS (emphatic question)
    "?.",  # EOS (neutral/rhetorical question)
    "?~",  # EOS (tag question)
    "#",   # accent phrase boundary
    "[",   # rising pitch mark
    "]",   # falling pitch mark
]

_JAPANESE_PHONEMES: list[str] = [
    # voiced vowels
    "a", "i", "u", "e", "o",
    # unvoiced vowels (uppercase)
    "A", "I", "U", "E", "O",
    "a:", "i:", "u:", "e:", "o:",
    # special consonant-centric phonemes
    "N",
    "N_m", "N_n", "N_ng", "N_uvular",
    "cl", "q",
    # plosives + voiced counterparts
    "k", "ky", "kw",
    "g", "gy", "gw",
    "t", "ty",
    "d", "dy",
    "p", "py",
    "b", "by",
    # affricates, fricatives, etc.
    "ch", "ts",
    "s", "sh",
    "z", "j", "zy",
    "f", "h", "hy",
    "v",
    # nasals / approximants
    "n", "ny",
    "m", "my",
    "r", "ry",
    "w", "y",
]


def _build_japanese_id_map() -> dict[str, list[int]]:
    """Build the JA phoneme_id_map with PUA-converted keys.

    The ordering is identical to ``piper_train.phonemize.jp_id_map``:
    each token is passed through ``map_token()`` so that multi-character
    tokens become single PUA characters, and the resulting character is
    used as the dictionary key.  This ensures compatibility with models
    trained by piper_train.
    """
    symbols = [map_token(s) for s in (_SPECIAL_TOKENS + _JAPANESE_PHONEMES)]
    return {symbol: [idx] for idx, symbol in enumerate(symbols)}


@lru_cache(maxsize=8)
def get_phoneme_id_map(language: str) -> dict[str, list[int]]:
    """Return the built-in phoneme_id_map for *language*.

    Parameters
    ----------
    language : str
        BCP-47 language code (e.g. ``"ja"``).

    Returns
    -------
    dict[str, list[int]]
        Mapping from (PUA-encoded) symbol to a list containing its
        integer ID.

    Raises
    ------
    ValueError
        If *language* is not ``"ja"``.  Phase 0 only ships a built-in
        ID map for Japanese; other languages need the map from the
        model's ``config.json``.
    """
    if language == "ja":
        return _build_japanese_id_map()

    raise ValueError(
        f"No built-in phoneme_id_map for language {language!r}. "
        "Use the phoneme_id_map from the model's config.json instead."
    )
