import re
from dataclasses import dataclass


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

from .custom_dict import CustomDictionary
from .token_mapper import map_sequence


__all__ = ["phonemize_japanese", "phonemize_japanese_with_prosody", "ProsodyInfo"]


@dataclass
class ProsodyInfo:
    """Prosody information extracted from OpenJTalk labels.

    Attributes
    ----------
    a1 : int
        Relative position from accent nucleus. Can be negative (before nucleus),
        zero (at nucleus), or positive (after nucleus). Example: -4, -3, ..., 0, 1, ...
    a2 : int
        Position of current mora in the accent phrase (1-based).
        Resets to 1 at each accent phrase boundary.
    a3 : int
        Total number of morae in the current accent phrase.
        Useful for phrase-level prosody control.
    """

    a1: int  # アクセント核からの相対位置 (負値=核より前, 0=核, 正値=核より後)
    a2: int  # アクセント句内のモーラ位置 (1-based)
    a3: int  # アクセント句内の総モーラ数


# Regular expressions reused many times
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")


def _is_question(text: str) -> bool:
    """Return True if *text* ends with a Japanese/ASCII question mark."""
    return text.strip().endswith("?") or text.strip().endswith("？")


def _get_question_type(text: str) -> str:
    """Return the appropriate question marker based on text ending.

    Returns one of: "?!", "?.", "?~", "?", or "$" (for non-questions).

    Markers:
    - "?!" : Emphatic question (強調疑問) - ends with ?! or ！？
    - "?." : Neutral/rhetorical question (平叙疑問) - ends with ?. or 。？
    - "?~" : Tag question (確認疑問) - ends with ?~ or ～？ or ？～
    - "?"  : Generic question - ends with ? or ？
    - "$"  : Declarative (non-question)
    """
    stripped = text.strip()

    # Multi-char patterns first (check longer patterns before shorter)
    if stripped.endswith("?!") or stripped.endswith("！？") or stripped.endswith("？！"):
        return "?!"
    if stripped.endswith("?.") or stripped.endswith("。？") or stripped.endswith("？。"):
        return "?."
    if stripped.endswith("?~") or stripped.endswith("～？") or stripped.endswith("？～"):
        return "?~"

    # Single ? fallback
    if stripped.endswith("?") or stripped.endswith("？"):
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

    Parameters
    ----------
    tokens : list[str]
        List of phoneme tokens (before map_sequence)

    Returns
    -------
    list[str]
        List with 'N' replaced by context-appropriate variants
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


def phonemize_japanese(
    text: str, custom_dict: CustomDictionary | str | list[str] | None = None
) -> list[str]:
    """Convert *text* into a list of phoneme/prosody tokens that Piper can ingest.

    The algorithm follows the so-called "Kurihara method" that inserts the
    following extra symbols in the phoneme sequence:

    ^   : beginning of sentence
    $/?: end of sentence (choose ? for interrogative)
    _   : short pause (pau)
    #   : accent phrase boundary
    [   : rising-pitch mark (accent phrase head)
    ]   : falling-pitch mark (accent nucleus)

    Parameters
    ----------
    text : str
        Input text to phonemize
    custom_dict : CustomDictionary, str, List[str], optional
        Custom dictionary instance or path(s) to dictionary file(s)

    Notes
    -----
    1. We rely on *pyopenjtalk.extract_fullcontext* to obtain full-context labels.
    2. "sil" at the beginning / end of the utterance is converted into ^ / $ or ?.
    3. Custom dictionary is applied before OpenJTalk processing for better pronunciation.
    """

    # カスタム辞書を適用
    if custom_dict is not None:
        if isinstance(custom_dict, CustomDictionary):
            dictionary = custom_dict
        else:
            # パスが渡された場合は辞書を作成
            dictionary = CustomDictionary(custom_dict)

        # テキストに辞書を適用
        text = dictionary.apply_to_text(text)

    labels = pyopenjtalk.extract_fullcontext(text)
    tokens: list[str] = []

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            # Should never happen – skip just in case
            continue
        phoneme = m_ph.group(1)

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                tokens.append("^")
            elif idx == len(labels) - 1:
                # Always add end marker when we find the last sil
                tokens.append(_get_question_type(text))
            # Skip adding ordinary phoneme for sil
            continue

        # Short pause
        if phoneme == "pau":
            tokens.append("_")
            continue

        # Keep unvoiced vowels as uppercase for linguistic accuracy

        tokens.append(phoneme)

        # ------------------------------------------------------------------
        # Prosody mark extraction – see Open JTalk label definition
        # ------------------------------------------------------------------
        # A1 : accented? 1 if accented mora else 0
        # A2 : position of current mora in the accent phrase (1-based)
        # A3 : number of mora in the accent phrase
        #
        # A2_next is needed to detect accent nucleus and phrase boundary.
        # ------------------------------------------------------------------
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)
        if not (m_a1 and m_a2 and m_a3):
            # Cannot get accent info – continue
            continue

        a1 = int(m_a1.group(1))
        a2 = int(m_a2.group(1))
        a3 = int(m_a3.group(1))

        # Look-ahead to next label to fetch a2_next
        if idx < len(labels) - 1:
            m_a2_next = _RE_A2.search(labels[idx + 1])
            a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
        else:
            a2_next = -1

        # Insert accent nucleus mark "]" at the descending point.
        # Kurihara rule: a1==0 && a2_next == a2 + 1 (i.e., pitch goes from H to L)
        if (a1 == 0) and (a2_next == a2 + 1):
            tokens.append("]")

        # Insert accent phrase boundary "#" when current mora is last in phrase
        if (a2 == a3) and (a2_next == 1):
            tokens.append("#")

        # Insert rising mark "[" at phrase head (a2==1) when next mora is 2
        if (a2 == 1) and (a2_next == 2):
            tokens.append("[")

    # Apply context-dependent N phoneme rules
    tokens = _apply_n_phoneme_rules(tokens)

    # 多文字トークンを1コードポイントへ変換
    return map_sequence(tokens)


