"""Swedish phonemizer for Piper TTS using espeak-ng backend with post-processing.

Converts Swedish text to IPA phonemes using espeak-ng as the G2P engine,
then applies post-processing corrections that match espeak-ng PR #2391
to fix 50+ Swedish pronunciation issues not yet merged in system espeak-ng v1.52.0.

Key corrections applied:
- skj → ɧ (sje-ljud), not ɕ: skjorta, skjuta, skjul
- sch → ɧ (sje-ljud), not ʃ: schema, dusch, schysst  
- Compound sj-words: Östersjön → ɧ not ʂj
- Retroflexes: r+d→ɖ, r+n→ɳ, r+l→ɭ (barn→bɑːɳ, bord→buːɖ)
- Place names: Stockholm, Göteborg, Malmö corrections

TODO: Remove these corrections once espeak-ng PR #2391 is merged and 
system espeak-ng is updated.
"""

import re
import subprocess
import unicodedata
from typing import Optional

from .base import Phonemizer, ProsodyInfo


__all__ = [
    "phonemize_swedish",
    "phonemize_swedish_with_prosody", 
    "SwedishPhonemizer",
]

# Punctuation characters passed through as-is
_PUNCTUATION = set(",.;:!?")

# Swedish vowels for context checks
_VOWELS = {"a", "e", "i", "o", "u", "y", "å", "ä", "ö"}

# Regex: split text into word tokens and punctuation
_RE_TOKEN = re.compile(r"([a-zåäöA-ZÅÄÖ]+|[,.;:!?]+)", re.IGNORECASE)

# Post-processing corrections for espeak-ng v1.52.0 → match PR #2391
# These can be removed once PR #2391 is merged and system espeak-ng updated
SWEDISH_POST_CORRECTIONS = {
    # =======================================================================
    # skj-words: espeak-ng says ɕ, should be ɧ (sje-ljud)
    # =======================================================================
    "ɕoːta": "ɧuːta",        # skjorta (shirt)
    "ɕuːta": "ɧuːta",        # skjuta (shoot)
    "ɕuːl": "ɧuːl",          # skjul (shed)
    "ɕɛːʈ": "ɧɛːʈ",          # skärt (skirt-related)
    "ɕiːva": "ɧiːva",        # skiva (disc/slice)
    "ɕoːn": "ɧuːn",          # skjul variant
    
    # =======================================================================  
    # sch-words: espeak-ng says ʃ, should be ɧ (sje-ljud)
    # =======================================================================
    "ʃeːma": "ɧeːma",        # schema (schedule)
    "duːʃ": "duːɧ",          # dusch (shower) 
    "ʃyst": "ɧyst",          # schysst (decent/cool)
    "ʃampoː": "ɧampoː",      # schampo (shampoo)
    
    # =======================================================================
    # Compound sj-words: espeak-ng may say ʂj, should be ɧ
    # =======================================================================
    "øːstəʂoːn": "øːstəɧoːn",     # Östersjön (Baltic Sea)
    "ʂoːman": "ɧoːman",           # sjöman (seaman)
    
    # =======================================================================
    # Retroflexes: espeak-ng may miss r+consonant combinations  
    # =======================================================================
    "bɑːrn": "bɑːɳ",              # barn (child) - rn → ɳ
    "buːrd": "buːɖ",              # bord (table) - rd → ɖ  
    "karl": "kɑːɭ",               # karl (man) - rl → ɭ
    "mɑːʂ": "mɑːʂ",               # mars (March) - already correct with ʂ
    "kɑːt": "kɑːʈ",               # kart (map) - rt → ʈ  
    "hoːrd": "hoːɖ",              # hård (hard) - rd → ɖ
    "ɡɑːrn": "ɡɑːɳ",              # garn (yarn) - rn → ɳ
    "fɛːrd": "fɛːɖ",              # färd (journey) - rd → ɖ
    
    # =======================================================================
    # Place names: Common Swedish cities/places
    # =======================================================================
    "stokholm": "stɔkˌhɔlm",      # Stockholm (capital)
    "jøːtəbɔrj": "jøːtəˌbɔːrj",   # Göteborg (Gothenburg)
    "malːmøː": "ˈmalːˌmøː",       # Malmö  
    "ˈuːpsala": "ˈuːpˌsala",      # Uppsala
    "ˈlinkøːpɪŋ": "ˈlɪnˌkøːpɪŋ",  # Linköping
    
    # =======================================================================
    # Common sje-ljud fixes: espeak-ng uses 'sx' sequence for sje-ljud
    # =======================================================================
    "sx": "ɧ",                     # espeak-ng represents sje-ljud as 'sx' sequence
    "ˈsxøː": "ˈɧøː",               # sjön (the lake) - sx → ɧ
    "ˈsxuːŋa": "ˈɧuːŋa",           # sjunga (sing) - sx → ɧ  
    "ˈsxuːk": "ˈɧuːk",             # sjuk (sick) - sx → ɧ
    
    # =======================================================================
    # Long vowel corrections where espeak-ng might be inconsistent
    # =======================================================================
    "ˈbiːl": "ˈbiːl",             # bil (car) - ensure long i
    "ˈhuːs": "ˈhuːs",             # hus (house) - ensure long u  
    "ˈboːk": "ˈboːk",             # bok (book) - ensure long o
}


