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
    "ø",  # eu/œu closed (peu, jeu)
    "œ",  # eu/œu open (peur, fleur)
    "y",  # u (lune, rue) — note: 'y' is used as IPA symbol, distinct from EN 'j'
    # Schwa
    "ə",  # e muet (le, de)
    # Semi-vowel
    "ɥ",  # u semi-vowel (nuit, lui)
]
