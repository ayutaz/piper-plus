"""PUA (Private Use Area) mapping for multi-character phoneme tokens.

Multi-character IPA tokens (e.g. ``"a:"``, ``"ch"``, ``"tɕʰ"``) are mapped
to single Unicode codepoints in the Private Use Area so that downstream
ID-map lookups work character-by-character.

The mapping table is identical to ``piper_train.phonemize.token_mapper``
and the C++ implementations.  Codepoints are baked into trained models
and **must not** be changed.
"""

from __future__ import annotations

import logging
import warnings

__all__ = ["FIXED_PUA_MAPPING", "TOKEN2CHAR", "CHAR2TOKEN", "map_token"]

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Fixed PUA mapping table (87 entries)
# CRITICAL: Every codepoint here is baked into trained models.
# Do NOT change assigned codepoints.
# -------------------------------------------------------------------------
FIXED_PUA_MAPPING: dict[str, int] = {
    # =======================================================================
    # Japanese (JA)
    # =======================================================================
    # Long vowels
    "a:": 0xE000,
    "i:": 0xE001,
    "u:": 0xE002,
    "e:": 0xE003,
    "o:": 0xE004,
    # Special consonants
    "cl": 0xE005,
    # Palatalized consonants
    "ky": 0xE006,
    "kw": 0xE007,
    "gy": 0xE008,
    "gw": 0xE009,
    "ty": 0xE00A,
    "dy": 0xE00B,
    "py": 0xE00C,
    "by": 0xE00D,
    # Affricates and special sounds
    "ch": 0xE00E,
    "ts": 0xE00F,
    "sh": 0xE010,
    "zy": 0xE011,
    "hy": 0xE012,
    # Palatalized nasals/liquids
    "ny": 0xE013,
    "my": 0xE014,
    "ry": 0xE015,
    # Question type markers (Issue #204)
    "?!": 0xE016,  # Emphatic question
    "?.": 0xE017,  # Neutral/rhetorical question
    "?~": 0xE018,  # Tag question
    # N phoneme variants (Issue #207)
    "N_m": 0xE019,  # bilabial
    "N_n": 0xE01A,  # alveolar
    "N_ng": 0xE01B,  # velar
    "N_uvular": 0xE01C,  # uvular
    # =======================================================================
    # Multilingual shared
    # =======================================================================
    "rr": 0xE01D,  # Spanish trill r
    "y_vowel": 0xE01E,  # Close front rounded vowel [y]
    # 0xE01F reserved
    # =======================================================================
    # Chinese (ZH)
    # =======================================================================
    "p\u02b0": 0xE020,  # ph  aspirated bilabial
    "t\u02b0": 0xE021,  # th  aspirated alveolar
    "k\u02b0": 0xE022,  # kh  aspirated velar
    "t\u0255": 0xE023,  # tc  alveolo-palatal affricate
    "t\u0255\u02b0": 0xE024,  # tch aspirated alveolo-palatal affricate
    "t\u0282": 0xE025,  # ts  retroflex affricate
    "t\u0282\u02b0": 0xE026,  # tsh aspirated retroflex affricate
    "ts\u02b0": 0xE027,  # tsh aspirated alveolar affricate
    # Diphthongs
    "a\u026a": 0xE028,  # ai
    "e\u026a": 0xE029,  # ei
    "a\u028a": 0xE02A,  # ao
    "o\u028a": 0xE02B,  # ou
    # Nasal finals
    "an": 0xE02C,
    "\u0259n": 0xE02D,  # en
    "a\u014b": 0xE02E,  # ang
    "\u0259\u014b": 0xE02F,  # eng
    "u\u014b": 0xE030,  # ong
    # i-compound finals
    "ia": 0xE031,
    "i\u025b": 0xE032,  # ie
    "iou": 0xE033,
    "ia\u028a": 0xE034,  # iao
    "i\u025bn": 0xE035,  # ian
    "in": 0xE036,
    "ia\u014b": 0xE037,  # iang
    "i\u014b": 0xE038,  # ing
    "iu\u014b": 0xE039,  # iong
    # u-compound finals
    "ua": 0xE03A,
    "uo": 0xE03B,
    "ua\u026a": 0xE03C,  # uai
    "ue\u026a": 0xE03D,  # uei
    "uan": 0xE03E,
    "u\u0259n": 0xE03F,  # uen
    "ua\u014b": 0xE040,  # uang
    "u\u0259\u014b": 0xE041,  # ueng
    # u-compound finals
    "y\u025b": 0xE042,  # ye
    "y\u025bn": 0xE043,  # yuan
    "yn": 0xE044,
    # Syllabic consonants
    "\u027b\u0329": 0xE045,  # syllabic retroflex
    # Tone markers
    "tone1": 0xE046,
    "tone2": 0xE047,
    "tone3": 0xE048,
    "tone4": 0xE049,
    "tone5": 0xE04A,
    # =======================================================================
    # Korean (KO)
    # =======================================================================
    "p\u0348": 0xE04B,  # tense bilabial
    "t\u0348": 0xE04C,  # tense alveolar
    "k\u0348": 0xE04D,  # tense velar
    "s\u0348": 0xE04E,  # tense sibilant
    "t\u0348\u0255": 0xE04F,  # tense alveolo-palatal affricate
    "k\u031a": 0xE050,  # unreleased velar
    "t\u031a": 0xE051,  # unreleased alveolar
    "p\u031a": 0xE052,  # unreleased bilabial
    # 0xE053 reserved
    # =======================================================================
    # Spanish (ES) / Portuguese (PT)
    # =======================================================================
    "t\u0283": 0xE054,  # voiceless postalveolar affricate
    "d\u0292": 0xE055,  # voiced postalveolar affricate
    # =======================================================================
    # French (FR)
    # =======================================================================
    "\u025b\u0303": 0xE056,  # nasal open-mid front unrounded
    "\u0251\u0303": 0xE057,  # nasal open back unrounded
    "\u0254\u0303": 0xE058,  # nasal open-mid back rounded
}

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
