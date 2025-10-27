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


__all__ = ["phonemize_japanese", "OpenJTalkProsodyFeatures", "extract_prosody_from_label"]


@dataclass
class OpenJTalkProsodyFeatures:
    """Prosody features extracted from OpenJTalk full-context labels.

    All fields are integers representing linguistic features. Use -1 for unknown/undefined values.
    Total: 16 features covering A~K fields from OpenJTalk labels.
    """
    # A field: Accent information (mora and accent phrase level)
    accent_position: int      # A1: Accent nucleus position (0=flat, 1-N=downstep position)
    mora_position: int        # A2: Position of current mora in accent phrase (1-based)
    mora_total: int          # A3: Total number of mora in accent phrase

    # C field: Part-of-speech information
    pos_major: int           # C1: Major POS category (1=adj, 2=noun, 11=verb, etc.)
    pos_minor: int           # C2: Minor POS category
    pos_detail: int          # C3: Detailed POS category

    # F field: Intonation information
    accent_type: int         # F2: Accent type of accent phrase
    boundary_tone: int       # F5: Boundary tone (pitch pattern at phrase boundary)

    # B, E, G fields: Context information (previous/next accent phrases)
    prev_accent_pos: int     # B1: Accent position of previous accent phrase
    next_accent_pos: int     # E1: Accent position of next accent phrase
    phrase_position: int     # G1: Position of current accent phrase in sentence (1-based)
    phrase_total: int        # G2: Total number of accent phrases in sentence

    # D, H, K fields: Higher-level statistics
    word_length: int         # D2: Number of mora in current word
    bunsetsu_length: int     # H1: Number of mora in current bunsetsu (phrase)
    utterance_length: int    # K2: Total number of mora in utterance

    # Additional field for normalization
    is_special_token: bool = False  # True for BOS/EOS/pause tokens

    def to_list(self) -> list[int]:
        """Convert to list representation for model input (16 integers)."""
        return [
            self.accent_position,
            self.mora_position,
            self.mora_total,
            self.pos_major,
            self.pos_minor,
            self.pos_detail,
            self.accent_type,
            self.boundary_tone,
            self.prev_accent_pos,
            self.next_accent_pos,
            self.phrase_position,
            self.phrase_total,
            self.word_length,
            self.bunsetsu_length,
            self.utterance_length,
            1 if self.is_special_token else 0,
        ]

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


