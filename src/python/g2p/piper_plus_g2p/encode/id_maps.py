"""Language-specific phoneme-to-ID maps for Piper TTS.

Built-in ID maps for Japanese (single-language) and the 8-language
multilingual map (JA/EN/ZH/ES/FR/PT/KO/SV).  The multilingual map is
returned for composite language codes (e.g. ``"ja-en-zh-ko-es-fr-pt-sv"``),
``"multilingual"``, or single codes ``"ko"`` / ``"sv"`` that require the
combined symbol set.
"""

from __future__ import annotations

from functools import lru_cache

from .pua import map_token

__all__ = ["get_phoneme_id_map"]


def _assert_single_codepoint_keys(
    phoneme_id_map: dict[str, list[int]], *, language: str
) -> None:
    """Invariant: every key in a generated phoneme_id_map must be exactly 1 codepoint.

    A multi-codepoint key would cause the C++ runtime to reject the config
    (see docs/spec/pua-contract.toml). This is the last line of defence
    after ``map_token(strict=True)`` already raises on unmapped tokens.
    """
    bad_keys = [k for k in phoneme_id_map if len(k) != 1]
    if bad_keys:
        raise AssertionError(
            f"Generated phoneme_id_map for language={language!r} contains "
            f"{len(bad_keys)} multi-codepoint key(s): {bad_keys!r}. "
            "All keys must be single Unicode codepoints (PUA-encoded). "
            "Update pua.json and runtime tables (see docs/spec/pua-contract.toml)."
        )


# -------------------------------------------------------------------------
# Japanese phoneme inventory (identical ordering to piper_train)
# -------------------------------------------------------------------------
_SPECIAL_TOKENS: list[str] = [
    "_",  # short pause (pad, id=0)
    "^",  # BOS
    "$",  # EOS (declarative)
    "?",  # EOS (interrogative - generic)
    "?!",  # EOS (emphatic question)
    "?.",  # EOS (neutral/rhetorical question)
    "?~",  # EOS (tag question)
    "#",  # accent phrase boundary
    "[",  # rising pitch mark
    "]",  # falling pitch mark
]

_JAPANESE_PHONEMES: list[str] = [
    # voiced vowels
    "a",
    "i",
    "u",
    "e",
    "o",
    # unvoiced vowels (uppercase)
    "A",
    "I",
    "U",
    "E",
    "O",
    "a:",
    "i:",
    "u:",
    "e:",
    "o:",
    # special consonant-centric phonemes
    "N",
    "N_m",
    "N_n",
    "N_ng",
    "N_uvular",
    "cl",
    "q",
    # plosives + voiced counterparts
    "k",
    "ky",
    "kw",
    "g",
    "gy",
    "gw",
    "t",
    "ty",
    "d",
    "dy",
    "p",
    "py",
    "b",
    "by",
    # affricates, fricatives, etc.
    "ch",
    "ts",
    "s",
    "sh",
    "z",
    "j",
    "zy",
    "f",
    "h",
    "hy",
    "v",
    # nasals / approximants
    "n",
    "ny",
    "m",
    "my",
    "r",
    "ry",
    "w",
    "y",
]


def _build_japanese_id_map() -> dict[str, list[int]]:
    """Build the JA phoneme_id_map with PUA-converted keys.

    The ordering is identical to ``piper_train.phonemize.jp_id_map``:
    each token is passed through ``map_token()`` so that multi-character
    tokens become single PUA characters, and the resulting character is
    used as the dictionary key.  This ensures compatibility with models
    trained by piper_train.
    """
    # strict=True at build time: any multi-codepoint inventory token without a
    # PUA mapping is a CI-fatal bug (see docs/spec/pua-contract.toml).
    inventory = _SPECIAL_TOKENS + _JAPANESE_PHONEMES
    symbols = [map_token(s, strict=True) for s in inventory]
    result = {symbol: [idx] for idx, symbol in enumerate(symbols)}
    _assert_single_codepoint_keys(result, language="ja")
    return result


# -------------------------------------------------------------------------
# Multilingual (8-language) phoneme inventory
# Combined symbol set matching piper_train's multilingual_id_map output
# for the canonical language set: ja-en-zh-es-fr-pt-ko-sv
# -------------------------------------------------------------------------
_ENGLISH_PHONEMES: list[str] = [
    "ɪ",
    "ʊ",
    "ɛ",
    "ɔ",
    "æ",
    "ɑ",
    "ʌ",
    "ə",
    "ɜ",
    "ɹ",
    "ɝ",
    "ɫ",
    "ð",
    "θ",
    "ŋ",
    "ʃ",
    "ʒ",
    "dʒ",
    "tʃ",
    "p",
    "b",
    "t",
    "d",
    "f",
    "v",
    "s",
    "z",
    "h",
    "l",
    "m",
    "n",
    "r",
    "w",
    "j",
    "g",
    "ɡ",
    "x",
    "ˈ",
    "ˌ",
    "ː",
    "i",
    "u",
    "e",
    "o",
    "aɪ",
    "aʊ",
    "eɪ",
    "oʊ",
    "ɔɪ",
]

