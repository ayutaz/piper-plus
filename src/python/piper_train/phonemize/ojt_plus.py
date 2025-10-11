"""Advanced postprocessing functions for Japanese phonemization (Phase 3).

This module provides enhanced postprocessing functions for OpenJTalk/jpreprocess
NJD features, including:
- Accent nucleus position adjustment (retreat_acc_nuc)
- Conjugation accent correction (modify_acc_after_chaining)
- Iteration mark processing (process_odori_features)

Original source:
- kabosu-core (https://github.com/q9uri/kabosu-core)
- pyopenjtalk-plus (https://github.com/VOICEVOX/pyopenjtalk-plus)

License: MIT
Copyright (c) 2018: Ryuichi Yamamoto
"""

from .types import NjdObject


# Optional jpreprocess support
try:
    import jpreprocess

    HAS_JPREPROCESS = True
except ImportError:
    HAS_JPREPROCESS = False
    jpreprocess = None  # type: ignore

# Optional sudachipy for multi-reading kanji disambiguation
try:
    from sudachipy import dictionary, tokenizer

    HAS_SUDACHIPY = True
except ImportError:
    HAS_SUDACHIPY = False

# Optional ONNX-based nani prediction model
try:
    from .yomi_model.nani_predict import predict

    HAS_NANI_PREDICT = True
except ImportError:
    HAS_NANI_PREDICT = False
    predict = None  # type: ignore


# Multi-reading kanji list (70+ characters with multiple readings)
# Source: kabosu-core (https://github.com/q9uri/kabosu-core)
MULTI_READ_KANJI_LIST = [
    "風",
    "何",
    "観",
    "方",
    "出",
    "時",
    "上",
    "下",
    "君",
    "手",
    "嫌",
    "表",
    "対",
    "色",
    "人",
    "前",
    "後",
    "角",
    "金",
    "頭",
    "筆",
    "水",
    "間",
    "棚",
    # From Wikipedia「同形異音語」- commonly confused kanji
    # Excluding '汚','通','臭','辛' where Sudachi is less accurate
    "床",
    "入",
    "来",
    "塗",
    "怒",
    "包",
    "被",
    "開",
    "弾",
    "捻",
    "潜",
    "支",
    "抱",
    "行",
    "降",
    "種",
    "訳",
    "糞",
    # From Wikipedia「同形異音語」- kanji with 3+ readings
    "空",
    "性",
    "体",
    "等",
    "生",
    "止",
    "堪",
    "捩",
    # Additional kanji
    "家",
    "縁",
    "労",
    "中",
    "高",
    "低",
    "気",
    "要",
    "退",
    "面",
    "色",
    "主",
    "術",
    "直",
    "片",
    "緒",
    "小",
    "大",
]  # fmt: skip


__all__ = [
    "retreat_acc_nuc",
    "modify_acc_after_chaining",
    "process_odori_features",
    "modify_filler_accent",
    "modify_kanji_yomi",
    "MULTI_READ_KANJI_LIST",
]


def retreat_acc_nuc(njd_features: list[NjdObject]) -> list[NjdObject]:
    """Adjust accent nucleus position for long vowels, heavy vowels, and moraic nasals.

    When a long vowel (ー), geminate (ッ), or moraic nasal (ン) appears at the
    accent nucleus position, the nucleus shifts to the previous mora.

    Args:
        njd_features: NJD features from run_frontend()

    Returns:
        Modified njd_features with adjusted accent nucleus positions

    Examples:
        "カー" with nucleus on "ー" → nucleus shifts to "カ"
        "マッチ" with nucleus on "ッ" → nucleus shifts to "マ"
    """
    if not njd_features:
        return njd_features

    # Characters inappropriate for accent nucleus
    inappropriate_for_nuclear_chars = ["ー", "ッ", "ン"]
    # Translation table to remove small kana for mora counting
    delete_youon = str.maketrans("", "", "ャュョァィゥェォ")
    phase_len = 0
    acc = 0
    head = njd_features[0]

    for _, njd in enumerate(njd_features):
        # Accent boundary node (chain_flag 0 or -1) contains accent nucleus position
        if njd["chain_flag"] in [0, -1]:
            head = njd
            acc = njd["acc"]
            phase_len = 0

        phase_len += njd["mora_size"]
        pron = njd["pron"].translate(delete_youon)
        if len(pron) == 0:
            pron = njd["pron"]

        if acc > 0:
            if acc <= njd["mora_size"]:
                try:
                    nuc_pron = pron[acc - 1]
                except IndexError:
                    nuc_pron = pron[0]
                if nuc_pron in inappropriate_for_nuclear_chars:
                    head["acc"] += -1
                acc = -1
            else:
                acc = acc - njd["mora_size"]

    return njd_features


