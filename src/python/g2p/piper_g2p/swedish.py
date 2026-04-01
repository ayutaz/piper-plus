"""Rule-based Swedish G2P (grapheme-to-phoneme) module for piper-g2p.

Converts Swedish text to IPA phonemes using orthographic rules.
No external dependencies required.

Pipeline (per word):
  Stage 2: Loanword suffix detection (-tion/-sion/-age etc.)
  Stage 3: Loanword prefix detection (sch/sh/ch/ph/th)  [in _convert_consonant]
  Stage 4: Native G2P conversion (consonants + vowels)
  Stage 5: Retroflex assimilation (r+C -> retroflex, cascade)
  Stage 6: Stress detection + marker insertion

Known limitations
-----------------
* Dictionary lookup is not included in piper-g2p (available in piper_train).
* The rule-based system handles common Swedish orthography well but may
  produce incorrect results for irregular loanwords not covered by the
  suffix/prefix rules.
"""

from __future__ import annotations

import re
import unicodedata
from enum import IntEnum

from .base import Phonemizer, ProsodyInfo

__all__ = [
    "phonemize_swedish",
    "phonemize_swedish_with_prosody",
    "SwedishPhonemizer",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRONT_VOWELS = frozenset("eiyäö")
BACK_VOWELS = frozenset("aouå")
ALL_VOWELS = FRONT_VOWELS | BACK_VOWELS
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")
PUNCTUATION = set(",.;:!?")

_RE_TOKEN = re.compile(r"([a-zåäöéàüáèëï]+|[,.;:!?]+)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# StressLevel
# ---------------------------------------------------------------------------


class StressLevel(IntEnum):
    NONE = 0
    SECONDARY = 1
    PRIMARY = 2


# ---------------------------------------------------------------------------
# Default consonant -> IPA (single-letter fallback)
# ---------------------------------------------------------------------------

_CONSONANT_DEFAULT: dict[str, str] = {
    "b": "b",
    "c": "k",
    "d": "d",
    "f": "f",
    "g": "\u0261",  # ɡ (IPA, U+0261)
    "h": "h",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "q": "k",
    "r": "r",
    "s": "s",
    "t": "t",
    "v": "v",
    "w": "v",
    "x": "ks",
    "z": "s",
}

# ---------------------------------------------------------------------------
# Exception word lists
# ---------------------------------------------------------------------------

HARD_K_WORDS: frozenset[str] = frozenset(
    {
        "kille",
        "kissa",
        "kiosk",
        "kebab",
        "kennel",
        "keps",
        "ketchup",
        "kick",
        "kilt",
        "kimono",
        "kitsch",
        "kibbutz",
        "kiwi",
        "kilo",
        "kex",
        "kent",
        "kerna",
        "keso",
        "kikare",
        "kines",
        "kinesisk",
        "leker",
        "leken",
        "lekerska",
        "steker",
        "steket",
        "söker",
        "söket",
        "tänker",
        "tänket",
        "dyker",
        "dyket",
        "ryker",
        "röker",
        "röket",
        "smeker",
        "läker",
        "läket",
        "märker",
        "märket",
        "räcker",
        "väcker",
        "viker",
        "stryker",
        "sjunker",
        "sticker",
        "pojke",
        "fröken",
        "onkel",
        "sockel",
        "socker",
        "ocker",
        "märke",
        "mörker",
        "tecken",
        "vacker",
        "naken",
        "säker",
        "enkel",
        "paket",
        "raket",
        "staket",
        "silke",
        "vinkel",
        "skelett",
        "ficka",
        "dricka",
        "docka",
        "backe",
        "flicka",
        "bricka",
        "trycke",
        "skicka",
        "rike",
        "kirke",
    }
)

HARD_K_STEMS: frozenset[str] = frozenset(
    {
        "lek",
        "stek",
        "sök",
        "tänk",
        "dyk",
        "ryk",
        "rök",
        "smek",
        "läk",
        "märk",
        "räck",
        "väck",
        "vik",
        "stryk",
        "sjunk",
        "stick",
        "back",
        "block",
        "trick",
        "tryck",
        "skick",
        "flick",
        "brick",
        "drick",
        "dock",
        "fick",
        "sick",
        "tack",
        "sack",
        "pack",
        "lock",
        "sock",
        "rock",
    }
)

HARD_G_WORDS: frozenset[str] = frozenset(
    {
        "bagel",
        "bageri",
        "bygel",
        "bygge",
        "båge",
        "dager",
        "flygel",
        "gecko",
        "hage",
        "hagel",
        "hunger",
        "lager",
        "läge",
        "läger",
        "mage",
        "nagel",
        "regel",
        "segel",
        "seger",
        "stege",
        "tagel",
        "tegel",
        "tiger",
        "tygel",
        "finger",
        "ängel",
        "fågel",
        "spegel",
        "fogel",
        "duger",
        "flyger",
        "ligger",
        "ljuger",
        "lägger",
        "stiger",
        "suger",
        "tigger",
        "väger",
        "äger",
        "ger",
        "agera",
        "delegera",
        "reagera",
        "segregera",
        "tangera",
        "engagera",
        "arrangera",
        "ignorera",
        "navigera",
        "negera",
        "intrigera",
        "ge",
        "gel",
        "berg",
        "borg",
    }
)

HARD_G_STEMS: frozenset[str] = frozenset(
    {
        "lig",
        "stig",
        "sug",
        "tig",
        "väg",
        "äg",
        "flyg",
        "ljug",
        "lägg",
        "dug",
        "drag",
        "lag",
        "dag",
        "mag",
        "nag",
        "bag",
        "byg",
        "tag",
        "seg",
        "vag",
        "reg",
        "berg",
        "borg",
    }
)

# "o" -> /oː/ instead of default /uː/
O_LONG_AS_OO: frozenset[str] = frozenset(
    {
        "son",
        "mor",
        "bror",
        "lov",
        "dom",
        "ton",
        "zon",
        "fon",
        "ion",
        "ko",
        "lo",
        "ro",
        "tro",
        "bo",
        "god",
        "jord",
        "ord",
        "kol",
        "pol",
        "kontroll",
        "roll",
        "mol",
        "fot",
        "rot",
        "blod",
        "flod",
        "mod",
        "nod",
        "rod",
        "tog",
    }
)

# Words ending in m that use short vowel despite single-C ending
FINAL_M_SHORT_WORDS: frozenset[str] = frozenset(
    {
        "hem",
        "rum",
        "fem",
        "lem",
        "kam",
        "dam",
        "ham",
        "lam",
        "ram",
        "stam",
        "tom",
        "som",
        "dom",
        "dum",
        "gum",
        "glöm",
        "dröm",
        "ström",
    }
)

FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "jag",
        "du",
        "han",
        "hon",
        "vi",
        "de",
        "dem",
        "den",
        "det",
        "sig",
        "sin",
        "min",
        "din",
        "av",
        "i",
        "på",
        "för",
        "med",
        "om",
        "till",
        "från",
        "hos",
        "ur",
        "och",
        "men",
        "att",
        "som",
        "när",
        "var",
        "en",
        "ett",
        "är",
        "har",
        "kan",
        "ska",
        "vill",
        "inte",
    }
)

