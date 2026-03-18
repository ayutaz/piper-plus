// Rule-based French grapheme-to-phoneme conversion for Piper TTS.
// Port of src/python/piper_train/phonemize/french.py to C++.
//
// Converts French text to IPA phonemes using grapheme-to-phoneme rules.
// No external G2P engine required.

#include "french_phonemize.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>

namespace piper {
namespace { // anonymous namespace for internal helpers

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character phoneme tokens
// ---------------------------------------------------------------------------
// Must match token_mapper.py FIXED_PUA_MAPPING + dynamic allocation order.
constexpr char32_t PUA_Y_VOWEL    = 0xE01E; // y_vowel [y] (lune, tu)
constexpr char32_t PUA_NASAL_EIN  = 0xE056; // nasal open-mid front unrounded [nasal epsilon tilde]
constexpr char32_t PUA_NASAL_AN   = 0xE057; // nasal open back unrounded [nasal alpha tilde]
constexpr char32_t PUA_NASAL_ON   = 0xE058; // nasal open-mid back rounded [nasal open-o tilde]

// Single IPA codepoints (output directly)
constexpr char32_t IPA_OPEN_E     = 0x025B; // open-mid front unrounded
constexpr char32_t IPA_OPEN_O     = 0x0254; // open-mid back rounded
constexpr char32_t IPA_SCHWA      = 0x0259; // schwa
constexpr char32_t IPA_VOICED_G   = 0x0261; // voiced velar plosive (IPA g)
constexpr char32_t IPA_ESH        = 0x0283; // voiceless postalveolar fricative
constexpr char32_t IPA_EZH        = 0x0292; // voiced postalveolar fricative
constexpr char32_t IPA_UVULAR_R   = 0x0281; // voiced uvular fricative
constexpr char32_t IPA_PALATAL_N  = 0x0272; // palatal nasal
constexpr char32_t IPA_TURNED_H   = 0x0265; // labial-palatal approximant
constexpr char32_t IPA_SLASHED_O  = 0x00F8; // close-mid front rounded
constexpr char32_t IPA_OE_LIG     = 0x0153; // open-mid front rounded

// Punctuation codepoints used in output
constexpr char32_t CH_COMMA       = U',';
constexpr char32_t CH_PERIOD      = U'.';
constexpr char32_t CH_SEMICOLON   = U';';
constexpr char32_t CH_COLON       = U':';
constexpr char32_t CH_EXCL        = U'!';
constexpr char32_t CH_QUEST       = U'?';
constexpr char32_t CH_INV_EXCL    = 0x00A1;
constexpr char32_t CH_INV_QUEST   = 0x00BF;
constexpr char32_t CH_EM_DASH     = 0x2014;
constexpr char32_t CH_EN_DASH     = 0x2013;
constexpr char32_t CH_ELLIPSIS    = 0x2026;
constexpr char32_t CH_LAQUO       = 0x00AB;
constexpr char32_t CH_RAQUO       = 0x00BB;
constexpr char32_t CH_SPACE       = U' ';

// ---------------------------------------------------------------------------
// Character classification sets
// ---------------------------------------------------------------------------

static bool isVowelChar(char32_t ch) {
    // aeiouy plus accented variants
    switch (ch) {
        case U'a': case U'e': case U'i': case U'o': case U'u': case U'y':
        case 0x00E0: // a-grave
        case 0x00E2: // a-circ
        case 0x00E6: // ae ligature
        case 0x00E9: // e-acute
        case 0x00E8: // e-grave
        case 0x00EA: // e-circ
        case 0x00EB: // e-diaeresis
        case 0x00EE: // i-circ
        case 0x00EF: // i-diaeresis
        case 0x00F4: // o-circ
        case 0x00F9: // u-grave
        case 0x00FB: // u-circ
        case 0x00FC: // u-diaeresis
        case 0x0153: // oe ligature
            return true;
        default:
            return false;
    }
}

static bool isConsonantChar(char32_t ch) {
    switch (ch) {
        case U'b': case U'c': case U'd': case U'f': case U'g':
        case U'h': case U'j': case U'k': case U'l': case U'm':
        case U'n': case U'p': case U'q': case U'r': case U's':
        case U't': case U'v': case U'w': case U'x': case U'z':
            return true;
        default:
            return false;
    }
}

static bool isSilentFinal(char32_t ch) {
    switch (ch) {
        case U'd': case U'g': case U'h': case U'm': case U'n':
        case U'p': case U's': case U't': case U'x': case U'z':
            return true;
        default:
            return false;
    }
}

static bool isPunctuation(char32_t ch) {
    switch (ch) {
        case CH_COMMA: case CH_PERIOD: case CH_SEMICOLON: case CH_COLON:
        case CH_EXCL: case CH_QUEST: case CH_INV_EXCL: case CH_INV_QUEST:
        case CH_EM_DASH: case CH_EN_DASH: case CH_ELLIPSIS:
        case CH_LAQUO: case CH_RAQUO:
            return true;
        default:
            return false;
    }
}

static bool isFrontVowelForCG(char32_t ch) {
    // Characters that trigger c->s and g->zh softening
    switch (ch) {
        case U'e': case U'i': case U'y':
        case 0x00E9: // e-acute
        case 0x00E8: // e-grave
        case 0x00EA: // e-circ
        case 0x00EB: // e-diaeresis
        case 0x00EE: // i-circ
        case 0x00EF: // i-diaeresis
            return true;
        default:
            return false;
    }
}

// ---------------------------------------------------------------------------
// Exception word sets
// ---------------------------------------------------------------------------

// Words where "ille" is pronounced /il/ not /ij/
static const std::unordered_set<std::u32string> ILLE_AS_IL = {
    U"ville", U"mille", U"tranquille"
};

// Polysyllabic words ending in -er pronounced /ehr/ not /e/
static const std::unordered_set<std::u32string> ER_AS_EHR = {
    U"hiver", U"enfer", U"amer", U"cancer", U"super",
    U"laser", U"hamster", U"master", U"poster", U"cluster",
    U"starter", U"leader", U"transfer", U"fer"
};

// ---------------------------------------------------------------------------
// UTF-8 <-> UTF-32 helpers — delegated to utf8_utils.hpp
// ---------------------------------------------------------------------------

using utf8_util::utf8ToU32;

// ---------------------------------------------------------------------------
// Normalize: collapse NFD combining sequences, lowercase, strip whitespace
// ---------------------------------------------------------------------------

// Collapse NFD (decomposed) base+combining-mark pairs into NFC pre-composed
// codepoints.  This handles input where accented characters arrive as two
// codepoints (e.g. U+0065 U+0301 for e-acute) instead of the single NFC form
// (U+00E9).  Both upper- and lowercase base letters are handled; toLowerFr()
// is applied afterwards.
//
// Combining marks handled:
//   U+0300 combining grave accent
//   U+0301 combining acute accent
//   U+0302 combining circumflex accent
//   U+0303 combining tilde
//   U+0308 combining diaeresis
//   U+0327 combining cedilla
static std::u32string collapseNFD(const std::u32string &input) {
    std::u32string out;
    out.reserve(input.size());

    size_t i = 0;
    size_t n = input.size();
    while (i < n) {
        char32_t ch = input[i];

        // Check if next codepoint is a combining mark we handle
        if (i + 1 < n) {
            char32_t comb = input[i + 1];
            char32_t composed = 0;

            switch (comb) {
            case 0x0300: // combining grave accent
                switch (ch) {
                    case U'A': composed = 0x00C0; break; // A-grave
                    case U'a': composed = 0x00E0; break; // a-grave
                    case U'E': composed = 0x00C8; break; // E-grave
                    case U'e': composed = 0x00E8; break; // e-grave
                    case U'U': composed = 0x00D9; break; // U-grave
                    case U'u': composed = 0x00F9; break; // u-grave
                    default: break;
                }
                break;

            case 0x0301: // combining acute accent
                switch (ch) {
                    case U'E': composed = 0x00C9; break; // E-acute
                    case U'e': composed = 0x00E9; break; // e-acute
                    default: break;
                }
                break;

            case 0x0302: // combining circumflex accent
                switch (ch) {
                    case U'A': composed = 0x00C2; break; // A-circumflex
                    case U'a': composed = 0x00E2; break; // a-circumflex
                    case U'E': composed = 0x00CA; break; // E-circumflex
                    case U'e': composed = 0x00EA; break; // e-circumflex
                    case U'I': composed = 0x00CE; break; // I-circumflex
                    case U'i': composed = 0x00EE; break; // i-circumflex
                    case U'O': composed = 0x00D4; break; // O-circumflex
                    case U'o': composed = 0x00F4; break; // o-circumflex
                    case U'U': composed = 0x00DB; break; // U-circumflex
                    case U'u': composed = 0x00FB; break; // u-circumflex
                    default: break;
                }
                break;

            case 0x0303: // combining tilde (loan words: ñ)
                switch (ch) {
                    case U'N': composed = 0x00D1; break; // N-tilde
                    case U'n': composed = 0x00F1; break; // n-tilde
                    default: break;
                }
                break;

            case 0x0308: // combining diaeresis
                switch (ch) {
                    case U'E': composed = 0x00CB; break; // E-diaeresis
                    case U'e': composed = 0x00EB; break; // e-diaeresis
                    case U'I': composed = 0x00CF; break; // I-diaeresis
                    case U'i': composed = 0x00EF; break; // i-diaeresis
                    case U'U': composed = 0x00DC; break; // U-diaeresis
                    case U'u': composed = 0x00FC; break; // u-diaeresis
                    default: break;
                }
                break;

            case 0x0327: // combining cedilla
                switch (ch) {
                    case U'C': composed = 0x00C7; break; // C-cedilla
                    case U'c': composed = 0x00E7; break; // c-cedilla
                    default: break;
                }
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

        out.push_back(ch);
        ++i;
    }

    return out;
}

// Simple ASCII-range + Latin-1 Supplement + Latin Extended-A tolower
static char32_t toLowerFr(char32_t ch) {
    // ASCII
    if (ch >= U'A' && ch <= U'Z')
        return ch + 32;
    // Latin-1 Supplement uppercase block: 0xC0-0xD6, 0xD8-0xDE -> +0x20
    if ((ch >= 0x00C0 && ch <= 0x00D6) || (ch >= 0x00D8 && ch <= 0x00DE))
        return ch + 0x20;
    // OE ligature: U+0152 -> U+0153
    if (ch == 0x0152)
        return 0x0153;
    // AE ligature: U+00C6 -> U+00E6 (already covered above)
    return ch;
}

static std::u32string normalize(const std::u32string &input) {
    // First collapse NFD combining sequences into NFC pre-composed forms.
    // This must happen before lowercasing so that e.g. 'E' + U+0301 becomes
    // U+00C9 (E-acute) which toLowerFr() then maps to U+00E9 (e-acute).
    std::u32string nfc = collapseNFD(input);

    std::u32string result;
    result.reserve(nfc.size());

    bool lastWasSpace = true; // to collapse leading spaces
    for (char32_t ch : nfc) {
        // Collapse whitespace
        if (ch == U' ' || ch == U'\t' || ch == U'\n' || ch == U'\r') {
            if (!lastWasSpace) {
                result.push_back(U' ');
                lastWasSpace = true;
            }
            continue;
        }
        lastWasSpace = false;
        result.push_back(toLowerFr(ch));
    }
    // Strip trailing space
    if (!result.empty() && result.back() == U' ')
        result.pop_back();

    return result;
}

// ---------------------------------------------------------------------------
// Tokenizer: split into words and punctuation
// ---------------------------------------------------------------------------

// Apostrophe normalization (curly -> straight, then treated as word boundary)
static std::u32string normalizeApostrophes(const std::u32string &s) {
    std::u32string result;
    result.reserve(s.size());
    for (char32_t ch : s) {
        if (ch == 0x2019 || ch == 0x2018) {
            // Typographic apostrophes -> space (word boundary)
            result.push_back(U' ');
        } else if (ch == U'\'') {
            result.push_back(U' ');
        } else {
            result.push_back(ch);
        }
    }
    return result;
}

static bool isLetterFr(char32_t ch) {
    // a-z
    if (ch >= U'a' && ch <= U'z') return true;
    // French accented + special letters
    switch (ch) {
        case 0x00E0: case 0x00E2: case 0x00E6: // a-grave, a-circ, ae
        case 0x00E9: case 0x00E8: case 0x00EA: case 0x00EB: // e accented
        case 0x00EE: case 0x00EF: // i accented
        case 0x00F4: // o-circ
        case 0x00F9: case 0x00FB: case 0x00FC: // u accented
        case 0x0153: // oe ligature
        case 0x00E7: // c-cedilla
        case 0x00F1: // n-tilde (for borrowed words)
            return true;
        default:
            return false;
    }
}

struct Token {
    std::u32string text;
    bool isPunct;
};

static std::vector<Token> splitWords(const std::u32string &text) {
    std::u32string processed = normalizeApostrophes(text);
    std::vector<Token> tokens;

    size_t i = 0;
    size_t n = processed.size();
    while (i < n) {
        char32_t ch = processed[i];

        // Skip spaces
        if (ch == U' ') {
            ++i;
            continue;
        }

        // Punctuation token (single char)
        if (isPunctuation(ch)) {
            Token tok;
            tok.text.push_back(ch);
            tok.isPunct = true;
            tokens.push_back(std::move(tok));
            ++i;
            continue;
        }

        // Letter sequence (word)
        if (isLetterFr(ch)) {
            Token tok;
            tok.isPunct = false;
            while (i < n && isLetterFr(processed[i])) {
                tok.text.push_back(processed[i]);
                ++i;
            }
            tokens.push_back(std::move(tok));
            continue;
        }

        // Skip unknown characters
        ++i;
    }

    return tokens;
}

// ---------------------------------------------------------------------------
// Core word conversion: French grapheme-to-phoneme rules
// ---------------------------------------------------------------------------

// Count vowel characters in a word
static int countVowels(const std::u32string &word) {
    int count = 0;
    for (char32_t ch : word) {
        if (isVowelChar(ch)) ++count;
    }
    return count;
}

static std::vector<Phoneme> convertWord(const std::u32string &word) {
    std::vector<Phoneme> phonemes;
    size_t i = 0;
    size_t n = word.size();

    while (i < n) {
        char32_t ch = word[i];

        // ---------------------------------------------------------------
        // Multi-character sequences (longest match first)
        // ---------------------------------------------------------------

        // -er word-final: verb infinitive ending -> /e/
        if (ch == U'e' && i + 1 == n - 1 && word[i + 1] == U'r') {
            int vc = countVowels(word);
            if (vc >= 2 && ER_AS_EHR.find(word) == ER_AS_EHR.end()) {
                // Polysyllabic -er -> /e/ (silent r)
                phonemes.push_back(U'e');
                i += 2;
                continue;
            }
            // else: monosyllabic or exception -- fall through
        }

        // "eau" -> o
        if (ch == U'e' && i + 2 < n && word[i + 1] == U'a' && word[i + 2] == U'u') {
            phonemes.push_back(U'o');
            i += 3;
            continue;
        }

        // "ouille" -> /uj/
        if (ch == U'o' && i + 5 < n
            && word[i + 1] == U'u' && word[i + 2] == U'i'
            && word[i + 3] == U'l' && word[i + 4] == U'l' && word[i + 5] == U'e'
            && (i + 6 >= n || !isVowelChar(word[i + 6])))
        {
            phonemes.push_back(U'u');
            phonemes.push_back(U'j');
            i += 6;
            continue;
        }

        // "aille" -> /aj/
        if (ch == U'a' && i + 4 < n
            && word[i + 1] == U'i' && word[i + 2] == U'l'
            && word[i + 3] == U'l' && word[i + 4] == U'e'
            && (i + 5 >= n || !isVowelChar(word[i + 5])))
        {
            phonemes.push_back(U'a');
            phonemes.push_back(U'j');
            i += 5;
            continue;
        }

        // "euille" -> /oej/ at word end (feuille)
        if (ch == U'e' && i + 5 < n
            && word[i + 1] == U'u' && word[i + 2] == U'i'
            && word[i + 3] == U'l' && word[i + 4] == U'l' && word[i + 5] == U'e'
            && i + 6 >= n)
        {
            phonemes.push_back(IPA_OE_LIG);
            phonemes.push_back(U'j');
            i += 6;
            continue;
        }

        // "eil" at word end -> /ej/ (soleil, reveil)
        if (ch == U'e' && i + 2 < n
            && word[i + 1] == U'i' && word[i + 2] == U'l'
            && i + 3 >= n)
        {
            phonemes.push_back(IPA_OPEN_E);
            phonemes.push_back(U'j');
            i += 3;
            continue;
        }

        // "eille" -> /ej/
        if (ch == U'e' && i + 4 < n
            && word[i + 1] == U'i' && word[i + 2] == U'l'
            && word[i + 3] == U'l' && word[i + 4] == U'e'
            && (i + 5 >= n || !isVowelChar(word[i + 5])))
        {
            phonemes.push_back(IPA_OPEN_E);
            phonemes.push_back(U'j');
            i += 5;
            continue;
        }

        // "ain", "aim" -> nasal-epsilon-tilde
        if (ch == U'a' && i + 2 < n
            && word[i + 1] == U'i'
            && (word[i + 2] == U'n' || word[i + 2] == U'm'))
        {
            if (i + 3 >= n || !isVowelChar(word[i + 3])) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 3;
                continue;
            }
        }

        // "ein", "eim" -> nasal-epsilon-tilde
        if (ch == U'e' && i + 2 < n
            && word[i + 1] == U'i'
            && (word[i + 2] == U'n' || word[i + 2] == U'm'))
        {
            if (i + 3 >= n || !isVowelChar(word[i + 3])) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 3;
                continue;
            }
        }

        // "oin" -> w + nasal-epsilon-tilde
        if (ch == U'o' && i + 2 < n
            && word[i + 1] == U'i' && word[i + 2] == U'n')
        {
            if (i + 3 >= n || !isVowelChar(word[i + 3])) {
                phonemes.push_back(U'w');
                phonemes.push_back(PUA_NASAL_EIN);
                i += 3;
                continue;
            }
        }

        // "ien" -> j + nasal-epsilon-tilde
        if (ch == U'i' && i + 2 < n
            && word[i + 1] == U'e' && word[i + 2] == U'n')
        {
            if (i + 3 >= n || !isVowelChar(word[i + 3])) {
                phonemes.push_back(U'j');
                phonemes.push_back(PUA_NASAL_EIN);
                i += 3;
                continue;
            }
        }

        // "tion" -> /sjon/ (or /tjon/ after 's')
        if (ch == U't' && i + 3 < n
            && word[i + 1] == U'i' && word[i + 2] == U'o' && word[i + 3] == U'n')
        {
            if (i + 4 >= n || !isVowelChar(word[i + 4])) {
                if (i > 0 && word[i - 1] == U's') {
                    // "stion" -> the 's' already emitted /s/, produce /t/
                    phonemes.push_back(U't');
                } else {
                    phonemes.push_back(U's');
                }
                phonemes.push_back(U'j');
                phonemes.push_back(PUA_NASAL_ON);
                i += 4;
                continue;
            }
        }

        // "ille" -> /ij/ default, /il/ for exceptions
        if (ch == U'i' && i + 3 < n
            && word[i + 1] == U'l' && word[i + 2] == U'l' && word[i + 3] == U'e'
            && (i + 4 >= n || !isVowelChar(word[i + 4])))
        {
            phonemes.push_back(U'i');
            if (ILLE_AS_IL.find(word) != ILLE_AS_IL.end()) {
                phonemes.push_back(U'l');
            } else {
                phonemes.push_back(U'j');
            }
            i += 4;
            continue;
        }

        // "gn" -> palatal nasal
        if (ch == U'g' && i + 1 < n && word[i + 1] == U'n') {
            phonemes.push_back(IPA_PALATAL_N);
            i += 2;
            continue;
        }

        // "ph" -> f
        if (ch == U'p' && i + 1 < n && word[i + 1] == U'h') {
            phonemes.push_back(U'f');
            i += 2;
            continue;
        }

        // "th" -> t
        if (ch == U't' && i + 1 < n && word[i + 1] == U'h') {
            phonemes.push_back(U't');
            i += 2;
            continue;
        }

        // "ch" -> voiceless postalveolar fricative
        if (ch == U'c' && i + 1 < n && word[i + 1] == U'h') {
            phonemes.push_back(IPA_ESH);
            i += 2;
            continue;
        }

        // "qu" -> k
        if (ch == U'q' && i + 1 < n && word[i + 1] == U'u') {
            phonemes.push_back(U'k');
            i += 2;
            continue;
        }

        // "gu" + front vowel -> voiced velar (silent u)
        if (ch == U'g' && i + 1 < n && word[i + 1] == U'u') {
            if (i + 2 < n && isFrontVowelForCG(word[i + 2])) {
                phonemes.push_back(IPA_VOICED_G);
                i += 2; // consume 'g' and 'u', leave the vowel
                continue;
            }
        }

        // ---------------------------------------------------------------
        // Nasal vowels: vowel + n/m before consonant or end
        // ---------------------------------------------------------------

        // "an", "am", "en", "em" -> nasal-alpha-tilde
        if ((ch == U'a' || ch == U'e')
            && i + 1 < n && (word[i + 1] == U'n' || word[i + 1] == U'm'))
        {
            if (i + 2 >= n) {
                phonemes.push_back(PUA_NASAL_AN);
                i += 2;
                continue;
            }
            if (!isVowelChar(word[i + 2]) && word[i + 2] != word[i + 1]) {
                phonemes.push_back(PUA_NASAL_AN);
                i += 2;
                continue;
            }
        }

        // "in", "im" -> nasal-epsilon-tilde
        if (ch == U'i' && i + 1 < n && (word[i + 1] == U'n' || word[i + 1] == U'm')) {
            if (i + 2 >= n) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if (!isVowelChar(word[i + 2]) && word[i + 2] != word[i + 1]) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // "on", "om" -> nasal-open-o-tilde
        if (ch == U'o' && i + 1 < n && (word[i + 1] == U'n' || word[i + 1] == U'm')) {
            if (i + 2 >= n) {
                phonemes.push_back(PUA_NASAL_ON);
                i += 2;
                continue;
            }
            if (!isVowelChar(word[i + 2]) && word[i + 2] != word[i + 1]) {
                phonemes.push_back(PUA_NASAL_ON);
                i += 2;
                continue;
            }
        }

        // "un", "um" -> nasal-epsilon-tilde (modern French merger)
        if (ch == U'u' && i + 1 < n && (word[i + 1] == U'n' || word[i + 1] == U'm')) {
            if (i + 2 >= n) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if (!isVowelChar(word[i + 2]) && word[i + 2] != word[i + 1]) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // "yn", "ym" -> nasal-epsilon-tilde (syndicat, symbole)
        if (ch == U'y' && i + 1 < n && (word[i + 1] == U'n' || word[i + 1] == U'm')) {
            if (i + 2 >= n) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if (!isVowelChar(word[i + 2]) && word[i + 2] != word[i + 1]) {
                phonemes.push_back(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // ---------------------------------------------------------------
        // Vowel digraphs
        // ---------------------------------------------------------------

        // "ou" -> u
        if (ch == U'o' && i + 1 < n && word[i + 1] == U'u') {
            phonemes.push_back(U'u');
            i += 2;
            continue;
        }

        // "au" -> o
        if (ch == U'a' && i + 1 < n && word[i + 1] == U'u') {
            phonemes.push_back(U'o');
            i += 2;
            continue;
        }

        // "oi" -> wa
        if (ch == U'o' && i + 1 < n && word[i + 1] == U'i') {
            phonemes.push_back(U'w');
            phonemes.push_back(U'a');
            i += 2;
            continue;
        }

        // "ai" -> open-e
        if (ch == U'a' && i + 1 < n && word[i + 1] == U'i') {
            phonemes.push_back(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "ei" -> open-e
        if (ch == U'e' && i + 1 < n && word[i + 1] == U'i') {
            phonemes.push_back(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "eu", "oeu" -> slashed-o (closed) or oe-ligature (open before pronounced consonant)
        if ((ch == U'e' && i + 1 < n && word[i + 1] == U'u')
            || (ch == 0x0153 /* oe ligature */ && i + 1 < n && word[i + 1] == U'u'))
        {
            // Open before a pronounced consonant in the same syllable
            if (i + 2 < n
                && isConsonantChar(word[i + 2])
                && !isSilentFinal(word[i + 2]))
            {
                phonemes.push_back(IPA_OE_LIG);
            } else {
                phonemes.push_back(IPA_SLASHED_O);
            }
            i += 2;
            continue;
        }

        // ---------------------------------------------------------------
        // Single vowels
        // ---------------------------------------------------------------

        // e-acute -> e
        if (ch == 0x00E9) {
            phonemes.push_back(U'e');
            ++i;
            continue;
        }

        // e-grave, e-circumflex -> open-e
        if (ch == 0x00E8 || ch == 0x00EA) {
            phonemes.push_back(IPA_OPEN_E);
            ++i;
            continue;
        }

        // e-diaeresis -> open-e
        if (ch == 0x00EB) {
            phonemes.push_back(IPA_OPEN_E);
            ++i;
            continue;
        }

        // a-grave, a-circumflex -> a
        if (ch == 0x00E0 || ch == 0x00E2) {
            phonemes.push_back(U'a');
            ++i;
            continue;
        }

        // plain a
        if (ch == U'a') {
            phonemes.push_back(U'a');
            ++i;
            continue;
        }

        // i-circumflex, i-diaeresis -> i
        if (ch == 0x00EE || ch == 0x00EF) {
            phonemes.push_back(U'i');
            ++i;
            continue;
        }

        // i: before vowel -> j (semi-vowel), except before word-final silent 'e'
        if (ch == U'i') {
            if (i + 1 < n && isVowelChar(word[i + 1])) {
                // Don't glide before word-final silent 'e' (vie, amie)
                if (i + 1 == n - 1 && word[i + 1] == U'e') {
                    phonemes.push_back(U'i');
                } else {
                    phonemes.push_back(U'j');
                }
            } else {
                phonemes.push_back(U'i');
            }
            ++i;
            continue;
        }

        // o-circumflex -> o
        if (ch == 0x00F4) {
            phonemes.push_back(U'o');
            ++i;
            continue;
        }

        // plain o: open before pronounced consonant, closed otherwise
        if (ch == U'o') {
            // Build effective remaining by trimming trailing "es" or "e"
            bool allConsonants = true;
            bool hasPronouncedConsonant = false;
            bool hasEffective = false;

            size_t effStart = i + 1;
            size_t effEnd = n;
            if (effEnd > effStart) {
                // Strip trailing "es"
                if (effEnd - effStart >= 2
                    && word[effEnd - 2] == U'e' && word[effEnd - 1] == U's')
                {
                    effEnd -= 2;
                }
                // Strip trailing "e" (only if we didn't already strip "es")
                else if (word[effEnd - 1] == U'e') {
                    effEnd -= 1;
                }
            }

            for (size_t k = effStart; k < effEnd; ++k) {
                hasEffective = true;
                if (!isConsonantChar(word[k])) {
                    allConsonants = false;
                    break;
                }
                if (!isSilentFinal(word[k])) {
                    hasPronouncedConsonant = true;
                }
            }

            if (hasEffective && allConsonants && hasPronouncedConsonant) {
                phonemes.push_back(IPA_OPEN_O);
            } else {
                phonemes.push_back(U'o');
            }
            ++i;
            continue;
        }

        // u-grave, u-circumflex -> y_vowel
        if (ch == 0x00F9 || ch == 0x00FB) {
            phonemes.push_back(PUA_Y_VOWEL);
            ++i;
            continue;
        }

        // u-diaeresis -> y_vowel
        if (ch == 0x00FC) {
            phonemes.push_back(PUA_Y_VOWEL);
            ++i;
            continue;
        }

        // u: semi-vowel before i, otherwise y_vowel
        if (ch == U'u') {
            if (i + 1 < n && word[i + 1] == U'i') {
                phonemes.push_back(IPA_TURNED_H); // labial-palatal approximant
                phonemes.push_back(U'i');
                i += 2;
                continue;
            }
            phonemes.push_back(PUA_Y_VOWEL);
            ++i;
            continue;
        }

        // y: before vowel -> j, otherwise -> i
        if (ch == U'y') {
            if (i + 1 < n && isVowelChar(word[i + 1])) {
                phonemes.push_back(U'j');
            } else {
                phonemes.push_back(U'i');
            }
            ++i;
            continue;
        }

        // oe ligature -> oe-lig IPA
        if (ch == 0x0153) {
            phonemes.push_back(IPA_OE_LIG);
            ++i;
            continue;
        }

        // ae ligature -> e
        if (ch == 0x00E6) {
            phonemes.push_back(U'e');
            ++i;
            continue;
        }

        // plain 'e': context-dependent
        if (ch == U'e') {
            // Word-final 'e' is silent (e muet)
            if (i == n - 1) {
                ++i;
                continue;
            }

            // Look at what follows
            size_t consCount = 0;
            for (size_t k = i + 1; k < n; ++k) {
                if (isConsonantChar(word[k])) {
                    ++consCount;
                } else {
                    break;
                }
            }

            // Closed syllable: 2+ leading consonants -> open-e
            if (consCount >= 2) {
                phonemes.push_back(IPA_OPEN_E);
                ++i;
                continue;
            }

            // All remaining chars are consonants with at least one pronounced
            bool allCons = true;
            bool hasPronounced = false;
            for (size_t k = i + 1; k < n; ++k) {
                if (!isConsonantChar(word[k])) {
                    allCons = false;
                    break;
                }
                if (!isSilentFinal(word[k])) {
                    hasPronounced = true;
                }
            }
            if (i + 1 < n && allCons && hasPronounced) {
                phonemes.push_back(IPA_OPEN_E);
            } else {
                phonemes.push_back(IPA_SCHWA);
            }
            ++i;
            continue;
        }

        // ---------------------------------------------------------------
        // Consonants
        // ---------------------------------------------------------------

        // c: before front vowel -> s, otherwise -> k
        if (ch == U'c') {
            if (i + 1 < n && isFrontVowelForCG(word[i + 1])) {
                phonemes.push_back(U's');
            } else {
                phonemes.push_back(U'k');
            }
            ++i;
            continue;
        }

        // c-cedilla -> s
        if (ch == 0x00E7) {
            phonemes.push_back(U's');
            ++i;
            continue;
        }

        // g: before front vowel -> voiced postalveolar fricative, otherwise -> voiced velar
        if (ch == U'g') {
            if (i + 1 < n && isFrontVowelForCG(word[i + 1])) {
                phonemes.push_back(IPA_EZH);
            } else {
                phonemes.push_back(IPA_VOICED_G);
            }
            ++i;
            continue;
        }

        // j -> voiced postalveolar fricative
        if (ch == U'j') {
            phonemes.push_back(IPA_EZH);
            ++i;
            continue;
        }

        // r -> uvular r (skip doubled r)
        if (ch == U'r') {
            phonemes.push_back(IPA_UVULAR_R);
            if (i + 1 < n && word[i + 1] == U'r') {
                i += 2;
            } else {
                ++i;
            }
            continue;
        }

        // x: context-dependent
        if (ch == U'x') {
            // Word-final x is silent
            if (i == n - 1) {
                ++i;
                continue;
            }
            // Silent before final silent 'e'/'es'
            {
                size_t remLen = n - (i + 1);
                bool silentBefore = false;
                if (remLen == 1 && word[i + 1] == U'e') {
                    silentBefore = true;
                } else if (remLen == 2 && word[i + 1] == U'e' && word[i + 2] == U's') {
                    silentBefore = true;
                }
                if (silentBefore) {
                    ++i;
                    continue;
                }
            }
            // "ex" + vowel -> /gz/
            if (i > 0 && word[i - 1] == U'e'
                && i + 1 < n && isVowelChar(word[i + 1]))
            {
                phonemes.push_back(IPA_VOICED_G);
                phonemes.push_back(U'z');
                ++i;
                continue;
            }
            // Default: x -> /ks/
            phonemes.push_back(U'k');
            phonemes.push_back(U's');
            ++i;
            continue;
        }

        // h is always silent
        if (ch == U'h') {
            ++i;
            continue;
        }

        // ---------------------------------------------------------------
        // Double consonant -> single (pass-through marker for fall-through)
        // ---------------------------------------------------------------
        // If this consonant is doubled, the simple mapping below will skip
        // the duplicate.

        // ---------------------------------------------------------------
        // Simple consonant mappings
        // ---------------------------------------------------------------
        {
            Phoneme mapped = 0;
            switch (ch) {
                case U'b': mapped = U'b'; break;
                case U'd': mapped = U'd'; break;
                case U'f': mapped = U'f'; break;
                case U'k': mapped = U'k'; break;
                case U'l': mapped = U'l'; break;
                case U'm': mapped = U'm'; break;
                case U'n': mapped = U'n'; break;
                case U'p': mapped = U'p'; break;
                case U's': mapped = U's'; break;
                case U't': mapped = U't'; break;
                case U'v': mapped = U'v'; break;
                case U'w': mapped = U'w'; break;
                case U'z': mapped = U'z'; break;
                default:   mapped = 0;    break;
            }

            if (mapped != 0) {
                // Handle final silent consonants
                bool isWordFinal = (i == n - 1);
                bool isBeforeFinalS = (i == n - 2 && word[n - 1] == U's');
                bool isFinal = isWordFinal || isBeforeFinalS;

                if (isFinal && isSilentFinal(ch)) {
                    ++i;
                    continue;
                }

                // Intervocalic s voicing: single 's' between vowels -> z
                if (ch == U's') {
                    bool prevVowel = (i > 0 && isVowelChar(word[i - 1]));
                    bool nextVowel = (i + 1 < n && isVowelChar(word[i + 1]));
                    bool isSingle = !(i + 1 < n && word[i + 1] == U's');
                    if (prevVowel && nextVowel && isSingle) {
                        phonemes.push_back(U'z');
                        ++i;
                        continue;
                    }
                }

                phonemes.push_back(mapped);
                // Skip doubled consonant
                if (i + 1 < n && word[i + 1] == ch) {
                    i += 2;
                } else {
                    ++i;
                }
                continue;
            }
        }

        // Punctuation
        if (isPunctuation(ch)) {
            phonemes.push_back(ch);
            ++i;
            continue;
        }

        // Unknown character: skip
        ++i;
    }

    return phonemes;
}

// ---------------------------------------------------------------------------
// Top-level French phonemization
// ---------------------------------------------------------------------------

} // anonymous namespace

void phonemize_french(const std::string &text,
                      std::vector<std::vector<Phoneme>> &phonemes)
{
    phonemes.clear();

    if (!utf8::is_valid(text.begin(), text.end())) {
        return;
    }

    // Decode UTF-8 input to UTF-32
    std::u32string u32text = utf8ToU32(text);

    // Normalize: lowercase, collapse whitespace
    std::u32string normalized = normalize(u32text);

    // Tokenize into words and punctuation
    std::vector<Token> tokens = splitWords(normalized);

    // Build a single sentence of phonemes
    std::vector<Phoneme> sentence;
    bool needSpace = false;

    for (const auto &tok : tokens) {
        if (!tok.isPunct && needSpace) {
            sentence.push_back(CH_SPACE);
        }

        if (tok.isPunct) {
            for (char32_t ch : tok.text) {
                sentence.push_back(ch);
            }
        } else {
            std::vector<Phoneme> wordPhonemes = convertWord(tok.text);
            for (Phoneme p : wordPhonemes) {
                sentence.push_back(p);
            }
        }

        needSpace = true;
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