def extract_prosody_from_label(label: str) -> OpenJTalkProsodyFeatures:
    """Extract numerical prosody features from OpenJTalk full-context label.

    Extracts features from A, B, C, D, E, F, G, H, K fields of OpenJTalk labels.
    Returns a 16-dimensional feature vector suitable for neural network input.

    Parameters
    ----------
    label : str
        OpenJTalk full-context label string

    Returns
    -------
    OpenJTalkProsodyFeatures
        Prosody features with 16 integer values (-1 for undefined/unknown)

    Notes
    -----
    OpenJTalk label format (excerpt):
        xx^xx-phoneme+yy=zz/A:a1+a2+a3/B:b1-b2_b3/C:c1_c2+c3/D:d1+d2_d3/
        E:e1_e2!e3_e4-e5/F:f1_f2#f3_f4@f5_f6|f7_f8/G:g1_g2%g3_g4_g5/
        H:h1_h2/I:i1-i2@i3+i4&i5-i6|i7+i8/J:j1_j2/K:k1+k2-k3
    """
    # Helper function to safely parse integer from regex match
    def safe_int(match_obj, group_idx: int, default: int = -1) -> int:
        if match_obj:
            value = match_obj.group(group_idx)
            if value and value != "xx":
                try:
                    return int(value)
                except ValueError:
                    pass
        return default

    # A field: Accent information
    m_a1 = _RE_A1.search(label)
    m_a2 = _RE_A2.search(label)
    m_a3 = _RE_A3.search(label)
    accent_position = safe_int(m_a1, 1, 0)
    mora_position = safe_int(m_a2, 1, 0)
    mora_total = safe_int(m_a3, 1, 0)

    # C field: Part-of-speech (/C:c1_c2+c3/)
    m_c = _RE_C.search(label)
    pos_major = safe_int(m_c, 1, 0)
    pos_minor = safe_int(m_c, 2, 0)
    pos_detail = safe_int(m_c, 3, 0)

    # F field: Intonation (/F:f1_f2#f3_f4@f5_f6|f7_f8/)
    # f1=mora count, f2=accent type, f5=boundary tone
    m_f = _RE_F.search(label)
    accent_type = safe_int(m_f, 2, 0)
    boundary_tone = safe_int(m_f, 5, 0)

    # B field: Previous/next POS and phrase position (/B:b1-b2_b3/)
    # b1=prev accent phrase POS, b2=next accent phrase POS, b3=phrase position in IP
    m_b = _RE_B.search(label)
    prev_pos_b1 = safe_int(m_b, 1, 0)  # Not directly used, we use E1 for prev accent pos
    # For prev_accent_pos, we use E field instead

    # E field: Previous accent phrase info (/E:e1_e2!...)
    # e1=mora count of prev phrase, e2=accent type of prev phrase
    m_e = _RE_E.search(label)
    prev_accent_pos = safe_int(m_e, 2, 0)  # e2: accent type of previous accent phrase

    # G field: Next accent phrase info (/G:g1_g2%...)
    # g1=mora count of next phrase, g2=accent type of next phrase
    m_g = _RE_G.search(label)
    next_accent_pos = safe_int(m_g, 2, 0)  # g2: accent type of next accent phrase

    # For phrase position and total, we need to extract from I field or calculate
    # I field: /I:i1-i2@i3+i4&i5-i6|i7+i8/
    # i3=position of current AP in IP (1-based), i4=total APs in IP
    m_i = _RE_I.search(label)
    phrase_position = safe_int(m_i, 3, 0)
    phrase_total = safe_int(m_i, 4, 0)

    # D field: Word-level POS (/D:d1+d2_d3/)
    # d2=mora count in word
    m_d = _RE_D.search(label)
    word_length = safe_int(m_d, 2, 0)

    # H field: Bunsetsu info (/H:h1_h2/)
    # h1=mora count in bunsetsu
    m_h = _RE_H.search(label)
    bunsetsu_length = safe_int(m_h, 1, 0)

    # K field: Utterance statistics (/K:k1+k2-k3/)
    # k2=total mora in utterance
    m_k = _RE_K.search(label)
    utterance_length = safe_int(m_k, 2, 0)

    return OpenJTalkProsodyFeatures(
        accent_position=accent_position,
        mora_position=mora_position,
        mora_total=mora_total,
        pos_major=pos_major,
        pos_minor=pos_minor,
        pos_detail=pos_detail,
        accent_type=accent_type,
        boundary_tone=boundary_tone,
        prev_accent_pos=prev_accent_pos,
        next_accent_pos=next_accent_pos,
        phrase_position=phrase_position,
        phrase_total=phrase_total,
        word_length=word_length,
        bunsetsu_length=bunsetsu_length,
        utterance_length=utterance_length,
        is_special_token=False,
    )


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
    text: str,
    custom_dict: CustomDictionary | str | list[str] | None = None,
) -> tuple[list[str], list[OpenJTalkProsodyFeatures]]:
    """Convert *text* into phonemes and prosody features separated.

    Returns
    -------
    tuple[list[str], list[OpenJTalkProsodyFeatures]]
        - phonemes: List of phoneme symbols (55-token vocabulary)
        - prosody_features: List of prosody features (16-dimensional vectors)

    Control symbols in phoneme sequence:
    ^   : beginning of sentence
    $/?: end of sentence (choose ? for interrogative)
    _   : short pause (pau)

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
    4. Returns phonemes and prosody features separately for proper neural encoding.
    5. Each phoneme has a corresponding prosody feature vector (16 integers).
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
    phonemes: list[str] = []
    prosody_features: list[OpenJTalkProsodyFeatures] = []

    # Special token prosody (all zeros with is_special_token=True)
    def special_token_prosody() -> OpenJTalkProsodyFeatures:
        return OpenJTalkProsodyFeatures(
            accent_position=0,
            mora_position=0,
            mora_total=0,
            pos_major=0,
            pos_minor=0,
            pos_detail=0,
            accent_type=0,
            boundary_tone=0,
            prev_accent_pos=0,
            next_accent_pos=0,
            phrase_position=0,
            phrase_total=0,
            word_length=0,
            bunsetsu_length=0,
            utterance_length=0,
            is_special_token=True,
        )

    for idx, label in enumerate(labels):
        m_ph = _RE_PHONEME.search(label)
        if not m_ph:
            # Should never happen – skip just in case
            continue
        phoneme = m_ph.group(1)

        # Beginning / end silence handling
        if phoneme == "sil":
            if idx == 0:
                phonemes.append("^")
                prosody_features.append(special_token_prosody())
            elif idx == len(labels) - 1:
                # Always add end marker when we find the last sil
                phonemes.append("?" if _is_question(text) else "$")
                prosody_features.append(special_token_prosody())
            # Skip adding ordinary phoneme for sil
            continue

        # Short pause
        if phoneme == "pau":
            phonemes.append("_")
            prosody_features.append(special_token_prosody())
            continue

        # Extract prosody features from label
        prosody = extract_prosody_from_label(label)

        # Add phoneme and its prosody feature
        phonemes.append(phoneme)
        prosody_features.append(prosody)

    # 多文字音素をそのまま使用（PUA変換なし）
    return phonemes, prosody_features