SK_BACK_VOWEL_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "människa",
        "marskalk",
    }
)

# ---------------------------------------------------------------------------
# Vowel mappings (Complementary Quantity)
# ---------------------------------------------------------------------------

_LONG_VOWEL_MAP: dict[str, str] = {
    "a": "\u0251\u02d0",  # ɑː
    "e": "e\u02d0",  # eː
    "i": "i\u02d0",  # iː
    "o": "u\u02d0",  # uː (default; /oː/ from O_LONG_AS_OO)
    "u": "\u0289\u02d0",  # ʉː
    "y": "y\u02d0",  # yː
    "\u00e5": "o\u02d0",  # å -> oː
    "\u00e4": "\u025b\u02d0",  # ä -> ɛː
    "\u00f6": "\u00f8\u02d0",  # ö -> øː
}

_SHORT_VOWEL_MAP: dict[str, str] = {
    "a": "a",
    "e": "\u025b",  # ɛ
    "i": "\u026a",  # ɪ
    "o": "\u0254",  # ɔ
    "u": "\u0275",  # ɵ
    "y": "\u028f",  # ʏ
    "\u00e5": "\u0254",  # å -> ɔ
    "\u00e4": "\u025b",  # ä -> ɛ
    "\u00f6": "\u0153",  # ö -> œ
}