def modify_acc_after_chaining(njd_features: list[NjdObject]) -> list[NjdObject]:
    """Modify accent after verb chaining with auxiliary verbs.

    For the special auxiliary "マス" (masu), if the preceding verb has an accent
    nucleus, the nucleus shifts to "ま" (ma).

    Args:
        njd_features: NJD features from run_frontend()

    Returns:
        Modified njd_features with corrected accent positions

    Examples:
        "書きます" → "か[きま]す" (kakimasu: nucleus on "きま")
        "参ります" → "ま[いりま]す" (mairimasu: nucleus on "いりま")
        "書いております" → "[か]いております" (nucleus stays on "か")
    """
    if not njd_features:
        return njd_features

    acc = 0
    is_after_nuc = False
    phase_len = 0
    head = njd_features[0]

    for njd in njd_features:
        # Accent boundary node (chain_flag 0 or -1) contains accent nucleus position
        if njd["chain_flag"] in [0, -1]:
            is_after_nuc = False
            head = njd
            acc = njd["acc"]
            phase_len = 0

        # If acc == 0, no special auxiliary exists
        if acc == 0:
            continue
        elif is_after_nuc:
            if njd["ctype"] == "特殊・マス":
                # Shift nucleus to "ま" in masu
                head["acc"] = (
                    phase_len + 1 if njd["cform"] != "未然形" else phase_len + 2
                )
            elif njd["ctype"] == "特殊・ナイ":
                # Shift nucleus for nai auxiliary
                head["acc"] = phase_len
            elif njd["orig"] in ["れる", "られる", "すぎる", "せる", "させる"]:
                # Handle passive/causative/excessive auxiliaries
                head["acc"] = phase_len + njd["acc"]
            else:
                is_after_nuc = False
                acc = 0
            phase_len += njd["mora_size"]
        else:
            phase_len += njd["mora_size"]
            if acc <= njd["mora_size"]:
                is_after_nuc = True
            else:
                acc = acc - njd["mora_size"]

    return njd_features


