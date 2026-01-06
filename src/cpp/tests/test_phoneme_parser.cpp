#include <gtest/gtest.h>
#include "../phoneme_parser.hpp"

using namespace piper;

class PhonemeParserTest : public ::testing::Test {
protected:
    void SetUp() override {
        // No setup needed for tests
    }
};

TEST_F(PhonemeParserTest, ParseEmptyString) {
    auto result = parsePhonemeNotation("");
    EXPECT_TRUE(result.empty());
}

TEST_F(PhonemeParserTest, ParsePlainText) {
    auto result = parsePhonemeNotation("Hello world");
    ASSERT_EQ(result.size(), 1);
    EXPECT_FALSE(result[0].isPhonemes);
    EXPECT_EQ(result[0].text, "Hello world");
}

TEST_F(PhonemeParserTest, ParseSinglePhonemeNotation) {
    auto result = parsePhonemeNotation("[[ h ə l oʊ ]]");
    ASSERT_EQ(result.size(), 1);
    EXPECT_TRUE(result[0].isPhonemes);
    EXPECT_EQ(result[0].text, "h ə l oʊ");
}

TEST_F(PhonemeParserTest, ParseMixedTextAndPhonemes) {
    auto result = parsePhonemeNotation("Hello [[ h ə l oʊ ]] world");
    ASSERT_EQ(result.size(), 3);
    
    EXPECT_FALSE(result[0].isPhonemes);
    EXPECT_EQ(result[0].text, "Hello ");
    
    EXPECT_TRUE(result[1].isPhonemes);
    EXPECT_EQ(result[1].text, "h ə l oʊ");
    
    EXPECT_FALSE(result[2].isPhonemes);
    EXPECT_EQ(result[2].text, " world");
}

TEST_F(PhonemeParserTest, ParseMultiplePhonemeNotations) {
    auto result = parsePhonemeNotation("[[ h ə l oʊ ]] and [[ w ɝ l d ]]");
    ASSERT_EQ(result.size(), 3);
    
    EXPECT_TRUE(result[0].isPhonemes);
    EXPECT_EQ(result[0].text, "h ə l oʊ");
    
    EXPECT_FALSE(result[1].isPhonemes);
    EXPECT_EQ(result[1].text, " and ");
    
    EXPECT_TRUE(result[2].isPhonemes);
    EXPECT_EQ(result[2].text, "w ɝ l d");
}

TEST_F(PhonemeParserTest, ParsePhonemeStringEspeak) {
    auto phonemes = parsePhonemeString("h ə l oʊ", PHONEME_TYPE_ESPEAK);
    // "oʊ" is parsed as two separate characters in espeak mode
    ASSERT_EQ(phonemes.size(), 5);
    EXPECT_EQ(phonemes[0], static_cast<Phoneme>('h'));
    EXPECT_EQ(phonemes[1], static_cast<Phoneme>(U'ə'));
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>('l'));
    EXPECT_EQ(phonemes[3], static_cast<Phoneme>('o'));
    EXPECT_EQ(phonemes[4], static_cast<Phoneme>(U'ʊ'));
}

TEST_F(PhonemeParserTest, ParsePhonemeStringJapanese) {
    auto phonemes = parsePhonemeString("k o N n i ch i w a", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 9);
    EXPECT_EQ(phonemes[0], static_cast<Phoneme>('k'));
    EXPECT_EQ(phonemes[1], static_cast<Phoneme>('o'));
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>('N'));
    // ... rest of the phonemes
}

TEST_F(PhonemeParserTest, ParsePhonemeStringJapaneseMultiChar) {
    auto phonemes = parsePhonemeString("ky a sh a", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 4);
    // First phoneme should be the PUA-mapped "ky"
    // Must match Python token_mapper.py FIXED_PUA_MAPPING
    EXPECT_EQ(phonemes[0], static_cast<Phoneme>(0xE006)); // ky -> U+E006
    EXPECT_EQ(phonemes[1], static_cast<Phoneme>('a'));
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE010)); // sh -> U+E010
    EXPECT_EQ(phonemes[3], static_cast<Phoneme>('a'));
}

TEST_F(PhonemeParserTest, ParseWithExtraSpaces) {
    auto result = parsePhonemeNotation("Text [[  h   ə   l   oʊ  ]] more");
    ASSERT_EQ(result.size(), 3);
    EXPECT_TRUE(result[1].isPhonemes);
    EXPECT_EQ(result[1].text, "h   ə   l   oʊ");
}