# ---------------------------------------------------------------------------
# Retroflex assimilation
# ---------------------------------------------------------------------------

RETROFLEX_MAP: dict[str, str] = {
    "t": "\u0288",  # ʈ
    "d": "\u0256",  # ɖ
    "s": "\u0282",  # ʂ
    "n": "\u0273",  # ɳ
    "l": "\u026d",  # ɭ
}

PROPAGATING_RETROFLEXES: frozenset[str] = frozenset(
    {
        "\u0288",
        "\u0256",
        "\u0282",
        "\u0273",  # ʈ ɖ ʂ ɳ
    }
)

# ---------------------------------------------------------------------------
# Stress detection
# ---------------------------------------------------------------------------

UNSTRESSED_PREFIXES: tuple[str, ...] = (
    "för",
    "be",
    "ge",
    "er",
    "an",
)

STRESS_ATTRACTING_SUFFIXES: tuple[str, ...] = (
    "ssion",
    "tion",
    "sion",
    "itet",
    "eri",
    "era",
    "ist",
    "ör",
    "ment",
    "ans",
    "ens",
    "ell",
    "ent",
    "ant",
    "ik",
    "ur",
    "al",
    "ös",
)

# ---------------------------------------------------------------------------
# Unstressed suffix patterns
# ---------------------------------------------------------------------------

_UNSTRESSED_SUFFIXES: tuple[tuple[str, list[str]], ...] = (
    ("ling", ["l", "\u026a", "\u014b"]),  # -ling -> l ɪ ŋ
    ("ning", ["n", "\u026a", "\u014b"]),  # -ning -> n ɪ ŋ
    ("ande", ["a", "n", "d", "\u025b"]),  # -ande -> a n d ɛ
    ("erna", ["\u025b", "r", "n", "a"]),  # -erna -> ɛ r n a
    ("arna", ["a", "r", "n", "a"]),  # -arna -> a r n a
    ("lig", ["l", "\u026a", "\u0261"]),  # -lig -> l ɪ ɡ
    ("en", ["\u025b", "n"]),  # -en -> ɛ n
    ("er", ["\u025b", "r"]),  # -er -> ɛ r
    ("el", ["\u025b", "l"]),  # -el -> ɛ l
    ("et", ["\u025b", "t"]),  # -et -> ɛ t
    ("ar", ["a", "r"]),  # -ar -> a r
    ("or", ["\u0254", "r"]),  # -or -> ɔ r
    ("ig", ["\u026a", "\u0261"]),  # -ig -> ɪ ɡ
    ("ad", ["a", "d"]),  # -ad -> a d
    ("a", ["a"]),  # -a -> a
    ("e", ["\u025b"]),  # -e -> ɛ
)

# ---------------------------------------------------------------------------
# Loanword rules
# ---------------------------------------------------------------------------

_LOANWORD_SUFFIX_RULES: tuple[tuple[str, list[str]], ...] = (
    ("ssion", ["\u0267", "u\u02d0", "n"]),  # -ssion -> ɧ uː n
    ("tion", ["\u0267", "u\u02d0", "n"]),  # -tion -> ɧ uː n
    ("sion", ["\u0267", "u\u02d0", "n"]),  # -sion -> ɧ uː n
    ("age", ["\u0251\u02d0", "\u0267"]),  # -age -> ɑː ɧ
    ("eur", ["\u00f8\u02d0", "r"]),  # -eur -> øː r
    ("eum", ["e\u02d0", "\u0275", "m"]),  # -eum -> eː ɵ m
    ("ium", ["\u026a", "\u0275", "m"]),  # -ium -> ɪ ɵ m
)

# ch exceptions that are /k/ not /ɧ/
CH_EXCEPTIONS_K: frozenset[str] = frozenset(
    {
        "kristus",
        "krist",
        "kron",
        "kronik",
        "och",  # "and" -> /ɔk/ or /ɔ/
    }
)

# Words where -age is Swedish (not French loan)
AGE_NATIVE_WORDS: frozenset[str] = frozenset(
    {
        "bage",
        "lage",
        "sage",
        "dage",
        "mage",
        "hage",
        "tage",
        "klage",
        "frage",
        "plage",
        "drage",
    }
)


# =========================================================================
# Core G2P Functions
# =========================================================================