def phonemize_japanese_with_prosody(
    text: str, custom_dict: CustomDictionary | str | list[str] | None = None
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert *text* into phoneme tokens with prosody information.

    This function extends phonemize_japanese() by also returning A1/A2/A3
    prosody values from OpenJTalk labels for each phoneme token.

    Parameters
    ----------
    text : str
        Input text to phonemize
    custom_dict : CustomDictionary, str, List[str], optional
        Custom dictionary instance or path(s) to dictionary file(s)

    Returns
    -------
    tuple[list[str], list[ProsodyInfo | None]]
        A tuple containing:
        - tokens: List of phoneme/prosody tokens (same as phonemize_japanese)
        - prosody_info: List of ProsodyInfo for each token, or None for
          special tokens (^, $, ?, _, #, [, ])

    Notes
    -----
    The prosody information (A1/A2/A3) is useful for:
    - A1: Detecting accent nucleus position
    - A2: Position-aware duration prediction
    - A3: Phrase-level prosody control

    Example
    -------
    >>> tokens, prosody = phonemize_japanese_with_prosody("こんにちは")
    >>> for t, p in zip(tokens, prosody):
    ...     if p:
    ...         print(f"{t}: A1={p.a1}, A2={p.a2}, A3={p.a3}")
    """
    # カスタム辞書を適用
    if custom_dict is not None:
        if isinstance(custom_dict, CustomDictionary):
            dictionary = custom_dict
        else:
            dictionary = CustomDictionary(custom_dict)
        text = dictionary.apply_to_text(text)

    labels = pyopenjtalk.extract_fullcontext(text)
    tokens: list[str] = []
    prosody_info: list[ProsodyInfo | None] = []

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            continue
        phoneme = m_ph.group(1)

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                tokens.append("^")
                prosody_info.append(None)
            elif idx == len(labels) - 1:
                tokens.append(_get_question_type(text))
                prosody_info.append(None)
            continue

        # Short pause
        if phoneme == "pau":
            tokens.append("_")
            prosody_info.append(None)
            continue

        # Add phoneme token
        tokens.append(phoneme)

        # Extract A1/A2/A3 values
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)

        if m_a1 and m_a2 and m_a3:
            a1 = int(m_a1.group(1))
            a2 = int(m_a2.group(1))
            a3 = int(m_a3.group(1))
            prosody_info.append(ProsodyInfo(a1=a1, a2=a2, a3=a3))

            # Look-ahead for prosody marks
            if idx < len(labels) - 1:
                m_a2_next = _RE_A2.search(labels[idx + 1])
                a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
            else:
                a2_next = -1

            # Insert accent nucleus mark "]"
            if (a1 == 0) and (a2_next == a2 + 1):
                tokens.append("]")
                prosody_info.append(None)

            # Insert accent phrase boundary "#"
            if (a2 == a3) and (a2_next == 1):
                tokens.append("#")
                prosody_info.append(None)

            # Insert rising mark "["
            if (a2 == 1) and (a2_next == 2):
                tokens.append("[")
                prosody_info.append(None)
        else:
            # No prosody info available
            prosody_info.append(None)

    # Apply context-dependent N phoneme rules
    # Note: This only replaces 'N' with variants in-place, so prosody_info alignment is preserved
    tokens = _apply_n_phoneme_rules(tokens)

    # Map multi-character tokens to single codepoints
    mapped_tokens = map_sequence(tokens)

    return mapped_tokens, prosody_info
