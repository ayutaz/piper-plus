from .token_mapper import register


__all__ = ["get_japanese_id_map", "JAPANESE_PHONEMES", "SPECIAL_TOKENS"]

# -----------------------------------------------------------------------------
# Japanese phoneme inventory (Open JTalk style) + prosody/special tokens
# -----------------------------------------------------------------------------
# NOTE: This list purposely errs on the side of *including* more phonemes than
# may actually appear in the corpus so that we avoid "Missing phoneme" warnings
# at学習時.  If some of these tokens never appear they are simply unused.
# -----------------------------------------------------------------------------

# Phase 1: Prosody tokens for enhanced Japanese TTS
PROSODY_TOKENS_PHASE1: list[str] = [
    # Accent type (0-5)
    "<ACC:0>", "<ACC:1>", "<ACC:2>", "<ACC:3>", "<ACC:4>", "<ACC:5>",
    # Mora count (1-10+)
    "<MORA:1>", "<MORA:2>", "<MORA:3>", "<MORA:4>", "<MORA:5>",
    "<MORA:6>", "<MORA:7>", "<MORA:8>", "<MORA:9>", "<MORA:10+>",
    # Part-of-speech (13 types)
    "<POS:ADJ>", "<POS:NOUN>", "<POS:ADV>", "<POS:PRON>", "<POS:CONJ>",
    "<POS:RENTAI>", "<POS:PREFIX>", "<POS:SUFFIX>", "<POS:PART>",
    "<POS:AUX>", "<POS:VERB>", "<POS:SYM>", "<POS:OTHER>",
    # Intonation boundary (0-1)
    "<INTN:0>", "<INTN:1>",
]

# Phase 2: Sentence-level prosody tokens
PROSODY_TOKENS_PHASE2: list[str] = [
    # Intonation phrase (fixed patterns)
    "<IP:1>", "<IP:2>", "<IP:3>", "<IP:4>", "<IP:5+>",
    # Breath group (fixed patterns)
    "<BG:1/1>", "<BG:1/2>", "<BG:2/2>",
]

# Prosody / sentence boundary tokens inserted by `phonemize_japanese`
SPECIAL_TOKENS: list[str] = [
    "_",  # short pause (pau)
    "^",  # BOS
    "$",  # EOS (declarative)
    "?",  # EOS (interrogative)
    "#",  # accent phrase boundary
    "[",  # rising pitch mark (accent phrase head)
    "]",  # falling pitch mark (accent nucleus)
] + PROSODY_TOKENS_PHASE1 + PROSODY_TOKENS_PHASE2  # Phase 1 + Phase 2 prosody tokens

# Core phoneme set – based on Open JTalk definitions and common practice in
# Japanese TTS front-ends (Tacotron, VITS, etc.)
# Long vowels (a:, i:, …) are kept as separate tokens.  Both voiced (lowercase)
# and unvoiced (uppercase) vowels are preserved for linguistic accuracy.
JAPANESE_PHONEMES: list[str] = [
    # voiced vowels
    "a",
    "i",
    "u",
    "e",
    "o",
    # unvoiced vowels (uppercase)
    "A",
    "I",
    "U",
    "E",
    "O",
    "a:",
    "i:",
    "u:",
    "e:",
    "o:",
    # special consonant-centric phonemes
    "N",  # 撥音 (ん)
    "cl",  # 促音 / 終止閉鎖
    "q",  # 促音 (alternate label)
    # plosives + voiced counterparts
    "k",
    "ky",
    "kw",  # くゎ系歴史的仮名・方言
    "g",
    "gy",
    "gw",  # ぐゎ系
    "t",
    "ty",
    "d",
    "dy",
    "p",
    "py",
    "b",
    "by",
    # affricates, fricatives, etc.
    "ch",
    "ts",
    "s",
    "sh",
    "z",
    "j",
    "zy",
    "f",
    "h",
    "hy",
    "v",  # 外来音ヴ用
    # nasals / approximants
    "n",
    "ny",
    "m",
    "my",
    "r",
    "ry",
    "w",
    "y",
]


def get_japanese_id_map() -> dict[str, list[int]]:
    """Return a mapping {symbol: [id]} suitable for Piper config.

    The first token (id=0) is always the pause "_" so that it functions as the
    padding symbol, mirroring the convention used in Piper's English mapping.
    """

    # 各トークンを1文字へ写像
    symbols: list[str] = [register(s) for s in (SPECIAL_TOKENS + JAPANESE_PHONEMES)]
    id_map: dict[str, list[int]] = {}
    for idx, symbol in enumerate(symbols):
        id_map[symbol] = [idx]
    return id_map
