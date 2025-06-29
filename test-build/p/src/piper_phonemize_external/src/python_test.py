from collections import Counter

from piper_phonemize import (
    phonemize_espeak,
    phonemize_codepoints,
    phoneme_ids_espeak,
    phoneme_ids_codepoints,
    get_codepoints_map,
    get_espeak_map,
    get_max_phonemes,
    tashkeel_run,
)

# -----------------------------------------------------------------------------

# Maximum number of phonemes in a Piper model.
# Larger than necessary to accomodate future phonemes.
assert get_max_phonemes() == 256

# -----------------------------------------------------------------------------

de_phonemes = phonemize_espeak("licht!", "de")

# "lˈɪçt!" where "ç" is decomposed into two codepoints
assert de_phonemes == [["l", "ˈ", "ɪ", "c", "̧", "t", "!"]], de_phonemes

# phoneme -> [id, ...]
espeak_map = get_espeak_map()
for phoneme in de_phonemes[0]:
    assert phoneme in espeak_map, f"Missing phoneme: {phoneme}"

de_ids = phoneme_ids_espeak(de_phonemes[0])

# 0 = pad
# 1 = bos
# 2 = eos
# 4 = !
assert de_ids == [1, 0, 24, 0, 120, 0, 74, 0, 16, 0, 140, 0, 32, 0, 4, 0, 2]

# Verify missing phoneme counts
missing_phonemes: Counter[str] = Counter()
assert phoneme_ids_espeak(["\u0000", "\u0000", "\u0000"], missing_phonemes) == [1, 0, 2]
assert missing_phonemes == {"\u0000": 3}, missing_phonemes

# -----------------------------------------------------------------------------

# Capitalization is required to get espeak to split the sentences.
en_phonemes = phonemize_espeak("Test 1. Test2.", "en-us")
assert en_phonemes == [
    ["t", "ˈ", "ɛ", "s", "t", " ", "w", "ˈ", "ʌ", "n", "."],
    ["t", "ˈ", "ɛ", "s", "t", " ", "t", "ˈ", "u", "ː", "."],
], en_phonemes

# -----------------------------------------------------------------------------

codepoints_map = get_codepoints_map()
assert "uk" in codepoints_map, "uk not supported"
uk_phonemes = phonemize_codepoints("ВЕСЕ́ЛКА")

# case folding / NFD normalization is automatically applied
assert uk_phonemes == [["в", "е", "с", "е", "́", "л", "к", "а"]]
for phoneme in uk_phonemes[0]:
    assert phoneme in codepoints_map["uk"]

uk_ids = phoneme_ids_codepoints("uk", uk_phonemes[0])

# 0 = pad
# 1 = bos
# 2 = eos
assert uk_ids == [1, 0, 14, 0, 18, 0, 33, 0, 18, 0, 45, 0, 27, 0, 26, 0, 12, 0, 2]

# Casing can be changed, but this will break models trained with the default ("fold").
assert phonemize_codepoints("ВЕСЕ́ЛКА", casing="upper") == [
    ["В", "Е", "С", "Е", "́", "Л", "К", "А"]
]

# Verify missing phoneme counts
missing_phonemes = Counter()
assert phoneme_ids_codepoints(
    "uk", ["\u0000", "\u0000", "\u0000"], missing_phonemes
) == [1, 0, 2]
assert missing_phonemes == {"\u0000": 3}, missing_phonemes

# -----------------------------------------------------------------------------

# Test Arabic with libtashkeel (https://github.com/mush42/libtashkeel)

expected_text = "مَرْحَبًا"
actual_text = tashkeel_run("مرحبا")
assert actual_text == expected_text, f"Expected {expected_text}, got {actual_text}"

# -----------------------------------------------------------------------------

print("OK")
