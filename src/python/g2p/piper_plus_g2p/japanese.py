"""Japanese phonemizer using OpenJTalk.

Produces clean IPA token lists without BOS/EOS markers or PUA encoding.
Multi-character tokens (``"ch"``, ``"sh"``, ``"N_m"`` etc.) are returned
as-is — the caller is responsible for any further encoding.
"""

import re
from functools import lru_cache

# Try to import pyopenjtalk-plus first (Windows compatible), fall back to pyopenjtalk
try:
    import pyopenjtalk_plus as pyopenjtalk
except ImportError:
    try:
        import pyopenjtalk
    except ImportError:
        raise ImportError(
            "Neither pyopenjtalk nor pyopenjtalk-plus is installed"
        ) from None

from .base import Phonemizer, ProsodyInfo
from .custom_dict import CustomDictionary

__all__ = [
    "JapanesePhonemizer",
    "clear_phonemize_cache",
]

# Phoneme extraction (always matches, including sil/pau labels)
_RE_PHONEME = re.compile(r"-(?P<ph>[^+]+)\+")
# Prosody extraction (3 regexes unified into 1; only matches non-sil labels)
_RE_PROSODY = re.compile(r"/A:(?P<a1>[\d-]+)\+(?P<a2>[0-9]+)\+(?P<a3>[0-9]+)/")


def _is_question(text: str) -> bool:
    """Return True if *text* ends with a Japanese/ASCII question mark."""
    return text.strip().endswith("?") or text.strip().endswith("\uff1f")


def _get_question_type(text: str) -> str:
    """Return the appropriate question marker based on text ending.

    Returns one of: ``"?!"``, ``"?."``, ``"?~"``, ``"?"``, or ``"$"``
    for non-questions.

    Markers:
    - ``"?!"`` : Emphatic question (強調疑問) — ends with ?! or ！？
    - ``"?."`` : Neutral/rhetorical question (平叙疑問) — ends with ?. or 。？
    - ``"?~"`` : Tag question (確認疑問) — ends with ?~ or ～？ or ？～
    - ``"?"``  : Generic question — ends with ? or ？
    - ``"$"``  : Declarative (non-question)
    """
    stripped = text.strip()

    # Multi-char patterns first (check longer patterns before shorter)
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

    # Single ? fallback
    if stripped.endswith("?") or stripped.endswith("\uff1f"):
        return "?"

    return "$"  # Not a question


# Set of tokens that should be skipped when looking for next phoneme
_SKIP_TOKENS = frozenset(("_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"))


def _apply_n_phoneme_rules(tokens: list[str]) -> list[str]:
    """Apply context-dependent rules to replace 'N' with specific variants.

    Japanese 'ん' (N) has different pronunciations depending on the following
    phoneme:

    - N_m     : before m/b/p (bilabial assimilation)
    - N_n     : before n/t/d/ts/ch (alveolar assimilation)
    - N_ng    : before k/g (velar assimilation)
    - N_uvular: at phrase end or before vowels/other consonants

    Uses a single reverse pass (O(n)) to track the next real phoneme.

    Parameters
    ----------
    tokens : list[str]
        List of phoneme tokens.

    Returns
    -------
    list[str]
        List with 'N' replaced by context-appropriate variants.
    """
    result = list(tokens)  # copy
    next_phoneme = None
    for i in range(len(result) - 1, -1, -1):
        token = result[i]
        if token not in _SKIP_TOKENS and token != "N":
            next_phoneme = token
        elif token == "N":
            # Determine N variant based on next phoneme
            if next_phoneme is None:
                result[i] = "N_uvular"  # End of phrase
            elif next_phoneme in ("m", "my", "b", "by", "p", "py"):
                result[i] = "N_m"  # Bilabial
            elif next_phoneme in ("n", "ny", "t", "ty", "d", "dy", "ts", "ch"):
                result[i] = "N_n"  # Alveolar
            elif next_phoneme in ("k", "ky", "kw", "g", "gy", "gw"):
                result[i] = "N_ng"  # Velar
            else:
                result[i] = "N_uvular"  # Vowels, other consonants
            next_phoneme = result[i]  # N_* itself is not a skip token
    return result


