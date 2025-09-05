"""Simplified Japanese phonemization for inference."""

import json
import logging
import os
from pathlib import Path

from .token_mapper import map_sequence


_LOGGER = logging.getLogger(__name__)

# Try to import pyopenjtalk
try:
    import pyopenjtalk

    HAS_PYOPENJTALK = True
except ImportError:
    HAS_PYOPENJTALK = False
    _LOGGER.warning("pyopenjtalk not available for Japanese phonemization")


class CustomDictionary:
    """Simple custom dictionary for phoneme replacement."""

    def __init__(self, dict_path: str | None = None):
        self.replacements = {}

        if dict_path and os.path.exists(dict_path):
            try:
                with open(dict_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.replacements = data.get("replacements", {})
                _LOGGER.info(
                    f"Loaded custom dictionary with {len(self.replacements)} entries"
                )
            except Exception as e:
                _LOGGER.warning(f"Failed to load custom dictionary: {e}")

    def apply(self, text: str) -> str:
        """Apply dictionary replacements to text."""
        for word, replacement in self.replacements.items():
            text = text.replace(word, replacement)
        return text


def phonemize_japanese(
    text: str, custom_dict: CustomDictionary | None = None, prosody: bool = True
) -> list[str]:
    """
    Phonemize Japanese text for inference.

    Args:
        text: Japanese text to phonemize
        custom_dict: Optional custom dictionary for word replacements
        prosody: Whether to include prosody marks (default: True)

    Returns:
        List of phoneme tokens
    """
    if not HAS_PYOPENJTALK:
        raise RuntimeError("pyopenjtalk is required for Japanese phonemization")

    # Apply custom dictionary if provided
    if custom_dict:
        text = custom_dict.apply(text)

    # Get full labels from pyopenjtalk
    if prosody:
        # Full phonemization with prosody marks
        full_labels = pyopenjtalk.make_label(pyopenjtalk.run_frontend(text))

        phonemes = ["^"]  # BOS

        for label in full_labels:
            if "xx" in label:
                continue

            # Parse the label format
            parts = label.split("+")
            if len(parts) < 2:
                continue

            # Extract phoneme from p1^p2-p3+p4=p5 format
            phoneme_part = parts[0].split("-")[-1]

            # Extract accent and phrase info
            if "/" in label:
                accent_info = label.split("/")
                if len(accent_info) >= 3:
                    # A: accent position, B: phrase length
                    a_part = accent_info[0].split(":")[-1]
                    if a_part and a_part != "xx":
                        try:
                            accent_pos = int(a_part)
                            # Add accent marks based on position
                            if accent_pos == 1:
                                phonemes.append("[")  # Rising pitch
                            elif accent_pos > 1:
                                phonemes.append("]")  # Falling pitch
                        except ValueError:
                            pass

            # Add the phoneme
            if phoneme_part and phoneme_part != "xx":
                phonemes.append(phoneme_part)

            # Check for pause
            if "pau" in label:
                phonemes.append("_")

            # Check for phrase boundary
            if "#" in label:
                phonemes.append("#")

        # Add EOS (check if last phoneme suggests a question)
        if text.endswith("？") or text.endswith("?"):
            phonemes.append("?")
        else:
            phonemes.append("$")
    else:
        # Simple phonemization without prosody
        phoneme_str = pyopenjtalk.g2p(text)
        phonemes = ["^"] + phoneme_str.split() + ["$"]

    # Map multi-character phonemes to single characters
    return map_sequence(phonemes)


def phonemize_japanese_simple(text: str) -> list[str]:
    """
    Simple Japanese phonemization without prosody marks.

    Args:
        text: Japanese text to phonemize

    Returns:
        List of phoneme tokens
    """
    return phonemize_japanese(text, prosody=False)


# Load default custom dictionary if available
def find_upwards(
    filename: str, start_dir: Path = None, max_depth: int = 10
) -> Path | None:
    """
    Search upward from start_dir for a file with the given filename.
    Returns the Path if found, else None.
    """
    if start_dir is None:
        start_dir = Path(__file__).parent
    current = start_dir.resolve()
    for _ in range(max_depth):
        candidate = current / filename
        if candidate.exists():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def get_default_dictionary() -> CustomDictionary | None:
    """Get the default custom dictionary if available."""
    # Search upward for the custom dictionary file
    dict_path = find_upwards("data/dictionaries/user_custom_dict.json")
    if dict_path:
        return CustomDictionary(str(dict_path))
    return None