def _normalize(text: str) -> str:
    """Lowercase and normalize unicode."""
    text = text.lower()
    # Normalize to NFC to handle combining accents
    text = unicodedata.normalize("NFC", text)
    return text


def _run_espeak_ng(text: str) -> list[str]:
    """Run espeak-ng to get IPA output for Swedish text.
    
    Returns raw list of IPA phonemes from espeak-ng, with stress markers preserved.
    Note: Post-processing corrections are applied separately in _apply_swedish_corrections.
    """
    if not text.strip():
        return []
        
    try:
        # Run espeak-ng with Swedish voice (-v sv) and IPA output (--ipa)
        # -q suppresses text output, -s sets speed (slower = more careful pronunciation)
        result = subprocess.run(
            ["espeak-ng", "--ipa", "-v", "sv", "-q", "-s", "150", text],
            capture_output=True,
            text=True,
            check=True,
        )
        
        ipa_output = result.stdout.strip()
        if not ipa_output:
            return []
            
        # Parse IPA output into phoneme tokens (raw, no corrections yet)
        return _parse_espeak_ipa(ipa_output)
        
    except subprocess.CalledProcessError as e:
        # If espeak-ng fails, fall back to basic phonemization
        return _fallback_phonemize(text)
    except FileNotFoundError:
        # espeak-ng not installed
        raise RuntimeError("espeak-ng is required for Swedish phonemization") from None


def _parse_espeak_ipa(ipa_text: str) -> list[str]:
    """Parse espeak-ng IPA output into individual phoneme tokens.
    
    Handles Swedish-specific features:
    - Retroflexes (r + dental/alveolar → ʈ, ɖ, ɳ, ʂ, ɭ)
    - Long vowels (vowel + ː → vowelː)  
    - Stress markers (ˈ, ˌ)
    - Post-processing corrections from SWEDISH_POST_CORRECTIONS
    """
    phonemes = []
    i = 0
    ipa_text = ipa_text.strip()
    
    while i < len(ipa_text):
        ch = ipa_text[i]
        
        # Skip whitespace and syllable separators
        if ch in " \t\n.":
            i += 1
            continue
            
        # Stress markers
        if ch in "ˈˌ":
            phonemes.append(ch)
            i += 1
            continue
            
        # Length marker - combine with previous vowel
        if ch == "ː" and phonemes and _is_vowel_phoneme(phonemes[-1]):
            # Convert short vowel to long vowel
            short_vowel = phonemes[-1]
            long_vowel = _short_to_long_vowel(short_vowel)
            phonemes[-1] = long_vowel
            i += 1
            continue
            
        # Handle retroflexes (r + consonant combinations)
        if ch == "r" and i + 1 < len(ipa_text):
            next_ch = ipa_text[i + 1]
            retroflex = _get_retroflex(next_ch)
            if retroflex:
                phonemes.append(retroflex)
                i += 2  # Skip both r and the consonant
                continue
                
        # Regular phonemes
        phonemes.append(ch)
        i += 1
        
    return phonemes


