"""French phoneme inventory for Piper TTS.

Only phonemes unique to French that are NOT already present in the
JA + EN inventories are listed here.
"""

__all__ = ["FRENCH_PHONEMES"]

# Phonemes unique to French
FRENCH_PHONEMES: list[str] = [
    # Nasal vowels
    "ɛ̃",  # in, ain, ein (vin, pain)
    "ɑ̃",  # an, en, am, em (France, temps)
    "ɔ̃",  # on, om (bon, nom)
    # Front rounded vowels
    "ø",   # eu/œu closed (peu, jeu)
    "œ",   # eu/œu open (peur, fleur); also euille (feuille)
    "y_vowel",  # Close front rounded vowel [y] (lune, tu) — avoids JA glide collision
    # Open vowels
    "ɔ",   # Open o (porte, or, homme)
    # Schwa
    "ə",  # e muet (le, de)
    # Semi-vowel
    "ɥ",  # u semi-vowel (nuit, lui)
    # Consonants
    "ɲ",   # gn digraph (montagne, cognac)
    "ʁ",   # French uvular r
    # Punctuation not in JA/EN inventories
    "—",   # em dash (U+2014)
    "–",   # en dash (U+2013)
    "…",   # horizontal ellipsis (U+2026)
    "«",   # left-pointing double angle quotation mark (U+00AB)
    "»",   # right-pointing double angle quotation mark (U+00BB)
]
