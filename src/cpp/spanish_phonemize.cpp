// Rule-based Spanish G2P (grapheme-to-phoneme) — C++ port of spanish.py.
//
// Converts Spanish text to IPA phonemes using orthographic rules.
// No external dependencies required (Spanish has nearly phonemic orthography).
// Uses Latin American pronunciation by default (seseo: c/z -> s).

#include "spanish_phonemize.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <algorithm>
#include <string>
#include <unordered_set>
#include <vector>

namespace piper {
namespace {

// -----------------------------------------------------------------------
// PUA codepoints for multi-character phonemes
// -----------------------------------------------------------------------
static constexpr Phoneme PUA_RR   = 0xE01D; // trill r (rr)
static constexpr Phoneme PUA_TCH  = 0xE054; // affricate tS (ch)

// IPA codepoints used in output
static constexpr Phoneme IPA_BETA    = 0x03B2; // voiced bilabial fricative
static constexpr Phoneme IPA_ETH     = 0x00F0; // voiced dental fricative
static constexpr Phoneme IPA_G_IPA   = 0x0261; // voiced velar stop (IPA g)
static constexpr Phoneme IPA_GAMMA   = 0x0263; // voiced velar fricative
static constexpr Phoneme IPA_PALATAL = 0x0272; // palatal nasal
static constexpr Phoneme IPA_TAP     = 0x027E; // alveolar tap
static constexpr Phoneme IPA_YE      = 0x029D; // voiced palatal fricative
static constexpr Phoneme IPA_STRESS  = 0x02C8; // primary stress marker

// -----------------------------------------------------------------------
// Punctuation set passed through as-is
// -----------------------------------------------------------------------
static bool isPunctuation(char32_t cp) {
    return cp == ',' || cp == '.' || cp == ';' || cp == ':' ||
           cp == '!' || cp == '?' || cp == 0x00A1 || cp == 0x00BF;
}

// -----------------------------------------------------------------------
// Vowels
// -----------------------------------------------------------------------
static bool isVowel(char32_t cp) {
    return cp == 'a' || cp == 'e' || cp == 'i' || cp == 'o' || cp == 'u';
}

static bool isStrongVowel(char32_t cp) {
    return cp == 'a' || cp == 'e' || cp == 'o';
}

static bool isWeakVowel(char32_t cp) {
    return cp == 'i' || cp == 'u';
}

// -----------------------------------------------------------------------
// Accent map: accented vowel -> base vowel
// -----------------------------------------------------------------------
static char32_t accentBase(char32_t cp) {
    switch (cp) {
        case 0x00E1: return 'a'; // a-acute
        case 0x00E9: return 'e'; // e-acute
        case 0x00ED: return 'i'; // i-acute
        case 0x00F3: return 'o'; // o-acute
        case 0x00FA: return 'u'; // u-acute
        case 0x00FC: return 'u'; // u-diaeresis
        default: return cp;
    }
}

static bool hasStressAccent(char32_t cp) {
    return cp == 0x00E1 || cp == 0x00E9 || cp == 0x00ED ||
           cp == 0x00F3 || cp == 0x00FA;
}

static bool isVowelOrAccented(char32_t cp) {
    return isVowel(cp) || hasStressAccent(cp) || cp == 0x00FC;
}

// -----------------------------------------------------------------------
// UTF-8 helpers — delegated to utf8_utils.hpp
// -----------------------------------------------------------------------

using utf8_util::toCodepoints;

// -----------------------------------------------------------------------
// Lowercasing (ASCII + Spanish accented letters)
// -----------------------------------------------------------------------
static char32_t toLowerSp(char32_t cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    if (cp == 0x00C1) return 0x00E1; // A-acute
    if (cp == 0x00C9) return 0x00E9; // E-acute
    if (cp == 0x00CD) return 0x00ED; // I-acute
    if (cp == 0x00D3) return 0x00F3; // O-acute
    if (cp == 0x00DA) return 0x00FA; // U-acute
    if (cp == 0x00DC) return 0x00FC; // U-diaeresis
    if (cp == 0x00D1) return 0x00F1; // N-tilde
    return cp;
}

// -----------------------------------------------------------------------
// Collapse NFD combining sequences into NFC pre-composed codepoints.
//
// Python's unicodedata.normalize("NFC", text) handles this automatically,
// but C++ receives raw UTF-8 which may contain decomposed forms
// (e.g., 'a' + U+0301 combining acute instead of U+00E1 á).
// We handle the small set of combiners relevant to Spanish:
//   U+0301 combining acute accent  → á é í ó ú / Á É Í Ó Ú
//   U+0308 combining diaeresis     → ü / Ü
//   U+0303 combining tilde         → ñ / Ñ
// -----------------------------------------------------------------------
static std::vector<char32_t> collapseCombiners(const std::vector<char32_t> &cps) {
    std::vector<char32_t> out;
    out.reserve(cps.size());
    for (size_t i = 0; i < cps.size(); ++i) {
        if (i + 1 < cps.size() && cps[i + 1] == 0x0301) { // combining acute
            switch (cps[i]) {
            case 'A': out.push_back(0x00C1); ++i; continue; // Á
            case 'a': out.push_back(0x00E1); ++i; continue; // á
            case 'E': out.push_back(0x00C9); ++i; continue; // É
            case 'e': out.push_back(0x00E9); ++i; continue; // é
            case 'I': out.push_back(0x00CD); ++i; continue; // Í
            case 'i': out.push_back(0x00ED); ++i; continue; // í
            case 'O': out.push_back(0x00D3); ++i; continue; // Ó
            case 'o': out.push_back(0x00F3); ++i; continue; // ó
            case 'U': out.push_back(0x00DA); ++i; continue; // Ú
            case 'u': out.push_back(0x00FA); ++i; continue; // ú
            default: break; // unknown base — fall through, don't skip combiner
            }
        } else if (i + 1 < cps.size() && cps[i + 1] == 0x0308) { // combining diaeresis
            if (cps[i] == 'U') { out.push_back(0x00DC); ++i; continue; } // Ü
            if (cps[i] == 'u') { out.push_back(0x00FC); ++i; continue; } // ü
        } else if (i + 1 < cps.size() && cps[i + 1] == 0x0303) { // combining tilde
            if (cps[i] == 'N') { out.push_back(0x00D1); ++i; continue; } // Ñ
            if (cps[i] == 'n') { out.push_back(0x00F1); ++i; continue; } // ñ
        }
        out.push_back(cps[i]);
    }
    return out;
}

// -----------------------------------------------------------------------
// Normalize: NFD→NFC collapse + lowercase
// -----------------------------------------------------------------------
static std::vector<char32_t> normalize(const std::vector<char32_t> &cps) {
    auto nfc = collapseCombiners(cps);
    std::vector<char32_t> out;
    out.reserve(nfc.size());
    for (auto cp : nfc) {
        out.push_back(toLowerSp(cp));
    }
    return out;
}

// -----------------------------------------------------------------------
// Tokenizer: split into word / punctuation tokens
//
// A "word" is a run of [a-z, accented vowels, n-tilde].
// A "punct" token is a run of punctuation chars.
// Everything else (digits, unknown) is skipped.
// -----------------------------------------------------------------------

struct Token {
    std::vector<char32_t> chars;
    bool isWord; // true = word, false = punctuation
};

static bool isSpanishAlpha(char32_t cp) {
    if (cp >= 'a' && cp <= 'z') return true;
    if (cp == 0x00F1) return true; // n-tilde
    if (cp == 0x00E1 || cp == 0x00E9 || cp == 0x00ED ||
        cp == 0x00F3 || cp == 0x00FA || cp == 0x00FC) return true;
    return false;
}

static std::vector<Token> tokenize(const std::vector<char32_t> &cps) {
    std::vector<Token> tokens;
    size_t n = cps.size();
    size_t i = 0;
    while (i < n) {
        if (isSpanishAlpha(cps[i])) {
            Token tok;
            tok.isWord = true;
            while (i < n && isSpanishAlpha(cps[i])) {
                tok.chars.push_back(cps[i]);
                ++i;
            }
            tokens.push_back(std::move(tok));
        } else if (isPunctuation(cps[i])) {
            Token tok;
            tok.isWord = false;
            while (i < n && isPunctuation(cps[i])) {
                tok.chars.push_back(cps[i]);
                ++i;
            }
            tokens.push_back(std::move(tok));
        } else {
            ++i; // skip whitespace, digits, unknown
        }
    }
    return tokens;
}

// -----------------------------------------------------------------------
// 27 common unstressed function words
// -----------------------------------------------------------------------
static const std::unordered_set<std::string> UNSTRESSED_FUNCTION_WORDS = {
    "el", "la", "los", "las", "un", "una",
    "de", "del", "al", "a", "en", "con", "por",
    "y", "o", "que", "se", "me", "te", "le",
    "lo", "nos", "su", "mi", "tu", "es", "no", "si"
};

// Helper: convert codepoint vector to UTF-8 string (for lookup).
static std::string cpVecToUtf8(const std::vector<char32_t> &cps) {
    return utf8_util::cpsToUtf8(cps);
}

// -----------------------------------------------------------------------
// Grapheme unit for syllabification
// -----------------------------------------------------------------------
struct GUnit {
    std::vector<char32_t> chars; // original characters (may contain accents)
    bool isVowel;
    bool isSilent;
};

// Map each char to its base form.
static char32_t baseOf(char32_t cp) { return accentBase(cp); }

static std::vector<GUnit> segmentGraphemes(const std::vector<char32_t> &word) {
    // Build base-form word for context checks
    std::vector<char32_t> bw;
    bw.reserve(word.size());
    for (auto c : word) bw.push_back(baseOf(c));

    std::vector<GUnit> units;
    size_t n = word.size();
    size_t i = 0;
    while (i < n) {
        char32_t bc = bw[i];

        // --- Multi-character graphemes (longest match first) ---

        // "qu" (u is silent)
        if (bc == 'q' && i + 1 < n && bw[i + 1] == 'u') {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "gu-diaeresis" before e/i
        if (bc == 'g' && i + 1 < n && word[i + 1] == 0x00FC
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "gu" before e/i (u silent)
        if (bc == 'g' && i + 1 < n && bw[i + 1] == 'u'
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "ch"
        if (bc == 'c' && i + 1 < n && bw[i + 1] == 'h') {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "ll"
        if (bc == 'l' && i + 1 < n && bw[i + 1] == 'l') {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "rr"
        if (bc == 'r' && i + 1 < n && bw[i + 1] == 'r') {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "sc" before e/i
        if (bc == 's' && i + 1 < n && bw[i + 1] == 'c'
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // "xc" before e/i
        if (bc == 'x' && i + 1 < n && bw[i + 1] == 'c'
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            units.push_back({{word[i], word[i + 1]}, false, false});
            i += 2; continue;
        }

        // Silent "h"
        if (bc == 'h') {
            units.push_back({{word[i]}, false, true});
            i += 1; continue;
        }

        // Vowels (including accented)
        if (isVowel(bc)) {
            units.push_back({{word[i]}, true, false});
            i += 1; continue;
        }

        // All other consonants
        units.push_back({{word[i]}, false, false});
        i += 1;
    }
    return units;
}

// -----------------------------------------------------------------------
// Syllabification
// -----------------------------------------------------------------------

// 13 inseparable onset clusters
static bool isInseparable(char32_t c1, char32_t c2) {
    if (c2 == 'l') {
        return c1 == 'b' || c1 == 'c' || c1 == 'f' ||
               c1 == 'g' || c1 == 'p' || c1 == 't';
    }
    if (c2 == 'r') {
        return c1 == 'b' || c1 == 'c' || c1 == 'd' || c1 == 'f' ||
               c1 == 'g' || c1 == 'p' || c1 == 't';
    }
    return false;
}

// Return the base consonant letter from a grapheme unit at non-silent index.
static char32_t baseConsOfUnit(const GUnit &u) {
    char32_t last = u.chars.back();
    return baseOf(last);
}

static std::vector<int> findSyllableBoundaries(
        const std::vector<char32_t> &/*word*/,
        const std::vector<GUnit> &units) {

    // Build non-silent mask
    std::vector<int> nsIdx;  // unit indices of non-silent units
    std::vector<bool> nsVow; // is_vowel for each non-silent unit
    for (int idx = 0; idx < (int)units.size(); ++idx) {
        if (units[idx].isSilent) continue;
        nsIdx.push_back(idx);
        nsVow.push_back(units[idx].isVowel);
    }

    int nsN = (int)nsIdx.size();
    if (nsN == 0) return {0};

    std::vector<int> nsBounds = {0};

    int i = 1;
    while (i < nsN) {
        if (nsVow[i]) {
            if (i > 0 && nsVow[i - 1]) {
                // Two adjacent vowels: hiatus vs diphthong
                char32_t prevG = units[nsIdx[i - 1]].chars.back();
                char32_t currG = units[nsIdx[i]].chars.back();
                char32_t prevB = baseOf(prevG);
                char32_t currB = baseOf(currG);
                if (isStrongVowel(prevB) && isStrongVowel(currB)) {
                    nsBounds.push_back(i); // hiatus
                } else {
                    // Accented weak vowel forces hiatus
                    if (isWeakVowel(currB) && hasStressAccent(currG)) {
                        nsBounds.push_back(i);
                    } else if (isWeakVowel(prevB) && hasStressAccent(prevG)) {
                        nsBounds.push_back(i);
                    }
                }
            }
            ++i;
        } else {
            // Consonant cluster before next vowel
            int consStart = i;
            while (i < nsN && !nsVow[i]) ++i;
            int consCount = i - consStart;
            if (i < nsN) { // vowel follows
                if (consCount == 1) {
                    nsBounds.push_back(consStart);
                } else if (consCount == 2) {
                    char32_t c1 = baseConsOfUnit(units[nsIdx[consStart]]);
                    char32_t c2 = baseConsOfUnit(units[nsIdx[consStart + 1]]);
                    if (isInseparable(c1, c2)) {
                        nsBounds.push_back(consStart);
                    } else {
                        nsBounds.push_back(consStart + 1);
                    }
                } else {
                    // 3+ consonants
                    char32_t c1 = baseConsOfUnit(units[nsIdx[i - 2]]);
                    char32_t c2 = baseConsOfUnit(units[nsIdx[i - 1]]);
                    if (isInseparable(c1, c2)) {
                        nsBounds.push_back(i - 2);
                    } else {
                        nsBounds.push_back(i - 1);
                    }
                }
            }
        }
    }

    // Map back to unit indices
    std::vector<int> result;
    result.reserve(nsBounds.size());
    for (int b : nsBounds) result.push_back(nsIdx[b]);
    return result;
}

// -----------------------------------------------------------------------
// Stress assignment
// -----------------------------------------------------------------------

// Find character-index of the first accented vowel in a codepoint word,
// or -1 if none.
static int findAccentIndex(const std::vector<char32_t> &word) {
    for (int i = 0; i < (int)word.size(); ++i) {
        if (hasStressAccent(word[i])) return i;
    }
    return -1;
}

static int getStressedSyllable(const std::vector<char32_t> &word,
                               const std::vector<GUnit> &units,
                               const std::vector<int> &boundaries) {
    int numSyl = (int)boundaries.size();
    if (numSyl == 0) return 0;

    // Check for explicit accent
    int accIdx = findAccentIndex(word);
    if (accIdx >= 0) {
        // Map char index to unit index
        int charOff = 0;
        int accUnitIdx = 0;
        for (int uid = 0; uid < (int)units.size(); ++uid) {
            int uLen = (int)units[uid].chars.size();
            if (charOff <= accIdx && accIdx < charOff + uLen) {
                accUnitIdx = uid;
                break;
            }
            charOff += uLen;
        }
        // Find which syllable contains this unit
        for (int s = numSyl - 1; s >= 0; --s) {
            if (boundaries[s] <= accUnitIdx) return s;
        }
        return 0;
    }

    if (numSyl == 1) return 0;

    // Default stress rules: last character base
    char32_t last = baseOf(word.back());
    if (isVowel(last) || last == 'n' || last == 's') {
        return std::max(0, numSyl - 2); // penultimate
    }
    return numSyl - 1; // ultimate
}

// -----------------------------------------------------------------------
// G2P: grapheme-to-phoneme conversion (character walk with lookahead)
// -----------------------------------------------------------------------

struct G2PResult {
    std::vector<Phoneme> phonemes;
    int stressedSyl;
    std::vector<GUnit> units;
    std::vector<int> boundaries;
};

static G2PResult g2pWord(const std::vector<char32_t> &word) {
    std::vector<Phoneme> ph;
    int n = (int)word.size();

    // Build base-form word
    std::vector<char32_t> bw;
    bw.reserve(n);
    for (auto c : word) bw.push_back(baseOf(c));

    auto prevIsVowel = [&](int idx) -> bool {
        return idx > 0 && isVowelOrAccented(word[idx - 1]);
    };
    auto isAfterNasal = [&](int idx) -> bool {
        return idx > 0 && (bw[idx - 1] == 'm' || bw[idx - 1] == 'n');
    };
    auto isWordInitial = [&](int idx) -> bool {
        return idx == 0;
    };

    int i = 0;
    while (i < n) {
        char32_t bc = bw[i];

        // --- Vowels ---
        if (isVowel(bc)) {
            ph.push_back(static_cast<Phoneme>(bc));
            ++i; continue;
        }

        // --- Multi-character sequences (longest first) ---

        // "qu" -> k
        if (bc == 'q' && i + 1 < n && bw[i + 1] == 'u') {
            ph.push_back('k');
            i += 2; continue;
        }

        // "ch" -> tS (PUA)
        if (bc == 'c' && i + 1 < n && bw[i + 1] == 'h') {
            ph.push_back(PUA_TCH);
            i += 2; continue;
        }

        // "ll" -> palatal fricative (yeismo)
        if (bc == 'l' && i + 1 < n && bw[i + 1] == 'l') {
            ph.push_back(IPA_YE);
            i += 2; continue;
        }

        // "rr" -> trill (PUA)
        if (bc == 'r' && i + 1 < n && bw[i + 1] == 'r') {
            ph.push_back(PUA_RR);
            i += 2; continue;
        }

        // "gu-diaeresis" before e/i -> g w
        if (bc == 'g' && i + 1 < n && word[i + 1] == 0x00FC
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            ph.push_back(IPA_G_IPA);
            ph.push_back('w');
            i += 2; continue;
        }

        // "gu" before e/i -> g (u silent); allophonic
        if (bc == 'g' && i + 1 < n && bw[i + 1] == 'u'
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            if (prevIsVowel(i) && !isAfterNasal(i)) {
                ph.push_back(IPA_GAMMA);
            } else {
                ph.push_back(IPA_G_IPA);
            }
            i += 2; continue;
        }

        // "sc" before e/i -> s (seseo, no geminate)
        if (bc == 's' && i + 1 < n && bw[i + 1] == 'c'
            && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
            ph.push_back('s');
            i += 2; continue;
        }

        // --- Single character rules ---

        // b / v (betacismo)
        if (bc == 'b' || bc == 'v') {
            if (isWordInitial(i) || isAfterNasal(i) ||
                (i > 0 && bw[i - 1] == 'l')) {
                ph.push_back('b');
            } else {
                ph.push_back(IPA_BETA);
            }
            ++i; continue;
        }

        // c
        if (bc == 'c') {
            if (i + 1 < n && (bw[i + 1] == 'e' || bw[i + 1] == 'i')) {
                ph.push_back('s'); // seseo
            } else {
                ph.push_back('k');
            }
            ++i; continue;
        }

        // d
        if (bc == 'd') {
            if (isWordInitial(i) || isAfterNasal(i) ||
                (i > 0 && bw[i - 1] == 'l')) {
                ph.push_back('d');
            } else {
                ph.push_back(IPA_ETH);
            }
            ++i; continue;
        }

        // f
        if (bc == 'f') { ph.push_back('f'); ++i; continue; }

        // g
        if (bc == 'g') {
            if (i + 1 < n && (bw[i + 1] == 'e' || bw[i + 1] == 'i')) {
                ph.push_back('x'); // velar fricative (jota)
            } else if (isWordInitial(i) || isAfterNasal(i) ||
                       (i > 0 && bw[i - 1] == 'l')) {
                ph.push_back(IPA_G_IPA);
            } else {
                ph.push_back(IPA_GAMMA);
            }
            ++i; continue;
        }

        // h (silent)
        if (bc == 'h') { ++i; continue; }

        // j
        if (bc == 'j') { ph.push_back('x'); ++i; continue; }

        // k
        if (bc == 'k') { ph.push_back('k'); ++i; continue; }

        // l
        if (bc == 'l') { ph.push_back('l'); ++i; continue; }

        // m
        if (bc == 'm') { ph.push_back('m'); ++i; continue; }

        // n
        if (bc == 'n') { ph.push_back('n'); ++i; continue; }

        // n-tilde
        if (bc == 0x00F1) { ph.push_back(IPA_PALATAL); ++i; continue; }

        // p
        if (bc == 'p') { ph.push_back('p'); ++i; continue; }

        // r (single)
        if (bc == 'r') {
            if (isWordInitial(i)) {
                ph.push_back(PUA_RR); // trill
            } else if (i > 0 && (bw[i - 1] == 'l' || bw[i - 1] == 'n' || bw[i - 1] == 's')) {
                ph.push_back(PUA_RR); // trill after l/n/s
            } else {
                ph.push_back(IPA_TAP);
            }
            ++i; continue;
        }

        // s
        if (bc == 's') { ph.push_back('s'); ++i; continue; }

        // t
        if (bc == 't') { ph.push_back('t'); ++i; continue; }

        // w
        if (bc == 'w') { ph.push_back('w'); ++i; continue; }

        // x
        if (bc == 'x') {
            // xc+e/i: c is absorbed, x provides /ks/
            if (i + 1 < n && bw[i + 1] == 'c'
                && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')) {
                ph.push_back('k');
                ph.push_back('s');
                i += 2; continue;
            }
            ph.push_back('k');
            ph.push_back('s');
            ++i; continue;
        }

        // y
        if (bc == 'y') {
            if (i == n - 1) {
                ph.push_back('i'); // word-final y -> vowel
            } else {
                ph.push_back(IPA_YE);
            }
            ++i; continue;
        }

        // z (seseo)
        if (bc == 'z') { ph.push_back('s'); ++i; continue; }

        // Unknown -> skip
        ++i;
    }

    // Syllabification & stress
    auto units = segmentGraphemes(word);
    auto bounds = findSyllableBoundaries(word, units);
    int stSyl = getStressedSyllable(word, units, bounds);

    return {std::move(ph), stSyl, std::move(units), std::move(bounds)};
}

// -----------------------------------------------------------------------
// Phoneme count per grapheme unit (for stress marker insertion)
// -----------------------------------------------------------------------
static int phonemeCountForUnit(const GUnit &unit) {
    // Build base form of the grapheme
    std::vector<char32_t> base;
    for (auto c : unit.chars) base.push_back(baseOf(c));

    // Silent h -> 0
    if (base.size() == 1 && base[0] == 'h') return 0;

    // "gu-diaeresis" digraph -> 2 (g + w)
    if (base.size() == 2 && base[0] == 'g' && unit.chars[1] == 0x00FC) return 2;

    // "xc" digraph before e/i -> k s (2 phonemes)
    if (base.size() == 2 && base[0] == 'x' && base[1] == 'c') return 2;

    // x -> ks (2)
    if (base.size() == 1 && base[0] == 'x') return 2;

    // Everything else -> 1
    return 1;
}

// -----------------------------------------------------------------------
// Insert stress marker before the stressed syllable's first vowel phoneme
// -----------------------------------------------------------------------
static void insertStressMarker(std::vector<Phoneme> &phonemes,
                               const std::vector<GUnit> &units,
                               const std::vector<int> &boundaries,
                               int stressedSyl) {
    if (phonemes.empty() || boundaries.empty()) return;
    if (stressedSyl >= (int)boundaries.size()) return;

    int numUnits = (int)units.size();
    int sylStart = boundaries[stressedSyl];
    int sylEnd = (stressedSyl + 1 < (int)boundaries.size())
                     ? boundaries[stressedSyl + 1]
                     : numUnits;

    // Find first vowel unit in stressed syllable
    int stressedUnitIdx = -1;
    for (int uid = sylStart; uid < sylEnd && uid < numUnits; ++uid) {
        if (units[uid].isVowel) {
            stressedUnitIdx = uid;
            break;
        }
    }
    if (stressedUnitIdx < 0) return;

    // Walk units -> accumulate phoneme count to find insertion point
    int phI = 0;
    for (int uid = 0; uid < numUnits; ++uid) {
        if (uid == stressedUnitIdx) {
            phonemes.insert(phonemes.begin() + phI, IPA_STRESS);
            return;
        }
        phI += phonemeCountForUnit(units[uid]);
    }
}

} // anonymous namespace

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

void phonemize_spanish(const std::string &text,
                       std::vector<std::vector<Phoneme>> &phonemes) {
    phonemes.clear();

    if (!utf8::is_valid(text.begin(), text.end())) {
        return;
    }

    // Decode and normalize
    auto cps = toCodepoints(text);
    cps = normalize(cps);

    // Tokenize
    auto tokens = tokenize(cps);
    if (tokens.empty()) return;

    std::vector<Phoneme> sentence;
    bool needSpace = false;

    for (const auto &tok : tokens) {
        // Punctuation token
        if (!tok.isWord) {
            for (auto cp : tok.chars) {
                sentence.push_back(cp);
            }
            continue;
        }

        // Word token
        if (needSpace) {
            sentence.push_back(static_cast<Phoneme>(' '));
        }

        auto res = g2pWord(tok.chars);

        // Check if unstressed function word
        std::string wordUtf8 = cpVecToUtf8(tok.chars);
        bool isFunction = UNSTRESSED_FUNCTION_WORDS.count(wordUtf8) > 0;

        if (!isFunction) {
            insertStressMarker(res.phonemes, res.units, res.boundaries,
                               res.stressedSyl);
        }

        for (auto p : res.phonemes) {
            sentence.push_back(p);
        }
        needSpace = true;
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
