// ZH-EN code-switching tests (TICKET-05 P6, mirror of TICKET-01 R5).

#include <gtest/gtest.h>

#include <cstdint>
#include <thread>
#include <vector>

#include "chinese_loanword.hpp"
#include "phoneme_parser.hpp"

using namespace piper;

namespace {

// Build a minimal LoanwordData for unit tests (avoids depending on the
// bundled JSON). Mirrors the canonical sub-section of zh_en_loanword.json.
LoanwordData makeTestData() {
    LoanwordData d;
    d.version = 1;
    d.acronyms["GPS"] = {"ji4", "pi4", "ai1", "si4"};
    d.acronyms["USB"] = {"you1", "ai1", "si4", "bi4"};
    d.acronyms["MP3"] = {"ai1"};  // override for digit test
    d.loanwords["Python"] = {"pai4", "sen1"};
    d.loanwords["ChatGPT"] = {"chai4", "ti2", "ji4", "pi4", "ti4"};
    for (char c = 'A'; c <= 'Z'; ++c) {
        d.letter_fallback[std::string(1, c)] = {"ei1"};  // dummy single syllable
    }
    return d;
}

}  // namespace

// =========================================================================
// Loader / parse tests
// =========================================================================

TEST(ZhEnLoanwordTest, ParseLoanwordJson_ValidV1) {
    const std::string json = R"({
        "version": 1,
        "acronyms": {"GPS": ["ji4"]},
        "loanwords": {"Python": ["pai4"]},
        "letter_fallback": {"A": ["ei1"]}
    })";
    auto data = parseLoanwordJson("test.json", json);
    EXPECT_EQ(data.version, 1);
    EXPECT_EQ(data.acronyms.at("GPS"), std::vector<std::string>{"ji4"});
    EXPECT_EQ(data.loanwords.at("Python"), std::vector<std::string>{"pai4"});
    EXPECT_EQ(data.letter_fallback.at("A"), std::vector<std::string>{"ei1"});
}

TEST(ZhEnLoanwordTest, ParseLoanwordJson_MissingVersion_Throws) {
    const std::string json = R"({"acronyms": {}})";
    EXPECT_THROW(parseLoanwordJson("test.json", json), LoanwordSchemaError);
}

TEST(ZhEnLoanwordTest, ParseLoanwordJson_NonListValue_Throws) {
    const std::string json = R"({"version": 1, "acronyms": {"GPS": "not_a_list"}})";
    try {
        parseLoanwordJson("test.json", json);
        FAIL() << "expected LoanwordSchemaError";
    } catch (const LoanwordSchemaError& e) {
        std::string msg = e.what();
        EXPECT_NE(msg.find("'acronyms.GPS'"), std::string::npos) << msg;
        EXPECT_NE(msg.find("must be list[str]"), std::string::npos) << msg;
    }
}

TEST(ZhEnLoanwordTest, ParseLoanwordJson_NonDictSection_Throws) {
    const std::string json = R"({"version": 1, "acronyms": "not_a_dict"})";
    try {
        parseLoanwordJson("test.json", json);
        FAIL() << "expected LoanwordSchemaError";
    } catch (const LoanwordSchemaError& e) {
        std::string msg = e.what();
        EXPECT_NE(msg.find("'acronyms'"), std::string::npos) << msg;
        EXPECT_NE(msg.find("must be a mapping"), std::string::npos) << msg;
    }
}

TEST(ZhEnLoanwordTest, Loader_AcceptsUnknownFieldsInSchemaV2) {
    // YELLOW-5: forward-compat — unknown top-level fields must not fail.
    const std::string v2 = R"({
        "version": 2,
        "schema_version": 2,
        "metadata": {"experimental": true},
        "acronyms": {"GPS": ["ji4"]},
        "loanwords": {"Python": ["pai4"]},
        "letter_fallback": {"A": ["ei1"]},
        "tone_overrides": {"GPS": "high"}
    })";
    auto data = parseLoanwordJson("future_v2.json", v2);
    EXPECT_EQ(data.version, 2);
    EXPECT_NE(data.acronyms.find("GPS"), data.acronyms.end());
}

// =========================================================================
// phonemizeEmbeddedEnglish tests
// =========================================================================

