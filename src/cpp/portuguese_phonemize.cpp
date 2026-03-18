// Rule-based Brazilian Portuguese phonemizer for Piper TTS.
// Ported from src/python/piper_train/phonemize/portuguese.py
//
// Converts Brazilian Portuguese text to IPA phonemes using grapheme-to-phoneme
// rules.  No external G2P engine required.

#include "portuguese_phonemize.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>

namespace piper {
namespace {

// ---------------------------------------------------------------------------
// PUA codepoints for multi-codepoint IPA tokens
// ---------------------------------------------------------------------------
constexpr char32_t PUA_AFFRICATE_TCH = 0xE054; // t\u0283 (palatalized t before i)
constexpr char32_t PUA_AFFRICATE_DZH = 0xE055; // d\u0292 (palatalized d before i)

// Single IPA codepoints used throughout
constexpr char32_t IPA_EPSILON    = 0x025B; // open-mid front unrounded (e aberto)
constexpr char32_t IPA_OPEN_O     = 0x0254; // open-mid back rounded   (o aberto)
constexpr char32_t IPA_VOICED_G   = 0x0261; // voiced velar plosive
constexpr char32_t IPA_ESH        = 0x0283; // voiceless postalveolar fricative
constexpr char32_t IPA_EZH        = 0x0292; // voiced postalveolar fricative
constexpr char32_t IPA_UVULAR_R   = 0x0281; // voiced uvular fricative
constexpr char32_t IPA_PALATAL_N  = 0x0272; // palatal nasal
constexpr char32_t IPA_TAP        = 0x027E; // alveolar tap
constexpr char32_t IPA_PALATAL_L  = 0x028E; // palatal lateral approximant

// Precomposed nasal vowels (NFC single codepoints)
constexpr char32_t NASAL_A = 0x00E3; // a tilde
constexpr char32_t NASAL_E = 0x1EBD; // e tilde
constexpr char32_t NASAL_I = 0x0129; // i tilde
constexpr char32_t NASAL_O = 0x00F5; // o tilde
constexpr char32_t NASAL_U = 0x0169; // u tilde

// ---------------------------------------------------------------------------
// Character classification helpers (operate on char32_t codepoints)
// ---------------------------------------------------------------------------

// Portuguese vowel letters (including accented forms)
static bool isVowelChar(char32_t ch) {
    switch (ch) {
    case 'a': case 'e': case 'i': case 'o': case 'u':
    case 0xE1: // a acute
    case 0xE0: // a grave
    case 0xE2: // a circumflex
    case 0xE3: // a tilde
    case 0xE9: // e acute
    case 0xEA: // e circumflex
    case 0xED: // i acute
    case 0xF3: // o acute
    case 0xF4: // o circumflex
    case 0xF5: // o tilde
    case 0xFA: // u acute
    case 0xFC: // u diaeresis
        return true;
    default:
        return false;
    }
}

static bool isStressAccent(char32_t ch) {
    // Acute accents: open vowels, primary stress
    switch (ch) {
    case 0xE1: case 0xE9: case 0xED: case 0xF3: case 0xFA:
        return true;
    default:
        return false;
    }
}

static bool isCircumflex(char32_t ch) {
    switch (ch) {
    case 0xE2: case 0xEA: case 0xF4:
        return true;
    default:
        return false;
    }
}

static bool isTilde(char32_t ch) {
    return ch == 0xE3 || ch == 0xF5;
}

static bool isAccented(char32_t ch) {
    return isStressAccent(ch) || isCircumflex(ch) || isTilde(ch)
           || ch == 0xE0 /*a grave*/ || ch == 0xFC /*u diaeresis*/;
}

// Map accented letter to its base vowel
static char32_t accentBase(char32_t ch) {
    switch (ch) {
    case 0xE1: case 0xE0: case 0xE2: case 0xE3: return 'a';
    case 0xE9: case 0xEA:                        return 'e';
    case 0xED:                                    return 'i';
    case 0xF3: case 0xF4: case 0xF5:             return 'o';
    case 0xFA: case 0xFC:                         return 'u';
    default:                                      return ch;
    }
}

// IPA: oral vowel phonemes (for post-processing checks)
static bool isIpaOralVowel(char32_t ch) {
    switch (ch) {
    case 'a': case 'e': case 'i': case 'o': case 'u':
    case IPA_EPSILON: case IPA_OPEN_O:
        return true;
    default:
        return false;
    }
}

static bool isIpaNasalVowel(char32_t ch) {
    switch (ch) {
    case NASAL_A: case NASAL_E: case NASAL_I: case NASAL_O: case NASAL_U:
        return true;
    default:
        return false;
    }
}

static bool isIpaVowel(char32_t ch) {
    return isIpaOralVowel(ch) || isIpaNasalVowel(ch);
}

static bool isIpaConsonant(char32_t ch) {
    switch (ch) {
    case 'b': case 'c': case 'd': case 'f': case 'h': case 'j':
    case 'k': case 'l': case 'm': case 'n': case 'p': case 's':
    case 't': case 'v': case 'w': case 'z':
    case IPA_VOICED_G: case IPA_PALATAL_N: case IPA_TAP: case IPA_UVULAR_R:
    case IPA_ESH: case IPA_PALATAL_L: case IPA_EZH:
        return true;
    default:
        return false;
    }
}

// Punctuation set
static bool isPunctuation(char32_t ch) {
    switch (ch) {
    case ',': case '.': case ';': case ':': case '!': case '?':
    case 0xA1:   // inverted exclamation
    case 0xBF:   // inverted question
    case 0x2014: // em dash
    case 0x2013: // en dash
    case 0x2026: // horizontal ellipsis
        return true;
    default:
        return false;
    }
}

// "Soft" vowels that trigger c->s and g->zh
static bool isSoftVowel(char32_t ch) {
    switch (ch) {
    case 'e': case 'i':
    case 0xE9: case 0xEA: case 0xED: // e acute, e circumflex, i acute
        return true;
    default:
        return false;
    }
}

// Plain lowercase vowels for intervocalic x check
static bool isPlainVowel(char32_t ch) {
    switch (ch) {
    case 'a': case 'e': case 'i': case 'o': case 'u':
        return true;
    default:
        return false;
    }
}

// ---------------------------------------------------------------------------
// UTF-8 to codepoint vector conversion + NFC lowercase normalization
// ---------------------------------------------------------------------------

// Delegated to utf8_utils.hpp; local alias for compatibility.
static std::vector<char32_t> utf8Decode(const std::string &s) {
    return utf8_util::toCodepoints(s);
}

// ---------------------------------------------------------------------------
// NFD -> NFC combining accent collapse for Portuguese
//
// When input arrives in NFD form (e.g. from macOS HFS+ or certain HTTP
// clients), accented letters are decomposed into a base letter followed by a
// combining accent codepoint.  The G2P rules expect precomposed NFC forms
// (e.g. U+00E1 'a acute' rather than U+0061 + U+0301).  This function
// collapses the most common Portuguese combining sequences in-place.
//
// Handled combining marks:
//   U+0300  COMBINING GRAVE ACCENT        -> a grave
//   U+0301  COMBINING ACUTE ACCENT        -> a/e/i/o/u acute
//   U+0302  COMBINING CIRCUMFLEX ACCENT   -> a/e/o circumflex
//   U+0303  COMBINING TILDE               -> a/o/n tilde
//   U+0308  COMBINING DIAERESIS           -> u diaeresis
//   U+0327  COMBINING CEDILLA             -> c cedilla
// ---------------------------------------------------------------------------

static void collapseNfdCombiningAccents(std::vector<char32_t> &cps) {
    if (cps.size() < 2) return;

    std::vector<char32_t> out;
    out.reserve(cps.size());

    size_t i = 0;
    size_t n = cps.size();
    while (i < n) {
        // If this is NOT the last codepoint, check for base + combining pair
        if (i + 1 < n) {
            char32_t base = cps[i];
            char32_t comb = cps[i + 1];
            char32_t composed = 0;

            switch (comb) {
            case 0x0300: // COMBINING GRAVE ACCENT
                if (base == 'a') composed = 0x00E0;
                else if (base == 'A') composed = 0x00C0;
                break;

            case 0x0301: // COMBINING ACUTE ACCENT
                switch (base) {
                case 'a': composed = 0x00E1; break;
                case 'e': composed = 0x00E9; break;
                case 'i': composed = 0x00ED; break;
                case 'o': composed = 0x00F3; break;
                case 'u': composed = 0x00FA; break;
                case 'A': composed = 0x00C1; break;
                case 'E': composed = 0x00C9; break;
                case 'I': composed = 0x00CD; break;
                case 'O': composed = 0x00D3; break;
                case 'U': composed = 0x00DA; break;
                default: break;
                }
                break;

            case 0x0302: // COMBINING CIRCUMFLEX ACCENT
                switch (base) {
                case 'a': composed = 0x00E2; break;
                case 'e': composed = 0x00EA; break;
                case 'o': composed = 0x00F4; break;
                case 'A': composed = 0x00C2; break;
                case 'E': composed = 0x00CA; break;
                case 'O': composed = 0x00D4; break;
                default: break;
                }
                break;

            case 0x0303: // COMBINING TILDE
                switch (base) {
                case 'a': composed = 0x00E3; break;
                case 'o': composed = 0x00F5; break;
                case 'A': composed = 0x00C3; break;
                case 'O': composed = 0x00D5; break;
                case 'n': composed = 0x00F1; break;
                case 'N': composed = 0x00D1; break;
                default: break;
                }
                break;

            case 0x0308: // COMBINING DIAERESIS
                if (base == 'u') composed = 0x00FC;
                else if (base == 'U') composed = 0x00DC;
                break;

            case 0x0327: // COMBINING CEDILLA
                if (base == 'c') composed = 0x00E7;
                else if (base == 'C') composed = 0x00C7;
                break;

            default:
                break;
            }

            if (composed != 0) {
                out.push_back(composed);
                i += 2; // consumed base + combining mark
                continue;
            }
        }

        out.push_back(cps[i]);
        ++i;
    }

    cps = std::move(out);
}

// Simple lowercase for Latin + common accented letters
static char32_t toLower(char32_t cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    // Latin-1 supplement uppercase (C0-DE except D7 multiply)
    if (cp >= 0xC0 && cp <= 0xDE && cp != 0xD7) return cp + 32;
    return cp;
}

// Normalize: NFC lowercase, collapse whitespace, trim
static std::vector<char32_t> normalize(const std::string &text) {
    // The Python version calls unicodedata.normalize("NFC", ...).
    // We handle the common NFD -> NFC combining accent sequences for
    // Portuguese, then lowercase and collapse whitespace.
    std::vector<char32_t> cps = utf8Decode(text);

    // NFD -> NFC: collapse combining accents before any other processing
    collapseNfdCombiningAccents(cps);

    // Lowercase
    for (auto &cp : cps) cp = toLower(cp);

    // Collapse whitespace + trim
    std::vector<char32_t> out;
    out.reserve(cps.size());
    bool prevSpace = true; // trim leading
    for (auto cp : cps) {
        bool ws = (cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r');
        if (ws) {
            if (!prevSpace) out.push_back(' ');
            prevSpace = true;
        } else {
            out.push_back(cp);
            prevSpace = false;
        }
    }
    // trim trailing
    if (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

// ---------------------------------------------------------------------------
// Tokenizer: split codepoint vector into word / punctuation tokens
// ---------------------------------------------------------------------------

struct Token {
    std::vector<char32_t> chars;
    bool isPunct;
};

static bool isWordChar(char32_t ch) {
    // a-z
    if (ch >= 'a' && ch <= 'z') return true;
    // Common Portuguese accented: 0xE0-0xFF range (Latin-1 supplement lowercase)
    if (ch >= 0xE0 && ch <= 0xFF && ch != 0xF7 /*division sign*/) return true;
    // c cedilla
    if (ch == 0xE7) return true;
    // n tilde
    if (ch == 0xF1) return true;
    return false;
}

static std::vector<Token> tokenize(const std::vector<char32_t> &cps) {
    std::vector<Token> tokens;
    size_t i = 0;
    size_t n = cps.size();
    while (i < n) {
        char32_t ch = cps[i];
        if (isWordChar(ch)) {
            Token tok;
            tok.isPunct = false;
            while (i < n && isWordChar(cps[i])) {
                tok.chars.push_back(cps[i]);
                ++i;
            }
            tokens.push_back(std::move(tok));
        } else if (isPunctuation(ch)) {
            Token tok;
            tok.isPunct = true;
            tok.chars.push_back(ch);
            ++i;
            tokens.push_back(std::move(tok));
        } else {
            // whitespace or unknown: skip
            ++i;
        }
    }
    return tokens;
}

// ---------------------------------------------------------------------------
// Vowel-group counting (digraph-aware) -- mirrors Python _count_vowel_groups
// ---------------------------------------------------------------------------

static int countVowelGroups(const std::vector<char32_t> &word) {
    int count = 0;
    size_t i = 0;
    size_t n = word.size();
    while (i < n) {
        char32_t ch = word[i];
        // qu digraph
        if (ch == 'q' && i + 1 < n && word[i + 1] == 'u') {
            // u silent or glide -- either way skip both and do NOT count as
            // a vowel group
            i += 2;
            continue;
        }
        // gu before e/i: u silent
        if (ch == 'g' && i + 1 < n && word[i + 1] == 'u') {
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                i += 2;
                continue;
            }
        }
        // ou diphthong: one vowel group
        if (ch == 'o' && i + 1 < n && word[i + 1] == 'u') {
            ++count;
            i += 2;
            continue;
        }
        if (isVowelChar(ch)) {
            ++count;
        }
        ++i;
    }
    return count;
}

// ---------------------------------------------------------------------------
// Stress position finder -- mirrors Python _find_stress_position
// Returns position from end (0 = last vowel group, 1 = penultimate, ...)
// ---------------------------------------------------------------------------

static int findStressPosition(const std::vector<char32_t> &word) {
    int vowelGroupCount = countVowelGroups(word);

    // Find accented vowel group position
    int accentGroup = -1;
    int currentGroup = 0;
    size_t i = 0;
    size_t n = word.size();
    while (i < n) {
        char32_t ch = word[i];
        // Skip digraphs same as countVowelGroups
        if (ch == 'q' && i + 1 < n && word[i + 1] == 'u') {
            i += 2;
            continue;
        }
        if (ch == 'g' && i + 1 < n && word[i + 1] == 'u') {
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                i += 2;
                continue;
            }
        }
        if (ch == 'o' && i + 1 < n && word[i + 1] == 'u') {
            if (isStressAccent(ch) || isCircumflex(ch) || isTilde(ch)) {
                accentGroup = currentGroup;
            }
            ++currentGroup;
            i += 2;
            continue;
        }
        if (isVowelChar(ch)) {
            if (isStressAccent(ch) || isCircumflex(ch) || isTilde(ch)) {
                accentGroup = currentGroup;
            }
            ++currentGroup;
        }
        ++i;
    }

    if (vowelGroupCount == 0) return 0;

    if (accentGroup >= 0) {
        return vowelGroupCount - 1 - accentGroup;
    }

    // Default rules based on ending
    // Strip trailing 's' for rule check
    std::vector<char32_t> stripped(word);
    while (!stripped.empty() && stripped.back() == 's') {
        stripped.pop_back();
    }
    size_t sn = stripped.size();

    // Check endings: a, e, o, am, em, en -> paroxytone
    bool paroxytone = false;
    if (sn >= 1) {
        char32_t last = stripped[sn - 1];
        if (last == 'a' || last == 'e' || last == 'o') {
            paroxytone = true;
        }
    }
    if (!paroxytone && sn >= 2) {
        char32_t sl = stripped[sn - 2];
        char32_t el = stripped[sn - 1];
        if ((sl == 'a' && el == 'm') ||
            (sl == 'e' && el == 'm') ||
            (sl == 'e' && el == 'n')) {
            paroxytone = true;
        }
    }

    if (paroxytone) {
        return std::min(1, vowelGroupCount - 1);
    }
    // Oxytone: last syllable
    return 0;
}

// ---------------------------------------------------------------------------
// Intervocalic helper (on original word codepoints)
// ---------------------------------------------------------------------------

static bool isIntervocalic(size_t i, const std::vector<char32_t> &word) {
    if (i == 0 || i >= word.size() - 1) return false;
    return isVowelChar(word[i - 1]) && isVowelChar(word[i + 1]);
}

// ---------------------------------------------------------------------------
// Convert a single word (codepoint vector) to IPA phonemes
// Returns (phonemes, stress_vowel_index)
// ---------------------------------------------------------------------------

struct WordResult {
    std::vector<char32_t> phonemes;
    int stressIdx; // index into phonemes of the primary stressed vowel (-1 if none)
};

// Map base vowel to its nasal counterpart
static char32_t nasalOf(char32_t base) {
    switch (base) {
    case 'a': return NASAL_A;
    case 'e': return NASAL_E;
    case 'i': return NASAL_I;
    case 'o': return NASAL_O;
    case 'u': return NASAL_U;
    default:  return base;
    }
}

// Map base vowel + acute accent to open IPA vowel
static char32_t openVowelOf(char32_t base) {
    switch (base) {
    case 'a': return 'a';
    case 'e': return IPA_EPSILON;
    case 'i': return 'i';
    case 'o': return IPA_OPEN_O;
    case 'u': return 'u';
    default:  return base;
    }
}

static WordResult convertWord(const std::vector<char32_t> &word) {
    WordResult wr;
    wr.stressIdx = -1;
    auto &ph = wr.phonemes;

    size_t i = 0;
    size_t n = word.size();

    // Determine stress target
    int stressFromEnd = findStressPosition(word);
    int vowelGroupCount = countVowelGroups(word);
    int stressVowelTarget = vowelGroupCount - 1 - stressFromEnd;
    int currentVowelGroup = 0;

    while (i < n) {
        char32_t ch = word[i];

        // === Multi-character sequences (longest first) ===

        // "nh" -> palatal nasal
        if (ch == 'n' && i + 1 < n && word[i + 1] == 'h') {
            ph.push_back(IPA_PALATAL_N);
            i += 2;
            continue;
        }
        // "lh" -> palatal lateral
        if (ch == 'l' && i + 1 < n && word[i + 1] == 'h') {
            ph.push_back(IPA_PALATAL_L);
            i += 2;
            continue;
        }
        // "ch" -> voiceless postalveolar fricative
        if (ch == 'c' && i + 1 < n && word[i + 1] == 'h') {
            ph.push_back(IPA_ESH);
            i += 2;
            continue;
        }
        // "rr" -> uvular fricative
        if (ch == 'r' && i + 1 < n && word[i + 1] == 'r') {
            ph.push_back(IPA_UVULAR_R);
            i += 2;
            continue;
        }
        // "ss" -> voiceless alveolar sibilant
        if (ch == 's' && i + 1 < n && word[i + 1] == 's') {
            ph.push_back('s');
            i += 2;
            continue;
        }
        // "sc" before e/i -> s (seseo)
        if (ch == 's' && i + 1 < n && word[i + 1] == 'c') {
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                ph.push_back('s');
                i += 2; // skip "sc", vowel handled next iteration
                continue;
            }
        }
        // "qu" digraph
        if (ch == 'q' && i + 1 < n && word[i + 1] == 'u') {
            ph.push_back('k');
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                // Silent u before e/i
                i += 2;
            } else {
                // Pronounced u before a/o -> append w glide
                ph.push_back('w');
                i += 2;
            }
            continue;
        }
        // "gu" before e/i -> voiced velar plosive (u silent)
        if (ch == 'g' && i + 1 < n && word[i + 1] == 'u') {
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                ph.push_back(IPA_VOICED_G);
                i += 2;
                continue;
            }
        }
        // "ou" -> o (common BR reduction, single vowel group)
        if (ch == 'o' && i + 1 < n && word[i + 1] == 'u') {
            bool isStressed = (currentVowelGroup == stressVowelTarget);
            if (isStressed) wr.stressIdx = static_cast<int>(ph.size());
            ph.push_back('o');
            ++currentVowelGroup;
            i += 2;
            continue;
        }

