// Rule-based Swedish G2P (grapheme-to-phoneme) -- C++ port of swedish.py.
//
// Converts Swedish text to IPA phonemes using orthographic rules.
// No external dependencies required.
//
// Pipeline (per word):
//   Stage 2: Loanword suffix detection (-tion/-sion/-age etc.)
//   Stage 4: Native G2P conversion (consonants + vowels)
//   Stage 5: Retroflex assimilation (r+C -> retroflex, cascade)
//   Stage 6: Stress detection + marker insertion

#include "swedish_phonemize.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <algorithm>
#include <string>
#include <unordered_set>
#include <vector>

namespace piper {
namespace {

// -----------------------------------------------------------------------
// PUA codepoints for Swedish long vowels
// -----------------------------------------------------------------------
static constexpr Phoneme PUA_I_LONG   = 0xE059; // iː
static constexpr Phoneme PUA_Y_LONG   = 0xE05A; // yː
static constexpr Phoneme PUA_E_LONG   = 0xE05B; // eː
static constexpr Phoneme PUA_EPS_LONG = 0xE05C; // ɛː
static constexpr Phoneme PUA_OE_LONG  = 0xE05D; // øː
static constexpr Phoneme PUA_AH_LONG  = 0xE05E; // ɑː
static constexpr Phoneme PUA_O_LONG   = 0xE05F; // oː
static constexpr Phoneme PUA_U_LONG   = 0xE060; // uː
static constexpr Phoneme PUA_UB_LONG  = 0xE061; // ʉː

// -----------------------------------------------------------------------
// IPA codepoints used in output
// -----------------------------------------------------------------------
static constexpr Phoneme IPA_STRESS  = 0x02C8; // ˈ primary stress marker

// Retroflex consonants
static constexpr Phoneme IPA_RETRO_D = 0x0256; // ɖ  retroflex voiced plosive
static constexpr Phoneme IPA_RETRO_T = 0x0288; // ʈ  retroflex voiceless plosive
static constexpr Phoneme IPA_RETRO_N = 0x0273; // ɳ  retroflex nasal
static constexpr Phoneme IPA_RETRO_L = 0x026D; // ɭ  retroflex lateral
static constexpr Phoneme IPA_RETRO_S = 0x0282; // ʂ  retroflex fricative

// Special fricatives
static constexpr Phoneme IPA_SJ      = 0x0267; // ɧ  sj-sound
static constexpr Phoneme IPA_TJ      = 0x0255; // ɕ  tj-sound

// Vowels
static constexpr Phoneme IPA_G_IPA   = 0x0261; // ɡ  voiced velar stop (IPA g)
static constexpr Phoneme IPA_ENG     = 0x014B; // ŋ  velar nasal
static constexpr Phoneme IPA_EPSILON = 0x025B; // ɛ  open-mid front unrounded
static constexpr Phoneme IPA_SM_CAP_I= 0x026A; // ɪ  near-close front unrounded
static constexpr Phoneme IPA_OPEN_O  = 0x0254; // ɔ  open-mid back rounded
static constexpr Phoneme IPA_BARRED_O= 0x0275; // ɵ  close-mid central rounded
static constexpr Phoneme IPA_SM_Y    = 0x028F; // ʏ  near-close front rounded
static constexpr Phoneme IPA_OE      = 0x0153; // œ  open-mid front rounded
static constexpr Phoneme IPA_ALPHA   = 0x0251; // ɑ  open back unrounded
static constexpr Phoneme IPA_SLASHED_O = 0x00F8; // ø  close-mid front rounded

// -----------------------------------------------------------------------
// Swedish vowel sets (lowercase codepoints after normalization)
// -----------------------------------------------------------------------
static bool isFrontVowel(char32_t cp) {
    return cp == 'e' || cp == 'i' || cp == 'y' ||
           cp == 0x00E4 || cp == 0x00F6;  // ä ö
}

static bool isBackVowel(char32_t cp) {
    return cp == 'a' || cp == 'o' || cp == 'u' || cp == 0x00E5; // å
}

static bool isSwedishVowel(char32_t cp) {
    return isFrontVowel(cp) || isBackVowel(cp);
}

static bool isSwedishConsonant(char32_t cp) {
    // Matches Python CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")
    switch (cp) {
        case 'b': case 'c': case 'd': case 'f': case 'g':
        case 'h': case 'j': case 'k': case 'l': case 'm':
        case 'n': case 'p': case 'q': case 'r': case 's':
        case 't': case 'v': case 'w': case 'x': case 'z':
            return true;
        default:
            return false;
    }
}

// -----------------------------------------------------------------------
// Punctuation set passed through as-is
// -----------------------------------------------------------------------
static bool isPunctuation(char32_t cp) {
    return cp == ',' || cp == '.' || cp == ';' || cp == ':' ||
           cp == '!' || cp == '?';
}

// -----------------------------------------------------------------------
// UTF-8 helpers
// -----------------------------------------------------------------------
using utf8_util::toCodepoints;
using utf8_util::cpsToUtf8;

// -----------------------------------------------------------------------
// Lowercasing (ASCII + Swedish letters)
// -----------------------------------------------------------------------
static char32_t toLowerSv(char32_t cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    if (cp == 0x00C5) return 0x00E5; // Å -> å
    if (cp == 0x00C4) return 0x00E4; // Ä -> ä
    if (cp == 0x00D6) return 0x00F6; // Ö -> ö
    if (cp == 0x00C9) return 0x00E9; // É -> é
    if (cp == 0x00C0) return 0x00E0; // À -> à
    if (cp == 0x00DC) return 0x00FC; // Ü -> ü
    if (cp == 0x00C1) return 0x00E1; // Á -> á
    if (cp == 0x00C8) return 0x00E8; // È -> è
    if (cp == 0x00CB) return 0x00EB; // Ë -> ë
    if (cp == 0x00CF) return 0x00EF; // Ï -> ï
    return cp;
}

// -----------------------------------------------------------------------
// Collapse NFD combining sequences into NFC pre-composed codepoints.
// -----------------------------------------------------------------------
static std::vector<char32_t> collapseCombiners(const std::vector<char32_t> &cps) {
    std::vector<char32_t> out;
    out.reserve(cps.size());
    for (size_t i = 0; i < cps.size(); ++i) {
        if (i + 1 < cps.size() && cps[i + 1] == 0x0301) { // combining acute
            switch (cps[i]) {
            case 'E': out.push_back(0x00C9); ++i; continue; // É
            case 'e': out.push_back(0x00E9); ++i; continue; // é
            case 'A': out.push_back(0x00C1); ++i; continue; // Á
            case 'a': out.push_back(0x00E1); ++i; continue; // á
            default: break;
            }
        } else if (i + 1 < cps.size() && cps[i + 1] == 0x0300) { // combining grave
            switch (cps[i]) {
            case 'A': out.push_back(0x00C0); ++i; continue; // À
            case 'a': out.push_back(0x00E0); ++i; continue; // à
            case 'E': out.push_back(0x00C8); ++i; continue; // È
            case 'e': out.push_back(0x00E8); ++i; continue; // è
            default: break;
            }
        } else if (i + 1 < cps.size() && cps[i + 1] == 0x0308) { // combining diaeresis
            switch (cps[i]) {
            case 'A': out.push_back(0x00C4); ++i; continue; // Ä
            case 'a': out.push_back(0x00E4); ++i; continue; // ä
            case 'O': out.push_back(0x00D6); ++i; continue; // Ö
            case 'o': out.push_back(0x00F6); ++i; continue; // ö
            case 'U': out.push_back(0x00DC); ++i; continue; // Ü
            case 'u': out.push_back(0x00FC); ++i; continue; // ü
            case 'E': out.push_back(0x00CB); ++i; continue; // Ë
            case 'e': out.push_back(0x00EB); ++i; continue; // ë
            case 'I': out.push_back(0x00CF); ++i; continue; // Ï
            case 'i': out.push_back(0x00EF); ++i; continue; // ï
            default: break;
            }
        } else if (i + 1 < cps.size() && cps[i + 1] == 0x030A) { // combining ring above
            switch (cps[i]) {
            case 'A': out.push_back(0x00C5); ++i; continue; // Å
            case 'a': out.push_back(0x00E5); ++i; continue; // å
            default: break;
            }
        }
        out.push_back(cps[i]);
    }
    return out;
}

// -----------------------------------------------------------------------
// Normalize: NFD->NFC collapse + lowercase
// -----------------------------------------------------------------------
static std::vector<char32_t> normalize(const std::vector<char32_t> &cps) {
    auto nfc = collapseCombiners(cps);
    std::vector<char32_t> out;
    out.reserve(nfc.size());
    for (auto cp : nfc) {
        out.push_back(toLowerSv(cp));
    }
    return out;
}

// -----------------------------------------------------------------------
// Swedish-specific alpha check
// -----------------------------------------------------------------------
static bool isSwedishAlpha(char32_t cp) {
    if (cp >= 'a' && cp <= 'z') return true;
    if (cp == 0x00E5 || cp == 0x00E4 || cp == 0x00F6) return true; // å ä ö
    if (cp == 0x00E9 || cp == 0x00E0 || cp == 0x00FC) return true; // é à ü
    if (cp == 0x00E1 || cp == 0x00E8 || cp == 0x00EB) return true; // á è ë
    if (cp == 0x00EF) return true; // ï
    return false;
}

// -----------------------------------------------------------------------
// Tokenizer: split into word / punctuation tokens
// -----------------------------------------------------------------------
struct Token {
    std::vector<char32_t> chars;
    bool isWord;
};

static std::vector<Token> tokenize(const std::vector<char32_t> &cps) {
    std::vector<Token> tokens;
    size_t n = cps.size();
    size_t i = 0;
    while (i < n) {
        if (isSwedishAlpha(cps[i])) {
            Token tok;
            tok.isWord = true;
            while (i < n && isSwedishAlpha(cps[i])) {
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
// Exception word lists
// -----------------------------------------------------------------------

// Words where k before front vowel is hard /k/ (not /ɕ/)
static const std::unordered_set<std::string> HARD_K_WORDS = {
    "kille", "kissa", "kiosk", "kebab", "kennel", "keps", "ketchup",
    "kick", "kilt", "kimono", "kitsch", "kibbutz", "kiwi", "kilo",
    "kex", "kent", "kerna", "keso", "kikare", "kines", "kinesisk",
    "leker", "leken", "lekerska", "steker", "steket",
    "söker", "söket", "tänker", "tänket",
    "dyker", "dyket", "ryker", "röker", "röket",
    "smeker", "läker", "läket", "märker", "märket",
    "räcker", "väcker", "viker", "stryker", "sjunker", "sticker",
    "pojke", "fröken", "onkel", "sockel", "socker", "ocker",
    "märke", "mörker", "tecken", "vacker", "naken", "säker",
    "enkel", "paket", "raket", "staket", "silke", "vinkel",
    "skelett", "ficka", "dricka", "docka", "backe", "flicka",
    "bricka", "trycke", "skicka", "rike", "kirke",
};

static const std::unordered_set<std::string> HARD_K_STEMS = {
    "lek", "stek", "sök", "tänk", "dyk", "ryk", "rök", "smek",
    "läk", "märk", "räck", "väck", "vik", "stryk", "sjunk", "stick",
    "back", "block", "trick", "tryck", "skick", "flick", "brick",
    "drick", "dock", "fick", "sick", "tack", "sack", "pack",
    "lock", "sock", "rock",
};

// Words where g before front vowel is hard /ɡ/ (not /j/)
static const std::unordered_set<std::string> HARD_G_WORDS = {
    "bagel", "bageri", "bygel", "bygge", "båge", "dager", "flygel",
    "gecko", "hage", "hagel", "hunger", "lager", "läge", "läger",
    "mage", "nagel", "regel", "segel", "seger", "stege", "tagel",
    "tegel", "tiger", "tygel", "finger", "ängel", "fågel", "spegel",
    "fogel", "duger", "flyger", "ligger", "ljuger", "lägger",
    "stiger", "suger", "tigger", "väger", "äger", "ger",
    "agera", "delegera", "reagera", "segregera", "tangera",
    "engagera", "arrangera", "ignorera", "navigera", "negera",
    "intrigera", "ge", "gel",
    "berg", "borg",
};

static const std::unordered_set<std::string> HARD_G_STEMS = {
    "lig", "stig", "sug", "tig", "väg", "äg", "flyg", "ljug",
    "lägg", "dug", "drag", "lag", "dag", "mag", "nag", "bag",
    "byg", "tag", "seg", "vag", "reg",
    "berg", "borg",
};

// "o" -> /oː/ instead of default /uː/
static const std::unordered_set<std::string> O_LONG_AS_OO = {
    "son", "mor", "bror", "lov", "dom", "ton", "zon", "fon", "ion",
    "ko", "lo", "ro", "tro", "bo", "god", "jord", "ord", "kol",
    "pol", "kontroll", "roll", "mol", "fot", "rot",
    "blod", "flod", "mod", "nod", "rod", "tog",
};

// Words ending in m that use short vowel despite single-C ending
static const std::unordered_set<std::string> FINAL_M_SHORT_WORDS = {
    "hem", "rum", "fem", "lem", "kam", "dam", "ham", "lam", "ram",
    "stam", "tom", "som", "dom", "dum", "gum", "glöm", "dröm", "ström",
};

// Function words (unstressed)
static const std::unordered_set<std::string> FUNCTION_WORDS = {
    "jag", "du", "han", "hon", "vi", "de", "dem", "den", "det",
    "sig", "sin", "min", "din",
    "av", "i", "på", "för", "med", "om", "till", "från", "hos", "ur",
    "och", "men", "att", "som", "när", "var",
    "en", "ett",
    "är", "har", "kan", "ska", "vill", "inte",
};

// Exceptions where sk before back vowel still produces /ɧ/
static const std::unordered_set<std::string> SK_BACK_VOWEL_EXCEPTIONS = {
    "människa", "marskalk",
};

// ch exceptions that are /k/ not /ɧ/
static const std::unordered_set<std::string> CH_EXCEPTIONS_K = {
    "kristus", "krist", "kron", "kronik",
    "och",
};

// Words where -age is native Swedish (not French loan)
static const std::unordered_set<std::string> AGE_NATIVE_WORDS = {
    "bage", "lage", "sage", "dage", "mage", "hage", "tage",
    "klage", "frage", "plage", "drage",
};

// -----------------------------------------------------------------------
// Unstressed prefixes for stress detection
// -----------------------------------------------------------------------
static const std::vector<std::string> UNSTRESSED_PREFIXES = {
    "för", "be", "ge", "er", "an",
};

// Stress-attracting suffixes (checked in order, longest first)
static const std::vector<std::string> STRESS_ATTRACTING_SUFFIXES = {
    "ssion", "tion", "sion",
    "itet", "eri", "era",
    "ist", "ör", "ment",
    "ans", "ens", "ell",
    "ent", "ant", "ik", "ur", "al", "ös",
};

// -----------------------------------------------------------------------
// Loanword suffix rules
// -----------------------------------------------------------------------
struct LoanSuffix {
    std::string suffix;
    std::vector<Phoneme> phonemes;
};

static const std::vector<LoanSuffix> LOANWORD_SUFFIX_RULES = {
    {"ssion", {IPA_SJ, PUA_U_LONG, 'n'}},           // -ssion -> ɧ uː n
    {"tion",  {IPA_SJ, PUA_U_LONG, 'n'}},            // -tion -> ɧ uː n
    {"sion",  {IPA_SJ, PUA_U_LONG, 'n'}},            // -sion -> ɧ uː n
    {"age",   {PUA_AH_LONG, IPA_SJ}},                // -age -> ɑː ɧ
    {"eur",   {PUA_OE_LONG, 'r'}},                    // -eur -> øː r
    {"eum",   {PUA_E_LONG, IPA_BARRED_O, 'm'}},      // -eum -> eː ɵ m
    {"ium",   {IPA_SM_CAP_I, IPA_BARRED_O, 'm'}},    // -ium -> ɪ ɵ m
};

// -----------------------------------------------------------------------
// Helper: codepoint vector to UTF-8 string (for lookup)
// -----------------------------------------------------------------------
static std::string cpVecToUtf8(const std::vector<char32_t> &cps) {
    return cpsToUtf8(cps);
}

// -----------------------------------------------------------------------
// Helper: check if word starts with a given prefix (codepoint-level)
// -----------------------------------------------------------------------
static bool startsWithStr(const std::string &word, const std::string &prefix) {
    return word.size() >= prefix.size() &&
           word.compare(0, prefix.size(), prefix) == 0;
}

static bool endsWithStr(const std::string &word, const std::string &suffix) {
    return word.size() >= suffix.size() &&
           word.compare(word.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// -----------------------------------------------------------------------
// Check if k/g is hard before front vowel (exception lists)
// -----------------------------------------------------------------------
static bool isHardK(const std::string &fullWord) {
    if (HARD_K_WORDS.count(fullWord) > 0) return true;
    // Morphological heuristic: strip common suffixes, check stems
    for (int suffLen = 3; suffLen >= 1; --suffLen) {
        if ((int)fullWord.size() > suffLen) {
            std::string stem = fullWord.substr(0, fullWord.size() - suffLen);
            if (HARD_K_STEMS.count(stem) > 0) return true;
        }
    }
    return false;
}

static bool isHardG(const std::string &fullWord) {
    if (HARD_G_WORDS.count(fullWord) > 0) return true;
    // -era verb heuristic: words ending in -era/-erar/-erade are typically
    // Swedish verbs derived from loanwords with hard g (e.g. navigera, ignorera)
    if (endsWithStr(fullWord, "erade") ||
        endsWithStr(fullWord, "erar") ||
        endsWithStr(fullWord, "era")) {
        return true;
    }
    for (int suffLen = 3; suffLen >= 1; --suffLen) {
        if ((int)fullWord.size() > suffLen) {
            std::string stem = fullWord.substr(0, fullWord.size() - suffLen);
            if (HARD_G_STEMS.count(stem) > 0) return true;
        }
    }
    return false;
}

// -----------------------------------------------------------------------
// Count syllables (vowel clusters)
// -----------------------------------------------------------------------
static int countSyllables(const std::vector<char32_t> &word) {
    int count = 0;
    bool prevVowel = false;
    for (auto ch : word) {
        if (isSwedishVowel(ch)) {
            if (!prevVowel) count++;
            prevVowel = true;
        } else {
            prevVowel = false;
        }
    }
    return std::max(count, 1);
}

static int countSyllablesUtf8(const std::string &word) {
    auto cps = toCodepoints(word);
    return countSyllables(cps);
}

// -----------------------------------------------------------------------
// Stress detection
// -----------------------------------------------------------------------
static int detectStress(const std::string &wordUtf8,
                        const std::vector<char32_t> &wordCps) {
    // Function words: no stress
    if (FUNCTION_WORDS.count(wordUtf8) > 0) return -1;

    int nSyl = countSyllables(wordCps);
    if (nSyl <= 1) return 0;

    // Check stress-attracting suffixes
    for (const auto &suffix : STRESS_ATTRACTING_SUFFIXES) {
        if (endsWithStr(wordUtf8, suffix) && wordUtf8.size() > suffix.size()) {
            std::string prefixPart = wordUtf8.substr(0, wordUtf8.size() - suffix.size());
            return countSyllablesUtf8(prefixPart);
        }
    }

    // Check unstressed prefixes
    for (const auto &prefix : UNSTRESSED_PREFIXES) {
        if (startsWithStr(wordUtf8, prefix) && wordUtf8.size() > prefix.size() + 1) {
            return 1;
        }
    }

    // Default: first syllable
    return 0;
}

// -----------------------------------------------------------------------
// Count following consonants after position
// -----------------------------------------------------------------------
static int countFollowingConsonants(const std::vector<char32_t> &word, int pos) {
    int count = 0;
    int i = pos + 1;
    while (i < (int)word.size() && isSwedishConsonant(word[i])) {
        count++;
        i++;
    }
    return count;
}

// -----------------------------------------------------------------------
// Vowel phoneme assignment (Complementary Quantity)
// -----------------------------------------------------------------------

static Phoneme getLongVowel(char32_t ch) {
    switch (ch) {
        case 'a':    return PUA_AH_LONG;   // ɑː
        case 'e':    return PUA_E_LONG;     // eː
        case 'i':    return PUA_I_LONG;     // iː
        case 'o':    return PUA_U_LONG;     // uː (default for 'o')
        case 'u':    return PUA_UB_LONG;    // ʉː
        case 'y':    return PUA_Y_LONG;     // yː
        case 0x00E5: return PUA_O_LONG;     // å -> oː
        case 0x00E4: return PUA_EPS_LONG;   // ä -> ɛː
        case 0x00F6: return PUA_OE_LONG;    // ö -> øː
        default:     return static_cast<Phoneme>(ch);
    }
}

static Phoneme getShortVowel(char32_t ch) {
    switch (ch) {
        case 'a':    return 'a';
        case 'e':    return IPA_EPSILON;    // ɛ
        case 'i':    return IPA_SM_CAP_I;   // ɪ
        case 'o':    return IPA_OPEN_O;     // ɔ
        case 'u':    return IPA_BARRED_O;   // ɵ
        case 'y':    return IPA_SM_Y;       // ʏ
        case 0x00E5: return IPA_OPEN_O;     // å -> ɔ
        case 0x00E4: return IPA_EPSILON;    // ä -> ɛ
        case 0x00F6: return IPA_OE;         // ö -> œ
        default:     return static_cast<Phoneme>(ch);
    }
}

static Phoneme getVowelPhoneme(const std::vector<char32_t> &word, int pos,
                               const std::string &fullWord, bool isStressed) {
    char32_t ch = word[pos];

    // Unstressed -> short
    if (!isStressed) {
        return getShortVowel(ch);
    }

    // Function word -> short
    if (FUNCTION_WORDS.count(fullWord) > 0) {
        return getShortVowel(ch);
    }

    // Final-m exception -> short
    if (FINAL_M_SHORT_WORDS.count(fullWord) > 0) {
        return getShortVowel(ch);
    }

    // Count following consonants
    int nFollowing = countFollowingConsonants(word, pos);

    // Word-final vowel -> long
    if (nFollowing == 0 && pos == (int)word.size() - 1) {
        Phoneme vowel = getLongVowel(ch);
        if (ch == 'o' && O_LONG_AS_OO.count(fullWord) > 0) {
            vowel = PUA_O_LONG; // oː
        }
        return vowel;
    }

    // r + single C exception: vowel stays long (r merges into retroflex)
    // Exception: 'o' excluded (too ambiguous)
    if (nFollowing == 2 && ch != 'o' && pos + 1 < (int)word.size() &&
        word[pos + 1] == 'r') {
        return getLongVowel(ch);
    }

    // Geminate / cluster (2+ consonants) -> short
    if (nFollowing >= 2) {
        return getShortVowel(ch);
    }

    // Single consonant -> long
    Phoneme vowel = getLongVowel(ch);
    if (ch == 'o' && O_LONG_AS_OO.count(fullWord) > 0) {
        vowel = PUA_O_LONG; // oː
    }
    return vowel;
}

// -----------------------------------------------------------------------
// Consonant conversion
// -----------------------------------------------------------------------

struct ConvertResult {
    std::vector<Phoneme> phonemes;
    int consumed;
};

static ConvertResult convertConsonant(const std::vector<char32_t> &word,
                                      int pos,
                                      const std::string &fullWord) {
    int remaining = (int)word.size() - pos;
    char32_t ch = word[pos];
    char32_t nextCh = (pos + 1 < (int)word.size()) ? word[pos + 1] : 0;
    (void)nextCh; // used in patterns below

    // === 3-char patterns (highest priority) ===
    if (remaining >= 3) {
        char32_t c0 = word[pos], c1 = word[pos + 1], c2 = word[pos + 2];
        // skj
        if (c0 == 's' && c1 == 'k' && c2 == 'j') {
            return {{IPA_SJ}, 3};
        }
        // stj
        if (c0 == 's' && c1 == 't' && c2 == 'j') {
            return {{IPA_SJ}, 3};
        }
        // sch
        if (c0 == 's' && c1 == 'c' && c2 == 'h') {
            return {{IPA_SJ}, 3};
        }
        // sng -> s n (simplified)
        if (c0 == 's' && c1 == 'n' && c2 == 'g') {
            return {{'s', 'n'}, 3};
        }
        // ckj -> ɕ (tj-sound)
        if (c0 == 'c' && c1 == 'k' && c2 == 'j') {
            return {{IPA_TJ}, 3};
        }
    }

    // === 2-char patterns ===
    if (remaining >= 2) {
        char32_t c0 = word[pos], c1 = word[pos + 1];

        // sk + context
        if (c0 == 's' && c1 == 'k') {
            if (remaining >= 3 && isFrontVowel(word[pos + 2])) {
                // sk + front vowel -> /ɧ/ (sj-sound)
                // Exception: SK_BACK_VOWEL_EXCEPTIONS
                if (SK_BACK_VOWEL_EXCEPTIONS.count(fullWord) == 0) {
                    return {{IPA_SJ}, 2};
                }
            }
            // sk + back vowel / consonant / word-final -> /sk/
            return {{'s', 'k'}, 2};
        }

        // sj -> ɧ
        if (c0 == 's' && c1 == 'j') {
            return {{IPA_SJ}, 2};
        }

        // sh -> ɧ (loanword)
        if (c0 == 's' && c1 == 'h') {
            return {{IPA_SJ}, 2};
        }

        // ch
        if (c0 == 'c' && c1 == 'h') {
            if (CH_EXCEPTIONS_K.count(fullWord) > 0) {
                return {{'k'}, 2};
            }
            return {{IPA_SJ}, 2};
        }

        // ph -> f (loanword)
        if (c0 == 'p' && c1 == 'h') {
            return {{'f'}, 2};
        }

        // th -> t (loanword)
        if (c0 == 't' && c1 == 'h') {
            return {{'t'}, 2};
        }

        // tj -> ɕ
        if (c0 == 't' && c1 == 'j') {
            return {{IPA_TJ}, 2};
        }

        // kj -> ɕ
        if (c0 == 'k' && c1 == 'j') {
            return {{IPA_TJ}, 2};
        }

        // gn
        if (c0 == 'g' && c1 == 'n') {
            if (pos == 0) {
                return {{IPA_G_IPA, 'n'}, 2}; // word-initial: ɡn
            }
            return {{IPA_ENG, 'n'}, 2}; // elsewhere: ŋn
        }

        // ng -> ŋ
        if (c0 == 'n' && c1 == 'g') {
            return {{IPA_ENG}, 2};
        }

        // nk -> ŋk
        if (c0 == 'n' && c1 == 'k') {
            return {{IPA_ENG, 'k'}, 2};
        }

        // ck -> k (geminate marker)
        if (c0 == 'c' && c1 == 'k') {
            return {{'k'}, 2};
        }

        // gj -> j (word-initial only)
        if (c0 == 'g' && c1 == 'j') {
            if (pos == 0) {
                return {{'j'}, 2};
            }
        }

        // lj -> j (word-initial only)
        if (c0 == 'l' && c1 == 'j') {
            if (pos == 0) {
                return {{'j'}, 2};
            }
        }

        // dj -> j (word-initial only)
        if (c0 == 'd' && c1 == 'j') {
            if (pos == 0) {
                return {{'j'}, 2};
            }
        }

        // hj -> j (word-initial only)
        if (c0 == 'h' && c1 == 'j') {
            if (pos == 0) {
                return {{'j'}, 2};
            }
        }
    }

    // === 1-char patterns ===

    // k + front vowel -> soft /ɕ/ (default) or hard /k/ (exception)
    if (ch == 'k' && pos + 1 < (int)word.size() && isFrontVowel(word[pos + 1])) {
        if (isHardK(fullWord)) {
            return {{'k'}, 1};
        }
        return {{IPA_TJ}, 1}; // ɕ
    }

    // g + front vowel -> soft /j/ (default) or hard /ɡ/ (exception)
    if (ch == 'g' && pos + 1 < (int)word.size() && isFrontVowel(word[pos + 1])) {
        if (isHardG(fullWord)) {
            return {{IPA_G_IPA}, 1};
        }
        return {{'j'}, 1};
    }

    // g + back vowel / consonant -> /ɡ/
    if (ch == 'g') {
        return {{IPA_G_IPA}, 1};
    }

    // c before e/i -> /s/, otherwise /k/
    if (ch == 'c') {
        if (pos + 1 < (int)word.size() && (word[pos + 1] == 'e' || word[pos + 1] == 'i')) {
            return {{'s'}, 1};
        }
        return {{'k'}, 1};
    }

    // x -> /ks/
    if (ch == 'x') {
        return {{'k', 's'}, 1};
    }

    // Default single consonant mappings
    switch (ch) {
        case 'b': return {{'b'}, 1};
        case 'd': return {{'d'}, 1};
        case 'f': return {{'f'}, 1};
        case 'h': return {{'h'}, 1};
        case 'j': return {{'j'}, 1};
        case 'k': return {{'k'}, 1};
        case 'l': return {{'l'}, 1};
        case 'm': return {{'m'}, 1};
        case 'n': return {{'n'}, 1};
        case 'p': return {{'p'}, 1};
        case 'q': return {{'k'}, 1};
        case 'r': return {{'r'}, 1};
        case 's': return {{'s'}, 1};
        case 't': return {{'t'}, 1};
        case 'v': return {{'v'}, 1};
        case 'w': return {{'v'}, 1};
        case 'z': return {{'s'}, 1};
        default: return {{static_cast<Phoneme>(ch)}, 1};
    }
}

// -----------------------------------------------------------------------
// Loanword suffix detection
// -----------------------------------------------------------------------

struct LoanResult {
    bool found;
    std::string stem;
    std::vector<Phoneme> suffixPhonemes;
};

static LoanResult detectLoanwordSuffix(const std::string &wordUtf8) {
    for (const auto &rule : LOANWORD_SUFFIX_RULES) {
        if (endsWithStr(wordUtf8, rule.suffix) &&
            wordUtf8.size() > rule.suffix.size()) {
            // Check native exceptions for -age
            if (rule.suffix == "age" && AGE_NATIVE_WORDS.count(wordUtf8) > 0) {
                continue;
            }
            std::string stem = wordUtf8.substr(0, wordUtf8.size() - rule.suffix.size());
            return {true, stem, rule.phonemes};
        }
    }
    return {false, "", {}};
}

// -----------------------------------------------------------------------
// Native word conversion (Stage 4)
// -----------------------------------------------------------------------

static std::vector<Phoneme> convertWordNative(const std::vector<char32_t> &word,
                                              const std::string &fullWord,
                                              int stressedSyl) {
    std::vector<Phoneme> phonemes;
    int pos = 0;
    int sylCount = 0;
    bool prevWasVowel = false;
    int n = (int)word.size();

    while (pos < n) {
        char32_t ch = word[pos];

        if (isSwedishVowel(ch)) {
            if (!prevWasVowel) {
                bool isStressed = (sylCount == stressedSyl && stressedSyl >= 0);
                Phoneme vowel = getVowelPhoneme(word, pos, fullWord, isStressed);
                phonemes.push_back(vowel);
                sylCount++;
            } else {
                // Consecutive vowel in same syllable (rare)
                phonemes.push_back(getShortVowel(ch));
            }
            prevWasVowel = true;
            pos++;
        } else if (isSwedishConsonant(ch)) {
            prevWasVowel = false;
            auto result = convertConsonant(word, pos, fullWord);
            for (auto ph : result.phonemes) {
                phonemes.push_back(ph);
            }
            pos += result.consumed;
        } else {
            // Skip unknown characters
            prevWasVowel = false;
            pos++;
        }
    }

    return phonemes;
}

// -----------------------------------------------------------------------
// Retroflex assimilation (Stage 5)
//
// State machine: NORMAL -> R_DETECTED -> CASCADING
// r + {t,d,s,n,l} -> retroflex
// -----------------------------------------------------------------------

static bool isRetroflexTarget(Phoneme ph) {
    return ph == 't' || ph == 'd' || ph == 's' || ph == 'n' || ph == 'l';
}

static Phoneme toRetroflex(Phoneme ph) {
    switch (ph) {
        case 't': return IPA_RETRO_T;
        case 'd': return IPA_RETRO_D;
        case 's': return IPA_RETRO_S;
        case 'n': return IPA_RETRO_N;
        case 'l': return IPA_RETRO_L;
        default:  return ph;
    }
}

static bool isPropagatingRetroflex(Phoneme ph) {
    return ph == IPA_RETRO_T || ph == IPA_RETRO_D ||
           ph == IPA_RETRO_S || ph == IPA_RETRO_N;
    // Note: IPA_RETRO_L (ɭ) stops cascade
}

static std::vector<Phoneme> applyRetroflex(const std::vector<Phoneme> &phonemes) {
    std::vector<Phoneme> result;
    int i = 0;
    int n = (int)phonemes.size();
    enum State { NORMAL, R_DETECTED, CASCADING };
    State state = NORMAL;

    while (i < n) {
        Phoneme ph = phonemes[i];

        switch (state) {
        case NORMAL:
            if (ph == 'r') {
                state = R_DETECTED;
            } else {
                result.push_back(ph);
            }
            break;

        case R_DETECTED:
            if (ph == 'r') {
                // rr -> geminate block, no assimilation
                result.push_back('r');
                result.push_back('r');
                state = NORMAL;
            } else if (isRetroflexTarget(ph)) {
                Phoneme retro = toRetroflex(ph);
                result.push_back(retro);
                if (isPropagatingRetroflex(retro)) {
                    state = CASCADING;
                } else {
                    // ɭ stops cascade
                    state = NORMAL;
                }
            } else {
                // r + non-assimilable -> output r and current phoneme
                result.push_back('r');
                result.push_back(ph);
                state = NORMAL;
            }
            break;

        case CASCADING:
            if (isRetroflexTarget(ph)) {
                Phoneme retro = toRetroflex(ph);
                result.push_back(retro);
                if (!isPropagatingRetroflex(retro)) {
                    state = NORMAL; // ɭ stops cascade
                }
            } else {
                result.push_back(ph);
                state = NORMAL;
            }
            break;
        }

        i++;
    }

    // Flush pending r
    if (state == R_DETECTED) {
        result.push_back('r');
    }

    return result;
}

// -----------------------------------------------------------------------
// IPA vowel check (for stress marker insertion)
// -----------------------------------------------------------------------
static bool isIpaVowel(Phoneme ph) {
    // Short vowels
    if (ph == 'a' || ph == 'e' || ph == 'i' || ph == 'o' || ph == 'u' || ph == 'y')
        return true;
    if (ph == IPA_EPSILON || ph == IPA_SM_CAP_I || ph == IPA_OPEN_O ||
        ph == IPA_BARRED_O || ph == IPA_SM_Y || ph == IPA_OE ||
        ph == IPA_ALPHA || ph == IPA_SLASHED_O)
        return true;
    // Long vowels (PUA)
    if (ph >= PUA_I_LONG && ph <= PUA_UB_LONG) return true;
    return false;
}

// -----------------------------------------------------------------------
// Insert stress marker (Stage 6)
// -----------------------------------------------------------------------
static std::vector<Phoneme> insertStressMarker(const std::vector<Phoneme> &phonemes,
                                               int stressSyl) {
    if (stressSyl < 0 || phonemes.empty()) return phonemes;

    // Find the index of the first vowel of the target syllable
    int sylCount = 0;
    int vowelIdx = -1;
    bool prevWasVowel = false;

    for (int i = 0; i < (int)phonemes.size(); i++) {
        bool isV = isIpaVowel(phonemes[i]);
        if (isV && !prevWasVowel) {
            if (sylCount == stressSyl) {
                vowelIdx = i;
                break;
            }
            sylCount++;
            prevWasVowel = true;
        } else if (!isV) {
            prevWasVowel = false;
        }
    }

    if (vowelIdx < 0) return phonemes;

    // Walk backwards to find syllable onset (consonants before the vowel)
    int onsetIdx = vowelIdx;
    while (onsetIdx > 0 && !isIpaVowel(phonemes[onsetIdx - 1])) {
        onsetIdx--;
    }

    // For syllable 0, onset starts at beginning
    if (stressSyl == 0) {
        onsetIdx = 0;
    }

    std::vector<Phoneme> result(phonemes);
    result.insert(result.begin() + onsetIdx, IPA_STRESS);
    return result;
}

// -----------------------------------------------------------------------
// Full word pipeline (Stage 2-6)
// -----------------------------------------------------------------------
static std::vector<Phoneme> phonemizeWord(const std::vector<char32_t> &wordCps,
                                          const std::string &wordUtf8) {
    if (wordCps.empty()) return {};

    // Detect stress syllable
    int stressedSyl = detectStress(wordUtf8, wordCps);

    // Stage 2: Check loanword suffix
    auto loanResult = detectLoanwordSuffix(wordUtf8);
    std::vector<Phoneme> rawPhonemes;

    if (loanResult.found) {
        auto stemCps = toCodepoints(loanResult.stem);
        int stemSylCount = countSyllables(stemCps);
        int stemStressed = (stressedSyl >= stemSylCount) ? -1 : stressedSyl;
        auto stemPhonemes = convertWordNative(stemCps, wordUtf8, stemStressed);
        rawPhonemes = stemPhonemes;
        rawPhonemes.insert(rawPhonemes.end(),
                           loanResult.suffixPhonemes.begin(),
                           loanResult.suffixPhonemes.end());
    } else {
        // Stage 4: Native conversion
        rawPhonemes = convertWordNative(wordCps, wordUtf8, stressedSyl);
    }

    // Stage 5: Retroflex assimilation
    auto phonemes = applyRetroflex(rawPhonemes);

    // Stage 6: Stress markers
    phonemes = insertStressMarker(phonemes, stressedSyl);

    return phonemes;
}

} // anonymous namespace

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

void phonemize_swedish(const std::string &text,
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

        std::string wordUtf8 = cpVecToUtf8(tok.chars);
        auto wordPhonemes = phonemizeWord(tok.chars, wordUtf8);

        for (auto p : wordPhonemes) {
            sentence.push_back(p);
        }
        needSpace = true;
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
