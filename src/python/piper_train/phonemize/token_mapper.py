# 新規追加ファイル: 多文字音素→1文字(コードポイント) 変換を共通提供
# This mapping must match the C++ implementation in openjtalk_phonemize.cpp
# and all language-specific C++ phonemizers (chinese_phonemize.cpp, etc.)

# Fixed PUA mapping table to ensure consistency between Python and C++.
# CRITICAL: Every PUA codepoint hardcoded in C++ MUST appear here.
# Do NOT change assigned codepoints — they are baked into trained models.
FIXED_PUA_MAPPING = {
    # =======================================================================
    # Japanese (JA) — openjtalk_phonemize_utils.cpp
    # =======================================================================
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
    # =======================================================================
    # Multilingual shared
    # =======================================================================
    "rr": 0xE01D,  # Spanish trill r (ES spanish_phonemize.cpp PUA_RR)
    "y_vowel": 0xE01E,  # Close front rounded vowel [y] (ZH pinyin ü, FR lune)
    # 0xE01F reserved (unused gap)
    # =======================================================================
    # Chinese (ZH) — chinese_phonemize.cpp
    # =======================================================================
    # --- Initials (aspirated/affricate) ---
    "p\u02b0": 0xE020,  # pʰ  aspirated bilabial (pinyin p)
    "t\u02b0": 0xE021,  # tʰ  aspirated alveolar (pinyin t)
    "k\u02b0": 0xE022,  # kʰ  aspirated velar (pinyin k)
    "t\u0255": 0xE023,  # tɕ  alveolo-palatal affricate (pinyin j)
    "t\u0255\u02b0": 0xE024,  # tɕʰ  aspirated alveolo-palatal affricate (pinyin q)
    # (ɕ U+0255 is a single codepoint — no PUA needed)
    "t\u0282": 0xE025,  # tʂ  retroflex affricate (pinyin zh)
    "t\u0282\u02b0": 0xE026,  # tʂʰ  aspirated retroflex affricate (pinyin ch)
    # (ʂ U+0282, ɻ U+027B are single codepoints — no PUA needed)
    "ts\u02b0": 0xE027,  # tsʰ  aspirated alveolar affricate (pinyin c)
    # --- Diphthongs ---
    "a\u026a": 0xE028,  # aɪ  (pinyin ai)
    "e\u026a": 0xE029,  # eɪ  (pinyin ei)
    "a\u028a": 0xE02A,  # aʊ  (pinyin ao)
    "o\u028a": 0xE02B,  # oʊ  (pinyin ou)
    # --- Nasal finals ---
    "an": 0xE02C,  # an  (pinyin an)
    "\u0259n": 0xE02D,  # ən  (pinyin en)
    "a\u014b": 0xE02E,  # aŋ  (pinyin ang)
    "\u0259\u014b": 0xE02F,  # əŋ  (pinyin eng)
    "u\u014b": 0xE030,  # uŋ  (pinyin ong)
    # --- i-compound finals (齐齿呼) ---
    "ia": 0xE031,  # ia  (pinyin ia/ya)
    "i\u025b": 0xE032,  # iɛ  (pinyin ie/ye)
    "iou": 0xE033,  # iou (pinyin iu/you)
    "ia\u028a": 0xE034,  # iaʊ (pinyin iao/yao)
    "i\u025bn": 0xE035,  # iɛn (pinyin ian/yan)
    "in": 0xE036,  # in  (pinyin in/yin)
    "ia\u014b": 0xE037,  # iaŋ (pinyin iang/yang)
    "i\u014b": 0xE038,  # iŋ  (pinyin ing/ying)
    "iu\u014b": 0xE039,  # iuŋ (pinyin iong/yong)
    # --- u-compound finals (合口呼) ---
    "ua": 0xE03A,  # ua  (pinyin ua/wa)
    "uo": 0xE03B,  # uo  (pinyin uo/wo)
    "ua\u026a": 0xE03C,  # uaɪ (pinyin uai/wai)
    "ue\u026a": 0xE03D,  # ueɪ (pinyin ui/wei)
    "uan": 0xE03E,  # uan (pinyin uan/wan)
    "u\u0259n": 0xE03F,  # uən (pinyin un/wen)
    "ua\u014b": 0xE040,  # uaŋ (pinyin uang/wang)
    "u\u0259\u014b": 0xE041,  # uəŋ (pinyin ueng/weng)
    # --- ü-compound finals (撮口呼) ---
    "y\u025b": 0xE042,  # yɛ  (pinyin üe/yue)
    "y\u025bn": 0xE043,  # yɛn (pinyin üan/yuan)
    "yn": 0xE044,  # yn  (pinyin ün/yun)
    # --- Syllabic consonants ---
    "\u027b\u0329": 0xE045,  # ɻ̩  syllabic retroflex (zhi/chi/shi/ri)
    # (ɨ U+0268 is a single codepoint — no PUA needed)
    # --- Tone markers ---
    "tone1": 0xE046,  # 阴平 (high level)
    "tone2": 0xE047,  # 阳平 (rising)
    "tone3": 0xE048,  # 上声 (dipping)
    "tone4": 0xE049,  # 去声 (falling)
    "tone5": 0xE04A,  # 轻声 (neutral)
    # =======================================================================
    # Korean (KO) — korean_phonemize.cpp
    # =======================================================================
    # Note: pʰ/tʰ/kʰ/tɕ/tɕʰ are shared with ZH (same PUA codepoints above)
    # --- Tense consonants (fortis / 경음) ---
    "p\u0348": 0xE04B,  # p͈  tense bilabial (ㅃ)
    "t\u0348": 0xE04C,  # t͈  tense alveolar (ㄸ)
    "k\u0348": 0xE04D,  # k͈  tense velar (ㄲ)
    "s\u0348": 0xE04E,  # s͈  tense sibilant (ㅆ)
    "t\u0348\u0255": 0xE04F,  # t͈ɕ  tense alveolo-palatal affricate (ㅉ)
    # --- Unreleased finals (내파음) ---
    "k\u031a": 0xE050,  # k̚  unreleased velar
    "t\u031a": 0xE051,  # t̚  unreleased alveolar
    "p\u031a": 0xE052,  # p̚  unreleased bilabial
    # 0xE053 reserved (unused gap)
    # =======================================================================
    # Spanish (ES) / Portuguese (PT) — spanish_phonemize.cpp, portuguese_phonemize.cpp
    # =======================================================================
    "t\u0283": 0xE054,  # tʃ  voiceless postalveolar affricate (ES ch, PT palatalized t)
    "d\u0292": 0xE055,  # dʒ  voiced postalveolar affricate (EN JH, PT palatalized d)
    # =======================================================================
    # French (FR) — french_phonemize.cpp
    # =======================================================================
    # --- Nasal vowels ---
    "\u025b\u0303": 0xE056,  # ɛ̃  nasal open-mid front unrounded (vin, pain)
    "\u0251\u0303": 0xE057,  # ɑ̃  nasal open back unrounded (France, temps)
    "\u0254\u0303": 0xE058,  # ɔ̃  nasal open-mid back rounded (bon, nom)
    # =======================================================================
    # Swedish (SV)
    # =======================================================================
    # --- Long vowels (母音長 — Complementary Quantity) ---
    "i\u02d0": 0xE059,  # iː  close front unrounded long
    "y\u02d0": 0xE05A,  # yː  close front rounded long
    "e\u02d0": 0xE05B,  # eː  close-mid front unrounded long
    "\u025b\u02d0": 0xE05C,  # ɛː  open-mid front unrounded long
    "\u00f8\u02d0": 0xE05D,  # øː  close-mid front rounded long
    "\u0251\u02d0": 0xE05E,  # ɑː  open back unrounded long
    "o\u02d0": 0xE05F,  # oː  close-mid back rounded long
    "u\u02d0": 0xE060,  # uː  close back rounded long
    "\u0289\u02d0": 0xE061,  # ʉː  close central rounded long
    # 0xE062-0xE063 reserved for SV future expansion (e.g., tonal accent)
}

# Build bidirectional mappings
TOKEN2CHAR = {}
CHAR2TOKEN = {}

# Initialize with fixed mappings
for token, codepoint in FIXED_PUA_MAPPING.items():
    ch = chr(codepoint)
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token

# Private Use Area for dynamic allocation (starting after the last FIXED codepoint)
# 0xE061 is the last used fixed codepoint (SV ʉː).
# 0xE062-0xE063 are reserved for SV future expansion, so dynamic starts at 0xE064.
_PUA_START = 0xE064
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