        // === Consonants ===

        if (ch == 'r') {
            if (isIntervocalic(i, word)) {
                ph.push_back(IPA_TAP);
            } else {
                ph.push_back(IPA_UVULAR_R);
            }
            ++i;
            continue;
        }
        if (ch == 's') {
            // Intervocalic s -> z
            if (i > 0 && i + 1 < n && isVowelChar(word[i - 1]) && isVowelChar(word[i + 1])) {
                ph.push_back('z');
            } else {
                ph.push_back('s');
            }
            ++i;
            continue;
        }
        if (ch == 'x') {
            if (i == 0) {
                ph.push_back(IPA_ESH);
            } else if (i > 0 && isVowelChar(word[i - 1])
                       && i + 1 < n && isVowelChar(word[i + 1])) {
                ph.push_back('z');
            } else {
                ph.push_back(IPA_ESH);
            }
            ++i;
            continue;
        }
        if (ch == 'c') {
            if (i + 1 < n && isSoftVowel(word[i + 1])) {
                ph.push_back('s');
            } else {
                ph.push_back('k');
            }
            ++i;
            continue;
        }
        if (ch == 0xE7 /* c cedilla */) {
            ph.push_back('s');
            ++i;
            continue;
        }
        if (ch == 'g') {
            if (i + 1 < n && isSoftVowel(word[i + 1])) {
                ph.push_back(IPA_EZH);
            } else {
                ph.push_back(IPA_VOICED_G);
            }
            ++i;
            continue;
        }
        if (ch == 'j') {
            ph.push_back(IPA_EZH);
            ++i;
            continue;
        }
        if (ch == 't') {
            // BR Portuguese: t before i -> affricate
            if (i + 1 < n && (word[i + 1] == 'i' || word[i + 1] == 0xED)) {
                ph.push_back(PUA_AFFRICATE_TCH);
            } else {
                ph.push_back('t');
            }
            ++i;
            continue;
        }
        if (ch == 'd') {
            // BR Portuguese: d before i -> affricate
            if (i + 1 < n && (word[i + 1] == 'i' || word[i + 1] == 0xED)) {
                ph.push_back(PUA_AFFRICATE_DZH);
            } else {
                ph.push_back('d');
            }
            ++i;
            continue;
        }
        if (ch == 'h') {
            // Silent (digraphs already handled above)
            ++i;
            continue;
        }
        // Simple consonant pass-through: b f k l m n p v
        if (ch == 'b' || ch == 'f' || ch == 'k' || ch == 'l'
            || ch == 'm' || ch == 'n' || ch == 'p' || ch == 'v') {
            ph.push_back(ch);
            ++i;
            continue;
        }
        if (ch == 'z') {
            ph.push_back('z');
            ++i;
            continue;
        }
        if (ch == 'w') {
            ph.push_back('w');
            ++i;
            continue;
        }

