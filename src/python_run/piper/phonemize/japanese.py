"""Japanese phonemization for inference.

Uses the same Kurihara-method algorithm as the training side
(piper_train.phonemize.japanese) to ensure phoneme-level consistency.
"""

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from .token_mapper import map_sequence


_LOGGER = logging.getLogger(__name__)

# Try to import pyopenjtalk-plus first (Windows compatible), fall back to pyopenjtalk
try:
    import pyopenjtalk_plus as pyopenjtalk

    HAS_PYOPENJTALK = True
except ImportError:
    try:
        import pyopenjtalk

        HAS_PYOPENJTALK = True
    except ImportError:
        HAS_PYOPENJTALK = False
        pyopenjtalk = None  # type: ignore[assignment]
        _LOGGER.warning("pyopenjtalk not available for Japanese phonemization")

# Regular expressions for HTS label parsing (same as training side)
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")

# Tokens to skip when looking for next phoneme in N-variant rules
_SKIP_TOKENS = frozenset(("_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"))


def _get_question_type(text: str) -> str:
    """Return the appropriate question marker based on text ending."""
    stripped = text.strip()

    if (
        stripped.endswith("?!")
        or stripped.endswith("\uff01\uff1f")
        or stripped.endswith("\uff1f\uff01")
    ):
        return "?!"
    if (
        stripped.endswith("?.")
        or stripped.endswith("\u3002\uff1f")
        or stripped.endswith("\uff1f\u3002")
    ):
        return "?."
    if (
        stripped.endswith("?~")
        or stripped.endswith("\uff5e\uff1f")
        or stripped.endswith("\uff1f\uff5e")
    ):
        return "?~"

    if stripped.endswith("?") or stripped.endswith("\uff1f"):
        return "?"

    return "$"


def _apply_n_phoneme_rules(tokens: list[str]) -> list[str]:
    """Apply context-dependent rules to replace 'N' with specific variants.

    Japanese 'N' has different pronunciations depending on the following phoneme:
    - N_m     : before m/b/p (bilabial assimilation)
    - N_n     : before n/t/d/ts/ch (alveolar assimilation)
    - N_ng    : before k/g (velar assimilation)
    - N_uvular: at phrase end or before vowels/other consonants
    """
    result = []
    for i, token in enumerate(tokens):
        if token != "N":
            result.append(token)
            continue

        next_phoneme = None
        for j in range(i + 1, len(tokens)):
            if tokens[j] not in _SKIP_TOKENS:
                next_phoneme = tokens[j]
                break

        if next_phoneme is None:
            result.append("N_uvular")
        elif next_phoneme in ("m", "my", "b", "by", "p", "py"):
            result.append("N_m")
        elif next_phoneme in ("n", "ny", "t", "ty", "d", "dy", "ts", "ch"):
            result.append("N_n")
        elif next_phoneme in ("k", "ky", "kw", "g", "gy", "gw"):
            result.append("N_ng")
        else:
            result.append("N_uvular")

    return result


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
                    "Loaded custom dictionary with %d entries",
                    len(self.replacements),
                )
            except Exception as e:
                _LOGGER.warning("Failed to load custom dictionary: %s", e)

    def apply(self, text: str) -> str:
        """Apply dictionary replacements to text."""
        for word, replacement in self.replacements.items():
            text = text.replace(word, replacement)
        return text


# OpenJTalk has a buffer limit (~2700 chars). Split on sentence boundaries.
_MAX_OPENJTALK_CHARS = 2000
_RE_JA_SENTENCE_SPLIT = re.compile(r"(?<=[。！？\n])")


def _split_long_text(text: str, max_chars: int = _MAX_OPENJTALK_CHARS) -> list[str]:
    """Split text into chunks safe for OpenJTalk processing."""
    if len(text) <= max_chars:
        return [text]

    sentences = _RE_JA_SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) > max_chars and current:
            chunks.append(current)
            current = ""
        current += sent
    if current:
        chunks.append(current)
    return chunks


