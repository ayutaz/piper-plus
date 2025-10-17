# 新規追加ファイル: 多文字音素→1文字(コードポイント) 変換を共通提供
# This mapping must match the C++ implementation in openjtalk_phonemize.cpp

# Fixed PUA mapping table to ensure consistency between Python and C++
FIXED_PUA_MAPPING = {
    # Long vowels
    "a:": 0xE000,
    "i:": 0xE001,
    "u:": 0xE002,
    "e:": 0xE003,
    "o:": 0xE004,
    # Special consonants
    "cl": 0xE005,
    # Palatalized consonants
    "ky": 0xE006,
    "kw": 0xE007,
    "gy": 0xE008,
    "gw": 0xE009,
    "ty": 0xE00A,
    "dy": 0xE00B,
    "py": 0xE00C,
    "by": 0xE00D,
    # Affricates and special sounds
    "ch": 0xE00E,
    "ts": 0xE00F,
    "sh": 0xE010,
    "zy": 0xE011,
    "hy": 0xE012,
    # Palatalized nasals/liquids
    "ny": 0xE013,
    "my": 0xE014,
    "ry": 0xE015,
}

# Phase 1: Prosody tokens PUA mapping
PROSODY_PUA_MAPPING_PHASE1 = {
    # Accent type (0xE030-0xE035)
    "<ACC:0>": 0xE030,
    "<ACC:1>": 0xE031,
    "<ACC:2>": 0xE032,
    "<ACC:3>": 0xE033,
    "<ACC:4>": 0xE034,
    "<ACC:5>": 0xE035,
    # Mora count (0xE040-0xE049)
    "<MORA:1>": 0xE040,
    "<MORA:2>": 0xE041,
    "<MORA:3>": 0xE042,
    "<MORA:4>": 0xE043,
    "<MORA:5>": 0xE044,
    "<MORA:6>": 0xE045,
    "<MORA:7>": 0xE046,
    "<MORA:8>": 0xE047,
    "<MORA:9>": 0xE048,
    "<MORA:10+>": 0xE049,
    # Part-of-speech (0xE050-0xE05C)
    "<POS:ADJ>": 0xE050,
    "<POS:NOUN>": 0xE051,
    "<POS:ADV>": 0xE052,
    "<POS:PRON>": 0xE053,
    "<POS:CONJ>": 0xE054,
    "<POS:RENTAI>": 0xE055,
    "<POS:PREFIX>": 0xE056,
    "<POS:SUFFIX>": 0xE057,
    "<POS:PART>": 0xE058,
    "<POS:AUX>": 0xE059,
    "<POS:VERB>": 0xE05A,
    "<POS:SYM>": 0xE05B,
    "<POS:OTHER>": 0xE05C,
    # Intonation boundary (0xE060-0xE061)
    "<INTN:0>": 0xE060,
    "<INTN:1>": 0xE061,
}

# Phase 2: Sentence-level prosody tokens PUA mapping
PROSODY_PUA_MAPPING_PHASE2 = {
    # Intonation phrase (0xE070-0xE074)
    "<IP:1>": 0xE070,
    "<IP:2>": 0xE071,
    "<IP:3>": 0xE072,
    "<IP:4>": 0xE073,
    "<IP:5+>": 0xE074,
    # Breath group (0xE080-0xE082)
    "<BG:1/1>": 0xE080,
    "<BG:1/2>": 0xE081,
    "<BG:2/2>": 0xE082,
}

