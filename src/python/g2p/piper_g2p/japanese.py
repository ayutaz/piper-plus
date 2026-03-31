"""Japanese phonemizer using OpenJTalk.

Produces clean IPA token lists without BOS/EOS markers or PUA encoding.
Multi-character tokens (``"ch"``, ``"sh"``, ``"N_m"`` etc.) are returned
as-is — the caller is responsible for any further encoding.
"""

import re

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

__all__ = [
    "JapanesePhonemizer",
]

# Regular expressions reused many times
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")


def _is_question(text: str) -> bool:
    """Return True if *text* ends with a Japanese/ASCII question mark."""
    return text.strip().endswith("?") or text.strip().endswith("\uFF1F")


def _get_question_type(text: str) -> str:
    """Return the appropriate question marker based on text ending.

    Returns one of: ``"?!"``, ``"?."``, ``"?~"``, ``"?"``, or ``""``
    (empty string for non-questions).

    Markers:
    - ``"?!"`` : Emphatic question (強調疑問) — ends with ?! or ！？
    - ``"?."`` : Neutral/rhetorical question (平叙疑問) — ends with ?. or 。？
    - ``"?~"`` : Tag question (確認疑問) — ends with ?~ or ～？ or ？～
    - ``"?"``  : Generic question — ends with ? or ？
    - ``""``   : Declarative (non-question)
    """
    stripped = text.strip()

    # Multi-char patterns first (check longer patterns before shorter)
    if (
        stripped.endswith("?!")
        or stripped.endswith("\uFF01\uFF1F")
        or stripped.endswith("\uFF1F\uFF01")
    ):
        return "?!"
    if (
        stripped.endswith("?.")
        or stripped.endswith("\u3002\uFF1F")
        or stripped.endswith("\uFF1F\u3002")
    ):
        return "?."
    if (
        stripped.endswith("?~")
        or stripped.endswith("\uFF5E\uFF1F")
        or stripped.endswith("\uFF1F\uFF5E")
    ):
        return "?~"

    # Single ? fallback
    if stripped.endswith("?") or stripped.endswith("\uFF1F"):
        return "?"

    return ""  # Not a question


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

    Parameters
    ----------
    tokens : list[str]
        List of phoneme tokens.

    Returns
    -------
    list[str]
        List with 'N' replaced by context-appropriate variants.
    """
    result = []
    for i, token in enumerate(tokens):
        if token != "N":
            result.append(token)
            continue

        # Look ahead to find next actual phoneme
        next_phoneme = None
        for j in range(i + 1, len(tokens)):
            if tokens[j] not in _SKIP_TOKENS:
                next_phoneme = tokens[j]
                break

        # Determine N variant based on next phoneme
        if next_phoneme is None:
            result.append("N_uvular")  # End of phrase
        elif next_phoneme in ("m", "my", "b", "by", "p", "py"):
            result.append("N_m")  # Bilabial
        elif next_phoneme in ("n", "ny", "t", "ty", "d", "dy", "ts", "ch"):
            result.append("N_n")  # Alveolar
        elif next_phoneme in ("k", "ky", "kw", "g", "gy", "gw"):
            result.append("N_ng")  # Velar
        else:
            result.append("N_uvular")  # Vowels, other consonants

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
            # Should never happen — skip just in case
            continue
        phoneme = m_ph.group(1)

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                # No BOS — skip leading sil
                pass
            elif idx == len(labels) - 1:
                # EOS: only emit question marker if present
                if question_marker:
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

        # ------------------------------------------------------------------
        # Prosody mark extraction — see Open JTalk label definition
        # ------------------------------------------------------------------
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)

        if m_a1 and m_a2 and m_a3:
            a1 = int(m_a1.group(1))
            a2 = int(m_a2.group(1))
            a3 = int(m_a3.group(1))
            prosody_info.append(ProsodyInfo(a1=a1, a2=a2, a3=a3))

            # Look-ahead to next label to fetch a2_next
            if idx < len(labels) - 1:
                m_a2_next = _RE_A2.search(labels[idx + 1])
                a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
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


class JapanesePhonemizer(Phonemizer):
    """Japanese phonemizer using OpenJTalk.

    Returns clean IPA token lists.  BOS/EOS markers are **not** emitted;
    question markers (``"?"``, ``"?!"``, ``"?."``, ``"?~"``) are appended
    only when the input text ends with a question mark.
    Multi-character tokens are returned as-is (no PUA mapping).
    """

    def phonemize(self, text: str) -> list[str]:
        tokens, _prosody = _phonemize_core(text)
        return tokens

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return _phonemize_core(text)
