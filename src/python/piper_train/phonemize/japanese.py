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

from .custom_dict import CustomDictionary
from .token_mapper import map_sequence


__all__ = ["phonemize_japanese"]

# Regular expressions reused many times
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")

# Phase 1: Additional regex patterns for prosody extraction
_RE_C = re.compile(r"/C:([^_]+)_([^+]+)\+([^/]+)")
_RE_F = re.compile(r"/F:([^_]+)_([^#]+)#([^_]+)_([^@]+)@([^_]+)_([^\|]+)\|([^_]+)_([^/]+)")

# Part-of-speech mapping (Phase 1)
POS_MAP = {
    "01": "<POS:ADJ>",     # 形容詞
    "02": "<POS:NOUN>",    # 名詞
    "03": "<POS:ADV>",     # 副詞
    "04": "<POS:PRON>",    # 代名詞
    "05": "<POS:CONJ>",    # 接続詞
    "06": "<POS:RENTAI>",  # 連体詞
    "07": "<POS:PREFIX>",  # 接頭辞
    "08": "<POS:SUFFIX>",  # 接尾辞
    "09": "<POS:PART>",    # 助詞
    "10": "<POS:AUX>",     # 助動詞
    "11": "<POS:VERB>",    # 動詞
    "12": "<POS:SYM>",     # 記号
    "13": "<POS:OTHER>",   # その他
    "18": "<POS:NOUN>",    # 固有名詞 → 名詞に統合
    "24": "<POS:PART>",    # 接続助詞 → 助詞に統合
}


def _is_question(text: str) -> bool:
    """Return True if *text* ends with a Japanese/ASCII question mark."""
    return text.strip().endswith("?") or text.strip().endswith("？")


def extract_prosody_features(label: str) -> dict:
    """Extract prosody features from OpenJTalk full-context label (Phase 1).

    Extracts:
    - C field: Part-of-speech information (c1)
    - F field: Accent type (f2), mora count (f1), intonation boundary (f3)

    Parameters
    ----------
    label : str
        OpenJTalk full-context label

    Returns
    -------
    dict
        Dictionary containing prosody features with keys:
        - "pos": Part-of-speech token (if available)
        - "accent": Accent type token (if available)
        - "mora": Mora count token (if available)
        - "intonation": Intonation boundary token (if available)
    """
    features = {}

    # C field: Part-of-speech (only when c1 != "xx")
    m_c = _RE_C.search(label)
    if m_c:
        c1 = m_c.group(1)
        if c1 != "xx":
            features["pos"] = POS_MAP.get(c1, "<POS:OTHER>")

    # F field: Accent type, mora count, intonation boundary
    m_f = _RE_F.search(label)
    if m_f:
        f1 = m_f.group(1)  # Mora count
        f2 = m_f.group(2)  # Accent type
        f3 = m_f.group(3)  # Intonation boundary

        if f1 != "xx":
            mora_count = int(f1)
            if mora_count >= 10:
                features["mora"] = "<MORA:10+>"
            else:
                features["mora"] = f"<MORA:{mora_count}>"

        if f2 != "xx":
            acc_type = int(f2)
            if acc_type >= 5:
                features["accent"] = "<ACC:5>"
            else:
                features["accent"] = f"<ACC:{acc_type}>"

        if f3 != "xx":
            features["intonation"] = f"<INTN:{f3}>"

    return features


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

    # Track accent phrase start to insert prosody tokens only once per phrase
    current_accent_phrase_start = -1

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

        # ------------------------------------------------------------------
        # Phase 1: Extract prosody features before adding phoneme
        # ------------------------------------------------------------------
        # Get accent info first to determine if this is accent phrase start
        m_a1 = _RE_A1.search(label)
        m_a2 = _RE_A2.search(label)
        m_a3 = _RE_A3.search(label)

        if m_a1 and m_a2 and m_a3:
            a2 = int(m_a2.group(1))

            # Insert prosody tokens at accent phrase start (a2==1)
            if a2 == 1 and current_accent_phrase_start != idx:
                current_accent_phrase_start = idx
                features = extract_prosody_features(label)

                # Insert in order: POS → ACC → MORA → INTN
                if "pos" in features:
                    tokens.append(features["pos"])
                if "accent" in features:
                    tokens.append(features["accent"])
                if "mora" in features:
                    tokens.append(features["mora"])
                if "intonation" in features:
                    tokens.append(features["intonation"])

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
        # Note: m_a1, m_a2, m_a3 already extracted above for prosody tokens
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
