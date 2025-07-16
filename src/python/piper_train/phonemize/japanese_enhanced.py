"""Enhanced Japanese phonemizer with accent strength levels."""

import re

import pyopenjtalk

from .token_mapper import map_sequence

__all__ = ["phonemize_japanese_enhanced"]

# Regular expressions
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")  # Same as basic phonemizer
_RE_A3 = re.compile(r"\+([0-9]+)/")  # Same as basic phonemizer
_RE_F1 = re.compile(r"/F:(\d+)_")  # F1: lexical accent position
_RE_F2 = re.compile(r"_(\d+)#")  # F2: current mora position in word
_RE_F7 = re.compile(r"\|(\d+)_")  # F7: number of moras in word

# Extended accent strength marks
ACCENT_STRENGTH_MARKS = {
    "weak_rise": "[1",
    "medium_rise": "[2",
    "strong_rise": "[3",
    "weak_fall": "]1",
    "medium_fall": "]2",
    "strong_fall": "]3",
}

# Question type patterns
QUESTION_PATTERNS = {
    "yes_no": re.compile(r"(ですか|ますか|ですの|ますの)[？?]?$"),
    "wh": re.compile(r"(いつ|どこ|だれ|なに|なぜ|どう|どの|どれ|どちら).*[？?]?$"),
    "rhetorical": re.compile(r"(でしょう|だろう|ではないか)[？?]?$"),
    "tag": re.compile(r"(ね|よね)[？?]?$"),
}


def _detect_question_type(text: str) -> str:
    """Detect the type of question from text."""
    text = text.strip()

    # Check each pattern
    for q_type, pattern in QUESTION_PATTERNS.items():
        if pattern.search(text):
            return q_type

    # Default to yes_no if ends with question mark
    if text.endswith("?") or text.endswith("？"):
        return "yes_no"

    return "statement"


def _calculate_accent_strength(
    a1: int,
    a2: int,
    a3: int,
    f1: int,
    f7: int,
    position_in_phrase: float,
) -> str:
    """Calculate accent strength based on multiple factors.

    Args:
        a1: Accent flag (1 if accented mora)
        a2: Position in accent phrase
        a3: Number of moras in accent phrase
        f1: Lexical accent position
        f7: Number of moras in word
        position_in_phrase: Relative position in phrase (0.0-1.0)

    Returns:
        Accent strength level ("weak", "medium", "strong")
    """
    # Base strength calculation
    if a3 <= 2:
        base_strength = "weak"
    elif a3 <= 4:
        base_strength = "medium"
    else:
        base_strength = "strong"

    # Adjust for position in phrase
    if position_in_phrase < 0.2:  # Beginning of phrase
        if base_strength == "weak":
            return "medium"
        if base_strength == "medium":
            return "strong"
    elif position_in_phrase > 0.8:  # End of phrase
        if base_strength == "strong":
            return "medium"
        if base_strength == "medium":
            return "weak"

    # Adjust for lexical accent
    if f1 > 0 and a2 == f1:
        # At lexical accent position
        if base_strength == "weak":
            return "medium"
        if base_strength == "medium":
            return "strong"

    return base_strength


def phonemize_japanese_enhanced(text: str) -> list[str]:
    """Enhanced Japanese phonemizer with accent strength levels.

    Extends the basic Kurihara method with:
    - 3-level accent strength marks ([1, [2, [3, ]1, ]2, ]3)
    - Question type detection (yes/no, WH, rhetorical, tag)
    - More nuanced prosody based on phrase structure

    Args:
        text: Japanese text to phonemize

    Returns:
        List of phonemes and prosody marks
    """
    labels = pyopenjtalk.extract_fullcontext(text)
    tokens: list[str] = []

    # Detect question type
    question_type = _detect_question_type(text)

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            continue
        phoneme = m_ph.group(1)

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                tokens.append("^")
            elif idx == len(labels) - 1:
                # Enhanced end markers based on question type
                if question_type == "yes_no":
                    tokens.append("?")
                elif question_type == "wh":
                    tokens.append("?!")  # Special marker for WH questions
                elif question_type == "rhetorical":
                    tokens.append("?.")  # Rhetorical question
                elif question_type == "tag":
                    tokens.append("?~")  # Tag question
                else:
                    tokens.append("$")
            continue

        # Short pause
        if phoneme == "pau":
            tokens.append("_")
            continue

        tokens.append(phoneme)

        # Extract prosody information
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)
        m_f1 = _RE_F1.search(label)
        m_f7 = _RE_F7.search(label)

        if not (m_a1 and m_a2 and m_a3):
            continue

        a1 = int(m_a1.group(1))
        a2 = int(m_a2.group(1))
        a3 = int(m_a3.group(1))

        # Extract additional features
        f1 = int(m_f1.group(1)) if m_f1 else 0
        f7 = int(m_f7.group(1)) if m_f7 else a3

        # Calculate relative position in phrase
        position_in_phrase = a2 / a3 if a3 > 0 else 0.5

        # Get next mora information
        if idx < len(labels) - 1:
            m_a2_next = _RE_A2.search(labels[idx + 1])
            a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
        else:
            a2_next = -1

        # Calculate accent strength
        strength = _calculate_accent_strength(a1, a2, a3, f1, f7, position_in_phrase)

        # Insert accent nucleus mark with strength
        if (a1 == 0) and (a2_next == a2 + 1):
            if strength == "weak":
                tokens.append("]1")
            elif strength == "medium":
                tokens.append("]2")
            else:
                tokens.append("]3")

        # Insert phrase boundary and rising mark with strength
        if (a2 == a3) and (a2_next == 1):
            tokens.append("#")
            # Add rising mark with strength for next phrase
            if idx < len(labels) - 1:
                next_label = labels[idx + 1]
                if "sil" not in next_label and "pau" not in next_label:
                    # Determine strength for rising mark
                    if a3 <= 2:
                        tokens.append("[1")
                    elif a3 <= 4:
                        tokens.append("[2")
                    else:
                        tokens.append("[3")

        # First mora of accent phrase (rising mark)
        # Only add rising mark when a2==1 and next mora is 2
        if (a2 == 1) and (a2_next == 2):
            if idx > 0:
                prev_label = labels[idx - 1]
                if "sil" in prev_label or "pau" in prev_label:
                    # After silence, use stronger accent
                    if strength == "weak":
                        tokens.append("[2")
                    elif strength == "medium":
                        tokens.append("[3")
                    else:
                        tokens.append("[3")
                # Normal rising mark
                elif strength == "weak":
                    tokens.append("[1")
                elif strength == "medium":
                    tokens.append("[2")
                else:
                    tokens.append("[3")
            # Default rising mark at start
            elif strength == "weak":
                tokens.append("[1")
            elif strength == "medium":
                tokens.append("[2")
            else:
                tokens.append("[3")

    # Map tokens if needed
    tokens = map_sequence(tokens)

    return tokens