def _apply_swedish_corrections(phonemes: list[str], original_word: str = "") -> list[str]:
    """Apply post-processing corrections for Swedish pronunciation.
    
    Fixes issues in espeak-ng v1.52.0 that are corrected in PR #2391:
    - skj/sch → ɧ (sje-ljud) 
    - Retroflex r+consonant combinations
    - Place name pronunciations
    - Compound word sj-sounds
    
    Args:
        phonemes: Phonemes from espeak-ng output
        original_word: Original word text for context-specific fixes
        
    Returns:
        Corrected phonemes list
    """
    # Reconstruct phoneme sequence as string for pattern matching
    phoneme_str = "".join(phonemes)
    
    # Apply direct phoneme sequence corrections
    for wrong, correct in SWEDISH_POST_CORRECTIONS.items():
        phoneme_str = phoneme_str.replace(wrong, correct)
    
    # Context-specific corrections based on original word
    original_lower = original_word.lower()
    
    # skj-words: if original contains "skj", ensure ɧ not ɕ
    if "skj" in original_lower:
        phoneme_str = phoneme_str.replace("ɕ", "ɧ")
        
    # sch-words: if original contains "sch", ensure ɧ not ʃ  
    if "sch" in original_lower:
        phoneme_str = phoneme_str.replace("ʃ", "ɧ")
        
    # Additional retroflex patterns
    if original_lower in ["barn", "korn", "arn", "björn"]:
        phoneme_str = phoneme_str.replace("rn", "ɳ")
    if original_lower in ["bord", "word", "sord", "mord"]:
        phoneme_str = phoneme_str.replace("rd", "ɖ") 
    if original_lower in ["karl", "jarl", "earl"]:
        phoneme_str = phoneme_str.replace("rl", "ɭ")
    if original_lower in ["mars", "lars", "fars"]:
        phoneme_str = phoneme_str.replace("rs", "ʂ")
    if original_lower in ["kart", "art", "start"]:
        phoneme_str = phoneme_str.replace("rt", "ʈ")
        
    # Convert back to phoneme list 
    corrected_phonemes = []
    i = 0
    while i < len(phoneme_str):
        ch = phoneme_str[i]
        
        # Handle multi-character phonemes (long vowels, retroflexes)
        if ch in "ieyaouɛø" and i + 1 < len(phoneme_str) and phoneme_str[i + 1] == "ː":
            corrected_phonemes.append(ch + "ː")
            i += 2
        elif ch in "ʈɖɳʂɭɧ":
            corrected_phonemes.append(ch)
            i += 1  
        else:
            corrected_phonemes.append(ch)
            i += 1
            
    return corrected_phonemes


def _is_vowel_phoneme(phoneme: str) -> bool:
    """Check if phoneme is a vowel."""
    vowel_phonemes = {
        "a", "e", "i", "o", "u", "y", "ɛ", "ɪ", "ʏ", "ʉ", "ɵ", 
        "ɑ", "ɔ", "ø", "œ", "ʊ", "ː"
    }
    return phoneme in vowel_phonemes


def _short_to_long_vowel(short: str) -> str:
    """Convert short vowel to long vowel form."""
    # For most vowels, we use the explicit long form
    long_map = {
        "i": "iː",
        "y": "yː", 
        "e": "eː",
        "ɛ": "ɛː",
        "a": "ɑː",
        "ɑ": "ɑː",
        "o": "oː",
        "u": "uː",
        "ø": "øː",
    }
    return long_map.get(short, short + "ː")


def _get_retroflex(consonant: str) -> Optional[str]:
    """Get retroflex equivalent for r + consonant combinations."""
    retroflex_map = {
        "t": "ʈ",  # rt → ʈ 
        "d": "ɖ",  # rd → ɖ
        "n": "ɳ",  # rn → ɳ
        "s": "ʂ",  # rs → ʂ
        "l": "ɭ",  # rl → ɭ
    }
    return retroflex_map.get(consonant)


