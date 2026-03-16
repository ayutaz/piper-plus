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
    # Question type markers (Issue #204)
    "?!": 0xE016,  # Emphatic question - 強調疑問
    "?.": 0xE017,  # Neutral/rhetorical question - 平叙疑問
    "?~": 0xE018,  # Tag question - 確認疑問
    # N phoneme variants (Issue #207)
    "N_m": 0xE019,  # ん before m/b/p (bilabial)
    "N_n": 0xE01A,  # ん before n/t/d/ts/ch (alveolar)
    "N_ng": 0xE01B,  # ん before k/g (velar)
    "N_uvular": 0xE01C,  # ん at end or before vowels
    # Multilingual extensions
    "rr": 0xE01D,  # Spanish trill r (orthographic, not IPA)
    "y_vowel": 0xE01E,  # Close front rounded vowel [y] (ZH pinyin ü, FR lune) - distinct from JA glide "y"
}

# Build bidirectional mappings
TOKEN2CHAR = {}
CHAR2TOKEN = {}

# Initialize with fixed mappings
for token, codepoint in FIXED_PUA_MAPPING.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Private Use Area for dynamic allocation (starting after fixed mappings)
_PUA_START = 0xE020  # Start after the last fixed mapping
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