def _normalize(text: str) -> str:
    """Lowercase, NFC normalize."""
    return unicodedata.normalize("NFC", text.lower())


def _is_vowel(ch: str) -> bool:
    return ch in ALL_VOWELS


def _is_consonant(ch: str) -> bool:
    return ch in CONSONANTS


def _char_at(word: str, pos: int) -> str:
    """Safe character access."""
    return word[pos] if 0 <= pos < len(word) else ""


# ---------------------------------------------------------------------------
# Soft/Hard consonant decision
# ---------------------------------------------------------------------------


def _is_hard_k(word: str) -> bool:
    """Check if k in this word is hard /k/ before a front vowel."""
    if word in HARD_K_WORDS:
        return True
    # Morphological heuristic: strip common suffixes, check stems
    for suffix_len in (3, 2, 1):
        if len(word) > suffix_len:
            stem = word[:-suffix_len]
            if stem in HARD_K_STEMS:
                return True
    return False


def _is_hard_g(word: str) -> bool:
    """Check if g in this word is hard /g/ before a front vowel."""
    if word in HARD_G_WORDS:
        return True
    # -era verb heuristic
    if word.endswith(("era", "erar", "erade")):
        return True
    for suffix_len in (3, 2, 1):
        if len(word) > suffix_len:
            stem = word[:-suffix_len]
            if stem in HARD_G_STEMS:
                return True
    return False


def _convert_consonant(  # noqa: PLR0911
    word: str, pos: int, full_word: str
) -> tuple[list[str], int]:
    """Convert consonant(s) starting at pos.

    Returns (ipa_phonemes, chars_consumed).
    """
    remaining = len(word) - pos
    ch = word[pos]
    next_ch = _char_at(word, pos + 1)

    # === 3-char patterns (highest priority) ===
    if remaining >= 3:
        tri = word[pos : pos + 3]
        if tri == "skj":
            return (["\u0267"], 3)  # ɧ
        if tri == "stj":
            return (["\u0267"], 3)  # ɧ
        if tri == "sch":
            return (["\u0267"], 3)  # ɧ
        if tri == "sng":
            return (["s", "n"], 3)  # simplified
        if tri == "ckj":
            return (["\u0255"], 3)  # ɕ (tj-sound)

    # === 2-char patterns ===
    if remaining >= 2:
        di = word[pos : pos + 2]

        # sk + context
        if di == "sk":
            if (
                remaining >= 3
                and _char_at(word, pos + 2) in FRONT_VOWELS
                and full_word not in SK_BACK_VOWEL_EXCEPTIONS
            ):
                # sk + front vowel -> /ɧ/ (sj-sound)
                return (["\u0267"], 2)  # ɧ
            # sk + back vowel / consonant / word-final -> /sk/
            return (["s", "k"], 2)

        if di == "sj":
            return (["\u0267"], 2)  # ɧ

        if di == "sh":
            return (["\u0267"], 2)  # ɧ (loanword)

        if di == "ch":
            # Check exceptions where ch = /k/
            if full_word in CH_EXCEPTIONS_K:
                return (["k"], 2)
            return (["\u0267"], 2)  # ɧ (loanword)

        if di == "ph":
            return (["f"], 2)  # loanword

        if di == "th":
            return (["t"], 2)  # loanword

        if di == "tj":
            return (["\u0255"], 2)  # ɕ (tj-sound)

        if di == "kj":
            return (["\u0255"], 2)  # ɕ (tj-sound)

        if di == "gn":
            # word-initial gn -> /ɡn/, elsewhere /ŋn/
            if pos == 0:
                return (["\u0261", "n"], 2)  # ɡn
            return (["\u014b", "n"], 2)  # ŋn

        if di == "ng":
            return (["\u014b"], 2)  # ŋ

        if di == "nk":
            return (["\u014b", "k"], 2)  # ŋk

        if di == "ck":
            return (["k"], 2)  # geminate marker (vowel already short)

        if di == "gj" and pos == 0:
            return (["j"], 2)

        if di == "lj" and pos == 0:
            return (["j"], 2)

        if di == "dj" and pos == 0:
            return (["j"], 2)

        if di == "hj" and pos == 0:
            return (["j"], 2)

    # === 1-char patterns ===

    # k + front vowel -> soft /ɕ/ (default) or hard /k/ (exception)
    if ch == "k" and next_ch in FRONT_VOWELS:
        if _is_hard_k(full_word):
            return (["k"], 1)
        return (["\u0255"], 1)  # ɕ

    # g + front vowel -> soft /j/ (default) or hard /ɡ/ (exception)
    if ch == "g" and next_ch in FRONT_VOWELS:
        if _is_hard_g(full_word):
            return (["\u0261"], 1)  # ɡ
        return (["j"], 1)

    # g + back vowel / consonant -> /ɡ/
    if ch == "g":
        return (["\u0261"], 1)  # ɡ

    # c before e/i -> /s/, otherwise /k/
    if ch == "c":
        if next_ch in {"e", "i"}:
            return (["s"], 1)
        return (["k"], 1)

    # x -> /ks/
    if ch == "x":
        return (["k", "s"], 1)

    # Default single consonant
    ipa = _CONSONANT_DEFAULT.get(ch)
    if ipa is not None:
        if len(ipa) > 1:
            return (list(ipa), 1)
        return ([ipa], 1)

    # Unknown consonant: pass through
    return ([ch], 1)