        // === Vowels ===

        if (isVowelChar(ch)) {
            bool isStressed = (currentVowelGroup == stressVowelTarget);
            char32_t base = accentBase(ch);

            // --- Nasalization check ---
            bool isNasal = false;
            bool nasalAbsorbed = false;

            if (isTilde(ch)) {
                isNasal = true;
            } else if (i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm')) {
                // Exception: "nh" digraph -- do NOT nasalize before nh
                if (word[i + 1] == 'n' && i + 2 < n && word[i + 2] == 'h') {
                    isNasal = false;
                } else if (i + 2 >= n) {
                    // n/m at end of word: absorb nasal consonant
                    isNasal = true;
                    nasalAbsorbed = true;
                } else if (!isVowelChar(word[i + 2])) {
                    // n/m followed by consonant: absorb nasal coda
                    isNasal = true;
                    nasalAbsorbed = true;
                }
            }

            char32_t phoneme;
            if (isNasal) {
                phoneme = nasalOf(base);
            } else if (isStressAccent(ch)) {
                // Acute accent = open vowel
                phoneme = openVowelOf(base);
            } else if (isCircumflex(ch)) {
                // Circumflex = closed vowel (base)
                phoneme = base;
            } else {
                phoneme = base;
            }

            if (isStressed) wr.stressIdx = static_cast<int>(ph.size());
            ph.push_back(phoneme);
            ++currentVowelGroup;

            if (nasalAbsorbed) {
                i += 2; // skip vowel + nasal consonant
            } else {
                ++i;
            }
            continue;
        }

