/**
 * Test: CJK punctuation contract (Issue #823).
 *
 * Reads tests/fixtures/g2p/cjk_punctuation_cases.json, which
 * scripts/build_cjk_punctuation_fixture.py builds from
 * docs/spec/cjk-punctuation-contract.toml. Every runtime has the same test,
 * so a detector or Latin-segment rewrite that drifts from the contract fails
 * in the runtime that drifted.
 *
 * The multilingual checks go through the engine-less G2P C API (the path the
 * Android and Swift wrappers use). Japanese is not exercised there because
 * the OpenJTalk dictionary is not staged.
 *
 * MSVC reads every hex digit after "\x", so a literal whose escape is
 * followed by a letter a-f / digit is split ("\x8c" "amigo").
 */

#include <gtest/gtest.h>
#include "piper_plus.h"
#include "../json.hpp"
#include "../language_detector.hpp"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#ifndef PIPER_PLUS_SOURCE_DIR
#error "PIPER_PLUS_SOURCE_DIR must point at the repository root"
#endif

namespace {

using nlohmann::json;

const std::string kRoot = PIPER_PLUS_SOURCE_DIR;

const json &fixture() {
    static const json doc = [] {
        std::ifstream in(kRoot + "/tests/fixtures/g2p/cjk_punctuation_cases.json",
                         std::ios::binary);
        if (!in) throw std::runtime_error("cannot open cjk_punctuation_cases.json");
        std::stringstream buf;
        buf << in.rdbuf();
        return json::parse(buf.str());
    }();
    return doc;
}

char32_t codePoint(const json &entry) {
    // "U+3001" -> 0x3001
    return static_cast<char32_t>(
        std::stoul(entry["code_point"].get<std::string>().substr(2), nullptr, 16));
}

piper::UnicodeLanguageDetector makeDetector() {
    return piper::UnicodeLanguageDetector(
        fixture()["detector_languages"].get<std::vector<std::string>>(),
        fixture()["default_latin"].get<std::string>());
}

// Tokens are joined with one space; a word boundary token " " therefore
// appears as three spaces (two empty parts when split). Same as
// test_c_api_g2p_golden.cpp.
std::vector<std::string> splitPhonemes(const std::string &s) {
    std::vector<std::string> tokens;
    if (s.empty()) return tokens;
    int emptyParts = 0;
    size_t start = 0;
    while (true) {
        size_t end = s.find(' ', start);
        std::string part = s.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (!part.empty()) {
            emptyParts = 0;
            tokens.push_back(part);
        } else if (++emptyParts == 2) {
            emptyParts = 0;
            tokens.emplace_back(" ");
        }
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return tokens;
}

// Points PIPER_PLUS_DICTIONARIES_PATH at the canonical CMU / pinyin files
// and restores the previous value afterwards.
class ScopedDictionaries {
public:
    ScopedDictionaries() {
        const char *old = std::getenv("PIPER_PLUS_DICTIONARIES_PATH");
        if (old) previous_ = old;
        set(kRoot + "/src/rust/piper-plus-g2p/data");
    }
    ~ScopedDictionaries() { set(previous_); }

private:
    static void set(const std::string &value) {
#ifdef _WIN32
        _putenv_s("PIPER_PLUS_DICTIONARIES_PATH", value.c_str());
#else
        if (value.empty()) {
            unsetenv("PIPER_PLUS_DICTIONARIES_PATH");
        } else {
            setenv("PIPER_PLUS_DICTIONARIES_PATH", value.c_str(), 1);
        }
#endif
    }
    std::string previous_;
};

class CjkPunctuationG2p : public ::testing::Test {
protected:
    void SetUp() override {
        handle_ = piper_plus_g2p_create(nullptr);
        ASSERT_NE(handle_, nullptr);
    }
    void TearDown() override { piper_plus_g2p_free(handle_); }

    // Auto-detects the language of every segment (no language hint).
    std::vector<std::string> phonemize(const std::string &text) {
        PiperPlusPhonemeResult r{};
        EXPECT_EQ(piper_plus_g2p_phonemize(handle_, text.c_str(), nullptr, &r), PIPER_PLUS_OK)
            << text;
        return splitPhonemes(r.phonemes ? r.phonemes : "");
    }

    ScopedDictionaries dictionaries_;  // must outlive create()
    PiperPlusG2pHandle *handle_ = nullptr;
};

}  // namespace

TEST(CjkPunctuationContract, FixtureIsNotEmpty) {
    EXPECT_GT(fixture()["neutral"].size(), 100u);
    EXPECT_EQ(fixture()["fullwidth_latin"].size(), 52u);
}

TEST(CjkPunctuationContract, NeutralCodePointsBelongToNoLanguage) {
    const auto detector = makeDetector();
    for (bool contextHasKana : {false, true}) {
        std::vector<std::string> wrong;
        for (const auto &c : fixture()["neutral"]) {
            const std::string lang = detector.detectChar(codePoint(c), contextHasKana);
            if (!lang.empty()) wrong.push_back(c["code_point"].get<std::string>() + "->" + lang);
        }
        std::string all;
        for (const auto &w : wrong) all += w + " ";
        EXPECT_TRUE(wrong.empty()) << "contextHasKana=" << contextHasKana << ": " << all;
    }
}

TEST(CjkPunctuationContract, FullwidthLatinLettersStayLatin) {
    const auto detector = makeDetector();
    const std::string defaultLatin = fixture()["default_latin"];
    std::vector<std::string> wrong;
    for (const auto &c : fixture()["fullwidth_latin"]) {
        if (detector.detectChar(codePoint(c), false) != defaultLatin) {
            wrong.push_back(c["code_point"].get<std::string>());
        }
    }
    std::string all;
    for (const auto &w : wrong) all += w + " ";
    EXPECT_TRUE(wrong.empty()) << all;
}

TEST(CjkPunctuationContract, LatinSegmentRewrite) {
    std::vector<std::string> wrong;
    for (const auto &c : fixture()["neutral"]) {
        const std::string actual = piper::normalizeCjkPunctuationForLatin(c["char"]);
        if (actual != c["latin"].get<std::string>()) {
            wrong.push_back(c["code_point"].get<std::string>() + " -> '" + actual + "'");
        }
    }
    std::string all;
    for (const auto &w : wrong) all += w + "\n";
    EXPECT_TRUE(wrong.empty()) << all;

    // Everything else is left alone, the fullwidth Latin letters included.
    for (const std::string text : {
             std::string("Hello, world!"),
             std::string("caf\xc3\xa9"),                                // café
             std::string("\xef\xbc\xa1\xef\xbc\xa2\xef\xbc\xa3"),       // ＡＢＣ
             std::string("\xe4\xbd\xa0\xe5\xa5\xbd"),                   // 你好
             std::string("\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab"
                         "\xe3\x81\xa1\xe3\x81\xaf"),                   // こんにちは
             std::string(),
         }) {
        EXPECT_EQ(piper::normalizeCjkPunctuationForLatin(text), text);
    }
}

TEST(CjkPunctuationContract, ChineseSentenceIsOneSegment) {
    const auto detector = makeDetector();
    // 你好，今天天气很好。
    const auto segments = detector.segmentText(
        "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8c\xe4\xbb\x8a\xe5\xa4\xa9"
        "\xe5\xa4\xa9\xe6\xb0\x94\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82");
    ASSERT_EQ(segments.size(), 1u);
    EXPECT_EQ(segments[0].lang, "zh");
}

TEST_F(CjkPunctuationG2p, ChineseSentenceKeepsItsPunctuation) {
    // 你好，今天天气很好。
    const auto tokens = phonemize(
        "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8c\xe4\xbb\x8a\xe5\xa4\xa9"
        "\xe5\xa4\xa9\xe6\xb0\x94\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82");
    ASSERT_FALSE(tokens.empty());
    EXPECT_EQ(std::count(tokens.begin(), tokens.end(), ","), 1);
    EXPECT_EQ(tokens.back(), ".");

    // 北京欢迎你。
    const auto beijing = phonemize(
        "\xe5\x8c\x97\xe4\xba\xac\xe6\xac\xa2\xe8\xbf\x8e\xe4\xbd\xa0\xe3\x80\x82");
    ASSERT_FALSE(beijing.empty());
    EXPECT_EQ(beijing.back(), ".");
}

TEST_F(CjkPunctuationG2p, EnglishAfterChineseCommaIsReadAsALoanword) {
    // The ZH-EN dispatch needs the Chinese segment right before the English
    // one; a Japanese segment for "，" would sit between them.
    auto withComma = phonemize("\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8cGPS");  // 你好，GPS
    const auto without = phonemize("\xe4\xbd\xa0\xe5\xa5\xbdGPS");          // 你好GPS
    withComma.erase(std::remove(withComma.begin(), withComma.end(), ","), withComma.end());
    EXPECT_EQ(withComma, without);
}

TEST_F(CjkPunctuationG2p, LatinTextWithCjkPunctuationReadsLikeAscii) {
    // The English G2P drops characters it does not know, which would join
    // "Hello，world" into one word.
    const std::pair<std::string, std::string> cases[] = {
        {"Hello\xef\xbc\x8cworld", "Hello,world"},                 // Hello，world
        {"Hello\xe3\x80\x81world\xe3\x80\x82", "Hello,world."},    // Hello、world。
        {"Hola\xef\xbc\x8c" "amigo\xef\xbc\x81", "Hola,amigo!"},   // Hola，amigo！
        {"I have \xef\xbc\x93 cats\xef\xbc\x8e", "I have 3 cats."},  // I have ３ cats．
    };
    for (const auto &[cjk, ascii] : cases) {
        EXPECT_EQ(phonemize(cjk), phonemize(ascii)) << ascii;
    }
}