# ---------------------------------------------------------------------------
# Vowel phoneme assignment (Complementary Quantity)
# ---------------------------------------------------------------------------


def _count_following_consonants(word: str, pos: int) -> int:
    """Count consecutive consonant characters after position pos."""
    count = 0
    i = pos + 1
    while i < len(word) and _is_consonant(word[i]):
        count += 1
        i += 1
    return count


def get_vowel_phoneme(  # noqa: PLR0911
    word: str, pos: int, full_word: str, is_stressed: bool
) -> str:
    """Determine vowel phoneme (long or short) at position.

    Complementary Quantity rules:
    - Unstressed -> always short
    - Function word -> always short
    - Geminate / cluster (2+ following consonants) -> short
    - Single consonant or word-final -> long
    - Special: r+C exception preserves length
    - Special: final-m words -> short
    - Special: "o" -> /oː/ if in O_LONG_AS_OO
    """
    ch = word[pos]

    # Unstressed -> short
    if not is_stressed:
        return _SHORT_VOWEL_MAP.get(ch, ch)

    # Function word -> short
    if full_word in FUNCTION_WORDS:
        return _SHORT_VOWEL_MAP.get(ch, ch)

    # Final-m exception -> short
    if full_word in FINAL_M_SHORT_WORDS:
        return _SHORT_VOWEL_MAP.get(ch, ch)

    # Count following consonants
    n_following = _count_following_consonants(word, pos)

    # Word-final vowel -> long
    if n_following == 0 and pos == len(word) - 1:
        vowel = _LONG_VOWEL_MAP.get(ch, ch)
        if ch == "o" and full_word in O_LONG_AS_OO:
            vowel = "o\u02d0"  # oː
        return vowel

    # r + single C exception: vowel stays long (r merges into retroflex)
    # Exception: 'o' is excluded (too ambiguous: kort=/ɔ/, bord=/uː/)
    if n_following == 2 and ch != "o" and pos + 1 < len(word) and word[pos + 1] == "r":
        vowel = _LONG_VOWEL_MAP.get(ch, ch)
        return vowel

    # Geminate / cluster (2+ consonants) -> short
    if n_following >= 2:
        return _SHORT_VOWEL_MAP.get(ch, ch)

    # Single consonant -> long
    vowel = _LONG_VOWEL_MAP.get(ch, ch)
    if ch == "o" and full_word in O_LONG_AS_OO:
        vowel = "o\u02d0"  # oː
    return vowel


# ---------------------------------------------------------------------------
# Retroflex assimilation
# ---------------------------------------------------------------------------