def process_odori_features(
    njd_features: list[NjdObject],
    jpreprocess_instance=None,
) -> list[NjdObject]:
    """Process iteration marks (踊り字) and repetition marks appropriately.

    Handles two types of iteration marks:
    1. 々 (odoriji): Repeats the previous kanji
    2. ゝ, ゞ, ヽ, ヾ (ichinojiten): Repeats the previous character

    Args:
        njd_features: NJD features from OpenJTalk morphological analysis
        jpreprocess_instance: jpreprocess instance for re-analyzing kanji.
            Used when re-analyzing the previous kanji for single iteration marks.

    Returns:
        NJD features with corrected readings for iteration marks

    Examples:
        Single kanji iteration:
        - "叙々苑" → "ジョジョエン" (jojoEn)
        - "叙々々苑" → "ジョジョジョエン" (jojojoEn)

        Multiple kanji iteration:
        - "民主々義" → "ミンシュシュギ" (minshushugi)
        - "学生々活" → "ガクセイセイカツ" (gakuseiseikatsu)

        Repetition marks:
        - "こゝろ" → "こころ" (kokoro)
        - "みすゞ" → "みすず" (misuzu)
    """
    if not njd_features:
        return njd_features

    def is_dancing(orig: str) -> bool:
        """Check if string consists only of 々."""
        return set(orig) == {"々"}

    def is_odoriji(orig: str) -> bool:
        """Check if string consists only of repetition marks."""
        return set(orig) <= {"ゝ", "ゞ", "ヽ", "ヾ"}

    def count_odori(orig: str) -> int:
        """Count the number of 々 in the string."""
        return orig.count("々")

    def is_kanji_token(token: NjdObject) -> bool:
        """Check if token contains kanji."""
        if token["pos"] == "記号":
            return False
        return any(0x4E00 <= ord(c) <= 0x9FFF for c in token["orig"])

    def is_single_kanji_token(token: NjdObject) -> bool:
        """Check if token is a single kanji character."""
        return (
            is_kanji_token(token)
            and len(token["orig"]) == 1
            and 0x4E00 <= ord(token["orig"][0]) <= 0x9FFF
        )

    def needs_reanalysis(
        odori_feature: NjdObject,
        prev_feature: NjdObject,
        next_feature: NjdObject | None = None,
    ) -> tuple[bool, str, str | None]:
        """Determine if re-analysis of previous kanji is needed."""
        if count_odori(odori_feature["orig"]) != 1:
            return False, "", None

        if not is_kanji_token(prev_feature):
            return False, "", None

        if len(prev_feature["orig"]) > 1:
            last_char = prev_feature["orig"][-1]
            if 0x4E00 <= ord(last_char) <= 0x9FFF:
                if next_feature is not None and is_single_kanji_token(next_feature):
                    return True, last_char, next_feature["orig"]
                return True, last_char, None

        return False, "", None

    def reanalyze_kanji(kanji: str, jpreprocess_inst) -> list[NjdObject]:
        """Re-analyze kanji to get reading."""
        features = jpreprocess_inst.run_frontend(kanji)
        return features

    def process_odoriji_mark(
        odori_feature: NjdObject,
        prev_feature: NjdObject,
    ) -> NjdObject:
        """Process repetition mark (ゝ, ゞ, ヽ, ヾ)."""
        # Parse previous reading into characters
        prev_read_chars = []
        prev_pron_chars = []

        # Parse katakana character by character
        i = 0
        while i < len(prev_feature["read"]):
            char = prev_feature["read"][i]
            if i + 1 < len(prev_feature["read"]) and prev_feature["read"][i + 1] in {"ャ", "ュ", "ョ", "ァ", "ィ", "ゥ", "ェ", "ォ"}:  # fmt: skip
                prev_read_chars.append(char + prev_feature["read"][i + 1])
                i += 2
            else:
                prev_read_chars.append(char)
                i += 1

        i = 0
        while i < len(prev_feature["pron"]):
            char = prev_feature["pron"][i]
            if i + 1 < len(prev_feature["pron"]) and prev_feature["pron"][i + 1] in {"ャ", "ュ", "ョ", "ァ", "ィ", "ゥ", "ェ", "ォ"}:  # fmt: skip
                prev_pron_chars.append(char + prev_feature["pron"][i + 1])
                i += 2
            else:
                prev_pron_chars.append(char)
                i += 1

        # Get last character reading
        mora_per_char = prev_feature["mora_size"] / len(prev_read_chars)
        prev_read = prev_read_chars[-1]
        prev_pron = prev_pron_chars[-1]
        prev_mora_size = mora_per_char

        # Dakuten mapping
        dakuten_map = {
            "カ": "ガ", "キ": "ギ", "ク": "グ", "ケ": "ゲ", "コ": "ゴ",
            "サ": "ザ", "シ": "ジ", "ス": "ズ", "セ": "ゼ", "ソ": "ゾ",
            "タ": "ダ", "チ": "ヂ", "ツ": "ヅ", "テ": "デ", "ト": "ド",
            "ハ": "バ", "ヒ": "ビ", "フ": "ブ", "ヘ": "ベ", "ホ": "ボ",
            "か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご",
            "さ": "ざ", "し": "じ", "す": "ず", "せ": "ぜ", "そ": "ぞ",
            "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で", "と": "ど",
            "は": "ば", "ひ": "び", "ふ": "ぶ", "へ": "べ", "ほ": "ぼ",
        }  # fmt: skip

        dakuten_reverse_map = {v: k for k, v in dakuten_map.items()}

        # Determine repetition mark type
        odori_char = odori_feature["orig"]
        if odori_char in {"ゝ", "ヽ"}:
            # Without dakuten: use undakuten version
            odori_feature["read"] = dakuten_reverse_map.get(prev_read, prev_read)
            odori_feature["pron"] = dakuten_reverse_map.get(prev_pron, prev_pron)
            odori_feature["mora_size"] = int(prev_mora_size)
        elif odori_char in {"ゞ", "ヾ"}:
            # With dakuten: use dakuten version
            odori_feature["read"] = dakuten_map.get(prev_read, prev_read)
            odori_feature["pron"] = dakuten_map.get(prev_pron, prev_pron)
            odori_feature["mora_size"] = int(prev_mora_size)

        # Change POS to avoid issues
        if odori_feature["pos"] == "記号":
            odori_feature["pos"] = "名詞"
            odori_feature["pos_group1"] = "一般"
            odori_feature["pos_group2"] = "*"
            odori_feature["pos_group3"] = "*"
            odori_feature["ctype"] = "*"
            odori_feature["cform"] = "*"

        return odori_feature

    # Main processing loop
    i = 0
    while i < len(njd_features):
        if is_dancing(njd_features[i]["orig"]):
            # Check if re-analysis is needed for single iteration mark
            if i > 0 and jpreprocess_instance is not None and HAS_JPREPROCESS:
                next_feature = (
                    njd_features[i + 1] if i + 1 < len(njd_features) else None
                )
                needs_reanalysis_flag, target_kanji, next_kanji = needs_reanalysis(
                    njd_features[i], njd_features[i - 1], next_feature
                )
                if needs_reanalysis_flag:
                    if next_kanji is not None:
                        # Re-analyze with following kanji
                        analyzed = reanalyze_kanji(
                            target_kanji + next_kanji, jpreprocess_instance
                        )
                        njd_features[i : i + 2] = analyzed
                        i += len(analyzed)
                        continue
                    else:
                        # Re-analyze last kanji only
                        analyzed = reanalyze_kanji(target_kanji, jpreprocess_instance)
                        njd_features[i] = analyzed[0]
                        njd_features[i]["pos"] = "名詞"
                        njd_features[i]["pos_group1"] = "一般"
                        njd_features[i]["pos_group2"] = "*"
                        njd_features[i]["pos_group3"] = "*"
                        njd_features[i]["ctype"] = "*"
                        njd_features[i]["cform"] = "*"
                        i += 1
                        continue

            # Find consecutive iteration marks
            start = i
            end = i
            total_odori = 0
            while end < len(njd_features) and is_dancing(njd_features[end]["orig"]):
                total_odori += count_odori(njd_features[end]["orig"])
                end += 1

            # Extract previous kanji tokens
            normal_list = []
            j = start - 1
            collected_chars = 0
            while j >= 0:
                if is_kanji_token(njd_features[j]):
                    normal_list.append(njd_features[j])
                    collected_chars += len(njd_features[j]["orig"])
                    if collected_chars >= (2 if total_odori >= 2 else 1):
                        break
                j -= 1
            normal_list.reverse()

            if not normal_list:
                i = end
                continue

            # Determine replacement reading
            is_single_kanji = len(normal_list) == 1 and len(normal_list[0]["orig"]) == 1
            if is_single_kanji:
                base_read = normal_list[0]["read"]
                base_pron = normal_list[0]["pron"]
                base_mora_size = normal_list[0]["mora_size"]
            else:
                base_read = "".join(item["read"] for item in normal_list)
                base_pron = "".join(item["pron"] for item in normal_list)
                base_mora_size = sum(item["mora_size"] for item in normal_list)

            # Process consecutive iteration marks
            for j in range(start, end):
                current_odori = count_odori(njd_features[j]["orig"])
                if is_single_kanji:
                    njd_features[j]["read"] = base_read * current_odori
                    njd_features[j]["pron"] = base_pron * current_odori
                    njd_features[j]["mora_size"] = base_mora_size * current_odori
                else:
                    njd_features[j]["read"] = base_read
                    njd_features[j]["pron"] = base_pron
                    njd_features[j]["mora_size"] = base_mora_size

                if njd_features[j]["pos"] == "記号":
                    njd_features[j]["pos"] = "名詞"
                    njd_features[j]["pos_group1"] = "一般"
                    njd_features[j]["pos_group2"] = "*"
                    njd_features[j]["pos_group3"] = "*"
                    njd_features[j]["ctype"] = "*"
                    njd_features[j]["cform"] = "*"

            i = end

        elif is_odoriji(njd_features[i]["orig"]):
            # Process repetition marks (ゝ, ゞ, ヽ, ヾ)
            if i > 0:
                njd_features[i] = process_odoriji_mark(
                    njd_features[i], njd_features[i - 1]
                )
            i += 1
        else:
            i += 1

    return njd_features


