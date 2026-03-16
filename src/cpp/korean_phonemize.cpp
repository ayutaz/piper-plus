// Korean phonemizer — C++ port of korean.py Hangul decomposition + IPA mapping.
//
// Converts Korean text to IPA phonemes by decomposing Hangul syllable blocks
// into jamo (initial, medial, final) and mapping each to IPA tokens.
// Multi-codepoint IPA tokens use PUA codepoints matching token_mapper.py.
//
// Without g2pk2, only basic liaison (연음화) is applied as a phonological rule.
// No external dependencies beyond utf8.h.

#include "korean_phonemize.hpp"
#include "utf8.h"

#include <string>
#include <vector>

namespace piper {
namespace {

// ---------------------------------------------------------------------------
// Hangul syllable block range (U+AC00 .. U+D7A3)
// ---------------------------------------------------------------------------
constexpr char32_t HANGUL_START = 0xAC00;
constexpr char32_t HANGUL_END   = 0xD7A3;

// Decomposition constants
constexpr int N_INITIALS = 19;
constexpr int N_MEDIALS  = 21;
constexpr int N_FINALS   = 28;

// ---------------------------------------------------------------------------
// Jamo decomposition result
// ---------------------------------------------------------------------------
struct Jamo {
    int initial;  // 0..18
    int medial;   // 0..20
    int final_;   // 0..27 (0 = no final consonant)
};

static bool isHangulSyllable(char32_t ch) {
    return ch >= HANGUL_START && ch <= HANGUL_END;
}

static Jamo decompose(char32_t ch) {
    int code = static_cast<int>(ch - HANGUL_START);
    return {
        code / (N_MEDIALS * N_FINALS),
        (code % (N_MEDIALS * N_FINALS)) / N_FINALS,
        code % N_FINALS
    };
}

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character IPA tokens
// Must match token_mapper.py dynamic allocation order (ZH first, then KO).
// ---------------------------------------------------------------------------

// Aspirated consonants (shared with Chinese — registered by zh_id_map.py)
constexpr Phoneme PUA_PH   = 0xE020; // pʰ
constexpr Phoneme PUA_TH   = 0xE021; // tʰ
constexpr Phoneme PUA_KH   = 0xE022; // kʰ

// Affricates (shared with Chinese)
constexpr Phoneme PUA_TC   = 0xE023; // tɕ
constexpr Phoneme PUA_TCH  = 0xE024; // tɕʰ

// Tense consonants (Korean-only — registered by ko_id_map.py)
constexpr Phoneme PUA_PP   = 0xE04B; // p͈
constexpr Phoneme PUA_TT   = 0xE04C; // t͈
constexpr Phoneme PUA_KK   = 0xE04D; // k͈
constexpr Phoneme PUA_SS   = 0xE04E; // s͈
constexpr Phoneme PUA_TTCH = 0xE04F; // t͈ɕ

// Unreleased finals (Korean-only)
constexpr Phoneme PUA_K_UNREL = 0xE050; // k̚
constexpr Phoneme PUA_T_UNREL = 0xE051; // t̚
constexpr Phoneme PUA_P_UNREL = 0xE052; // p̚

// Single IPA codepoints used in output
constexpr Phoneme IPA_FLAP    = 0x027E; // ɾ alveolar flap (ㄹ initial)
constexpr Phoneme IPA_ENG     = 0x014B; // ŋ velar nasal (ㅇ coda)
constexpr Phoneme IPA_OPEN_E  = 0x025B; // ɛ open-mid front unrounded (ㅐ)
constexpr Phoneme IPA_OPEN_MID_BACK = 0x028C; // ʌ open-mid back unrounded (ㅓ)
constexpr Phoneme IPA_CLOSE_BACK_UNR = 0x026F; // ɯ close back unrounded (ㅡ)
constexpr Phoneme IPA_VELAR_APPROX   = 0x0270; // ɰ velar approximant (ㅢ)

// ---------------------------------------------------------------------------
// Initial consonants (초성) — 19 entries, index → phoneme(s)
//
// Each entry is a small fixed-size array. A value of 0 means "no phoneme"
// (used for ㅇ which is silent in initial position).
// ---------------------------------------------------------------------------
struct InitialEntry {
    Phoneme ph;   // single phoneme (0 = silent)
};

static const InitialEntry INITIAL_TABLE[N_INITIALS] = {
    { 'k'       },  //  0: ㄱ
    { PUA_KK    },  //  1: ㄲ (tense)
    { 'n'       },  //  2: ㄴ
    { 't'       },  //  3: ㄷ
    { PUA_TT    },  //  4: ㄸ (tense)
    { IPA_FLAP  },  //  5: ㄹ
    { 'm'       },  //  6: ㅁ
    { 'p'       },  //  7: ㅂ
    { PUA_PP    },  //  8: ㅃ (tense)
    { 's'       },  //  9: ㅅ
    { PUA_SS    },  // 10: ㅆ (tense)
    { 0         },  // 11: ㅇ (silent in initial)
    { PUA_TC    },  // 12: ㅈ
    { PUA_TTCH  },  // 13: ㅉ (tense)
    { PUA_TCH   },  // 14: ㅊ (aspirated)
    { PUA_KH    },  // 15: ㅋ (aspirated)
    { PUA_TH    },  // 16: ㅌ (aspirated)
    { PUA_PH    },  // 17: ㅍ (aspirated)
    { 'h'       },  // 18: ㅎ
};

// ---------------------------------------------------------------------------
// Medial vowels (중성) — 21 entries, index → 1-2 phonemes
//
// Diphthongs produce glide + vowel (2 phonemes).
// ---------------------------------------------------------------------------
struct MedialEntry {
    Phoneme ph[2]; // up to 2 phonemes; ph[1]==0 means single phoneme
};

static const MedialEntry MEDIAL_TABLE[N_MEDIALS] = {
    { { 'a', 0               } },  //  0: ㅏ
    { { IPA_OPEN_E, 0        } },  //  1: ㅐ
    { { 'j', 'a'             } },  //  2: ㅑ
    { { 'j', IPA_OPEN_E      } },  //  3: ㅒ
    { { IPA_OPEN_MID_BACK, 0 } },  //  4: ㅓ
    { { 'e', 0               } },  //  5: ㅔ
    { { 'j', IPA_OPEN_MID_BACK } }, // 6: ㅕ
    { { 'j', 'e'             } },  //  7: ㅖ
    { { 'o', 0               } },  //  8: ㅗ
    { { 'w', 'a'             } },  //  9: ㅘ
    { { 'w', IPA_OPEN_E      } },  // 10: ㅙ
    { { 'w', 'e'             } },  // 11: ㅚ (modern Seoul: [we])
    { { 'j', 'o'             } },  // 12: ㅛ
    { { 'u', 0               } },  // 13: ㅜ
    { { 'w', IPA_OPEN_MID_BACK } }, // 14: ㅝ
    { { 'w', 'e'             } },  // 15: ㅞ
    { { 'w', 'i'             } },  // 16: ㅟ
    { { 'j', 'u'             } },  // 17: ㅠ
    { { IPA_CLOSE_BACK_UNR, 0 } }, // 18: ㅡ
    { { IPA_VELAR_APPROX, 'i' } }, // 19: ㅢ
    { { 'i', 0               } },  // 20: ㅣ
};

// ---------------------------------------------------------------------------
// Final consonants (종성) — 28 entries, index → single phoneme
//
// Finals are neutralized to 7 surface forms: k̚, t̚, p̚, n, m, l, ŋ.
// Complex finals (겹받침) are simplified to their representative sound.
// Index 0 = no final consonant (phoneme value 0).
// ---------------------------------------------------------------------------
struct FinalEntry {
    Phoneme ph;          // 0 = no final
    int liaisonInitial;  // initial index to use for liaison (-1 = none)
};

// Liaison mapping: which initial consonant index the final "becomes" when
// followed by ㅇ (silent initial). -1 means no liaison or index 0 (none).
// This captures the most common liaison pattern (연음화).
static const FinalEntry FINAL_TABLE[N_FINALS] = {
    { 0,              -1 },  //  0: (none)
    { PUA_K_UNREL,     0 },  //  1: ㄱ -> liaison: ㄱ (initial 0)
    { PUA_K_UNREL,     1 },  //  2: ㄲ -> liaison: ㄲ (initial 1)
    { PUA_K_UNREL,     9 },  //  3: ㄳ -> liaison: ㅅ (initial 9)
    { 'n',            -1 },  //  4: ㄴ
    { 'n',            12 },  //  5: ㄵ -> liaison: ㅈ (initial 12)
    { 'n',            -1 },  //  6: ㄶ (ㄴ+ㅎ -> n, h dropped)
    { PUA_T_UNREL,     3 },  //  7: ㄷ -> liaison: ㄷ (initial 3)
    { 'l',             5 },  //  8: ㄹ -> liaison: ㄹ (initial 5)
    { PUA_K_UNREL,     0 },  //  9: ㄺ -> liaison: ㄱ (initial 0)
    { 'm',             5 },  // 10: ㄻ -> liaison: ㄹ (initial 5)?  simplified: m stands
    { 'l',             7 },  // 11: ㄼ -> liaison: ㅂ (initial 7)
    { 'l',             9 },  // 12: ㄽ -> liaison: ㅅ (initial 9)
    { 'l',            16 },  // 13: ㄾ -> liaison: ㅌ (initial 16)
    { 'l',            17 },  // 14: ㄿ -> liaison: ㅍ (initial 17)
    { 'l',            -1 },  // 15: ㅀ (ㄹ+ㅎ -> l, h dropped)
    { 'm',            -1 },  // 16: ㅁ
    { PUA_P_UNREL,     7 },  // 17: ㅂ -> liaison: ㅂ (initial 7)
    { PUA_P_UNREL,     9 },  // 18: ㅄ -> liaison: ㅅ (initial 9)
    { PUA_T_UNREL,     9 },  // 19: ㅅ -> liaison: ㅅ (initial 9)
    { PUA_T_UNREL,    10 },  // 20: ㅆ -> liaison: ㅆ (initial 10)
    { IPA_ENG,        -1 },  // 21: ㅇ (velar nasal in coda)
    { PUA_T_UNREL,    12 },  // 22: ㅈ -> liaison: ㅈ (initial 12)
    { PUA_T_UNREL,    14 },  // 23: ㅊ -> liaison: ㅊ (initial 14)
    { PUA_K_UNREL,    15 },  // 24: ㅋ -> liaison: ㅋ (initial 15)
    { PUA_T_UNREL,    16 },  // 25: ㅌ -> liaison: ㅌ (initial 16)
    { PUA_P_UNREL,    17 },  // 26: ㅍ -> liaison: ㅍ (initial 17)
    { PUA_T_UNREL,    -1 },  // 27: ㅎ (h dropped in liaison context)
};

// ---------------------------------------------------------------------------
// Punctuation set (passed through as-is)
// ---------------------------------------------------------------------------
static bool isPunctuation(char32_t ch) {
    switch (ch) {
        case ',': case '.': case ';': case ':': case '!': case '?':
        case 0x3002: // 。 CJK period
        case 0xFF0C: // ， CJK comma
        case 0xFF01: // ！ CJK exclamation
        case 0xFF1F: // ？ CJK question
        case 0x3001: // 、 CJK enumeration comma
            return true;
        default:
            return false;
    }
}

// ---------------------------------------------------------------------------
// UTF-8 -> codepoint vector
// ---------------------------------------------------------------------------
static std::vector<char32_t> toCodepoints(const std::string &s) {
    std::vector<char32_t> cps;
    auto it = s.begin();
    while (it != s.end()) {
        cps.push_back(utf8::unchecked::next(it));
    }
    return cps;
}

// ---------------------------------------------------------------------------
// Syllable structure for liaison processing
// ---------------------------------------------------------------------------
struct KoSyllable {
    int initial;  // 0..18
    int medial;   // 0..20
    int final_;   // 0..27
};

// ---------------------------------------------------------------------------
// Emit phonemes for a single syllable (after liaison adjustment)
// ---------------------------------------------------------------------------
static void emitSyllable(const KoSyllable &syl, std::vector<Phoneme> &out) {
    // Initial consonant
    if (syl.initial >= 0 && syl.initial < N_INITIALS) {
        Phoneme ph = INITIAL_TABLE[syl.initial].ph;
        if (ph != 0) {
            out.push_back(ph);
        }
    }

    // Medial vowel (1-2 phonemes)
    if (syl.medial >= 0 && syl.medial < N_MEDIALS) {
        const MedialEntry &me = MEDIAL_TABLE[syl.medial];
        out.push_back(me.ph[0]);
        if (me.ph[1] != 0) {
            out.push_back(me.ph[1]);
        }
    }

    // Final consonant
    if (syl.final_ > 0 && syl.final_ < N_FINALS) {
        Phoneme ph = FINAL_TABLE[syl.final_].ph;
        if (ph != 0) {
            out.push_back(ph);
        }
    }
}

// ---------------------------------------------------------------------------
// Process a run of Hangul syllables: decompose, apply liaison, emit phonemes
// ---------------------------------------------------------------------------
static void processHangulRun(const std::vector<char32_t> &cps,
                             size_t start, size_t end,
                             std::vector<Phoneme> &out) {
    size_t count = end - start;
    if (count == 0) return;

    // Decompose all syllables
    std::vector<KoSyllable> syls;
    syls.reserve(count);
    for (size_t i = start; i < end; ++i) {
        Jamo j = decompose(cps[i]);
        syls.push_back({j.initial, j.medial, j.final_});
    }

    // Apply basic liaison (연음화):
    // If syllable[i] has a final consonant and syllable[i+1] starts with
    // ㅇ (initial==11, silent), move the final to become the next initial.
    for (size_t i = 0; i + 1 < syls.size(); ++i) {
        int fi = syls[i].final_;
        if (fi == 0) continue;                    // no final -> skip
        if (syls[i + 1].initial != 11) continue;  // next initial is not ㅇ

        int liaisonInit = FINAL_TABLE[fi].liaisonInitial;
        if (liaisonInit < 0) continue;  // no liaison defined

        // Move final -> next initial
        syls[i + 1].initial = liaisonInit;
        syls[i].final_ = 0;  // clear the final
    }

    // Emit phonemes for all syllables
    for (const auto &syl : syls) {
        emitSyllable(syl, out);
    }
}

} // anonymous namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void phonemize_korean(const std::string &text,
                      std::vector<std::vector<Phoneme>> &phonemes) {
    phonemes.clear();

    auto cps = toCodepoints(text);
    if (cps.empty()) return;

    std::vector<Phoneme> sentence;
    bool needSpace = false;

    size_t n = cps.size();
    size_t i = 0;

    while (i < n) {
        char32_t ch = cps[i];

        // Whitespace -> mark word boundary
        if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r') {
            needSpace = true;
            ++i;
            continue;
        }

        // Punctuation -> emit directly
        if (isPunctuation(ch)) {
            sentence.push_back(ch);
            needSpace = false;
            ++i;
            continue;
        }

        // Hangul syllable run
        if (isHangulSyllable(ch)) {
            if (needSpace && !sentence.empty()) {
                sentence.push_back(static_cast<Phoneme>(' '));
            }

            // Find the extent of the Hangul run
            size_t runStart = i;
            while (i < n && isHangulSyllable(cps[i])) {
                ++i;
            }
            processHangulRun(cps, runStart, i, sentence);
            needSpace = true;
            continue;
        }

        // Latin alphabetic -> pass through as-is
        if ((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z')) {
            if (needSpace && !sentence.empty()) {
                sentence.push_back(static_cast<Phoneme>(' '));
            }
            // Lowercase
            Phoneme lower = (ch >= 'A' && ch <= 'Z') ? ch + 32 : ch;
            sentence.push_back(lower);
            needSpace = true;
            ++i;
            continue;
        }

        // Unknown character -> skip
        ++i;
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
