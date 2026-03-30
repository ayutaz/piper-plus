"""Swedish phoneme inventory for Piper TTS.

Only phonemes NOT already present in Japanese (jp_id_map.py), English
(bilingual_id_map.py), Spanish (es_id_map.py), or French (fr_id_map.py) 
are listed here. Shared symbols are deduplicated automatically when 
building the unified ID map.
"""

__all__ = ["SWEDISH_PHONEMES"]

# -----------------------------------------------------------------------
# Swedish-only phonemes (IPA symbols not in existing language inventories)
# -----------------------------------------------------------------------
# Shared with JA/EN/ES/FR (NOT listed here):
#   a, e, i, o, u, ɛ       — vowels (JA+EN+FR)  
#   b, d, f, k, l, m, n,   — consonants (JA+EN)
#   p, s, t, w, j, v, z
#   ɡ, ˈ, ˌ, ː             — EN
#   x                      — Spanish jota
#   ɲ                      — Spanish/French palatal nasal (ñ/gn)
#   ʁ                      — French uvular r
#
# Swedish-ONLY phonemes that need new IDs:
SWEDISH_PHONEMES: list[str] = [
    # --- Vowels ---
    # Short vowels
    "ɪ",       # kort i (bill)
    "ʏ",       # kort y (bygg) 
    "ʉ",       # kort ʉ (hund) — unique to Swedish!
    "ɵ",       # kort ɵ (bund) — unique to Swedish!
    "ɛː",      # lång ɛ (bär)
    "øː",      # lång ø (höst)
    "œ",       # kort œ (hörn)
    "ɑː",      # lång a (far)
    "ɔ",       # kort o (boll)
    "oː",      # lång o (bok)
    "uː",      # lång u (ful)
    "ʊ",       # kort u (full)
    "yː",      # lång y (by)
    "iː",      # lång i (bil)
    "eː",      # lång e (ben)
    
    # --- Consonanter ---
    "ɕ",       # tjock-ljud (kjol, tjugo) — alveolopalatal frikativa
    "ɧ",       # sje-ljud (sjö, sju) — UNIKT för svenska!
    "r",       # dental/alveolar tremulant
    "ŋ",       # velar nasal (kung)
    
    # --- Retroflexer (r + dental/alveolar) ---
    "ʈ",       # retroflex t (kart) 
    "ɖ",       # retroflex d (bord)
    "ɳ",       # retroflex n (barn)
    "ʂ",       # retroflex s (mars)
    "ɭ",       # retroflex l (karl)
]