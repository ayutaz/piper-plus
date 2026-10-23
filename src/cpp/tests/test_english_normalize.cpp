/**
 * Test: the C++ port of g2p_en's English text normalization (#821).
 *
 * Python's English G2P (g2p_en) spells numbers out, strips accents, filters
 * characters, replaces i.e./e.g. and tokenizes with nltk's TweetTokenizer
 * before its dictionary lookup. english_normalize.hpp ports those steps; this
 * test compares the port with tests/fixtures/g2p/english_normalize_cases.json,
 * which scripts/build_english_normalize_fixture.py generates from the Python
 * code. Every case must match, and a fixture with no case fails.
 *
 * It also covers what has no Python counterpart to compare with: the reading
 * of words outside the CMU dictionary (Python uses a neural predictor; the
 * port must at least never drop the word), and the phoneme stream for inputs
 * whose words are all in the dictionary, which must equal Python's output.
 *
 * Design: docs/design/english-g2p-normalization-cpp-rust-2026-10-23.md
 */

#include <gtest/gtest.h>

#include "../english_normalize.hpp"
#include "../english_phonemize.hpp"
#include "../json.hpp"
#include "../utf8_utils.hpp"

#include <cctype>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#ifndef PIPER_PLUS_SOURCE_DIR
#error "PIPER_PLUS_SOURCE_DIR must point at the repository root"
#endif