def apply_retroflex(phonemes: list[str]) -> list[str]:
    """Apply retroflex assimilation: r + {t,d,s,n,l} -> retroflex.

    State machine: NORMAL -> R_DETECTED -> CASCADING
    """
    result: list[str] = []
    i = 0
    state = "NORMAL"

    while i < len(phonemes):
        ph = phonemes[i]

        if state == "NORMAL":
            if ph == "r":
                state = "R_DETECTED"
                i += 1
                continue
            result.append(ph)

        elif state == "R_DETECTED":
            if ph == "r":
                # rr -> geminate block, no assimilation
                result.append("r")
                result.append("r")
                state = "NORMAL"
            elif ph in RETROFLEX_MAP:
                retro = RETROFLEX_MAP[ph]
                result.append(retro)
                state = "CASCADING" if retro in PROPAGATING_RETROFLEXES else "NORMAL"
            else:
                # r + non-assimilable -> output r and reprocess
                result.append("r")
                result.append(ph)
                state = "NORMAL"

        elif state == "CASCADING":
            if ph in RETROFLEX_MAP:
                retro = RETROFLEX_MAP[ph]
                result.append(retro)
                if retro not in PROPAGATING_RETROFLEXES:
                    state = "NORMAL"  # ɭ stops cascade
            else:
                result.append(ph)
                state = "NORMAL"

        i += 1

    # Flush pending r
    if state == "R_DETECTED":
        result.append("r")

    return result


# ---------------------------------------------------------------------------
# Stress detection
# ---------------------------------------------------------------------------


def _count_syllables(word: str) -> int:
    """Count syllables by counting vowel clusters."""
    count = 0
    prev_vowel = False
    for ch in word:
        if ch in ALL_VOWELS:
            if not prev_vowel:
                count += 1
            prev_vowel = True
        else:
            prev_vowel = False
    return max(count, 1)


def detect_stress(word: str) -> int:
    """Detect primary stress syllable index (0-based).

    Priority:
    1. Function words -> -1 (no stress)
    2. Monosyllabic -> 0
    3. Stress-attracting suffix -> suffix position
    4. Unstressed prefix -> 2nd syllable
    5. Default -> 1st syllable (0)
    """
    if word in FUNCTION_WORDS:
        return -1

    n_syl = _count_syllables(word)
    if n_syl <= 1:
        return 0

    # Check stress-attracting suffixes
    for suffix in STRESS_ATTRACTING_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            # Count syllables before suffix to find position
            prefix_part = word[: -len(suffix)]
            return _count_syllables(prefix_part)

    # Check unstressed prefixes
    for prefix in UNSTRESSED_PREFIXES:
        if word.startswith(prefix) and len(word) > len(prefix) + 1:
            # Stress on syllable after prefix
            return 1

    # Default: first syllable
    return 0


def _is_ipa_vowel(ph: str) -> bool:
    """Check if a phoneme string represents a vowel."""
    ipa_vowel_chars = frozenset(
        "aeiouyo\u00e5\u00e4\u00f6"
        "\u0251\u025b\u026a\u0254\u028a\u0289\u028f"
        "\u0153\u00f8\u0275"
    )
    return any(c in ipa_vowel_chars for c in ph)


def _insert_stress_marker(phonemes: list[str], stress_syl: int) -> list[str]:
    """Insert primary stress marker before the onset of the stressed syllable."""
    if stress_syl < 0 or not phonemes:
        return phonemes

    # 1. Find the index of the first vowel of the target syllable
    syl_count = 0
    vowel_idx = -1
    prev_was_vowel = False

    for i, ph in enumerate(phonemes):
        is_v = _is_ipa_vowel(ph)
        if is_v and not prev_was_vowel:
            if syl_count == stress_syl:
                vowel_idx = i
                break
            syl_count += 1
            prev_was_vowel = True
        elif not is_v:
            prev_was_vowel = False

    if vowel_idx < 0:
        return phonemes

    # 2. Walk backwards to find syllable onset (consonants before the vowel)
    onset_idx = vowel_idx
    while onset_idx > 0 and not _is_ipa_vowel(phonemes[onset_idx - 1]):
        onset_idx -= 1

    # For syllable 0, onset starts at beginning
    if stress_syl == 0:
        onset_idx = 0

    result = list(phonemes)
    result.insert(onset_idx, "\u02c8")  # primary stress marker
    return result


# ---------------------------------------------------------------------------
# Loanword handling
# ---------------------------------------------------------------------------


def detect_loanword_suffix(word: str) -> tuple[str, list[str]] | None:
    """Check for loanword suffix patterns.

    Returns (stem, suffix_phonemes) or None.
    """
    for suffix, phonemes in _LOANWORD_SUFFIX_RULES:
        if word.endswith(suffix) and len(word) > len(suffix):
            # Check native exceptions for -age
            if suffix == "age" and word in AGE_NATIVE_WORDS:
                continue
            stem = word[: -len(suffix)]
            return (stem, phonemes)
    return None


