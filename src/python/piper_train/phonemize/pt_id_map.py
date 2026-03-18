"""Portuguese (Brazilian) phoneme inventory for Piper TTS.

Only phonemes unique to Portuguese that are NOT already present in the
JA + EN + ES inventories are listed here.

Phonemes shared with other inventories (NOT listed here):
  tʃ — voiceless postalveolar affricate: shared with EN (bilingual_id_map.py)
  dʒ — voiced postalveolar affricate: shared with EN (bilingual_id_map.py)
  ʒ  — voiced postalveolar fricative: shared with EN (bilingual_id_map.py)
  ʃ  — voiceless postalveolar fricative: shared with EN (bilingual_id_map.py)
  ɲ  — palatal nasal: shared with ES (es_id_map.py)
  ɾ  — alveolar tap: shared with ES (es_id_map.py)
  ɡ  — voiced velar plosive (IPA U+0261): shared with EN
"""

from .token_mapper import register


__all__ = ["PORTUGUESE_PHONEMES"]

# Phonemes unique to Brazilian Portuguese
# Nasal vowels and PT-specific sounds not covered by JA/EN/ES
PORTUGUESE_PHONEMES: list[str] = [
    # Nasal vowels
    "ã",  # nasalized a (mão, cã)
    "ẽ",  # nasalized e (bem, tem)
    "ĩ",  # nasalized i (sim, fim)
    "õ",  # nasalized o (bom, som)
    "ũ",  # nasalized u (um, algum)
    # BR Portuguese affricates — t/d palatalization before /i/ and unstressed final /e/
    # e.g., "tipo" -> [tʃipu], "dia" -> [dʒia], "gente" -> [ʒẽtʃi]
    # These are shared with EN (bilingual_id_map.py) and get deduplicated IDs,
    # but must be listed here so the PT phonemizer's output is covered.
    "tʃ",  # voiceless postalveolar affricate (ti-, te# -> tʃi)
    "dʒ",  # voiced postalveolar affricate (di-, de# -> dʒi)
    # Palatal lateral approximant — unique to PT among JA/EN/ES inventories
    "ʎ",  # lh digraph (trabalho, filho) - palatal lateral approximant
    # Uvular fricative — shared with FR (fr_id_map.py), not in JA/EN/ES
    "ʁ",  # rr, word-initial r, coda r (carro, rio, mar) - uvular fricative
    # Punctuation not in JA/EN inventories (deduplicated with FR by multilingual_id_map)
    "—",  # em dash (U+2014)
    "–",  # en dash (U+2013)
    "…",  # horizontal ellipsis (U+2026)
]

# Register multi-character tokens to get PUA codepoints
for _token in PORTUGUESE_PHONEMES:
    register(_token)