def _phonemize_core(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Shared implementation for phonemize() and phonemize_with_prosody().

    Returns both tokens and prosody info in a single pass.
    """
    labels = pyopenjtalk.extract_fullcontext(text)
    tokens: list[str] = []
    prosody_info: list[ProsodyInfo | None] = []

    question_marker = _get_question_type(text)

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            continue
        phoneme = m_ph.group("ph")

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                pass
            elif idx == len(labels) - 1 and question_marker and question_marker != "$":
                tokens.append(question_marker)
                prosody_info.append(None)
            continue

        # Short pause
        if phoneme == "pau":
            tokens.append("_")
            prosody_info.append(None)
            continue

        # Add phoneme token
        tokens.append(phoneme)

        # Prosody extraction (unified A1/A2/A3 regex)
        m_p = _RE_PROSODY.search(label)

        if m_p:
            a1 = int(m_p.group("a1"))
            a2 = int(m_p.group("a2"))
            a3 = int(m_p.group("a3"))
            prosody_info.append(ProsodyInfo(a1=a1, a2=a2, a3=a3))

            # Look-ahead to next label to fetch a2_next
            if idx < len(labels) - 1:
                m_next = _RE_PROSODY.search(labels[idx + 1])
                a2_next = int(m_next.group("a2")) if m_next else -1
            else:
                a2_next = -1

            # Insert accent nucleus mark "]" at the descending point.
            if (a1 == 0) and (a2_next == a2 + 1):
                tokens.append("]")
                prosody_info.append(None)

            # Insert accent phrase boundary "#" when current mora is last
            if (a2 == a3) and (a2_next == 1):
                tokens.append("#")
                prosody_info.append(None)

            # Insert rising mark "[" at phrase head (a2==1) when next is 2
            if (a2 == 1) and (a2_next == 2):
                tokens.append("[")
                prosody_info.append(None)
        else:
            # No prosody info available
            prosody_info.append(None)

    # Apply context-dependent N phoneme rules
    # Note: only replaces 'N' in-place, prosody_info alignment is preserved
    tokens = _apply_n_phoneme_rules(tokens)

    return tokens, prosody_info


@lru_cache(maxsize=2000)
def _phonemize_core_cached(
    text: str,
) -> tuple[tuple[str, ...], tuple[ProsodyInfo | None, ...]]:
    """Cache wrapper for _phonemize_core().

    lru_cache requires hashable return values, so lists are converted to tuples.
    Callers must convert back to lists if mutation is needed.
    """
    tokens, prosody_info = _phonemize_core(text)
    return tuple(tokens), tuple(prosody_info)


def clear_phonemize_cache() -> None:
    """Clear the phonemization cache (call after custom dictionary changes)."""
    _phonemize_core_cached.cache_clear()


class JapanesePhonemizer(Phonemizer):
    """Japanese phonemizer using OpenJTalk.

    Returns clean IPA token lists.  BOS/EOS markers are **not** emitted;
    question markers (``"?"``, ``"?!"``, ``"?."``, ``"?~"``) are appended
    only when the input text ends with a question mark.
    Multi-character tokens are returned as-is (no PUA mapping).
    """

    def __init__(self, custom_dict: CustomDictionary | str | list[str] | None = None):
        if custom_dict is not None and not isinstance(custom_dict, CustomDictionary):
            custom_dict = CustomDictionary(custom_dict)
        self._custom_dict = custom_dict

    @property
    def language_code(self) -> str:
        return "ja"

    def _apply_custom_dict(self, text: str) -> str:
        if self._custom_dict is not None:
            text = self._custom_dict.apply_to_text(text)
        return text

    def phonemize(self, text: str) -> list[str]:
        text = self._apply_custom_dict(text)
        text = self._sanitize_input(text)
        if not text:
            return []
        tokens_tuple, _prosody_tuple = _phonemize_core_cached(text)
        return list(tokens_tuple)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        text = self._apply_custom_dict(text)
        text = self._sanitize_input(text)
        if not text:
            return [], []
        tokens_tuple, prosody_tuple = _phonemize_core_cached(text)
        return list(tokens_tuple), list(prosody_tuple)