namespace {

using nlohmann::json;

const std::string kRoot = PIPER_PLUS_SOURCE_DIR;

json loadJson(const std::string &relative) {
    std::ifstream in(kRoot + "/" + relative, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open " + relative);
    std::stringstream buf;
    buf << in.rdbuf();
    return json::parse(buf.str());
}

std::string lower(std::string s) {
    for (auto &c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

std::string joinWords(const std::vector<std::string> &words) {
    std::string out = "[";
    for (size_t i = 0; i < words.size(); ++i) {
        if (i) out += ", ";
        out += "'" + words[i] + "'";
    }
    return out + "]";
}

const std::unordered_map<std::string, std::string> &cmuDict() {
    static const std::unordered_map<std::string, std::string> dict = [] {
        std::unordered_map<std::string, std::string> d;
        piper::loadCmuDict(kRoot + "/src/rust/piper-plus-g2p/data/cmudict_data.json", d);
        return d;
    }();
    return dict;
}

// Phonemes of `text` joined with '|', the way the Python reference below is
// written (a word boundary is the phoneme " ").
std::string phonemize(const std::string &text) {
    std::vector<std::vector<piper::Phoneme>> sentences;
    piper::phonemize_english(text, sentences, cmuDict());
    std::string out;
    for (const auto &sentence : sentences) {
        for (auto ph : sentence) {
            if (!out.empty()) out += '|';
            out += piper::utf8_util::cpToUtf8(ph);
        }
    }
    return out;
}

}  // namespace

// ---------------------------------------------------------------------------
// Shared fixture: normalize_numbers and the full normalization + tokenizer
// ---------------------------------------------------------------------------

TEST(EnglishNormalizeFixture, NumbersMatchPython) {
    const json doc = loadJson("tests/fixtures/g2p/english_normalize_cases.json");
    int compared = 0;
    std::vector<std::string> failures;
    for (const auto &c : doc["numbers"]) {
        const std::string input = c["input"];
        const std::string expected = c["output"];
        const std::string actual = piper::normalizeEnglishNumbers(input);
        ++compared;
        if (actual != expected) {
            failures.push_back("'" + input + "'\n  expected: '" + expected + "'\n  actual:   '" +
                               actual + "'");
        }
    }
    EXPECT_GT(compared, 0) << "english_normalize_cases.json has no 'numbers' case";
    std::string all;
    for (const auto &f : failures) all += f + "\n";
    EXPECT_TRUE(failures.empty()) << failures.size() << " of " << compared
                                  << " number cases differ:\n" << all;
}

TEST(EnglishNormalizeFixture, TokensMatchPython) {
    const json doc = loadJson("tests/fixtures/g2p/english_normalize_cases.json");
    int compared = 0;
    std::vector<std::string> failures;
    for (const auto &c : doc["tokens"]) {
        const std::string input = c["input"];
        const auto expected = c["tokens"].get<std::vector<std::string>>();
        std::vector<std::string> actual;
        for (const auto &t : piper::tokenizeEnglish(piper::normalizeEnglishText(input))) {
            actual.push_back(lower(t));
        }
        ++compared;
        if (actual != expected) {
            failures.push_back("'" + input + "'\n  expected: " + joinWords(expected) +
                               "\n  actual:   " + joinWords(actual));
        }
    }
    EXPECT_GT(compared, 0) << "english_normalize_cases.json has no 'tokens' case";
    std::string all;
    for (const auto &f : failures) all += f + "\n";
    EXPECT_TRUE(failures.empty()) << failures.size() << " of " << compared
                                  << " token cases differ:\n" << all;
}

// ---------------------------------------------------------------------------
// Pieces the fixture does not reach
// ---------------------------------------------------------------------------

TEST(EnglishNormalize, NumbersBeyondQuintillionAreReadDigitByDigit) {
    // inflect's scale words stop at quintillion in this port (design doc 3.2).
    EXPECT_EQ(piper::normalizeEnglishNumbers("1000000000000000000000"),
              "one zero zero zero zero zero zero zero zero zero zero zero zero zero zero "
              "zero zero zero zero zero zero zero");
    EXPECT_EQ(piper::normalizeEnglishNumbers("999999999999999999999"),
              "nine hundred ninety-nine quintillion, nine hundred ninety-nine quadrillion, "
              "nine hundred ninety-nine trillion, nine hundred ninety-nine billion, "
              "nine hundred ninety-nine million, nine hundred ninety-nine thousand, "
              "nine hundred ninety-nine");
}

// g2p_en removes whitespace and joins the words around it; Python reads the
// joined word with a neural predictor the port does not have, so the port
// makes any whitespace a word separator (U+00A0 and U+3000 in UTF-8 here).
TEST(EnglishNormalize, WhitespaceSeparatesWords) {
    EXPECT_EQ(piper::normalizeEnglishText("tab\tnew\nline\r\nend"), "tab new line  end");
    EXPECT_EQ(piper::normalizeEnglishText("no\xc2\xa0" "break\xe3\x80\x80" "space"), "no break space");
}

TEST(EnglishNormalize, CaseIsKeptForCamelCaseSplitting) {
    EXPECT_EQ(piper::normalizeEnglishText("ChatGPT, I.E. Caf\xc3\xa9"), "ChatGPT, that is Cafe");
}

TEST(EnglishNormalize, SourceWordsComeFromTheTextBeforeNumberExpansion) {
    EXPECT_EQ(piper::englishSourceWords("The 3 of US, don't"),
              (std::vector<std::string>{"the", "of", "us", "don't"}));
}

TEST(EnglishLetterNames, MatchTheSpecTable) {
    const std::vector<std::pair<char, std::string>> table = {
        {'a', "EY1"},     {'b', "B IY1"},  {'c', "S IY1"},  {'d', "D IY1"},
        {'e', "IY1"},     {'f', "EH1 F"},  {'g', "JH IY1"}, {'h', "EY1 CH"},
        {'i', "AY1"},     {'j', "JH EY1"}, {'k', "K EY1"},  {'l', "EH1 L"},
        {'m', "EH1 M"},   {'n', "EH1 N"},  {'o', "OW1"},    {'p', "P IY1"},
        {'q', "K Y UW1"}, {'r', "AA1 R"},  {'s', "EH1 S"},  {'t', "T IY1"},
        {'u', "Y UW1"},   {'v', "V IY1"},  {'w', "D AH1 B AH0 L Y UW0"},
        {'x', "EH1 K S"}, {'y', "W AY1"},  {'z', "Z IY1"},
    };
    ASSERT_EQ(table.size(), 26u);
    for (const auto &[letter, arpabet] : table) {
        const char *lowerName = piper::englishLetterArpabet(letter);
        const char upperLetter = static_cast<char>(letter - 'a' + 'A');
        const char *upperName = piper::englishLetterArpabet(upperLetter);
        ASSERT_NE(lowerName, nullptr) << letter;
        ASSERT_NE(upperName, nullptr) << upperLetter;
        EXPECT_EQ(lowerName, arpabet) << letter;
        EXPECT_EQ(upperName, arpabet) << upperLetter;
    }
    EXPECT_EQ(piper::englishLetterArpabet('\''), nullptr);
    EXPECT_EQ(piper::englishLetterArpabet('1'), nullptr);
}

TEST(EnglishCamelCase, SplitsOnCaseChanges) {
    using V = std::vector<std::string>;
    EXPECT_EQ(piper::splitEnglishCamelCase("ChatGPT"), (V{"Chat", "GPT"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("iPhone"), (V{"i", "Phone"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("GitHub"), (V{"Git", "Hub"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("MixedCase"), (V{"Mixed", "Case"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("XMLHttpRequest"), (V{"XML", "Http", "Request"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("RtwoDtwo"), (V{"Rtwo", "Dtwo"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("UPPERCASE"), (V{"UPPERCASE"}));
    EXPECT_EQ(piper::splitEnglishCamelCase("lower"), (V{"lower"}));
}

// ---------------------------------------------------------------------------
// Out-of-vocabulary ladder (design doc 3.5)
// ---------------------------------------------------------------------------

TEST(EnglishOovLadder, DictionaryWordsAreLookedUpLowercase) {
    ASSERT_FALSE(cmuDict().empty()) << "CMU dictionary not loaded";
    EXPECT_EQ(piper::englishWordToArpabet("Hello", cmuDict()), "HH AH0 L OW1");
    EXPECT_EQ(piper::englishWordToArpabet("uh-huh", cmuDict()), "AH1 HH AH1");
}

TEST(EnglishOovLadder, MorphologicalFallbackComesFirst) {
    EXPECT_EQ(piper::englishWordToArpabet("ninetys", cmuDict()), "N AY1 N T IY0 Z");
}

TEST(EnglishOovLadder, SplitsOnHyphenAndDot) {
    EXPECT_EQ(piper::englishWordToArpabet("hello-world", cmuDict()), "HH AH0 L OW1 W ER1 L D");
    EXPECT_EQ(piper::englishWordToArpabet("hello.world", cmuDict()), "HH AH0 L OW1 W ER1 L D");
    EXPECT_EQ(piper::englishWordToArpabet("COVID-nineteen", cmuDict()),
              "S IY1 OW1 V IY1 AY1 D IY1 N AY1 N T IY1 N");
}

TEST(EnglishOovLadder, RetriesWithoutApostrophes) {
    EXPECT_EQ(piper::englishWordToArpabet("hel'lo", cmuDict()), "HH AH0 L OW1");
    // Not in the dictionary without the apostrophes either: spelled.
    EXPECT_EQ(piper::englishWordToArpabet("x'y", cmuDict()), "EH1 K S W AY1");
}

TEST(EnglishOovLadder, SplitsCamelCaseOnTheOriginalCase) {
    EXPECT_EQ(piper::englishWordToArpabet("ChatGPT", cmuDict()), "CH AE1 T JH IY1 P IY1 T IY1");
    EXPECT_EQ(piper::englishWordToArpabet("iPhone", cmuDict()), "AY1 F OW1 N");
    EXPECT_EQ(piper::englishWordToArpabet("MixedCase", cmuDict()), "M IH1 K S T K EY1 S");
}

TEST(EnglishOovLadder, SpellsWhatIsLeft) {
    EXPECT_EQ(piper::englishWordToArpabet("TTS", cmuDict()), "T IY1 T IY1 EH1 S");
    EXPECT_EQ(piper::englishWordToArpabet("xyz", cmuDict()), "EH1 K S W AY1 Z IY1");
}

// ---------------------------------------------------------------------------
// phonemize_english end to end
// ---------------------------------------------------------------------------

TEST(EnglishPhonemize, OovWordsAreNeverSilent) {
    static const std::set<std::string> notSpoken = {" ", ".", ",", "!", "?", ";", ":", "'", "-"};
    for (const std::string word : {"ChatGPT", "TTS", "xyz", "aaaaa", "UPPERCASE", "MixedCase",
                                   "iPhone", "GitHub", "COVID-19", "R2D2", "'90s"}) {
        std::vector<std::vector<piper::Phoneme>> sentences;
        piper::phonemize_english(word, sentences, cmuDict());
        bool spoken = false;
        for (const auto &sentence : sentences) {
            for (auto ph : sentence) {
                if (!notSpoken.count(piper::utf8_util::cpToUtf8(ph))) spoken = true;
            }
        }
        EXPECT_TRUE(spoken) << "'" << word << "' produced no phoneme: '" << phonemize(word)
                            << "'";
    }
}

TEST(EnglishPhonemize, NoLeadingWordBoundary) {
    for (const std::string text : {"xyz hello", "123", "ChatGPT is here", "$5", "\xe2\x80\x94 hi"}) {
        const std::string out = phonemize(text);
        ASSERT_FALSE(out.empty()) << text;
        EXPECT_NE(out.substr(0, 1), " ") << "'" << text << "' -> '" << out << "'";
    }
}

// Python reference: phonemize_english(text) joined with '|'. Every word of
// these inputs is in the CMU dictionary, so the two must agree exactly.
TEST(EnglishPhonemize, MatchesPythonWhenEveryWordIsInTheDictionary) {
    const std::vector<std::pair<std::string, std::string>> cases = {
        // Function words are matched against the words of the ORIGINAL text:
        // "three" takes "of" and "of" takes "us", so both lose their stress.
        {"the 3 of us", "ð|ə| |θ|ɹ|i|ː| |ʌ|v| |ˈ|ʌ|s"},
        {"I have $250 in my pocket.",
         "a|ɪ| |h|æ|v| |t|u|ː| |h|ʌ|n|d|ɹ|ə|d| |f|ˈ|ɪ|f|t|i|ː| |d|ˈ|ɑ|l|ɚ|z| |ɪ|n| |m|ˈ|a|ɪ| "
         "|p|ˈ|ɑ|k|ə|t|."},
        {"Is it 100%?", "ɪ|z| |ɪ|t| |w|ˈ|ʌ|n| |h|ˈ|ʌ|n|d|ɹ|ə|d|?"},
        {"$1.50 each",
         "w|ˈ|ʌ|n| |d|ˈ|ɑ|l|ɚ|,| |f|ˈ|ɪ|f|t|i|ː| |s|ˈ|ɛ|n|t|s| |ˈ|i|ː|t|ʃ"},
        {"It's 3 o'clock.", "ˈ|ɪ|t|s| |θ|ɹ|ˈ|i|ː| |ə|k|l|ˈ|ɑ|k|."},
        {"Hello, world!", "h|ə|l|ˈ|o|ʊ|,| |w|ˈ|ɜ|ː|l|d|!"},
        {"café", "k|ə|f|ˈ|e|ɪ"},
        {"uh-huh", "ˈ|ʌ|h|ˈ|ʌ"},
        {"e.g. cats", "f|ˈ|ɔ|ː|ɹ| |ɪ|ɡ|z|ˈ|æ|m|p|ə|l| |k|ˈ|æ|t|s"},
        {"E.G. or I.E.", "f|ˈ|ɔ|ː|ɹ| |ɪ|ɡ|z|ˈ|æ|m|p|ə|l| |ɔ|ː|ɹ| |ð|æ|t| |ˈ|ɪ|z"},
        {"don't stop", "d|ˈ|o|ʊ|n|t| |s|t|ˈ|ɑ|p"},
        {"You and I", "j|u|ː| |ə|n|d| |a|ɪ"},
        // Punctuation words: only a single , . ; : ! ? attaches without a
        // space; '...', "'", '-' and '. . .' are words of their own.
        {"wait...", "w|ˈ|e|ɪ|t| |.|.|."},
        {"wait . . . now", "w|ˈ|e|ɪ|t| |.| |.| |.| |n|ˈ|a|ʊ"},
        {"x - y", "ˈ|ɛ|k|s| |-| |w|ˈ|a|ɪ"},
        {"x -- y", "ˈ|ɛ|k|s| |-| |-| |w|ˈ|a|ɪ"},
        {"'quote'", "'| |k|w|ˈ|o|ʊ|t| |'"},
        {"cats' toys", "k|ˈ|æ|t|s| |'| |t|ˈ|ɔ|ɪ|z"},
        {"so''''", "s|ˈ|o|ʊ| |'| |'| |'"},
        {"hello-", "h|ə|l|ˈ|o|ʊ| |-"},
        {"-hello", "-| |h|ə|l|ˈ|o|ʊ"},
        {"Really?!!!!", "ɹ|ˈ|ɪ|l|i|ː|?|!|!|!"},
        {"a.b", "ə|.| |b|ˈ|i|ː"},
        {"it's.ok", "ˈ|ɪ|t|s|.| |ˈ|o|ʊ|k|ˈ|e|ɪ"},
        {". hello", ".| |h|ə|l|ˈ|o|ʊ"},
        {"?hello", "?| |h|ə|l|ˈ|o|ʊ"},
    };
    std::vector<std::string> failures;
    for (const auto &[text, expected] : cases) {
        const std::string actual = phonemize(text);
        if (actual != expected) {
            failures.push_back("'" + text + "'\n  expected: " + expected + "\n  actual:   " +
                               actual);
        }
    }
    std::string all;
    for (const auto &f : failures) all += f + "\n";
    EXPECT_TRUE(failures.empty()) << failures.size() << " of " << cases.size()
                                  << " cases differ:\n" << all;
}