def sudachi_analyze(text: str, multi_read_kanji_list: list[str]) -> list[list[str]]:
    """Analyze multi-reading kanji using Sudachi morphological analyzer.

    Args:
        text: Text to analyze
        multi_read_kanji_list: List of kanji with multiple readings

    Returns:
        List of [kanji, reading] pairs for multi-reading kanji found in text

    Examples:
        "風がこんな風に吹く" → [('風', 'カゼ'), ('風', 'フウ')]
    """
    if not HAS_SUDACHIPY:
        return []

    # Remove long vowel marks for analysis
    text = text.replace("ー", "")

    tokenizer_obj = dictionary.Dictionary().create()
    mode = tokenizer.Tokenizer.SplitMode.C
    m_list = tokenizer_obj.tokenize(text, mode)
    yomi_list = [
        [m.surface(), m.reading_form()]
        for m in m_list
        if m.surface() in multi_read_kanji_list
    ]
    return yomi_list


def modify_filler_accent(njd: list[NjdObject]) -> list[NjdObject]:
    """Modify accent for filler words (フィラー).

    Adjusts accent for filler words like "えー", "あのー" and ensures proper
    accent phrase boundaries after fillers.

    Args:
        njd: NJD features from run_frontend()

    Returns:
        Modified njd_features with corrected filler accents

    Examples:
        Filler with invalid accent → accent set to 0 (flat)
        Noun after filler → accent phrase boundary inserted
    """
    modified_njd = []
    is_after_filler = False

    for features in njd:
        if features["pos"] == "フィラー":
            # If accent position exceeds mora size, reset to flat accent
            if features["acc"] > features["mora_size"]:
                features["acc"] = 0
            is_after_filler = True

        elif is_after_filler:
            # Insert accent phrase boundary after filler if followed by noun
            if features["pos"] == "名詞":
                features["chain_flag"] = 0
            is_after_filler = False

        modified_njd.append(features)

    return modified_njd