TEST(ZhEnLoanwordTest, EmbeddedEnglish_Acronym_GPS) {
    auto data = makeTestData();
    std::vector<Phoneme> out;
    phonemizeEmbeddedEnglish("GPS", out, data);
    // GPS = ji4 + pi4 + ai1 + si4 = 4 syllables
    // ji4(3) + pi4(3) + ai1(2 zero initial) + si4(3) = 11 phonemes
    EXPECT_EQ(out.size(), 11u);
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_Loanword_Python_CaseSensitive) {
    auto data = makeTestData();
    std::vector<Phoneme> lower;
    phonemizeEmbeddedEnglish("Python", lower, data);
    // pai4(3) + sen1(3) = 6
    EXPECT_EQ(lower.size(), 6u);

    // PYTHON falls through to letter_fallback (not in our test data as
    // case-sensitive loanword) — should differ from "Python".
    std::vector<Phoneme> upper;
    phonemizeEmbeddedEnglish("PYTHON", upper, data);
    EXPECT_NE(lower.size(), upper.size());
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_ChatGPT_FiveSyllables) {
    auto data = makeTestData();
    std::vector<Phoneme> out;
    phonemizeEmbeddedEnglish("ChatGPT", out, data);
    // 5 syllables × 3 phonemes = 15
    EXPECT_EQ(out.size(), 15u);
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_Empty_ReturnsEmpty) {
    auto data = makeTestData();
    std::vector<Phoneme> out;
    phonemizeEmbeddedEnglish("", out, data);
    EXPECT_TRUE(out.empty());
    phonemizeEmbeddedEnglish(",.!?", out, data);
    EXPECT_TRUE(out.empty());
    phonemizeEmbeddedEnglish("   ", out, data);
    EXPECT_TRUE(out.empty());
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_TrailingPunctuation) {
    auto data = makeTestData();
    std::vector<Phoneme> plain;
    phonemizeEmbeddedEnglish("GPS", plain, data);
    for (const auto& suffix : {",", ".", "!", ":"}) {
        std::vector<Phoneme> got;
        phonemizeEmbeddedEnglish(std::string("GPS") + suffix, got, data);
        EXPECT_EQ(plain, got) << "suffix=" << suffix;
    }
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_LookupPriority_LoanwordBeatsAcronym) {
    LoanwordData d;
    d.version = 1;
    d.loanwords["AI"] = {"ma1"};
    d.acronyms["AI"] = {"ji4"};
    std::vector<Phoneme> got;
    phonemizeEmbeddedEnglish("AI", got, d);

    // Expected: same as loanword-only path
    LoanwordData d2;
    d2.version = 1;
    d2.loanwords["AI"] = {"ma1"};
    std::vector<Phoneme> loan_only;
    phonemizeEmbeddedEnglish("AI", loan_only, d2);
    EXPECT_EQ(got, loan_only);
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_AcronymWithDigits_MP3) {
    auto data = makeTestData();  // has acronyms.MP3 = {"ai1"}
    std::vector<Phoneme> got;
    phonemizeEmbeddedEnglish("MP3", got, data);

    // Compare against acronym-only path (no letter_fallback contamination)
    LoanwordData d;
    d.version = 1;
    d.acronyms["MP3"] = {"ai1"};
    std::vector<Phoneme> acronym_only;
    phonemizeEmbeddedEnglish("MP3", acronym_only, d);
    EXPECT_EQ(got, acronym_only);
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_DigitsDropped) {
    LoanwordData d;
    d.version = 1;
    d.letter_fallback["Z"] = {"zi4"};
    std::vector<Phoneme> z2z9;
    std::vector<Phoneme> zz;
    phonemizeEmbeddedEnglish("Z2Z9", z2z9, d);
    phonemizeEmbeddedEnglish("ZZ", zz, d);
    EXPECT_EQ(z2z9, zz);
}

TEST(ZhEnLoanwordTest, EmbeddedEnglish_TwoEmbeddedEn) {
    auto data = makeTestData();
    std::vector<Phoneme> combined;
    phonemizeEmbeddedEnglish("ChatGPT \xe5\x92\x8c Python", combined, data);  // \xe5\x92\x8c = 和
    std::vector<Phoneme> chatgpt;
    phonemizeEmbeddedEnglish("ChatGPT", chatgpt, data);
    std::vector<Phoneme> python;
    phonemizeEmbeddedEnglish("Python", python, data);
    EXPECT_EQ(combined.size(), chatgpt.size() + python.size());
}

// =========================================================================
// Concurrent access (TICKET-05 P6 §8.14)
// =========================================================================

TEST(ZhEnLoanwordTest, ConcurrentAccess) {
    auto data = std::make_shared<LoanwordData>(makeTestData());
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([data]() {
            for (int j = 0; j < 200; ++j) {
                std::vector<Phoneme> out;
                phonemizeEmbeddedEnglish("GPS", out, *data);
                EXPECT_EQ(out.size(), 11u);
            }
        });
    }
    for (auto& t : threads) t.join();
    SUCCEED();
}
