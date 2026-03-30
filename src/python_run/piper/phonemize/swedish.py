"""Swedish phonemizer for Piper TTS runtime using espeak-ng backend.

Lighter version for inference. Uses the same espeak-ng approach as the training
phonemizer but with simplified post-processing for key Swedish pronunciation fixes.
"""

import re
import subprocess
import unicodedata

from .token_mapper import map_sequence


__all__ = ["phonemize_swedish"]

# Punctuation characters passed through as-is
_PUNCTUATION = set(",.;:!?")

# Regex: split text into word tokens and punctuation
_RE_TOKEN = re.compile(r"([a-zåäöA-ZÅÄÖ]+|[,.;:!?]+)", re.IGNORECASE)

# Key pronunciation corrections for espeak-ng v1.52.0 (runtime subset)
SWEDISH_RUNTIME_CORRECTIONS = {
    # skj → ɧ (sje-ljud)
    "ɕ": "ɧ",
    # sch → ɧ (sje-ljud) 
    "ʃ": "ɧ",
    # espeak-ng uses 'sx' for sje-ljud, should be ɧ
    "sx": "ɧ",
    # Common retroflex patterns
    "rn": "ɳ",
    "rd": "ɖ", 
    "rl": "ɭ",
    "rs": "ʂ",
    "rt": "ʈ",
}


def _normalize(text: str) -> str:
    """Lowercase and normalize unicode."""
    text = text.lower()
    text = unicodedata.normalize("NFC", text)
    return text


def _run_espeak_ng_simple(text: str) -> list[str]:
    """Run espeak-ng for Swedish and return basic phoneme list."""
    if not text.strip():
        return []
        
    try:
        result = subprocess.run(
            ["espeak-ng", "--ipa", "-v", "sv", "-q", text],
            capture_output=True,
            text=True,
            check=True,
        )
        
        ipa_output = result.stdout.strip()
        if not ipa_output:
            return []
            
        # Simple parsing - just extract individual phonemes
        phonemes = []
        for char in ipa_output:
            if char not in " \t\n.":  # Skip whitespace and separators
                phonemes.append(char)
                
        return phonemes
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to basic orthographic mapping
        return _fallback_phonemize(text)


def _fallback_phonemize(text: str) -> list[str]:
    """Basic fallback if espeak-ng fails."""
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
            
    return phonemes


def _apply_runtime_corrections(phonemes: list[str], original_word: str = "") -> list[str]:
    """Apply key Swedish pronunciation corrections at runtime."""
    corrected = []
    original_lower = original_word.lower()
    
    for phoneme in phonemes:
        # Apply direct substitutions
        corrected_phoneme = SWEDISH_RUNTIME_CORRECTIONS.get(phoneme, phoneme)
        
        # Context-specific fixes
        if "skj" in original_lower and phoneme == "ɕ":
            corrected_phoneme = "ɧ"
        elif "sch" in original_lower and phoneme == "ʃ":
            corrected_phoneme = "ɧ"
            
        corrected.append(corrected_phoneme)
    
    return corrected


def phonemize_swedish(text: str) -> list[str]:
    """Convert Swedish text to phoneme list for TTS inference.
    
    Uses espeak-ng with post-processing corrections for key Swedish
    pronunciation issues not fixed in system espeak-ng v1.52.0.
    """
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes = []
    need_space = False

    for token in tokens:
        # Check if pure punctuation
        if all(c in _PUNCTUATION for c in token):
            phonemes.extend(token)
            continue

        # Regular word
        if need_space:
            phonemes.append(" ")

        # Get phonemes and apply corrections
        raw_phonemes = _run_espeak_ng_simple(token)
        corrected_phonemes = _apply_runtime_corrections(raw_phonemes, token)
        phonemes.extend(corrected_phonemes)

        need_space = True

    return map_sequence(phonemes)