def modify_kanji_yomi(
    text: str, pyopen_njd: list[NjdObject], multi_read_kanji_list: list[str]
) -> list[NjdObject]:
    """Modify readings for multi-reading kanji using Sudachi analysis.

    For kanji with multiple possible readings (e.g., 風 = kaze/fū, 何 = nani/nan),
    uses Sudachi morphological analyzer to determine the correct reading based on
    context. Special handling for "何" using ONNX-based prediction model.

    Args:
        text: Original text
        pyopen_njd: NJD features from OpenJTalk/jpreprocess
        multi_read_kanji_list: List of kanji with multiple readings

    Returns:
        Modified njd_features with corrected readings

    Examples:
        "風が強い" → "カゼが強い" (wind, not style)
        "何ですか" → context-based nani/nan determination
    """
    if not HAS_SUDACHIPY:
        # Cannot modify without Sudachi
        return pyopen_njd

    sudachi_yomi = sudachi_analyze(text, multi_read_kanji_list)
    return_njd = []
    pre_dict = None

    for dict_item in reversed(pyopen_njd):
        if dict_item["orig"] in multi_read_kanji_list:
            try:
                correct_yomi = sudachi_yomi.pop()
            except IndexError:
                # No more Sudachi results, return original
                return pyopen_njd

            if correct_yomi[0] != dict_item["orig"]:
                # Mismatch between Sudachi and OpenJTalk, return original
                return pyopen_njd

            elif dict_item["orig"] == "何":
                # Special case: Use ONNX model to predict nani vs nan
                if HAS_NANI_PREDICT and predict is not None:
                    is_read_nan = predict([pre_dict])
                    if is_read_nan == 1:
                        dict_item["pron"] = "ナン"
                        dict_item["read"] = "ナン"
                    else:
                        dict_item["pron"] = "ナニ"
                        dict_item["read"] = "ナニ"
                else:
                    # Fallback: use Sudachi reading
                    dict_item["pron"] = correct_yomi[1]
                    dict_item["read"] = correct_yomi[1]
                return_njd.append(dict_item)

            else:
                # Use Sudachi reading for other multi-reading kanji
                # Special case: 方 (hou) → ホオ for consistency
                if correct_yomi[0] == "方" and correct_yomi[1] == "ホウ":
                    correct_yomi[1] = "ホオ"
                dict_item["pron"] = correct_yomi[1]
                dict_item["read"] = correct_yomi[1]
                return_njd.append(dict_item)
        else:
            return_njd.append(dict_item)

        pre_dict = dict_item

    return_njd.reverse()
    return return_njd
