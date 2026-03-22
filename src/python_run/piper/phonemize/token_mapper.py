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
    # Question type markers (Issue #204)
    "?!": 0xE016,  # Emphatic question
    "?.": 0xE017,  # Neutral/rhetorical question
    "?~": 0xE018,  # Tag question
    # N phoneme variants (Issue #207)
    "N_m": 0xE019,  # before m/b/p (bilabial)
    "N_n": 0xE01A,  # before n/t/d/ts/ch (alveolar)
    "N_ng": 0xE01B,  # before k/g (velar)
    "N_uvular": 0xE01C,  # at end or before vowels
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