def _phonemize_sentence_core(sentence: str, prosody: bool) -> list[str]:
    """Phonemize a single sentence (no BOS/EOS, no custom dict, no splitting).

    Extracted from phonemize_japanese() for caching purposes.
    """
    if not prosody:
        phoneme_str = pyopenjtalk.g2p(sentence)
        tokens = phoneme_str.split()
        tokens = _apply_n_phoneme_rules(tokens)
        return map_sequence(tokens)

    # Full phonemization with prosody marks using HTS labels
    labels = pyopenjtalk.extract_fullcontext(sentence)
    tokens: list[str] = []

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            continue
        phoneme = m_ph.group(1)

        # Skip silence markers (BOS/EOS handled by caller)
        if phoneme == "sil":
            continue

        # Short pause
        if phoneme == "pau":
            tokens.append("_")
            continue

        tokens.append(phoneme)

        # Prosody mark extraction from A1/A2/A3
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)
        if not (m_a1 and m_a2 and m_a3):
            continue

        a1 = int(m_a1.group(1))
        a2 = int(m_a2.group(1))
        a3 = int(m_a3.group(1))

        # Look-ahead to next label
        if idx < len(labels) - 1:
            m_a2_next = _RE_A2.search(labels[idx + 1])
            a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
        else:
            a2_next = -1

        if (a1 == 0) and (a2_next == a2 + 1):
            tokens.append("]")
        if (a2 == a3) and (a2_next == 1):
            tokens.append("#")
        if (a2 == 1) and (a2_next == 2):
            tokens.append("[")

    tokens = _apply_n_phoneme_rules(tokens)
    return map_sequence(tokens)


@lru_cache(maxsize=2000)
def _phonemize_sentence_cached(sentence: str, prosody: bool) -> tuple[str, ...]:
    """Cache wrapper for _phonemize_sentence_core().

    Returns a tuple (immutable) for lru_cache hashability.
    """
    return tuple(_phonemize_sentence_core(sentence, prosody))


def clear_phonemize_cache() -> None:
    """Clear the phonemization cache (call after custom dictionary changes)."""
    _phonemize_sentence_cached.cache_clear()


def phonemize_japanese(
    text: str, custom_dict: CustomDictionary | None = None, prosody: bool = True
) -> list[str]:
    """Phonemize Japanese text using the Kurihara method.

    Prosody symbols inserted:
        ^   : beginning of sentence
        $/? : end of sentence
        _   : short pause (pau)
        #   : accent phrase boundary
        [   : rising-pitch mark
        ]   : falling-pitch mark
    """
    if not HAS_PYOPENJTALK:
        raise RuntimeError(
            "pyopenjtalk or pyopenjtalk-plus is required for Japanese phonemization. "
            "Install with: pip install pyopenjtalk-plus"
        )

    if custom_dict:
        text = custom_dict.apply(text)

    # Split long text to avoid OpenJTalk buffer overflow (~2700 char limit)
    chunks = _split_long_text(text)

    all_tokens: list[str] = []
    for chunk in chunks:
        chunk_tokens = list(_phonemize_sentence_cached(chunk, prosody))
        all_tokens.extend(chunk_tokens)

    # Wrap with BOS/EOS
    eos = _get_question_type(text) if prosody else "$"
    return map_sequence(["^"] + all_tokens + [eos])


def phonemize_japanese_simple(text: str) -> list[str]:
    """Simple Japanese phonemization without prosody marks."""
    return phonemize_japanese(text, prosody=False)


def find_upwards(
    filename: str, start_dir: Path | None = None, max_depth: int = 10
) -> Path | None:
    """Search upward from start_dir for a file with the given filename."""
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
    dict_path = find_upwards("data/dictionaries/user_custom_dict.json")
    if dict_path:
        return CustomDictionary(str(dict_path))
    return None