# Phase 4: Context prosody tokens PUA mapping (B,E,G fields)
PROSODY_PUA_MAPPING_PHASE4 = {
    # Previous accent phrase POS (0xE0A0-0xE0AC)
    "<PREV_POS:ADJ>": 0xE0A0,
    "<PREV_POS:NOUN>": 0xE0A1,
    "<PREV_POS:ADV>": 0xE0A2,
    "<PREV_POS:PRON>": 0xE0A3,
    "<PREV_POS:CONJ>": 0xE0A4,
    "<PREV_POS:RENTAI>": 0xE0A5,
    "<PREV_POS:PREFIX>": 0xE0A6,
    "<PREV_POS:SUFFIX>": 0xE0A7,
    "<PREV_POS:PART>": 0xE0A8,
    "<PREV_POS:AUX>": 0xE0A9,
    "<PREV_POS:VERB>": 0xE0AA,
    "<PREV_POS:SYM>": 0xE0AB,
    "<PREV_POS:OTHER>": 0xE0AC,
    # Next accent phrase POS (0xE0B0-0xE0BC)
    "<NEXT_POS:ADJ>": 0xE0B0,
    "<NEXT_POS:NOUN>": 0xE0B1,
    "<NEXT_POS:ADV>": 0xE0B2,
    "<NEXT_POS:PRON>": 0xE0B3,
    "<NEXT_POS:CONJ>": 0xE0B4,
    "<NEXT_POS:RENTAI>": 0xE0B5,
    "<NEXT_POS:PREFIX>": 0xE0B6,
    "<NEXT_POS:SUFFIX>": 0xE0B7,
    "<NEXT_POS:PART>": 0xE0B8,
    "<NEXT_POS:AUX>": 0xE0B9,
    "<NEXT_POS:VERB>": 0xE0BA,
    "<NEXT_POS:SYM>": 0xE0BB,
    "<NEXT_POS:OTHER>": 0xE0BC,
    # Intonation phrase position (0xE0C0-0xE0C4)
    "<INTN_POS:1>": 0xE0C0,
    "<INTN_POS:2>": 0xE0C1,
    "<INTN_POS:3>": 0xE0C2,
    "<INTN_POS:4>": 0xE0C3,
    "<INTN_POS:5+>": 0xE0C4,
    # Previous accent phrase mora count (0xE0D0-0xE0D9)
    "<PREV_MORA:1>": 0xE0D0,
    "<PREV_MORA:2>": 0xE0D1,
    "<PREV_MORA:3>": 0xE0D2,
    "<PREV_MORA:4>": 0xE0D3,
    "<PREV_MORA:5>": 0xE0D4,
    "<PREV_MORA:6>": 0xE0D5,
    "<PREV_MORA:7>": 0xE0D6,
    "<PREV_MORA:8>": 0xE0D7,
    "<PREV_MORA:9>": 0xE0D8,
    "<PREV_MORA:10+>": 0xE0D9,
    # Previous accent phrase accent type (0xE0E0-0xE0E5)
    "<PREV_ACC:0>": 0xE0E0,
    "<PREV_ACC:1>": 0xE0E1,
    "<PREV_ACC:2>": 0xE0E2,
    "<PREV_ACC:3>": 0xE0E3,
    "<PREV_ACC:4>": 0xE0E4,
    "<PREV_ACC:5>": 0xE0E5,
    # Next accent phrase mora count (0xE0F0-0xE0F9) - G field
    "<NEXT_MORA:1>": 0xE0F0,
    "<NEXT_MORA:2>": 0xE0F1,
    "<NEXT_MORA:3>": 0xE0F2,
    "<NEXT_MORA:4>": 0xE0F3,
    "<NEXT_MORA:5>": 0xE0F4,
    "<NEXT_MORA:6>": 0xE0F5,
    "<NEXT_MORA:7>": 0xE0F6,
    "<NEXT_MORA:8>": 0xE0F7,
    "<NEXT_MORA:9>": 0xE0F8,
    "<NEXT_MORA:10+>": 0xE0F9,
    # Next accent phrase accent type (0xE100-0xE105) - G field
    "<NEXT_ACC:0>": 0xE100,
    "<NEXT_ACC:1>": 0xE101,
    "<NEXT_ACC:2>": 0xE102,
    "<NEXT_ACC:3>": 0xE103,
    "<NEXT_ACC:4>": 0xE104,
    "<NEXT_ACC:5>": 0xE105,
}

