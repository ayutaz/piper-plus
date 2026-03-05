"""Chinese (Mandarin) phoneme inventory for Piper TTS.

Only phonemes unique to Chinese that are NOT already present in the
JA + EN inventories are listed here. Shared phonemes are deduplicated
by multilingual_id_map.py.
"""

from .token_mapper import register


__all__ = ["CHINESE_PHONEMES"]

# -------------------------------------------------------------------------
# Chinese-unique phonemes (IPA and tone markers)
# -------------------------------------------------------------------------
# Shared with JA/EN (NOT listed here):
#   a, e, i, o, u — vowels (JA)
#   b, d, f, g, h, j, k, l, m, n, p, s, t, w, z — consonants (JA/EN)
#   ts — affricate (JA)
#   ŋ — velar nasal (EN)
#   ə, ɛ, ɪ, ʊ — vowels (EN)
# -------------------------------------------------------------------------

CHINESE_PHONEMES: list[str] = [
    # --- Initials (声母) unique to Chinese ---
    # Aspirated plosives
    "pʰ",    # pinyin p (aspirated bilabial)
    "tʰ",    # pinyin t (aspirated alveolar)
    "kʰ",    # pinyin k (aspirated velar)
    # Alveolo-palatal consonants
    "tɕ",    # pinyin j (voiceless alveolo-palatal affricate)
    "tɕʰ",   # pinyin q (aspirated alveolo-palatal affricate)
    "ɕ",     # pinyin x (voiceless alveolo-palatal fricative)
    # Retroflex consonants
    "tʂ",    # pinyin zh (voiceless retroflex affricate)
    "tʂʰ",   # pinyin ch (aspirated retroflex affricate)
    "ʂ",     # pinyin sh (voiceless retroflex fricative)
    "ɻ",     # pinyin r (voiced retroflex approximant)
    # Aspirated alveolar affricate
    "tsʰ",   # pinyin c
    # Velar fricative
    "x",     # pinyin h (voiceless velar fricative)

    # --- Vowels unique to Chinese ---
    "ɤ",       # pinyin e (close-mid back unrounded)
    "y_vowel", # Close front rounded vowel [y] (pinyin ü) — "y_vowel" avoids collision with JA glide "y"

    # --- Diphthongs (compound finals as single tokens) ---
    "aɪ",    # pinyin ai
    "eɪ",    # pinyin ei
    "aʊ",    # pinyin ao
    "oʊ",    # pinyin ou

    # --- Nasal finals (as single tokens) ---
    "an",    # pinyin an
    "ən",    # pinyin en
    "aŋ",    # pinyin ang
    "əŋ",    # pinyin eng
    "uŋ",    # pinyin ong

    # --- Retroflex final / rhotacized schwa ---
    "ɚ",    # pinyin er and erhua (rhotacized schwa, U+025A)

    # --- i- (齐齿呼) compound finals ---
    "ia",    # pinyin ia/ya
    "iɛ",    # pinyin ie/ye
    "iou",   # pinyin iu/you
    "iaʊ",   # pinyin iao/yao
    "iɛn",   # pinyin ian/yan
    "in",    # pinyin in/yin
    "iaŋ",   # pinyin iang/yang
    "iŋ",    # pinyin ing/ying
    "iuŋ",   # pinyin iong/yong

    # --- u- (合口呼) compound finals ---
    "ua",    # pinyin ua/wa
    "uo",    # pinyin uo/wo
    "uaɪ",   # pinyin uai/wai
    "ueɪ",   # pinyin ui/wei
    "uan",   # pinyin uan/wan
    "uən",   # pinyin un/wen
    "uaŋ",   # pinyin uang/wang
    "uəŋ",   # pinyin ueng/weng

    # --- ü- (撮口呼) compound finals ---
    "yɛ",    # pinyin üe/yue
    "yɛn",   # pinyin üan/yuan
    "yn",    # pinyin ün/yun

    # --- Syllabic consonants ---
    "ɻ̩",     # zhi/chi/shi/ri syllabic vowel (retroflex)
    "ɨ",     # zi/ci/si syllabic vowel (alveolar)

    # --- Tone markers (声调) ---
    "tone1",  # 阴平 (˥ high level)
    "tone2",  # 阳平 (˧˥ rising)
    "tone3",  # 上声 (˨˩˦ dipping)
    "tone4",  # 去声 (˥˩ falling)
    "tone5",  # 轻声 (neutral tone)
]

# Register multi-character tokens to get PUA codepoints
for _token in CHINESE_PHONEMES:
    register(_token)
