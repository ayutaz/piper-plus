from .token_mapper import register


__all__ = ["get_japanese_id_map", "JAPANESE_PHONEMES", "SPECIAL_TOKENS"]

# -----------------------------------------------------------------------------
# Japanese phoneme inventory (Open JTalk style) + prosody/special tokens
# -----------------------------------------------------------------------------
# NOTE: This list purposely errs on the side of *including* more phonemes than
# may actually appear in the corpus so that we avoid "Missing phoneme" warnings
# at学習時.  If some of these tokens never appear they are simply unused.
# -----------------------------------------------------------------------------

# Control tokens inserted by `phonemize_japanese`
SPECIAL_TOKENS: list[str] = [
    "_",  # short pause (pau)
    "^",  # BOS
    "$",  # EOS (declarative)
    "?",  # EOS (interrogative)
]

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

    Returns baseline phoneme-only mapping with 55 tokens (4 control + 51 phonemes).
    No prosody tokens, no PUA conversion, no accent marks.
    """

    # Baseline: 韻律トークンなし（純粋な音素のみ）
    # アクセント記号なし（#, [, ]）、PUA変換なし
    # 多文字音素（ch, sh, ny等）をそのまま使用
    symbols: list[str] = SPECIAL_TOKENS + JAPANESE_PHONEMES

    id_map: dict[str, list[int]] = {}
    for idx, symbol in enumerate(symbols):
        id_map[symbol] = [idx]
    return id_map
