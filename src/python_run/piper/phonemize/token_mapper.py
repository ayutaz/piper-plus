# Token mapper: multi-character phonemes to single codepoint conversion
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

# Private Use Area for dynamic allocation (starting after fixed mappings)
_PUA_START = 0xE090  # Start after Phase 2 prosody tokens
_next = _PUA_START


def register(token: str) -> str:
    """Register *token* and return its single-codepoint replacement."""
    global _next  # noqa: PLW0603
    if token in TOKEN2CHAR:
        return TOKEN2CHAR[token]

    # If already single codepoint, use as-is
    if len(token) == 1:
        TOKEN2CHAR[token] = token
        CHAR2TOKEN[token] = token
        return token

    # Dynamic allocation (if not in fixed mapping)
    ch = chr(_next)
    _next += 1
    TOKEN2CHAR[token] = ch
    CHAR2TOKEN[ch] = token
    return ch


def map_sequence(seq):
    """seq is List[str]. Returns a list with each element replaced by a single character."""
    return [register(t) for t in seq]
