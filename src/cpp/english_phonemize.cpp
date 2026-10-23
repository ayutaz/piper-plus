// English G2P using CMU dictionary — C++ port of english.py.
//
// Converts English text to IPA phonemes using CMU dictionary lookup +
// ARPAbet-to-IPA conversion rules.  Output matches the Python
// src/python/g2p/piper_plus_g2p/english.py pipeline exactly:
//   - Context-dependent ARPAbet->IPA (AA+R merge, stressed ER, etc.)
//   - Function-word destressing
//   - Stress markers (primary/secondary) before vowels
//   - Each IPA character is a separate phoneme codepoint
//
// Before the lookup the text goes through the port of g2p_en's
// normalization (english_normalize.hpp): numbers are spelled out, accents
// stripped, i.e./e.g. replaced, and the TweetTokenizer subset splits words.
//
// Python reads words outside the CMU dictionary with a neural predictor.
// This port cannot, so it reads them with a ladder (englishWordToArpabet)
// that never yields nothing: morphological fallback (-ing, -ed, -s/-es, -er,
// -ly, -est), then the parts around '-' / '.', the word without apostrophes,
// the CamelCase parts, and finally the names of the letters.

#include "english_phonemize.hpp"
#include "english_normalize.hpp"
#include "json.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using json = nlohmann::json;

