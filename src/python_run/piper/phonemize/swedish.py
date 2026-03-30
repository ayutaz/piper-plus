"""Rule-based Swedish phonemizer for Piper TTS runtime.

Optimized rule-based Swedish G2P for inference.
Implements core Swedish orthographic rules without external dependencies.
"""

import re
import unicodedata

from .token_mapper import map_sequence


__all__ = ["phonemize_swedish"]

# Punctuation characters
_PUNCTUATION = set(",.;:!?")

# Swedish vowel and consonant letters
_VOWELS = set("aeiouyåäö")
_CONSONANTS = set("bcdfghjklmnpqrstvwxz")

# Front vowels for palatalization
_FRONT_VOWELS = set("eiwyäö")

# Regex for tokenization
_RE_TOKEN = re.compile(r"([a-zåäöA-ZÅÄÖ]+|[,.;:!?]+)", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Normalize text."""
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return text


def _determine_vowel_length(vowel: str, word: str, pos: int) -> str:
    """Simplified Swedish vowel length for runtime."""
    # Count syllables
    syllable_count = len([ch for ch in word if ch in _VOWELS])
    after_vowel = word[pos + 1:]
    
    # Monosyllabic words: check for geminates
    if syllable_count == 1:
        if any(after_vowel[i:i+2] in [cc*2 for cc in _CONSONANTS] + ["ck"] 
               for i in range(len(after_vowel)-1)):
            is_long = False  # Geminate -> short
        else:
            is_long = True   # Monosyllabic -> long
    else:
        # Polysyllabic: count consonants
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
                
            if i + 2 < len(after_vowel):
                trigraph = after_vowel[i:i+3]
                if trigraph in ("skj", "stj", "sch"):
                    consonant_sounds += 1
                    i += 3
                    continue
            
            if i + 1 < len(after_vowel):
                digraph = after_vowel[i:i+2]
                
                if digraph in ("rn", "rd", "rt", "rs", "rl", "sj", "tj", "kj", "ng", "ch"):
                    consonant_sounds += 1
                    i += 2
                    continue
                
                # Geminates
                elif (digraph[0] == digraph[1] and digraph[0] in _CONSONANTS) or digraph == "ck":
                    is_long = False
                    break
            
            consonant_sounds += 1
            i += 1
        
        # CV.CV pattern check
        is_long = consonant_sounds == 1 and next_vowel_found
    
    if is_long:
        long_map = {
            "a": "ɑː", "e": "eː", "i": "iː", "o": "uː", "u": "ʉː",
            "y": "yː", "å": "oː", "ä": "ɛː", "ö": "øː"
        }
        return long_map.get(vowel, vowel + "ː")
    else:
        short_map = {
            "a": "a", "e": "ɛ", "i": "ɪ", "o": "ɔ", "u": "ɵ",
            "y": "ʏ", "å": "ɔ", "ä": "ɛ", "ö": "œ"
        }
        return short_map.get(vowel, vowel)


def _convert_word(word: str) -> list[str]:
    """Convert Swedish word to phonemes."""
    phonemes = []
    n = len(word)
    i = 0
    
    while i < n:
        ch = word[i]
        
        # Three-letter combinations
        if i + 2 < n:
            trigraph = word[i:i+3]
            if trigraph in ("skj", "stj", "sch"):
                phonemes.append("ɧ")
                i += 3
                continue
        
        # Two-letter combinations
        if i + 1 < n:
            digraph = word[i:i+2]
            ch2 = word[i+1]
            
            # ch -> tje-ljud
            if digraph == "ch":
                phonemes.append("ɕ")
                i += 2
                continue
                
            # Initial silent consonants
            elif i == 0 and digraph in ("dj", "gj", "hj", "lj"):
                phonemes.append("j")
                i += 2
                continue
                
            # sje-ljud
            elif digraph == "sj":
                phonemes.append("ɧ")
                i += 2
                continue
                
            # sk before front vowels
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
                
            # ck → k
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
                
            # Double consonants
            elif ch == ch2 and ch in _CONSONANTS:
                phonemes.append(ch)
                i += 2
                continue
        
        # Vowels with length
        if ch in _VOWELS:
            vowel_phoneme = _determine_vowel_length(ch, word, i)
            phonemes.append(vowel_phoneme)
            i += 1
            continue
        
        # Consonants with context
        elif ch == "k":
            if i + 1 < n and word[i+1] in _FRONT_VOWELS:
                phonemes.append("ɕ")
            else:
                phonemes.append("k")
        elif ch == "g":
            if i + 1 < n and word[i+1] in _FRONT_VOWELS:
                phonemes.append("j")
            else:
                phonemes.append("ɡ")
        elif ch == "c":
            if i + 1 < n and word[i+1] in "eiy":
                phonemes.append("s")
            else:
                phonemes.append("k")
        elif ch in "bcdfhjlmnprstv":
            phonemes.append(ch)
        elif ch == "w":
            phonemes.append("v")
        elif ch == "x":
            phonemes.extend(["k", "s"])
        elif ch == "z":
            phonemes.append("s")
        elif ch == "q":
            phonemes.append("k")
        
        i += 1
    
    return phonemes


def phonemize_swedish(text: str) -> list[str]:
    """Convert Swedish text to phonemes for TTS inference."""
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)
    
    phonemes = []
    need_space = False
    
    for token in tokens:
        # Punctuation
        if all(c in _PUNCTUATION for c in token):
            phonemes.extend(token)
            continue
        
        # Regular word
        if need_space:
            phonemes.append(" ")
        
        word_phonemes = _convert_word(token)
        phonemes.extend(word_phonemes)
        need_space = True
    
    return map_sequence(phonemes)