        // Punctuation pass-through
        if (isPunctuation(ch)) {
            ph.push_back(ch);
            ++i;
            continue;
        }

        // Unknown character: skip
        ++i;
    }

    return wr;
}

// ---------------------------------------------------------------------------
// Post-processing step 1: remove duplicate nasal coda
// Mirrors Python _remove_duplicate_nasal_coda
// ---------------------------------------------------------------------------

// Returns the number of elements removed *and* adjusts stressIdx accordingly.
static int removeDuplicateNasalCoda(std::vector<char32_t> &ph, int &stressIdx) {
    int removed = 0;
    int i = static_cast<int>(ph.size()) - 1;
    while (i >= 1) {
        if ((ph[i] == 'n' || ph[i] == 'm') && isIpaNasalVowel(ph[i - 1])) {
            // Check boundary: at end, or next is space / punctuation
            bool atBoundary = (static_cast<size_t>(i) == ph.size() - 1)
                              || (ph[i + 1] == ' ') || isPunctuation(ph[i + 1]);
            if (atBoundary) {
                // If the removed element is before stressIdx, shift it back
                if (stressIdx >= 0 && i < stressIdx) {
                    --stressIdx;
                }
                ph.erase(ph.begin() + i);
                ++removed;
            }
        }
        --i;
    }
    return removed;
}