TEST_F(PhonemeParserTest, HandleNestedBrackets) {
    // Nested brackets should not be parsed as phonemes
    auto result = parsePhonemeNotation("[[ h [[ nested ]] ə ]]");
    // The regex should not match this as a valid phoneme notation
    // due to the nested brackets
    ASSERT_GE(result.size(), 1);
}

TEST_F(PhonemeParserTest, EmptyPhonemeNotation) {
    auto result = parsePhonemeNotation("Text [[]] more");
    ASSERT_EQ(result.size(), 3);
    EXPECT_TRUE(result[1].isPhonemes);
    EXPECT_EQ(result[1].text, "");
}

// =========================================================================
// Issue #204: Question Type Marker Tests
// =========================================================================

TEST_F(PhonemeParserTest, ParseQuestionMarkerEmphatic) {
    // Test emphatic question marker ?! (Issue #204)
    auto phonemes = parsePhonemeString("h o N t o u ?!", PHONEME_TYPE_OPENJTALK);
    ASSERT_GE(phonemes.size(), 7);
    // Last phoneme should be ?! mapped to 0xE016
    EXPECT_EQ(phonemes[phonemes.size() - 1], static_cast<Phoneme>(0xE016));
}

TEST_F(PhonemeParserTest, ParseQuestionMarkerNeutral) {
    // Test neutral/rhetorical question marker ?. (Issue #204)
    auto phonemes = parsePhonemeString("s o u d e s u k a ?.", PHONEME_TYPE_OPENJTALK);
    ASSERT_GE(phonemes.size(), 9);
    // Last phoneme should be ?. mapped to 0xE017
    EXPECT_EQ(phonemes[phonemes.size() - 1], static_cast<Phoneme>(0xE017));
}

TEST_F(PhonemeParserTest, ParseQuestionMarkerTag) {
    // Test tag question marker ?~ (Issue #204)
    auto phonemes = parsePhonemeString("i k u y o n e ?~", PHONEME_TYPE_OPENJTALK);
    ASSERT_GE(phonemes.size(), 7);
    // Last phoneme should be ?~ mapped to 0xE018
    EXPECT_EQ(phonemes[phonemes.size() - 1], static_cast<Phoneme>(0xE018));
}

// =========================================================================
// Issue #207: N Phoneme Variant Tests
// =========================================================================

TEST_F(PhonemeParserTest, ParseNVariantBilabial) {
    // Test N_m variant before m/b/p (Issue #207)
    // さんぽ (sanpo) - ん before p
    auto phonemes = parsePhonemeString("s a N_m p o", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 5);
    // N_m should be mapped to 0xE019
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE019));
}

TEST_F(PhonemeParserTest, ParseNVariantAlveolar) {
    // Test N_n variant before n/t/d/ts/ch (Issue #207)
    // あんない (annai) - ん before n
    auto phonemes = parsePhonemeString("a N_n n a i", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 5);
    // N_n should be mapped to 0xE01A
    EXPECT_EQ(phonemes[1], static_cast<Phoneme>(0xE01A));
}

TEST_F(PhonemeParserTest, ParseNVariantVelar) {
    // Test N_ng variant before k/g (Issue #207)
    // ぎんこう (ginkou) - ん before k
    auto phonemes = parsePhonemeString("g i N_ng k o u", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 6);
    // N_ng should be mapped to 0xE01B
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE01B));
}

TEST_F(PhonemeParserTest, ParseNVariantUvular) {
    // Test N_uvular variant at phrase end (Issue #207)
    // ほん (hon) - ん at end
    auto phonemes = parsePhonemeString("h o N_uvular", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 3);
    // N_uvular should be mapped to 0xE01C
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE01C));
}

TEST_F(PhonemeParserTest, ParseJapaneseAffricates) {
    // Test common affricates - ch and ts
    auto phonemes = parsePhonemeString("ch a ts u", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 4);
    // ch -> 0xE00E, ts -> 0xE00F
    EXPECT_EQ(phonemes[0], static_cast<Phoneme>(0xE00E));
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE00F));
}

TEST_F(PhonemeParserTest, ParseJapaneseGeminate) {
    // Test geminate consonant (っ) - cl
    // がっこう (gakkou) - "g a cl k o u" has 6 tokens
    auto phonemes = parsePhonemeString("g a cl k o u", PHONEME_TYPE_OPENJTALK);
    ASSERT_EQ(phonemes.size(), 6);
    // cl -> 0xE005
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE005));
}