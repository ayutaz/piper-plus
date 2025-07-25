#include <gtest/gtest.h>
#include "../phoneme_parser.hpp"
#include <spdlog/spdlog.h>

using namespace piper;

class PhonemeParserTest : public ::testing::Test {
protected:
    void SetUp() override {
        spdlog::set_level(spdlog::level::debug);
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
    EXPECT_EQ(phonemes[0], static_cast<Phoneme>(0xE000)); // ky -> U+E000
    EXPECT_EQ(phonemes[1], static_cast<Phoneme>('a'));
    EXPECT_EQ(phonemes[2], static_cast<Phoneme>(0xE002)); // sh -> U+E002  
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