// ---------------------------------------------------------------------------
// Post-processing step 2: coda-l vocalization (l -> w in coda)
// Mirrors Python _apply_coda_l_vocalization
// ---------------------------------------------------------------------------

static void applyCodaLVocalization(std::vector<char32_t> &ph) {
    for (size_t i = 0; i < ph.size(); ++i) {
        if (ph[i] != 'l') continue;

        // l at end of list -> coda
        if (i == ph.size() - 1) {
            ph[i] = 'w';
            continue;
        }
        char32_t next = ph[i + 1];
        // l before space or punctuation -> coda (word-final)
        if (next == ' ' || isPunctuation(next)) {
            ph[i] = 'w';
            continue;
        }
        // l before a consonant -> coda
        // Also handle PUA affricates
        if (isIpaConsonant(next) || next == PUA_AFFRICATE_TCH || next == PUA_AFFRICATE_DZH) {
            if (!isIpaVowel(next)) {
                ph[i] = 'w';
                continue;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Post-processing step 3: BR postprocessing
// (t/d palatalization before final unstressed e, final vowel reduction)
// Mirrors Python _apply_br_postprocessing
// ---------------------------------------------------------------------------

// Find word ranges (delimited by space phonemes)
struct Range { size_t start; size_t end; };

static std::vector<Range> findWordRanges(const std::vector<char32_t> &ph) {
    std::vector<Range> ranges;
    size_t start = 0;
    for (size_t i = 0; i < ph.size(); ++i) {
        if (ph[i] == ' ') {
            if (i > start) ranges.push_back({start, i});
            start = i + 1;
        }
    }
    if (start < ph.size()) ranges.push_back({start, ph.size()});
    return ranges;
}

static void applyBrPostprocessing(std::vector<char32_t> &ph, int stressIdx) {
    // --- Pass 1: t/d palatalization + unstressed final e/o reduction ---
    auto ranges = findWordRanges(ph);

    for (auto &rng : ranges) {
        if (rng.end - rng.start < 2) continue;

        int lastIdx = static_cast<int>(rng.end) - 1;
        // Skip trailing punctuation
        while (lastIdx >= static_cast<int>(rng.start) && isPunctuation(ph[lastIdx])) {
            --lastIdx;
        }
        if (lastIdx < static_cast<int>(rng.start)) continue;

        // Unstressed final 'e'
        if (ph[lastIdx] == 'e' && lastIdx != stressIdx) {
            // Preceded by 't' -> t + e -> affricate + i
            if (lastIdx >= static_cast<int>(rng.start) + 1 && ph[lastIdx - 1] == 't') {
                ph[lastIdx - 1] = PUA_AFFRICATE_TCH;
                ph[lastIdx] = 'i';
                continue;
            }
            // Preceded by 'd' -> d + e -> affricate + i
            if (lastIdx >= static_cast<int>(rng.start) + 1 && ph[lastIdx - 1] == 'd') {
                ph[lastIdx - 1] = PUA_AFFRICATE_DZH;
                ph[lastIdx] = 'i';
                continue;
            }
            // General reduction: unstressed final e -> i
            ph[lastIdx] = 'i';
        }
        // Unstressed final 'o' -> u
        else if (ph[lastIdx] == 'o' && lastIdx != stressIdx) {
            ph[lastIdx] = 'u';
        }
    }

    // --- Pass 2: non-final unstressed vowel reduction ---
    // Python implementation is conservative (no-op). We mirror that.
}

// ---------------------------------------------------------------------------
// Full word conversion pipeline (word G2P + all post-processing)
// ---------------------------------------------------------------------------

static WordResult processWord(const std::vector<char32_t> &word) {
    WordResult wr = convertWord(word);
    removeDuplicateNasalCoda(wr.phonemes, wr.stressIdx);
    applyCodaLVocalization(wr.phonemes);
    applyBrPostprocessing(wr.phonemes, wr.stressIdx);
    return wr;
}

// ---------------------------------------------------------------------------
// Top-level phonemization (text -> sentence of Phoneme codepoints)
// Mirrors Python phonemize_portuguese / phonemize_portuguese_with_prosody
// ---------------------------------------------------------------------------

static std::vector<Phoneme> phonemizeSentence(const std::string &text) {
    std::vector<char32_t> cps = normalize(text);
    std::vector<Token> tokens = tokenize(cps);

    std::vector<char32_t> result;
    bool needSpace = false;

    for (auto &tok : tokens) {
        if (tok.isPunct) {
            for (auto ch : tok.chars) {
                result.push_back(ch);
            }
            needSpace = true;
        } else {
            if (needSpace) {
                result.push_back(' ');
            }
            WordResult wr = processWord(tok.chars);
            for (auto p : wr.phonemes) {
                result.push_back(p);
            }
            needSpace = true;
        }
    }

    // Convert char32_t to Phoneme (both are char32_t, identity)
    std::vector<Phoneme> phonemes;
    phonemes.reserve(result.size());
    for (auto cp : result) {
        phonemes.push_back(static_cast<Phoneme>(cp));
    }
    return phonemes;
}

} // anonymous namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void phonemize_portuguese(const std::string &text,
                          std::vector<std::vector<Phoneme>> &phonemes) {
    phonemes.clear();
    if (text.empty()) return;

    if (!utf8::is_valid(text.begin(), text.end())) {
        return;
    }

    std::vector<Phoneme> sentence = phonemizeSentence(text);
    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