# ---------------------------------------------------------------------------
# Native word conversion (Stage 4)
# ---------------------------------------------------------------------------


def _convert_word_native(word: str, full_word: str, stressed_syl: int) -> list[str]:
    """Convert a word using native Swedish G2P rules."""
    phonemes: list[str] = []
    pos = 0
    syl_count = 0
    prev_was_vowel = False

    while pos < len(word):
        ch = word[pos]

        if ch in ALL_VOWELS:
            if not prev_was_vowel:
                is_stressed = syl_count == stressed_syl and stressed_syl >= 0
                vowel = get_vowel_phoneme(word, pos, full_word, is_stressed)
                phonemes.append(vowel)
                syl_count += 1
            else:
                # Consecutive vowel in same syllable (rare in Swedish)
                vowel = _SHORT_VOWEL_MAP.get(ch, ch)
                phonemes.append(vowel)
            prev_was_vowel = True
            pos += 1

        elif ch in CONSONANTS:
            prev_was_vowel = False
            ipa_list, consumed = _convert_consonant(word, pos, full_word)
            phonemes.extend(ipa_list)
            pos += consumed

        else:
            # Skip unknown characters
            prev_was_vowel = False
            pos += 1

    return phonemes


# ---------------------------------------------------------------------------
# Full word pipeline (Stage 2-6)
# ---------------------------------------------------------------------------


def _phonemize_word(word: str) -> list[str]:
    """Full G2P pipeline for a single word.

    Stage 2: Loanword suffix detection
    Stage 4: Native G2P conversion
    Stage 5: Retroflex assimilation
    Stage 6: Stress detection + marker insertion
    """
    if not word:
        return []

    # Detect stress syllable
    stressed_syl = detect_stress(word)

    # Stage 2: Check loanword suffix
    loanword = detect_loanword_suffix(word)
    if loanword is not None:
        stem, suffix_phonemes = loanword
        # Stem syllables are before the suffix stress -> unstressed
        stem_syl_count = _count_syllables(stem)
        stem_stressed = -1 if stressed_syl >= stem_syl_count else stressed_syl
        stem_phonemes = _convert_word_native(stem, word, stem_stressed)
        # Combine stem + suffix
        raw_phonemes = stem_phonemes + suffix_phonemes
    else:
        # Stage 4: Native conversion
        raw_phonemes = _convert_word_native(word, word, stressed_syl)

    # Stage 5: Retroflex assimilation
    phonemes = apply_retroflex(raw_phonemes)

    # Stage 6: Stress markers
    phonemes = _insert_stress_marker(phonemes, stressed_syl)

    return phonemes


# =========================================================================
# Public API (text-level)
# =========================================================================


def phonemize_swedish_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Swedish text to phoneme list with prosody features.

    Returns
    -------
    (phonemes, prosody_info_list)
        a1=0, a2=stress (0/1/2), a3=word phoneme count.
        Unlike piper_train, NO PUA mapping is applied (IPA-first design).
    """
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    for token in tokens:
        if all(c in PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue

        if need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        word_phonemes = _phonemize_word(token)

        # Count non-stress phonemes for a3
        word_phoneme_count = sum(
            1 for p in word_phonemes if p not in ("\u02c8", "\u02cc")
        )

        for ph in word_phonemes:
            if ph == "\u02c8":
                a2 = 2  # primary stress
            elif ph == "\u02cc":
                a2 = 1  # secondary stress
            else:
                a2 = 0
            phonemes.append(ph)
            prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))

        need_space = True

    return phonemes, prosody_list


def phonemize_swedish(text: str) -> list[str]:
    """Convert Swedish text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_swedish_with_prosody(text)
    return phonemes


# =========================================================================
# SwedishPhonemizer (Phonemizer ABC)
# =========================================================================


class SwedishPhonemizer(Phonemizer):
    """Swedish phonemizer using rule-based G2P.

    No external dependencies required. Uses orthographic rules,
    exception word lists, loanword suffix detection, and retroflex
    assimilation.
    """

    @property
    def language_code(self) -> str:
        return "sv"

    def phonemize(self, text: str) -> list[str]:
        text = self._sanitize_input(text)
        if not text:
            return []
        return phonemize_swedish(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_swedish_with_prosody(text)