# Phase 5: Complete field extraction PUA mapping (D,H,K fields)
PROSODY_PUA_MAPPING_PHASE5 = {
    # Previous word POS (0xE120-0xE12C) - D field
    "<PREV_WORD_POS:ADJ>": 0xE120,
    "<PREV_WORD_POS:NOUN>": 0xE121,
    "<PREV_WORD_POS:ADV>": 0xE122,
    "<PREV_WORD_POS:PRON>": 0xE123,
    "<PREV_WORD_POS:CONJ>": 0xE124,
    "<PREV_WORD_POS:RENTAI>": 0xE125,
    "<PREV_WORD_POS:PREFIX>": 0xE126,
    "<PREV_WORD_POS:SUFFIX>": 0xE127,
    "<PREV_WORD_POS:PART>": 0xE128,
    "<PREV_WORD_POS:AUX>": 0xE129,
    "<PREV_WORD_POS:VERB>": 0xE12A,
    "<PREV_WORD_POS:SYM>": 0xE12B,
    "<PREV_WORD_POS:OTHER>": 0xE12C,
    # Next word POS (0xE130-0xE13C) - D field
    "<NEXT_WORD_POS:ADJ>": 0xE130,
    "<NEXT_WORD_POS:NOUN>": 0xE131,
    "<NEXT_WORD_POS:ADV>": 0xE132,
    "<NEXT_WORD_POS:PRON>": 0xE133,
    "<NEXT_WORD_POS:CONJ>": 0xE134,
    "<NEXT_WORD_POS:RENTAI>": 0xE135,
    "<NEXT_WORD_POS:PREFIX>": 0xE136,
    "<NEXT_WORD_POS:SUFFIX>": 0xE137,
    "<NEXT_WORD_POS:PART>": 0xE138,
    "<NEXT_WORD_POS:AUX>": 0xE139,
    "<NEXT_WORD_POS:VERB>": 0xE13A,
    "<NEXT_WORD_POS:SYM>": 0xE13B,
    "<NEXT_WORD_POS:OTHER>": 0xE13C,
    # Bunsetsu position (0xE140-0xE147) - H field
    "<BUNSETSU:1/1>": 0xE140,
    "<BUNSETSU:1/2>": 0xE141,
    "<BUNSETSU:2/2>": 0xE142,
    "<BUNSETSU:1/3>": 0xE143,
    "<BUNSETSU:2/3>": 0xE144,
    "<BUNSETSU:3/3>": 0xE145,
    "<BUNSETSU:1/4>": 0xE146,
    "<BUNSETSU:4/4>": 0xE147,
    # Utterance breath group count (0xE150-0xE153) - K field
    "<UTT_BG:1>": 0xE150,
    "<UTT_BG:2>": 0xE151,
    "<UTT_BG:3>": 0xE152,
    "<UTT_BG:4+>": 0xE153,
    # Utterance intonation phrase count (0xE154-0xE159) - K field
    "<UTT_IP:1>": 0xE154,
    "<UTT_IP:2>": 0xE155,
    "<UTT_IP:3>": 0xE156,
    "<UTT_IP:4>": 0xE157,
    "<UTT_IP:5>": 0xE158,
    "<UTT_IP:6+>": 0xE159,
    # Utterance total mora count (0xE15A-0xE15E) - K field
    "<UTT_MORA:1-10>": 0xE15A,
    "<UTT_MORA:11-20>": 0xE15B,
    "<UTT_MORA:21-30>": 0xE15C,
    "<UTT_MORA:31-50>": 0xE15D,
    "<UTT_MORA:51+>": 0xE15E,
}

# Build bidirectional mappings
TOKEN2CHAR = {}
CHAR2TOKEN = {}

# Initialize with fixed mappings
for token, codepoint in FIXED_PUA_MAPPING.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Initialize with Phase 1 prosody mappings
for token, codepoint in PROSODY_PUA_MAPPING_PHASE1.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Initialize with Phase 2 prosody mappings
for token, codepoint in PROSODY_PUA_MAPPING_PHASE2.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Initialize with Phase 4 prosody mappings
for token, codepoint in PROSODY_PUA_MAPPING_PHASE4.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Initialize with Phase 5 prosody mappings
for token, codepoint in PROSODY_PUA_MAPPING_PHASE5.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Private Use Area for dynamic allocation (starting after fixed mappings)
_PUA_START = 0xE160  # Start after Phase 5 prosody tokens (0xE15E + margin)
_next = _PUA_START


def register(token: str) -> str:
    """Register *token* and return its single-codepoint replacement."""
    global _next
    if token in TOKEN2CHAR:
        return TOKEN2CHAR[token]

    # 既に1コードポイントの場合はそのまま流用
    if len(token) == 1:
        TOKEN2CHAR[token] = token
        CHAR2TOKEN[token] = token
        return token

    # 動的割り当て（固定マッピングに含まれていない場合）
    ch = chr(_next)
    _next += 1
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token
    return ch


def map_sequence(seq):
    """seq は List[str]。各要素を1文字に置換したリストを返す"""
    return [register(t) for t in seq]