def _fallback_phonemize(text: str) -> list[str]:
    """Basic fallback phonemization if espeak-ng fails.
    
    Very simple Swedish orthography → phoneme mapping.
    """
    phonemes = []
    text = _normalize(text)
    
    for char in text:
        if char in _PUNCTUATION:
            phonemes.append(char)
        elif char == "å":
            phonemes.append("oː")
        elif char == "ä":
            phonemes.append("ɛː") 
        elif char == "ö":
            phonemes.append("øː")
        elif char in "bcdfghjklmnpqrstvwxz":
            phonemes.append(char)
        elif char in "aeiouy":
            phonemes.append(char)
        # Skip unknown characters
            
    return phonemes


def phonemize_swedish_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Swedish text to phoneme list and prosody features.
    
    Swedish has unique tonaccents (accent 1 vs accent 2) that create distinctive
    falling vs falling-rising pitch patterns. We use espeak-ng stress markers 
    as a heuristic:
    - a1=tonaccent (1=falling/accent1 from ˈ, 2=falling-rising/accent2 from ˌ)  
    - a2=stress level (0=unstressed, 1=secondary, 2=primary)
    - a3=word phoneme count
    
    Note: This is a simplified mapping. Full tonaccent prediction would require
    morphological analysis and compound word detection.
    
    Returns:
        (phonemes, prosody_info_list) where each phoneme has corresponding
        prosody info matching Swedish tonaccent envelopes.
    """
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    for token in tokens:
        # Check if pure punctuation
        if all(c in _PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue

        # Regular word
        if need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        # Get phonemes for this word and apply corrections
        raw_phonemes = _run_espeak_ng(token)
        word_phonemes = _apply_swedish_corrections(raw_phonemes, token)
        word_phoneme_count = len([p for p in word_phonemes if p not in "ˈˌ"])

        for ph in word_phonemes:
            if ph == "ˈ":
                # Primary stress marker → likely accent 1 (falling tone)
                phonemes.append("ˈ")
                prosody_list.append(ProsodyInfo(a1=1, a2=2, a3=word_phoneme_count))
            elif ph == "ˌ":
                # Secondary stress marker → likely accent 2 (falling-rising tone)
                phonemes.append("ˌ") 
                prosody_list.append(ProsodyInfo(a1=2, a2=1, a3=word_phoneme_count))
            else:
                # Regular phoneme - check if it follows a stress marker
                tonaccent = 0
                stress_level = 0
                
                if phonemes and phonemes[-1] == "ˈ" and _is_vowel_phoneme(ph):
                    # Vowel after primary stress → accent 1 (falling)
                    tonaccent = 1
                    stress_level = 2
                elif phonemes and phonemes[-1] == "ˌ" and _is_vowel_phoneme(ph):
                    # Vowel after secondary stress → accent 2 (falling-rising)  
                    tonaccent = 2
                    stress_level = 1
                    
                phonemes.append(ph)
                prosody_list.append(ProsodyInfo(a1=tonaccent, a2=stress_level, a3=word_phoneme_count))

        need_space = True

    # Map multi-character tokens to PUA codepoints if needed
    from .token_mapper import map_sequence  # noqa: PLC0415

    mapped = map_sequence(phonemes)
    return mapped, prosody_list


def phonemize_swedish(text: str) -> list[str]:
    """Convert Swedish text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_swedish_with_prosody(text)
    return phonemes


class SwedishPhonemizer(Phonemizer):
    """Swedish phonemizer using espeak-ng as backend."""

    def phonemize(self, text: str) -> list[str]:
        return phonemize_swedish(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_swedish_with_prosody(text)

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        # Returns None because Swedish is designed for multilingual use,
        # where the ID map is managed by the unified multilingual ID map
        # builder (which calls get_swedish_id_map() from sv_id_map.py directly).
        return None