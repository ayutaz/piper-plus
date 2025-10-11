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

# Optional jpreprocess support for advanced postprocessing
try:
    import jpreprocess

    HAS_JPREPROCESS = True
    _global_jpreprocess_instance = None
except ImportError:
    HAS_JPREPROCESS = False
    jpreprocess = None  # type: ignore
    _global_jpreprocess_instance = None

from .custom_dict import CustomDictionary
from .japanese_utils import preprocess_japanese_text
from .token_mapper import map_sequence


# Phase 3: Advanced postprocessing functions
try:
    from .ojt_plus import (
        MULTI_READ_KANJI_LIST,
        modify_acc_after_chaining,
        modify_filler_accent,
        modify_kanji_yomi,
        process_odori_features,
        retreat_acc_nuc,
    )

    HAS_ADVANCED_POSTPROCESSING = True
except ImportError:
    HAS_ADVANCED_POSTPROCESSING = False


__all__ = ["phonemize_japanese"]

# Regular expressions reused many times
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")


def _is_question(text: str) -> bool:
    """Return True if *text* ends with a Japanese/ASCII question mark."""
    return text.strip().endswith("?") or text.strip().endswith("？")


def phonemize_japanese(
    text: str,
    custom_dict: CustomDictionary | str | list[str] | None = None,
    use_kabosu_preprocessing: bool = True,
    use_advanced_postprocessing: bool = True,
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
    use_kabosu_preprocessing : bool, optional
        If True, apply enhanced preprocessing (variant kanji normalization,
        English→Katakana conversion). Default: True
    use_advanced_postprocessing : bool, optional
        If True, apply advanced postprocessing (accent nucleus adjustment,
        conjugation accent correction, iteration mark processing).
        Requires jpreprocess. Default: True

    Notes
    -----
    1. We rely on *pyopenjtalk.extract_fullcontext* or *jpreprocess* to obtain full-context labels.
    2. "sil" at the beginning / end of the utterance is converted into ^ / $ or ?.
    3. Enhanced preprocessing (kabosu-core features) is applied first for better accuracy.
    4. Custom dictionary is applied before OpenJTalk processing for better pronunciation.
    5. Advanced postprocessing (Phase 3) is applied when jpreprocess is available.
    """

    # Step 1: Apply enhanced preprocessing (kabosu-core features)
    if use_kabosu_preprocessing:
        text = preprocess_japanese_text(text)

    # Step 2: カスタム辞書を適用
    if custom_dict is not None:
        if isinstance(custom_dict, CustomDictionary):
            dictionary = custom_dict
        else:
            # パスが渡された場合は辞書を作成
            dictionary = CustomDictionary(custom_dict)

        # テキストに辞書を適用
        text = dictionary.apply_to_text(text)

    # Step 3: Get labels (with or without advanced postprocessing)
    if use_advanced_postprocessing and HAS_JPREPROCESS and HAS_ADVANCED_POSTPROCESSING:
        # Use jpreprocess for advanced postprocessing (Phase 3)
        global _global_jpreprocess_instance
        if _global_jpreprocess_instance is None:
            _global_jpreprocess_instance = jpreprocess.jpreprocess()

        # Get NJD features
        njd_features = _global_jpreprocess_instance.run_frontend(text)

        # Apply advanced postprocessing functions (Phase 3 complete)
        # Order is important: follows kabosu-core's apply_postprocessing
        njd_features = retreat_acc_nuc(njd_features)
        njd_features = modify_filler_accent(njd_features)
        njd_features = modify_kanji_yomi(text, njd_features, MULTI_READ_KANJI_LIST)
        njd_features = modify_acc_after_chaining(njd_features)
        njd_features = process_odori_features(
            njd_features, _global_jpreprocess_instance
        )

        # Convert NJD features back to labels
        labels = _global_jpreprocess_instance.make_label(njd_features)
    else:
        # Use standard pyopenjtalk (backward compatible)
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
                tokens.append("?" if _is_question(text) else "$")
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

    # 多文字トークンを1コードポイントへ変換
    return map_sequence(tokens)
