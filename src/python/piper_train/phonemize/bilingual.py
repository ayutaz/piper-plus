"""Bilingual phonemizer for code-switching text (e.g. JA+EN mixed).

Detects language segments via Unicode ranges, delegates to the
appropriate language-specific phonemizer, and returns unified phoneme IDs.
"""

import re

from .base import Phonemizer, ProsodyInfo
from .bilingual_id_map import get_bilingual_id_map
from .registry import get_phonemizer

__all__ = ["BilingualPhonemizer"]

# Regex patterns for language detection
# CJK Unified Ideographs + Hiragana + Katakana + CJK punctuation
_RE_JA_CHAR = re.compile(
    r"[\u3000-\u303F\u3040-\u309F\u30A0-\u30FF"
    r"\u4E00-\u9FFF\uFF00-\uFFEF\u3400-\u4DBF]"
)
# Basic Latin letters (excluding common symbols)
_RE_EN_CHAR = re.compile(r"[A-Za-z]")


def _segment_text(text: str) -> list[tuple[str, str]]:
    """Split text into (language, segment) pairs.

    Uses a simple heuristic: characters in CJK/Hiragana/Katakana ranges
    are tagged as "ja", ASCII Latin characters as "en". Whitespace and
    punctuation are absorbed into the preceding segment.

    Returns:
        List of (lang, text) tuples, e.g.:
        [("ja", "今日は"), ("en", "good morning"), ("ja", "ですね")]
    """
    if not text.strip():
        return []

    segments: list[tuple[str, str]] = []
    current_lang: str | None = None
    current_chars: list[str] = []

    for ch in text:
        if _RE_JA_CHAR.match(ch):
            lang = "ja"
        elif _RE_EN_CHAR.match(ch):
            lang = "en"
        else:
            # Whitespace, digits, punctuation — keep in current segment
            lang = current_lang

        if lang is not None and lang != current_lang and current_lang is not None:
            segments.append((current_lang, "".join(current_chars)))
            current_chars = []

        if lang is not None:
            current_lang = lang
        current_chars.append(ch)

    if current_chars and current_lang is not None:
        segments.append((current_lang, "".join(current_chars)))

    return segments


class BilingualPhonemizer(Phonemizer):
    """Phonemizer that handles code-switching between multiple languages.

    Segments the input text by language, delegates to language-specific
    phonemizers, and concatenates results in a unified phoneme space.

    Parameters
    ----------
    languages : list[str]
        Language codes to support, e.g. ["ja", "en"].
        Each must be registered in the phonemizer registry.
    """

    def __init__(self, languages: list[str]):
        self._languages = languages
        self._id_map: dict[str, list[int]] | None = None
        self._last_eos: str = "$"  # EOS marker from last phonemize call

    def phonemize(self, text: str) -> list[str]:
        """Convert mixed-language text to a list of phoneme tokens."""
        phonemes, _ = self.phonemize_with_prosody(text)
        return phonemes

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """Convert mixed-language text to phoneme tokens with prosody.

        Each language segment is phonemized independently, then
        concatenated. BOS/EOS markers are NOT added here — they are
        handled in post_process_ids.
        """
        segments = _segment_text(text)
        if not segments:
            return [], []

        all_phonemes: list[str] = []
        all_prosody: list[ProsodyInfo | None] = []
        last_eos = "$"  # default EOS marker

        for lang, segment_text in segments:
            phonemizer = get_phonemizer(lang)
            phonemes, prosody_list = phonemizer.phonemize_with_prosody(segment_text)

            # Strip BOS (^) and EOS ($, ?, etc.) from individual segments
            # since we'll add unified BOS/EOS in post_process_ids
            stripped_phonemes: list[str] = []
            stripped_prosody: list[ProsodyInfo | None] = []
            for ph, pr in zip(phonemes, prosody_list, strict=True):
                if ph in ("^", "$", "?"):
                    if ph in ("$", "?"):
                        last_eos = ph  # capture EOS from this segment
                    continue
                stripped_phonemes.append(ph)
                stripped_prosody.append(pr)

            all_phonemes.extend(stripped_phonemes)
            all_prosody.extend(stripped_prosody)

        # Store the EOS from the last segment for post_process_ids
        self._last_eos = last_eos

        return all_phonemes, all_prosody

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        """Return the unified bilingual phoneme ID map."""
        if self._id_map is None:
            self._id_map = get_bilingual_id_map()
        return self._id_map

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding (espeak-ng compatible)."""
        pad_ids = phoneme_id_map.get("_", [0])
        bos_ids = phoneme_id_map.get("^")
        eos_ids = phoneme_id_map.get(self._last_eos, phoneme_id_map.get("$"))

        # Insert pad between every phoneme ID
        padded_ids: list[int] = []
        padded_prosody: list[dict | None] = []
        for phoneme_id, prosody_feature in zip(
            phoneme_ids, prosody_features, strict=True
        ):
            padded_ids.append(phoneme_id)
            padded_prosody.append(prosody_feature)
            padded_ids.extend(pad_ids)
            padded_prosody.extend([None] * len(pad_ids))

        phoneme_ids = padded_ids
        prosody_features = padded_prosody

        # Wrap with BOS/EOS
        if bos_ids:
            phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
            prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
