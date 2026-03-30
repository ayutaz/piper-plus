"""Rule-based Swedish G2P (grapheme-to-phoneme) module.

Converts Swedish text to IPA phonemes using orthographic rules.
No external dependencies required — implements Swedish phonology rules
including vowel length, retroflexes, sje-ljud, and tonaccents.

Features:
- Rule-based vowel length determination  
- Swedish-specific phonemes: ɧ (sje-ljud), ɕ (tje-ljud), ʉ/ɵ (central vowels)
- Retroflex consonants (r + dental/alveolar)
- Tonaccent prosody (accent 1 vs accent 2)
- Complete Swedish orthographic coverage
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Union

from .base import Phonemizer, ProsodyInfo


__all__ = [
    "phonemize_swedish",
    "phonemize_swedish_with_prosody", 
    "SwedishPhonemizer",
]

# Punctuation characters passed through as-is
_PUNCTUATION = set(",.;:!?")

# Swedish vowel and consonant letters
_VOWELS = set("aeiouyåäö")
_CONSONANTS = set("bcdfghjklmnpqrstvwxz")

# Front vowels that trigger palatalization of k/g  
_FRONT_VOWELS = set("eiwyäö")

# Regex: split text into word tokens and punctuation
_RE_TOKEN = re.compile(r"([a-zåäöA-ZÅÄÖ]+|[,.;:!?]+)", re.IGNORECASE)

# Common unstressed function words
_UNSTRESSED_FUNCTION_WORDS = frozenset({
    "och", "att", "det", "är", "på", "av", "för", "till", "med", "som",
    "den", "de", "en", "ett", "har", "var", "vid", "om", "nu", "då",
    "här", "där", "när", "vad", "hur", "kan", "ska", "vil", "må",
    "han", "hon", "den", "dem", "sin", "sitt", "sina", "min", "mitt", "mina",
})

# Words with accent 2 (falling-rising tonaccent)
_ACCENT_2_WORDS = frozenset({
    "pojke", "flicka", "kärlek", "vänskap", "framtid", "kunskap",
    "Sverige", "Europa", "Amerika", "regering", "demokrati",
    "pojkar", "flickor", "vänner", "frågor", "saker", "människor", 
    "Stockholm", "Göteborg", "Malmö", "Uppsala", "Linköping",
    "julklapp", "sommarsemester", "körkort", "sjukhus", "regnbåge",
})

# Exception words with irregular pronunciation
_EXCEPTION_WORDS = {
    "hej": ["h", "ɛ", "j"],
    "och": ["ɔ", "k"],
    "jag": ["j", "ɑː"],
    "det": ["d", "eː"],
    "är": ["ɛː"],
    "har": ["h", "ɑː", "r"],
    "inte": ["ɪ", "n", "t", "ɛ"],
    "var": ["v", "ɑː", "r"],
    "hur": ["h", "ʉː", "r"],
    "vad": ["v", "ɑː", "d"],
}


def _normalize(text: str) -> str:
    """Lowercase and normalize unicode."""
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return text


def _determine_vowel_length(vowel: str, word: str, pos: int) -> str:
    """Determine Swedish vowel length based on syllable structure.
    
    Swedish vowel length rules:
    1. Before SINGLE consonant (open syllable) = LONG
    2. Before consonant CLUSTER or double consonant = SHORT  
    3. BUT: retroflex combinations (rn, rd, rt, rl, rs) count as ONE consonant!
    4. ng always blocks vowel length (u before ng = short [ɵ])
    5. Exception: closed syllables like "hej" = short vowel
    """
    # Get consonants after this vowel
    after_vowel = word[pos + 1:]
    
    if not after_vowel:
        # Word-final vowel: typically long in open syllables
        return _vowel_long_form(vowel)
    
    # Check for immediate double consonants or ck (forces short)
    if len(after_vowel) >= 2:
        first_two = after_vowel[:2]
        if first_two == "ck" or (first_two[0] == first_two[1] and first_two[0] in _CONSONANTS):
            return _vowel_short_form(vowel)
    
    # Analyze consonant structure to determine length
    consonant_sounds = 0
    next_vowel_found = False
    i = 0
    
    while i < len(after_vowel):
        ch = after_vowel[i]
        if ch in _VOWELS:
            next_vowel_found = True
            break
        if ch not in _CONSONANTS:
            break
            
        # Multi-character consonants (longest first)
        if i + 2 < len(after_vowel):
            trigraph = after_vowel[i:i+3]
            if trigraph in ("skj", "stj", "sch"):
                consonant_sounds += 1
                i += 3
                continue
        
        if i + 1 < len(after_vowel):
            digraph = after_vowel[i:i+2]
            
            # ng always makes preceding vowel short (special rule)
            if digraph == "ng":
                return _vowel_short_form(vowel)
            
            # Retroflexes count as SINGLE sounds for vowel length
            if digraph in ("rn", "rd", "rt", "rs", "rl"):
                consonant_sounds += 1
                i += 2
                continue
            
            # Other single-sound digraphs
            elif digraph in ("sj", "tj", "kj", "ch", "ck"):
                consonant_sounds += 1
                i += 2
                continue
        
        # Single consonant
        consonant_sounds += 1
        i += 1
    
    # Special case: closed syllables without following vowel
    # But NOT when the consonant is a single retroflex (counts as one sound)
    if not next_vowel_found:
        # Exception: if the consonant after vowel is a single retroflex, still make vowel long
        if consonant_sounds == 1 and len(after_vowel) >= 2 and after_vowel[:2] in ("rn", "rd", "rt", "rs", "rl"):
            return _vowel_long_form(vowel)
        else:
            return _vowel_short_form(vowel)
    
    # Main rule: single consonant before vowel = long, multiple = short
    if consonant_sounds == 1:
        return _vowel_long_form(vowel)
    else:
        return _vowel_short_form(vowel)


def _vowel_long_form(vowel: str) -> str:
    """Get long form of Swedish vowel."""
    long_map = {
        "a": "ɑː", "e": "eː", "i": "iː", "o": "uː", "u": "ʉː",
        "y": "yː", "å": "oː", "ä": "ɛː", "ö": "øː"
    }
    return long_map.get(vowel, vowel + "ː")


def _vowel_short_form(vowel: str) -> str:
    """Get short form of Swedish vowel.""" 
    short_map = {
        "a": "a", "e": "ɛ", "i": "ɪ", "o": "ɔ", "u": "ɵ",
        "y": "ʏ", "å": "ɔ", "ä": "ɛ", "ö": "œ"
    }
    return short_map.get(vowel, vowel)


def _get_unstressed_vowel(vowel: str, context: str = "") -> str:
    """Get unstressed/reduced form of Swedish vowel (for endings like -en, -er, -el)."""
    # Unstressed 'e' in common endings becomes schwa-like [ɛ] or [e]
    if vowel == "e" and context in ("en", "er", "el", "et"):
        return "e"  # Reduced, not full [ɛ]
    return _vowel_short_form(vowel)


def _convert_word(word: str) -> List[str]:
    """Convert Swedish word to phonemes."""
    # Check exception words first
    if word in _EXCEPTION_WORDS:
        return _EXCEPTION_WORDS[word].copy()
    
    phonemes = []
    n = len(word)
    i = 0
    
    while i < n:
        ch = word[i]
        
        # Multi-character sequences (longest first)
        
        # Three-letter sje-ljud
        if i + 2 < n:
            trigraph = word[i:i+3]
            if trigraph in ("skj", "stj", "sch"):
                phonemes.append("ɧ")
                i += 3
                continue
        
        # Two-letter sequences
        if i + 1 < n:
            digraph = word[i:i+2]
            ch2 = word[i+1]
            
            # ch -> tje-ljud (in loanwords like "check")
            if digraph == "ch":
                phonemes.append("ɕ")
                i += 2
                continue
            
            # Initial silent consonants + j  
            elif i == 0 and digraph in ("dj", "gj", "hj", "lj"):
                phonemes.append("j")
                i += 2
                continue
                
            # sje-ljud
            elif digraph == "sj":
                phonemes.append("ɧ")
                i += 2
                continue
                
            # sk before front vowels = sje-ljud
            elif digraph == "sk" and i + 2 < n and word[i+2] in _FRONT_VOWELS:
                phonemes.append("ɧ")
                i += 2
                continue
                
            # tje-ljud
            elif digraph in ("tj", "kj"):
                phonemes.append("ɕ")
                i += 2
                continue
                
            # Nasals
            elif digraph == "ng":
                phonemes.append("ŋ")
                i += 2
                continue
            elif digraph == "nk":
                phonemes.append("ŋ")
                phonemes.append("k") 
                i += 2
                continue
                
            # ck -> k
            elif digraph == "ck":
                phonemes.append("k")
                i += 2
                continue
                
            # Retroflexes
            elif digraph in ("rn", "rd", "rt", "rs", "rl"):
                retroflex_map = {"rn": "ɳ", "rd": "ɖ", "rt": "ʈ", "rs": "ʂ", "rl": "ɭ"}
                phonemes.append(retroflex_map[digraph])
                i += 2
                continue
                
            # Double consonants -> single phoneme
            elif ch == ch2 and ch in _CONSONANTS:
                phonemes.append(ch)
                i += 2
                continue
        
        # Vowels with length determination
        if ch in _VOWELS:
            # Check if this is an unstressed ending
            if i >= n - 2 and word[i:] in ("en", "er", "el", "et"):
                vowel_phoneme = _get_unstressed_vowel(ch, word[i:])
            else:
                vowel_phoneme = _determine_vowel_length(ch, word, i)
            phonemes.append(vowel_phoneme)
            i += 1
            continue
        
        # Consonants with context rules
        elif ch == "k":
            # k before front vowels -> ɕ
            if i + 1 < n and word[i+1] in _FRONT_VOWELS:
                phonemes.append("ɕ")
            else:
                phonemes.append("k")
            i += 1
            continue
            
        elif ch == "g":
            # g before front vowels -> j
            if i + 1 < n and word[i+1] in _FRONT_VOWELS:
                phonemes.append("j")
            else:
                phonemes.append("ɡ")
            i += 1
            continue
            
        elif ch == "c":
            if i + 1 < n and word[i+1] in "eiy":
                phonemes.append("s")
            else:
                phonemes.append("k")
            i += 1
            continue
        
        # Simple consonant mappings
        elif ch in "bcdfhjlmnprstv":
            phonemes.append(ch)
            i += 1
            continue
            
        elif ch == "w":
            phonemes.append("v")
            i += 1
            continue
            
        elif ch == "x":
            phonemes.extend(["k", "s"])
            i += 1
            continue
            
        elif ch == "z":
            phonemes.append("s")
            i += 1
            continue
            
        elif ch == "q":
            phonemes.append("k")
            i += 1
            continue
        
        else:
            # Unknown character, skip
            i += 1
    
    return phonemes


def _get_tonaccent(word: str) -> int:
    """Determine tonaccent (1=falling, 2=falling-rising) for Swedish word."""
    
    # Count syllables (approximate)
    syllable_count = len([ch for ch in word if ch in _VOWELS])
    
    if syllable_count == 1:
        return 1  # Monosyllabic -> accent 1
    
    # Check explicit accent 2 words
    if word in _ACCENT_2_WORDS:
        return 2
    
    # Heuristics for accent 2:
    # - Long words (often compounds)
    # - Common suffixes
    # - Compound prefixes
    if (len(word) > 6 or
        word.endswith(("are", "ade", "ning", "het", "dom", "skap", "tion", "sion")) or
        any(word.startswith(prefix) for prefix in ("för", "upp", "över", "under", "med", "sam"))):
        return 2
    
    # Default: accent 1  
    return 1


def phonemize_swedish_with_prosody(text: str) -> Tuple[List[str], List[Optional[ProsodyInfo]]]:
    """Convert Swedish text to phonemes with prosody including tonaccent."""
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)
    
    phonemes: List[str] = []
    prosody_list: List[Optional[ProsodyInfo]] = []
    need_space = False
    
    for token in tokens:
        # Punctuation
        if all(c in _PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue
        
        # Regular word
        if need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
        
        # Convert word
        word_phonemes = _convert_word(token)
        word_phoneme_count = len(word_phonemes)
        syllable_count = len([ch for ch in token if ch in _VOWELS])
        
        # Determine tonaccent and stress
        tonaccent = _get_tonaccent(token)
        is_stressed = syllable_count > 1 and token not in _UNSTRESSED_FUNCTION_WORDS
        
        # Add stress marker for polysyllabic words
        if is_stressed:
            if tonaccent == 1:
                phonemes.append("ˈ")  # Primary stress -> accent 1
                prosody_list.append(ProsodyInfo(a1=1, a2=2, a3=word_phoneme_count))
            else:
                phonemes.append("ˌ")  # Secondary stress -> accent 2
                prosody_list.append(ProsodyInfo(a1=2, a2=1, a3=word_phoneme_count))
        
        # Add word phonemes with prosody
        for phoneme in word_phonemes:
            phonemes.append(phoneme)
            
            # Determine stress level for this phoneme
            if syllable_count == 1:
                stress_level = 2  # Monosyllabic = stressed
            elif is_stressed:
                stress_level = 2 if tonaccent == 1 else 1
            else:
                stress_level = 0  # Unstressed
                
            prosody_list.append(ProsodyInfo(
                a1=tonaccent,
                a2=stress_level,
                a3=word_phoneme_count
            ))
        
        need_space = True
    
    # Apply PUA mapping for multi-character phonemes
    from .token_mapper import map_sequence
    mapped_phonemes = map_sequence(phonemes)
    
    return mapped_phonemes, prosody_list


def phonemize_swedish(text: str) -> List[str]:
    """Convert Swedish text to phoneme list (without prosody).""" 
    phonemes, _ = phonemize_swedish_with_prosody(text)
    return phonemes


class SwedishPhonemizer(Phonemizer):
    """Rule-based Swedish phonemizer."""
    
    def phonemize(self, text: str) -> List[str]:
        return phonemize_swedish(text)
    
    def phonemize_with_prosody(self, text: str) -> Tuple[List[str], List[Optional[ProsodyInfo]]]:
        return phonemize_swedish_with_prosody(text)
    
    def get_phoneme_id_map(self) -> Optional[Dict[str, List[int]]]:
        # Returns None for multilingual use
        return None