namespace piper {
namespace {

// -----------------------------------------------------------------------
// IPA codepoints used in output
// -----------------------------------------------------------------------

// Vowel codepoints
constexpr char32_t IPA_TURNED_A   = 0x0251; // ɑ (AA)
constexpr char32_t IPA_ASH        = 0x00E6; // æ (AE)
constexpr char32_t IPA_TURNED_V   = 0x028C; // ʌ (AH stressed)
constexpr char32_t IPA_SCHWA      = 0x0259; // ə (AH unstressed)
constexpr char32_t IPA_OPEN_O     = 0x0254; // ɔ (AO first char)
constexpr char32_t IPA_EPSILON    = 0x025B; // ɛ (EH)
constexpr char32_t IPA_RHOTIC_SCH = 0x025A; // ɚ (ER unstressed)
constexpr char32_t IPA_REV_OPEN_E = 0x025C; // ɜ (ER stressed first char)
constexpr char32_t IPA_SM_CAP_I   = 0x026A; // ɪ (IH)
constexpr char32_t IPA_HORSESHOE  = 0x028A; // ʊ (UH)
constexpr char32_t IPA_LENGTH     = 0x02D0; // ː (length mark)

// Consonant codepoints
constexpr char32_t IPA_VOICED_G   = 0x0261; // ɡ (G)
constexpr char32_t IPA_ENG        = 0x014B; // ŋ (NG)
constexpr char32_t IPA_ALVEOLAR_R = 0x0279; // ɹ (R)
constexpr char32_t IPA_ESH        = 0x0283; // ʃ (SH)
constexpr char32_t IPA_EZH        = 0x0292; // ʒ (ZH)
constexpr char32_t IPA_THETA      = 0x03B8; // θ (TH)
constexpr char32_t IPA_ETH        = 0x00F0; // ð (DH)

// Stress markers
constexpr char32_t IPA_PRIMARY    = 0x02C8; // ˈ primary stress
constexpr char32_t IPA_SECONDARY  = 0x02CC; // ˌ secondary stress

// -----------------------------------------------------------------------
// ARPAbet-to-IPA table (matches english.py ARPABET_TO_IPA exactly)
//
// Each entry maps an ARPAbet base symbol to a sequence of IPA codepoints.
// Multi-codepoint values (like "ɔː" = ɔ + ː) are stored as vectors.
// -----------------------------------------------------------------------

// Build the lookup table once at first use.
static const std::unordered_map<std::string, std::vector<char32_t>> &arpaToIpa() {
    static const std::unordered_map<std::string, std::vector<char32_t>> table = {
        {"AA",  {IPA_TURNED_A}},                     // ɑ
        {"AE",  {IPA_ASH}},                          // æ
        {"AH",  {IPA_TURNED_V}},                     // ʌ (stressed default)
        {"AO",  {IPA_OPEN_O, IPA_LENGTH}},           // ɔː
        {"AW",  {'a', IPA_HORSESHOE}},               // aʊ
        {"AY",  {'a', IPA_SM_CAP_I}},                // aɪ
        {"B",   {'b'}},
        {"CH",  {'t', IPA_ESH}},                     // tʃ (two separate codepoints)
        {"D",   {'d'}},
        {"DH",  {IPA_ETH}},                          // ð
        {"EH",  {IPA_EPSILON}},                      // ɛ
        {"ER",  {IPA_RHOTIC_SCH}},                   // ɚ (unstressed default)
        {"EY",  {'e', IPA_SM_CAP_I}},                // eɪ
        {"F",   {'f'}},
        {"G",   {IPA_VOICED_G}},                     // ɡ
        {"HH",  {'h'}},
        {"IH",  {IPA_SM_CAP_I}},                     // ɪ
        {"IY",  {'i', IPA_LENGTH}},                  // iː
        {"JH",  {'d', IPA_EZH}},                     // dʒ (two separate codepoints)
        {"K",   {'k'}},
        {"L",   {'l'}},
        {"M",   {'m'}},
        {"N",   {'n'}},
        {"NG",  {IPA_ENG}},                          // ŋ
        {"OW",  {'o', IPA_HORSESHOE}},               // oʊ
        {"OY",  {IPA_OPEN_O, IPA_SM_CAP_I}},        // ɔɪ
        {"P",   {'p'}},
        {"R",   {IPA_ALVEOLAR_R}},                   // ɹ
        {"S",   {'s'}},
        {"SH",  {IPA_ESH}},                          // ʃ
        {"T",   {'t'}},
        {"TH",  {IPA_THETA}},                        // θ
        {"UH",  {IPA_HORSESHOE}},                    // ʊ
        {"UW",  {'u', IPA_LENGTH}},                  // uː
        {"V",   {'v'}},
        {"W",   {'w'}},
        {"Y",   {'j'}},
        {"Z",   {'z'}},
        {"ZH",  {IPA_EZH}},                          // ʒ
    };
    return table;
}

// Special AH unstressed -> schwa
static const std::vector<char32_t> AH_UNSTRESSED = {IPA_SCHWA}; // ə

// Stressed ER -> ɜː
static const std::vector<char32_t> ER_STRESSED = {IPA_REV_OPEN_E, IPA_LENGTH}; // ɜː

// AA + R merge -> ɑːɹ
static const std::vector<char32_t> AA_R_MERGED = {
    IPA_TURNED_A, IPA_LENGTH, IPA_ALVEOLAR_R}; // ɑːɹ

// -----------------------------------------------------------------------
// Punctuation set (attached to preceding word)
// -----------------------------------------------------------------------
static bool isPunctuation(char32_t cp) {
    return cp == ',' || cp == '.' || cp == ';' || cp == ':' ||
           cp == '!' || cp == '?';
}

// -----------------------------------------------------------------------
// Function words — stress removed to match espeak-ng behavior.
// Matches english.py _FUNCTION_WORDS exactly (97 entries).
// -----------------------------------------------------------------------
static const std::unordered_set<std::string> &functionWords() {
    static const std::unordered_set<std::string> words = {
        // articles / determiners
        "a", "an", "the",
        // pronouns
        "i", "me", "my", "mine", "myself",
        "you", "your", "yours", "yourself",
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "it", "its", "itself",
        "we", "us", "our", "ours", "ourselves",
        "they", "them", "their", "theirs", "themselves",
        // be-verbs
        "am", "is", "are", "was", "were", "be", "been", "being",
        // auxiliaries
        "have", "has", "had", "having",
        "do", "does", "did",
        "will", "would", "shall", "should",
        "can", "could", "may", "might", "must",
        // prepositions
        "at", "by", "for", "from", "in", "of", "on", "to", "with",
        "about", "after", "before", "between", "into", "through", "under",
        // conjunctions
        "and", "but", "or", "nor", "so", "yet",
        "if", "that", "than", "when", "while", "as", "because", "since",
        // others
        "not", "no",
    };
    return words;
}

// -----------------------------------------------------------------------
// UTF-8 helpers — delegated to utf8_utils.hpp
// -----------------------------------------------------------------------

using utf8_util::toCodepoints;

// -----------------------------------------------------------------------
// Tokenizer
//
// Words come from the g2p_en normalization port (english_normalize.hpp).
// As in english.py, a word that is a single `, . ; : ! ?` is punctuation and
// attaches to the preceding word; every other word (including "...", "'"
// and "-") gets a word boundary before it.  A word without letters is
// emitted as its characters; a word with letters is looked up.
// -----------------------------------------------------------------------

struct Token {
    std::string text;  // as written (case kept; looked up lowercased)
    bool isWord;       // false = single punctuation character
    bool hasLetter;
};

static std::vector<Token> tokenize(const std::string &text) {
    std::vector<Token> tokens;
    for (auto &word : tokenizeEnglish(normalizeEnglishText(text))) {
        const bool punct = word.size() == 1 && isPunctuation(static_cast<char32_t>(word[0]));
        const bool hasLetter = std::any_of(word.begin(), word.end(), [](char c) {
            return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
        });
        tokens.push_back({std::move(word), !punct, hasLetter});
    }
    return tokens;
}

// -----------------------------------------------------------------------
// ARPAbet parsing: split "HH AH0 L OW1" into [("HH",-1), ("AH",0),
//                  ("L",-1), ("OW",1)]
// -----------------------------------------------------------------------

struct ArpaToken {
    std::string base;  // e.g. "HH", "AH", "OW"
    int stress;        // 0, 1, 2, or -1 for consonants
};

static std::vector<ArpaToken> parseArpabet(const std::string &arpa) {
    std::vector<ArpaToken> result;
    std::istringstream iss(arpa);
    std::string tok;

    while (iss >> tok) {
        if (tok.empty()) continue;

        // Check if last character is a digit (stress marker)
        char last = tok.back();
        if (last >= '0' && last <= '2') {
            result.push_back({tok.substr(0, tok.size() - 1),
                              last - '0'});
        } else {
            result.push_back({tok, -1});
        }
    }
    return result;
}

// -----------------------------------------------------------------------
// ARPAbet-to-IPA conversion with context-dependent rules.
// Matches english.py _convert_word_to_ipa() exactly.
//
// Returns a list of (ipa_codepoints, stress) pairs per phoneme.
// -----------------------------------------------------------------------

struct IpaPhoneme {
    std::vector<char32_t> ipa;  // one or more codepoints
    int stress;                 // 0, 1, 2, or -1
};

static std::vector<IpaPhoneme> convertWordToIpa(
        const std::vector<ArpaToken> &tokens) {
    std::vector<IpaPhoneme> result;
    const auto &table = arpaToIpa();

    size_t i = 0;
    size_t n = tokens.size();

    while (i < n) {
        const auto &tok = tokens[i];

        // ---- Context-dependent rule: AA + R -> ɑːɹ ----
        if (tok.base == "AA" && i + 1 < n && tokens[i + 1].base == "R"
                && tokens[i + 1].stress == -1) {
            result.push_back({AA_R_MERGED, tok.stress});
            i += 2;
            continue;
        }

        // ---- Context-dependent rule: Stressed ER -> ɜː ----
        if (tok.base == "ER" && tok.stress == 1) {
            result.push_back({ER_STRESSED, tok.stress});
            ++i;
            continue;
        }

        // ---- Special case: Unstressed AH -> schwa ----
        if (tok.base == "AH" && tok.stress == 0) {
            result.push_back({AH_UNSTRESSED, tok.stress});
            ++i;
            continue;
        }

        // ---- Normal lookup ----
        auto it = table.find(tok.base);
        if (it != table.end()) {
            result.push_back({it->second, tok.stress});
        }
        // Unknown ARPAbet symbol: skip silently (matches Python warning behavior)

        ++i;
    }

    return result;
}

// -----------------------------------------------------------------------
// Apply function-word destressing: set all stress >= 1 to 0.
// Matches english.py: (ipa, 0 if stress >= 1 else stress)
// -----------------------------------------------------------------------

static void destress(std::vector<IpaPhoneme> &ipas) {
    for (auto &p : ipas) {
        if (p.stress >= 1) {
            p.stress = 0;
        }
    }
}

// -----------------------------------------------------------------------
// Emit phonemes for a word into the output sentence.
//
// For each IPA phoneme:
//   1. If stress == 1, insert ˈ (primary stress marker)
//   2. If stress == 2, insert ˌ (secondary stress marker)
//   3. Emit each codepoint of the IPA string individually
//
// This matches english.py lines 382-398 exactly.
// -----------------------------------------------------------------------

static void emitWord(const std::vector<IpaPhoneme> &ipas,
                     std::vector<Phoneme> &sentence) {
    for (const auto &p : ipas) {
        // Insert stress marker before the vowel
        if (p.stress == 1) {
            sentence.push_back(IPA_PRIMARY);
        } else if (p.stress == 2) {
            sentence.push_back(IPA_SECONDARY);
        }

        // Each IPA character becomes a separate Phoneme
        for (char32_t ch : p.ipa) {
            sentence.push_back(ch);
        }
    }
}

// -----------------------------------------------------------------------
// Morphological fallback for OOV words.
//
// Strips common English suffixes and looks up the base form in the CMU
// dictionary.  If found, returns the base ARPAbet string with the
// suffix phonemes appended.  Returns "" if no match is found.
//
// Supported suffix patterns:
//   -ing  (running->run, making->make, sitting->sit)
//   -ed   (walked->walk, stopped->stop, loved->love)
//   -s/-es/-ies  (cats->cat, boxes->box, countries->country)
//   -er   (faster->fast, runner->run)
//   -ly/-ily  (quickly->quick, happily->happy)
//   -est  (fastest->fast)
// -----------------------------------------------------------------------

static std::string tryMorphologicalFallback(
        const std::string &word,
        const std::unordered_map<std::string, std::string> &cmuDict) {

    // Helper: check if base is in dict and return combined ARPAbet.
    auto tryBase = [&](const std::string &base,
                       const char *suffixArpa) -> std::string {
        auto it = cmuDict.find(base);
        if (it != cmuDict.end()) {
            return it->second + " " + suffixArpa;
        }
        return {};
    };

    const size_t len = word.size();

    // ----- -ing (running->run, making->make, sitting->sit) -----
    if (len > 4 && word.compare(len - 3, 3, "ing") == 0) {
        std::string base = word.substr(0, len - 3);
        // Direct: running->runn? no, run+ning. Try base directly.
        auto r = tryBase(base, "IH0 NG");
        if (!r.empty()) return r;

        // Doubled consonant: sitting->sit (base="sitt", dedup->"sit")
        if (base.size() >= 2 && base.back() == base[base.size() - 2]) {
            r = tryBase(base.substr(0, base.size() - 1), "IH0 NG");
            if (!r.empty()) return r;
        }

        // Restored 'e': making->make
        r = tryBase(base + "e", "IH0 NG");
        if (!r.empty()) return r;
    }

    // ----- -ed (walked->walk, stopped->stop, loved->love) -----
    if (len > 3 && word.compare(len - 2, 2, "ed") == 0) {
        std::string base = word.substr(0, len - 2);
        auto r = tryBase(base, "D");
        if (!r.empty()) return r;

        // Doubled consonant: stopped->stop
        if (base.size() >= 2 && base.back() == base[base.size() - 2]) {
            r = tryBase(base.substr(0, base.size() - 1), "D");
            if (!r.empty()) return r;
        }

        // Strip only 'd': loved->love (base = word minus 'd')
        r = tryBase(word.substr(0, len - 1), "D");
        if (!r.empty()) return r;
    }

    // ----- -s / -es / -ies (cats->cat, boxes->box, countries->country) -----
    if (len > 2 && word.back() == 's') {
        // -ies -> -y: countries->country (check before -es/-s)
        if (len > 4 && word.compare(len - 3, 3, "ies") == 0) {
            auto r = tryBase(word.substr(0, len - 3) + "y", "Z");
            if (!r.empty()) return r;
        }

        // -es: boxes->box
        if (len > 3 && word.compare(len - 2, 2, "es") == 0) {
            auto r = tryBase(word.substr(0, len - 2), "IH0 Z");
            if (!r.empty()) return r;
        }

        // -s: cats->cat
        auto r = tryBase(word.substr(0, len - 1), "Z");
        if (!r.empty()) return r;
    }

    // ----- -er (faster->fast, runner->run) -----
    if (len > 3 && word.compare(len - 2, 2, "er") == 0) {
        std::string base = word.substr(0, len - 2);
        auto r = tryBase(base, "ER0");
        if (!r.empty()) return r;

        // Doubled consonant: runner->run
        if (base.size() >= 2 && base.back() == base[base.size() - 2]) {
            r = tryBase(base.substr(0, base.size() - 1), "ER0");
            if (!r.empty()) return r;
        }
    }

    // ----- -ly / -ily (quickly->quick, happily->happy) -----
    if (len > 3 && word.compare(len - 2, 2, "ly") == 0) {
        std::string base = word.substr(0, len - 2);
        auto r = tryBase(base, "L IY0");
        if (!r.empty()) return r;

        // -ily -> -y: happily->happy
        if (len > 4 && word[len - 3] == 'i') {
            r = tryBase(word.substr(0, len - 3) + "y", "L IY0");
            if (!r.empty()) return r;
        }
    }

    // ----- -est (fastest->fast) -----
    if (len > 4 && word.compare(len - 3, 3, "est") == 0) {
        auto r = tryBase(word.substr(0, len - 3), "AH0 S T");
        if (!r.empty()) return r;
    }

    return {};  // Truly OOV — no morphological match
}

} // anonymous namespace

// -----------------------------------------------------------------------
// Public API: load CMU dictionary from JSON
// -----------------------------------------------------------------------

bool loadCmuDict(const std::string &jsonPath,
                 std::unordered_map<std::string, std::string> &dict) {
    std::ifstream file(jsonPath);
    if (!file.is_open()) {
        return false;
    }

    try {
        json j;
        file >> j;

        if (!j.is_object()) {
            return false;
        }

        dict.clear();
        dict.reserve(j.size());

        for (auto it = j.begin(); it != j.end(); ++it) {
            if (it.value().is_string()) {
                dict[it.key()] = it.value().get<std::string>();
            }
        }

        return true;
    } catch (const json::exception &) {
        return false;
    }
}

// -----------------------------------------------------------------------
// Public API: ARPAbet for one word (CMU entry, else the OOV ladder)
//
// Python reads words outside the CMU dictionary with g2p_en's neural
// predictor, which is not ported. The ladder never yields nothing for a word
// with a letter: morphological fallback, then the parts around '-' / '.',
// the word without apostrophes, the CamelCase parts, and finally the names
// of the letters. The parts are joined into one word.
// -----------------------------------------------------------------------

std::string englishWordToArpabet(const std::string &word,
                                 const std::unordered_map<std::string, std::string> &cmuDict) {
    std::string lower;
    lower.reserve(word.size());
    for (char c : word) lower += (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;

    auto dictIt = cmuDict.find(lower);
    if (dictIt != cmuDict.end()) return dictIt->second;
    std::string morph = tryMorphologicalFallback(lower, cmuDict);
    if (!morph.empty()) return morph;

    auto joinParts = [&cmuDict](const std::vector<std::string> &parts) {
        std::string joined;
        for (const auto &part : parts) {
            std::string arpa = englishWordToArpabet(part, cmuDict);
            if (arpa.empty()) continue;
            if (!joined.empty()) joined += ' ';
            joined += arpa;
        }
        return joined;
    };

    if (word.find_first_of("-.") != std::string::npos) {
        std::vector<std::string> parts;
        std::string part;
        for (char c : word) {
            if (c == '-' || c == '.') {
                if (!part.empty()) parts.push_back(std::move(part));
                part.clear();
            } else {
                part += c;
            }
        }
        if (!part.empty()) parts.push_back(std::move(part));
        return joinParts(parts);
    }
    if (word.find('\'') != std::string::npos) {
        std::string stripped;
        for (char c : word) {
            if (c != '\'') stripped += c;
        }
        return englishWordToArpabet(stripped, cmuDict);
    }
    auto camelParts = splitEnglishCamelCase(word);
    if (camelParts.size() > 1) return joinParts(camelParts);

    std::string spelled;
    for (char c : word) {
        const char *name = englishLetterArpabet(c);
        if (!name) continue;
        if (!spelled.empty()) spelled += ' ';
        spelled += name;
    }
    return spelled;
}

// -----------------------------------------------------------------------
// Public API: phonemize English text
// -----------------------------------------------------------------------

void phonemize_english(const std::string &text,
                       std::vector<std::vector<Phoneme>> &phonemes,
                       const std::unordered_map<std::string, std::string> &cmuDict) {
    phonemes.clear();

    if (!utf8::is_valid(text.begin(), text.end())) {
        return;
    }

    auto tokens = tokenize(text);
    if (tokens.empty()) return;

    // Function words are matched, in order, against the words of the text
    // before number expansion (english.py _get_source_words).
    const auto sourceWords = englishSourceWords(text);
    const auto &funcWords = functionWords();
    size_t srcIdx = 0;

    std::vector<Phoneme> sentence;
    bool needSpace = false;

    for (const auto &tok : tokens) {
        std::vector<IpaPhoneme> wordIpas;
        if (tok.hasLetter) {
            const std::string arpa = englishWordToArpabet(tok.text, cmuDict);
            if (arpa.empty()) continue;
            wordIpas = convertWordToIpa(parseArpabet(arpa));
        } else {
            // A word without letters ("-", "'", "...") is spoken as its
            // characters, as Python does.
            wordIpas.push_back({toCodepoints(tok.text), -1});
        }

        if (tok.isWord) {
            if (srcIdx < sourceWords.size()) {
                if (funcWords.count(sourceWords[srcIdx]) > 0) destress(wordIpas);
                ++srcIdx;
            }
            // Insert word-boundary space (except before the first word);
            // punctuation attaches to the preceding word.
            if (needSpace) {
                sentence.push_back(static_cast<Phoneme>(' '));
            }
        }

        emitWord(wordIpas, sentence);
        needSpace = true;
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
