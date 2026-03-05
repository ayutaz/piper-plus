"""Portuguese (Brazilian) phoneme inventory for Piper TTS.

Only phonemes unique to Portuguese that are NOT already present in the
JA + EN + ES inventories are listed here.
"""

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
]