_CHINESE_PHONEMES: list[str] = [
    # Tone markers
    "tone1",
    "tone2",
    "tone3",
    "tone4",
    "tone5",
    # Vowels / finals (IPA output from ChinesePhonemizer)
    "an",
    "aŋ",
    "aɪ",
    "aʊ",
    "eɪ",
    "ia",
    "iaŋ",
    "iaʊ",
    "in",
    "iou",
    "iuŋ",
    "iŋ",
    "iɛ",
    "iɛn",
    "oʊ",
    "ua",
    "uan",
    "uaŋ",
    "uaɪ",
    "ueɪ",
    "uo",
    "uŋ",
    "uən",
    "y_vowel",
    "yn",
    "yɛ",
    "yɛn",
    "ən",
    "əŋ",
    "ɻ̩",
    # Consonants (IPA, single-char not shared with JA/EN)
    "ɕ",
    "ɚ",
    "ɤ",
    "ɨ",
    "ɻ",
    "ʂ",
    # Aspirated consonants
    "kʰ",
    "pʰ",
    "tʰ",
    # Affricates
    "ts",
    "tsʰ",
    "tɕ",
    "tɕʰ",
    "tʂ",
    "tʂʰ",
]

_SPANISH_PHONEMES: list[str] = [
    "rr",
    "ɲ",
    "ʎ",
    "β",
    "ɣ",
    "tʃ",
    "x",
]

_FRENCH_PHONEMES: list[str] = [
    "ʁ",
    "ɲ",
    "ɑ̃",
    "ɔ̃",
    "ɛ̃",
    "œ̃",
    "y",
    "ø",
    "œ",
    "y_vowel",
]

_PORTUGUESE_PHONEMES: list[str] = [
    "ɲ",
    "ʎ",
    "ʃ",
    "ʒ",
    "ɐ",
    "ɐ̃",
    "ẽ",
    "ĩ",
    "õ",
    "ũ",
]

_KOREAN_PHONEMES: list[str] = [
    # Aspirated consonants
    "pʰ",
    "tʰ",
    "kʰ",
    # Tense consonants (fortis / 경음)
    "p͈",
    "t͈",
    "k͈",
    "s͈",
    # Affricates
    "tɕ",
    "tɕʰ",
    "t͈ɕ",
    # Unreleased finals (내파음)
    "k̚",
    "t̚",
    "p̚",
    # Vowels unique to Korean
    "ɯ",  # close back unrounded vowel (ㅡ)
    # Consonants / glides
    "ɾ",  # alveolar flap (ㄹ initial)
    "ɰ",  # velar approximant (ㅢ first element)
]

_SWEDISH_PHONEMES: list[str] = [
    # Retroflex consonants
    "ɖ",  # retroflex voiced plosive (rd)
    "ʈ",  # retroflex voiceless plosive (rt)
    "ɳ",  # retroflex nasal (rn)
    "ɭ",  # retroflex lateral (rl)
    # Special fricatives
    "ɧ",  # sj-sound (voiceless dorso-palatal/velar fricative)
    # Vowels unique to Swedish (single codepoint)
    "ɵ",  # close-mid central rounded
    "ʏ",  # near-close front rounded
    "œ",  # open-mid front rounded
    "ɑ",  # open back unrounded
    "ø",  # close-mid front rounded
    # Long vowels (multi-codepoint -> PUA U+E059-E061)
    "iː",
    "yː",
    "eː",
    "ɛː",
    "øː",
    "ɑː",
    "oː",
    "uː",
    "ʉː",
]


def _build_multilingual_id_map() -> dict[str, list[int]]:
    """Build the combined multilingual phoneme_id_map.

    Symbol ordering: special tokens -> JA -> EN -> ZH -> ES -> FR -> PT -> KO -> SV.
    Shared symbols deduplicated (first occurrence wins).
    """
    all_inventories = [
        _JAPANESE_PHONEMES,
        _ENGLISH_PHONEMES,
        _CHINESE_PHONEMES,
        _SPANISH_PHONEMES,
        _FRENCH_PHONEMES,
        _PORTUGUESE_PHONEMES,
        _KOREAN_PHONEMES,
        _SWEDISH_PHONEMES,
    ]
    symbols: list[str] = []
    seen: set[str] = set()

    # strict=True at build time: any unmapped multi-codepoint token is a fatal
    # bug here (would produce an unloadable config for C++ runtime).
    for s in _SPECIAL_TOKENS:
        mapped = map_token(s, strict=True)
        if mapped not in seen:
            symbols.append(mapped)
            seen.add(mapped)

    for inventory in all_inventories:
        for s in inventory:
            mapped = map_token(s, strict=True)
            if mapped not in seen:
                symbols.append(mapped)
                seen.add(mapped)

    result = {symbol: [idx] for idx, symbol in enumerate(symbols)}
    _assert_single_codepoint_keys(result, language="multilingual")
    return result


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
        If *language* is not a recognized code.  Supported single-language
        codes: ``"ja"``, ``"ko"``, ``"sv"``.  Composite codes (e.g.
        ``"ja-en-zh-ko-es-fr-pt-sv"``) and ``"multilingual"`` also work.
    """
    if language == "ja":
        return _build_japanese_id_map()

    # Single-language codes that use the multilingual map
    # (ko and sv share symbols with other languages via the unified map)
    if language in ("ko", "sv"):
        return _build_multilingual_id_map()

    # Multilingual composite code (e.g. "ja-en-zh-es-fr-pt",
    # "ja-en-zh-ko-es-fr-pt-sv")
    if "-" in language or language == "multilingual":
        return _build_multilingual_id_map()

    raise ValueError(
        f"No built-in phoneme_id_map for single language {language!r}. "
        "Use get_phoneme_id_map('multilingual') for the combined map, "
        "or load phoneme_id_map from the model's config.json."
    )
