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

# Phase 2: Sentence-level prosody patterns
_RE_J = re.compile(r"/J:([^_]+)_([^/]+)")
_RE_I = re.compile(r"/I:([^-]+)-([^@]+)@([^+]+)\+([^&]+)&([^-]+)-([^\|]+)\|([^+]+)\+([^/]+)")

# Phase 4: Context prosody patterns
_RE_B = re.compile(r"/B:([^-]+)-([^_]+)_([^/]+)")
_RE_E = re.compile(r"/E:([^_]+)_([^!]+)")
_RE_G = re.compile(r"/G:([^_]+)_([^%]+)")

# Phase 5: Complete field extraction
_RE_D = re.compile(r"/D:([^+]+)\+([^_]+)_([^/]+)")
_RE_H = re.compile(r"/H:([^_]+)_([^/]+)")
_RE_K = re.compile(r"/K:([^+]+)\+([^-]+)-([^/]+)")

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


def extract_prosody_features(label: str, labels: list[str] = None, idx: int = -1) -> dict:
    """Extract prosody features from OpenJTalk full-context label (Phase 1-5).

    Extracts:
    - C field: Part-of-speech information (c1)
    - F field: Accent type (f2), mora count (f1), intonation boundary (f3)
    - J field: Intonation phrase information (j1) - Phase 2
    - I field: Breath group information (i3, i4) - Phase 2
    - B field: Previous/next POS (b1, b2), intonation position (b3) - Phase 4
    - E field: Previous accent phrase info (e1, e2) - Phase 4
    - G field: Next accent phrase info (g1, g2) - Phase 4
    - D field: Word-level previous/next POS (d1, d2) - Phase 5
    - H field: Bunsetsu information (h1, h2) - Phase 5
    - K field: Utterance statistics (k1, k2, k3) - Phase 5

    Parameters
    ----------
    label : str
        OpenJTalk full-context label
    labels : list[str], optional
        Full label list (required for Phase 4-5 context extraction)
    idx : int, optional
        Current label index in labels (required for Phase 4-5 context extraction)

    Returns
    -------
    dict
        Dictionary containing prosody features with keys:
        - "pos": Part-of-speech token (if available)
        - "accent": Accent type token (if available)
        - "mora": Mora count token (if available)
        - "intonation": Intonation boundary token (if available)
        - "intn_phrase": Intonation phrase token (if available) - Phase 2
        - "breath": Breath group token (if available) - Phase 2
        - "prev_pos": Previous POS token (if available) - Phase 4
        - "next_pos": Next POS token (if available) - Phase 4
        - "intn_pos": Intonation position token (if available) - Phase 4
        - "prev_mora": Previous mora count token (if available) - Phase 4
        - "prev_accent": Previous accent type token (if available) - Phase 4
        - "next_mora": Next mora count token (if available) - Phase 4
        - "next_accent": Next accent type token (if available) - Phase 4
        - "prev_word_pos": Previous word POS token (if available) - Phase 5
        - "next_word_pos": Next word POS token (if available) - Phase 5
        - "bunsetsu": Bunsetsu position token (if available) - Phase 5
        - "utt_bg": Utterance breath group count (if available) - Phase 5
        - "utt_ip": Utterance intonation phrase count (if available) - Phase 5
        - "utt_mora": Utterance total mora count (if available) - Phase 5
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

    # Phase 2: Jフィールド - イントネーション句（最初のsilでのみ有効）
    # 注意: Jフィールドは最初のsil（Label 0）でのみ有効値を持つ
    # 他のラベルではJ:xx_xxとなる
    m_j = _RE_J.search(label)
    if m_j:
        j1 = m_j.group(1)
        if j1 != "xx":
            # 固定パターントークンを使用（動的生成を避ける）
            j1_int = int(j1)
            if j1_int >= 5:
                features["intn_phrase"] = "<IP:5+>"
            else:
                features["intn_phrase"] = f"<IP:{j1_int}>"

    # Phase 2: Iフィールド - 呼気段落
    m_i = _RE_I.search(label)
    if m_i:
        i3 = m_i.group(3)  # 現在位置
        i4 = m_i.group(4)  # 総数
        if i3 != "xx" and i4 != "xx":
            # よく使われるパターンのみ定義
            breath_token = f"<BG:{i3}/{i4}>"
            # 固定パターンに含まれるもののみ使用
            if breath_token in ["<BG:1/1>", "<BG:1/2>", "<BG:2/2>"]:
                features["breath"] = breath_token

    # Phase 4: Bフィールド - 前後アクセント句の品詞とイントネーション句内位置
    m_b = _RE_B.search(label)
    if m_b:
        b1 = m_b.group(1)  # 前アクセント句の品詞
        b2 = m_b.group(2)  # 後アクセント句の品詞
        b3 = m_b.group(3)  # イントネーション句内位置

        if b1 != "xx":
            features["prev_pos"] = POS_MAP.get(b1, "<PREV_POS:OTHER>").replace("<POS:", "<PREV_POS:")

        if b2 != "xx":
            features["next_pos"] = POS_MAP.get(b2, "<NEXT_POS:OTHER>").replace("<POS:", "<NEXT_POS:")

        if b3 != "xx":
            b3_int = int(b3)
            if b3_int >= 5:
                features["intn_pos"] = "<INTN_POS:5+>"
            else:
                features["intn_pos"] = f"<INTN_POS:{b3_int}>"

    # Phase 4: Eフィールド - 前アクセント句のモーラ数とアクセント型
    m_e = _RE_E.search(label)
    if m_e:
        e1 = m_e.group(1)  # 前アクセント句のモーラ数
        e2 = m_e.group(2)  # 前アクセント句のアクセント型

        if e1 != "xx":
            e1_int = int(e1)
            if e1_int >= 10:
                features["prev_mora"] = "<PREV_MORA:10+>"
            else:
                features["prev_mora"] = f"<PREV_MORA:{e1_int}>"

        if e2 != "xx":
            e2_int = int(e2)
            if e2_int >= 5:
                features["prev_accent"] = "<PREV_ACC:5>"
            else:
                features["prev_accent"] = f"<PREV_ACC:{e2_int}>"

    # Phase 4: Gフィールド - 次アクセント句のモーラ数とアクセント型
    m_g = _RE_G.search(label)
    if m_g:
        g1 = m_g.group(1)  # 次アクセント句のモーラ数
        g2 = m_g.group(2)  # 次アクセント句のアクセント型

        if g1 != "xx":
            g1_int = int(g1)
            if g1_int >= 10:
                features["next_mora"] = "<NEXT_MORA:10+>"
            else:
                features["next_mora"] = f"<NEXT_MORA:{g1_int}>"

        if g2 != "xx":
            g2_int = int(g2)
            if g2_int >= 5:
                features["next_accent"] = "<NEXT_ACC:5>"
            else:
                features["next_accent"] = f"<NEXT_ACC:{g2_int}>"

    # Phase 5: Dフィールド - 単語レベルの前後品詞
    m_d = _RE_D.search(label)
    if m_d:
        d1 = m_d.group(1)  # 前の単語の品詞
        d2 = m_d.group(2)  # 後の単語の品詞

        if d1 != "xx":
            features["prev_word_pos"] = POS_MAP.get(d1, "<PREV_WORD_POS:OTHER>").replace("<POS:", "<PREV_WORD_POS:")

        if d2 != "xx":
            features["next_word_pos"] = POS_MAP.get(d2, "<NEXT_WORD_POS:OTHER>").replace("<POS:", "<NEXT_WORD_POS:")

    # Phase 5: Hフィールド - 文節情報
    m_h = _RE_H.search(label)
    if m_h:
        h1 = m_h.group(1)  # 文節内位置
        h2 = m_h.group(2)  # 文節内アクセント句総数
        if h1 != "xx" and h2 != "xx":
            bunsetsu_token = f"<BUNSETSU:{h1}/{h2}>"
            # 固定パターンのみ使用（動的生成を避ける）
            if bunsetsu_token in [
                "<BUNSETSU:1/1>", "<BUNSETSU:1/2>", "<BUNSETSU:2/2>",
                "<BUNSETSU:1/3>", "<BUNSETSU:2/3>", "<BUNSETSU:3/3>",
                "<BUNSETSU:1/4>", "<BUNSETSU:4/4>"
            ]:
                features["bunsetsu"] = bunsetsu_token

    # Phase 5: Kフィールド - 発話統計（文頭のsilでのみ有効）
    if idx == 0:  # 最初のsilでのみ
        m_k = _RE_K.search(label)
        if m_k:
            k1 = m_k.group(1)  # 発話内の呼気段落数
            k2 = m_k.group(2)  # 発話内のイントネーション句数
            k3 = m_k.group(3)  # 発話内のモーラ総数

            if k1 != "xx":
                k1_int = int(k1)
                if k1_int >= 4:
                    features["utt_bg"] = "<UTT_BG:4+>"
                else:
                    features["utt_bg"] = f"<UTT_BG:{k1_int}>"

            if k2 != "xx":
                k2_int = int(k2)
                if k2_int >= 6:
                    features["utt_ip"] = "<UTT_IP:6+>"
                else:
                    features["utt_ip"] = f"<UTT_IP:{k2_int}>"

            if k3 != "xx":
                k3_int = int(k3)
                if k3_int <= 10:
                    features["utt_mora"] = "<UTT_MORA:1-10>"
                elif k3_int <= 20:
                    features["utt_mora"] = "<UTT_MORA:11-20>"
                elif k3_int <= 30:
                    features["utt_mora"] = "<UTT_MORA:21-30>"
                elif k3_int <= 50:
                    features["utt_mora"] = "<UTT_MORA:31-50>"
                else:
                    features["utt_mora"] = "<UTT_MORA:51+>"

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
                # Phase 2 & Phase 5: 文頭でイントネーション句・呼気段落・発話統計情報を追加
                features = extract_prosody_features(label, labels, idx)
                if "intn_phrase" in features:
                    tokens.append(features["intn_phrase"])
                if "breath" in features:
                    tokens.append(features["breath"])
                # Phase 5: 発話統計情報
                if "utt_bg" in features:
                    tokens.append(features["utt_bg"])
                if "utt_ip" in features:
                    tokens.append(features["utt_ip"])
                if "utt_mora" in features:
                    tokens.append(features["utt_mora"])
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
                features = extract_prosody_features(label, labels, idx)

                # Phase 5: Insert word-level context tokens first
                if "prev_word_pos" in features:
                    tokens.append(features["prev_word_pos"])
                if "next_word_pos" in features:
                    tokens.append(features["next_word_pos"])

                # Phase 5: Insert bunsetsu info
                if "bunsetsu" in features:
                    tokens.append(features["bunsetsu"])

                # Phase 4: Insert accent phrase context tokens
                # Previous accent phrase info
                if "prev_pos" in features:
                    tokens.append(features["prev_pos"])
                if "prev_mora" in features:
                    tokens.append(features["prev_mora"])
                if "prev_accent" in features:
                    tokens.append(features["prev_accent"])

                # Next accent phrase info
                if "next_pos" in features:
                    tokens.append(features["next_pos"])
                if "next_mora" in features:
                    tokens.append(features["next_mora"])
                if "next_accent" in features:
                    tokens.append(features["next_accent"])

                # Intonation phrase position
                if "intn_pos" in features:
                    tokens.append(features["intn_pos"])

                # Phase 1: Insert current accent phrase info
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
