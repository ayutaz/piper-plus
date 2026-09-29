// Unit tests for the PRODUCTION sentence splitter (src/cpp/sentence_split.hpp,
// called by piper.cpp:splitTextToSentences). Issue #343 / #346 regressions.
//
// Until issue #703 this file carried hand-written copies of all four functions
// and said so ("These tests mirror the algorithm in piper.cpp"), so every
// assertion below ran against the copy rather than against what ships. A
// mirror cannot catch drift in the thing it mirrors, and this one had already
// lost production's `utf8::is_valid` guard -- the one input that can walk
// `utf8::unchecked` off the end was the one the tests could not reach.
//
// The functions now come from the header. Only the argument spelling is
// adapted: the tests name phoneme types, the algorithm switches on a
// punctuation set, and PhonemeType cannot express the third one (usesOpenJTalk
// is true for both of its values, which is why `EnglishPhonemes = 99` had to
// be invented here). SentenceSplitMode names all three.
//
// The integration path is covered by test_streaming.cpp, which calls
// textToAudioStreaming() -> splitTextToSentences().

#include <gtest/gtest.h>
#include <string>
#include <vector>
#include <cstdint>
#include <functional>

#include "sentence_split.hpp"
#include "utf8_utils.hpp"

// The tests name phoneme types; the splitter takes a punctuation set. These
// map one to the other, matching piper.cpp:phonemeTypeToSplitMode for the two
// real PhonemeType values. EnglishPhonemes has no PhonemeType counterpart --
// production cannot reach the ASCII branch today -- but the branch exists and
// is tested, so the spelling is kept.
namespace {

enum TestPhonemeType {
  OpenJTalkPhonemes = 0,
  MultilingualPhonemes = 1,
  EnglishPhonemes = 99,
};

piper::SentenceSplitMode toSplitMode(TestPhonemeType type) {
  switch (type) {
    case MultilingualPhonemes:
      return piper::SentenceSplitMode::Multilingual;
    case OpenJTalkPhonemes:
      return piper::SentenceSplitMode::OpenJTalk;
    case EnglishPhonemes:
      return piper::SentenceSplitMode::Ascii;
  }
  return piper::SentenceSplitMode::Ascii;
}

// Thin adapters so the existing call sites below are unchanged.
std::vector<std::string> splitTextToSentences(const std::string &text,
                                              TestPhonemeType phonemeType,
                                              size_t maxChunkSize = 0) {
  return piper::splitTextToSentencesIn(text, toSplitMode(phonemeType),
                                       maxChunkSize);
}

using piper::calculateDynamicChunkSize;
using piper::isClosingPunctuation;
using piper::isPunctCodepoint;

} // anonymous namespace

// ========================================================================
// Issue #343 core regression: Japanese text must NOT be byte-shredded
// ========================================================================

TEST(SplitSentencesTest, JapaneseBasic) {
  auto result = splitTextToSentences(
      u8"こんにちは。今日はいい天気ですね。ありがとう！",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_EQ(result[0], u8"こんにちは。");
  EXPECT_EQ(result[1], u8"今日はいい天気ですね。");
  EXPECT_EQ(result[2], u8"ありがとう！");
}

TEST(SplitSentencesTest, JapaneseQuestionMark) {
  auto result = splitTextToSentences(
      u8"元気ですか？はい、元気です。",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"元気ですか？");
  EXPECT_EQ(result[1], u8"はい、元気です。");
}

TEST(SplitSentencesTest, JapaneseCommaIsNotTerminator) {
  // 、(ideographic comma) is boundary punct but NOT a sentence terminator
  // for OpenJTalk. It should only split if chunk exceeds dynamicChunkSize.
  auto result = splitTextToSentences(
      u8"今日は、天気がいい。",
      OpenJTalkPhonemes);
  // Short text (10 codepoints), dynamicChunkSize = 10 (< 100)
  // 、 is not a terminator, so no split there. 。 is terminator -> split.
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"今日は、天気がいい。");
}

// ========================================================================
// English text
// ========================================================================

TEST(SplitSentencesTest, EnglishBasic) {
  auto result = splitTextToSentences(
      "Hello world. This is a test. Multiple sentences here!",
      EnglishPhonemes);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_EQ(result[0], "Hello world.");
  EXPECT_EQ(result[1], " This is a test.");
  EXPECT_EQ(result[2], " Multiple sentences here!");
}

TEST(SplitSentencesTest, EnglishSingleSentence) {
  auto result = splitTextToSentences(
      "Just one sentence.",
      EnglishPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], "Just one sentence.");
}

TEST(SplitSentencesTest, EnglishCommaNotTerminator) {
  // Commas are boundary punct but not terminators for English.
  // Short text, so no split at comma.
  auto result = splitTextToSentences(
      "Hello, world.",
      EnglishPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], "Hello, world.");
}

// ========================================================================
// Multilingual (MultilingualPhonemes)
// ========================================================================

TEST(SplitSentencesTest, MultilingualJapanese) {
  auto result = splitTextToSentences(
      u8"こんにちは。今日はいい天気ですね。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"こんにちは。");
  EXPECT_EQ(result[1], u8"今日はいい天気ですね。");
}

TEST(SplitSentencesTest, MultilingualEnglish) {
  auto result = splitTextToSentences(
      "Hello. World!",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], "Hello.");
  EXPECT_EQ(result[1], " World!");
}

TEST(SplitSentencesTest, MultilingualMixed) {
  auto result = splitTextToSentences(
      u8"こんにちは。Hello! 你好。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_EQ(result[0], u8"こんにちは。");
  EXPECT_EQ(result[1], u8"Hello!");
  EXPECT_EQ(result[2], u8" 你好。");
}

// ========================================================================
// Chinese text
// ========================================================================

TEST(SplitSentencesTest, ChineseBasic) {
  auto result = splitTextToSentences(
      u8"你好。今天天气很好。谢谢！",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_EQ(result[0], u8"你好。");
  EXPECT_EQ(result[1], u8"今天天气很好。");
  EXPECT_EQ(result[2], u8"谢谢！");
}

TEST(SplitSentencesTest, ChineseQuestionMark) {
  auto result = splitTextToSentences(
      u8"你好吗？我很好。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"你好吗？");
  EXPECT_EQ(result[1], u8"我很好。");
}

// ========================================================================
// Edge cases
// ========================================================================

TEST(SplitSentencesTest, EmptyText) {
  auto result = splitTextToSentences("", OpenJTalkPhonemes);
  EXPECT_TRUE(result.empty());
}

TEST(SplitSentencesTest, NoPunctuation) {
  auto result = splitTextToSentences(
      u8"こんにちは世界",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"こんにちは世界");
}

TEST(SplitSentencesTest, OnlyPunctuation) {
  auto result = splitTextToSentences(
      u8"。！？",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"。！？");
}

TEST(SplitSentencesTest, ConsecutivePunctuation) {
  // Multiple terminators in a row should be consumed as one run
  auto result = splitTextToSentences(
      u8"本当に！？信じられない。",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"本当に！？");
  EXPECT_EQ(result[1], u8"信じられない。");
}

TEST(SplitSentencesTest, TrailingTextAfterPunctuation) {
  auto result = splitTextToSentences(
      u8"テスト。残りのテキスト",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"テスト。");
  EXPECT_EQ(result[1], u8"残りのテキスト");
}

TEST(SplitSentencesTest, SingleCharacter) {
  auto result = splitTextToSentences(u8"あ", OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"あ");
}

TEST(SplitSentencesTest, SinglePunctuation) {
  auto result = splitTextToSentences(u8"。", OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"。");
}

// ========================================================================
// Issue #343 reproduction: the exact debug output from the bug report
// ========================================================================

TEST(SplitSentencesTest, Issue343Reproduction) {
  // This text was reported to produce 13 broken byte fragments.
  // After fix: should produce exactly 2 sentences.
  std::string text = u8"こんにちは。今日はいい天気ですね。";
  auto result = splitTextToSentences(text, OpenJTalkPhonemes);

  ASSERT_EQ(result.size(), 2u)
      << "Issue #343: text must NOT be byte-shredded into fragments";
  EXPECT_EQ(result[0], u8"こんにちは。");
  EXPECT_EQ(result[1], u8"今日はいい天気ですね。");

  // Verify no fragment contains invalid UTF-8
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FALSE(result[i].empty())
        << "Sentence " << i << " must not be empty";
    // Each sentence should start with a valid multibyte character, not a
    // bare continuation byte (0x80-0xBF).
    unsigned char firstByte = static_cast<unsigned char>(result[i][0]);
    EXPECT_FALSE(firstByte >= 0x80 && firstByte <= 0xBF)
        << "Sentence " << i << " starts with a UTF-8 continuation byte (broken)";
  }
}

TEST(SplitSentencesTest, Issue343MultilingualReproduction) {
  // Same text but through MultilingualPhonemes path
  std::string text = u8"こんにちは。今日はいい天気ですね。";
  auto result = splitTextToSentences(text, MultilingualPhonemes);

  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"こんにちは。");
  EXPECT_EQ(result[1], u8"今日はいい天気ですね。");
}

// ========================================================================
// Ellipsis handling (Multilingual mode)
// ========================================================================

TEST(SplitSentencesTest, MultilingualEllipsis) {
  // U+2026 (…) is boundary punct but NOT a sentence terminator (consistent
  // with the original regex which only checked 。！？.!? as terminators).
  // Short text -> no split at ellipsis.
  auto result = splitTextToSentences(
      u8"そうですか…次の話題。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"そうですか…次の話題。");
}

TEST(SplitSentencesTest, AsciiEllipsis) {
  auto result = splitTextToSentences(
      "Really... I see.",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], "Really...");
  EXPECT_EQ(result[1], " I see.");
}

// ========================================================================
// calculateDynamicChunkSize codepoint-level tests
// ========================================================================

TEST(DynamicChunkSizeTest, ShortASCII) {
  auto cps = piper::utf8_util::toCodepoints("Hello!");
  EXPECT_EQ(calculateDynamicChunkSize(cps), 6u);
}

TEST(DynamicChunkSizeTest, ShortCJK) {
  // 17 codepoints (not 51 bytes)
  auto cps = piper::utf8_util::toCodepoints(u8"こんにちは。今日はいい天気ですね。");
  EXPECT_EQ(cps.size(), 17u);
  EXPECT_EQ(calculateDynamicChunkSize(cps), 17u);
}

TEST(DynamicChunkSizeTest, LowPunctDensity) {
  // 110 codepoints (all ASCII), 1 period = ~0.9% density -> 3x base
  std::string text = "This is a very long text with minimal punctuation that goes on and on without many stops or breaks in the flow";
  auto cps = piper::utf8_util::toCodepoints(text);
  EXPECT_EQ(calculateDynamicChunkSize(cps), 150u);
}

TEST(DynamicChunkSizeTest, HighPunctDensityCJK) {
  // Build a long CJK text with high punctuation density (>100 codepoints).
  // Each "X。" pair = 2 codepoints. We need > 100, so 52 pairs = 104 codepoints.
  std::string text =
      u8"あ。い。う。え。お。か。き。く。け。こ。"   // 20 cp
      u8"さ。し。す。せ。そ。た。ち。つ。て。と。"   // 20 cp
      u8"な。に。ぬ。ね。の。は。ひ。ふ。へ。ほ。"   // 20 cp
      u8"ま。み。む。め。も。や。ゆ。よ。ら。り。"   // 20 cp
      u8"る。れ。ろ。わ。を。ん。が。ぎ。ぐ。げ。"   // 20 cp
      u8"ご。ざ。";                                     // 4 cp = 104 total
  auto cps = piper::utf8_util::toCodepoints(text);
  EXPECT_EQ(cps.size(), 104u);
  // 52 periods out of 104 = 50% density > 5% -> should return baseSize (50)
  size_t result = calculateDynamicChunkSize(cps);
  EXPECT_EQ(result, 50u);
}

// ========================================================================
// Issue #346: CJK closing bracket consumption
// ========================================================================

TEST(SplitSentencesTest, CJKClosingBracket_BasicKakko) {
  auto result = splitTextToSentences(
      u8"「こんにちは。」次の文。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「こんにちは。」");
  EXPECT_EQ(result[1], u8"次の文。");
}

TEST(SplitSentencesTest, CJKClosingBracket_DoubleCornerBracket) {
  auto result = splitTextToSentences(
      u8"『素晴らしい！』感動した。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"『素晴らしい！』");
  EXPECT_EQ(result[1], u8"感動した。");
}

TEST(SplitSentencesTest, CJKClosingBracket_FullwidthParen) {
  auto result = splitTextToSentences(
      u8"結果は（成功です。）次へ。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"結果は（成功です。）");
  EXPECT_EQ(result[1], u8"次へ。");
}

TEST(SplitSentencesTest, CJKClosingBracket_Sumitsuki) {
  auto result = splitTextToSentences(
      u8"【テスト。】次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"【テスト。】");
  EXPECT_EQ(result[1], u8"次。");
}

TEST(SplitSentencesTest, CJKClosingBracket_HalfwidthKakko) {
  auto result = splitTextToSentences(
      u8"｢テスト。｣次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"｢テスト。｣");
  EXPECT_EQ(result[1], u8"次。");
}

TEST(SplitSentencesTest, CJKClosingBracket_MultipleBrackets) {
  auto result = splitTextToSentences(
      u8"「『OK。』」次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「『OK。』」");
  EXPECT_EQ(result[1], u8"次。");
}

TEST(SplitSentencesTest, WesternClosingQuote) {
  auto result = splitTextToSentences(
      "She said \"Hello.\" Then left.",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], "She said \"Hello.\"");
  EXPECT_EQ(result[1], " Then left.");
}

TEST(SplitSentencesTest, WesternClosingParen) {
  auto result = splitTextToSentences(
      "Result (ok.) Next.",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], "Result (ok.)");
  EXPECT_EQ(result[1], " Next.");
}

TEST(SplitSentencesTest, CJKClosingBracket_NoClosingNoop) {
  auto result = splitTextToSentences(
      u8"テスト。次のテスト。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"テスト。");
  EXPECT_EQ(result[1], u8"次のテスト。");
}

TEST(SplitSentencesTest, CJKClosingBracket_NoTerminatorNoop) {
  // 「テスト」 -- 」 の前に文末記号がないため分割しない
  auto result = splitTextToSentences(
      u8"「テスト」続き。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"「テスト」続き。");
}

TEST(SplitSentencesTest, CJKClosingBracket_ConsecutiveThree) {
  // 3 consecutive closing brackets: all consumed greedily
  auto result = splitTextToSentences(
      u8"テスト。」』）次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"テスト。」』）");
  EXPECT_EQ(result[1], u8"次。");
}

TEST(SplitSentencesTest, CJKClosingBracket_EndOfString) {
  // Text ends with closing bracket, no trailing text
  auto result = splitTextToSentences(
      u8"「テスト。」",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"「テスト。」");
}

TEST(SplitSentencesTest, CJKClosingBracket_FullwidthPeriod) {
  // U+FF0E (fullwidth full stop) as sentence terminator + closing bracket
  auto result = splitTextToSentences(
      u8"「テスト．」次。",
      MultilingualPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「テスト．」");
  EXPECT_EQ(result[1], u8"次。");
}

TEST(SplitSentencesTest, CJKClosingBracket_OpenJTalkMode) {
  // OpenJTalk mode: 。 is both boundary and terminator, bracket consumed
  auto result = splitTextToSentences(
      u8"「こんにちは。」次の文。",
      OpenJTalkPhonemes);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_EQ(result[0], u8"「こんにちは。」");
  EXPECT_EQ(result[1], u8"次の文。");
}

// ========================================================================
// The guard the replica had lost (issue #703).
//
// toCodepoints() uses utf8::unchecked, which walks off the end of malformed
// input. Production has guarded against that since #343 by validating first
// and handing the text back as a single chunk; the hand-written copy in this
// file had no such check, so the one input that can crash the real function
// was the one these tests could not reach.
// ========================================================================

TEST(SplitSentencesTest, InvalidUtf8IsReturnedAsOneChunkNotDecoded) {
  // 0xFF is not a legal UTF-8 lead byte anywhere.
  // The literal is split so `\xFE` cannot swallow the following `d` as a third
  // hex digit (\xFEd is out of range and does not compile).
  const std::string malformed = std::string("abc.\xFF\xFE" "def.");
  const auto result = splitTextToSentences(malformed, EnglishPhonemes);

  ASSERT_EQ(result.size(), 1u)
      << "malformed input was decoded instead of passed through";
  EXPECT_EQ(result[0], malformed);
}

TEST(SplitSentencesTest, InvalidUtf8CallbackFiresExactlyOnce) {
  int calls = 0;
  const std::string malformed = "a\xC3.";  // truncated 2-byte sequence
  const auto result = piper::splitTextToSentencesIn(
      malformed, piper::SentenceSplitMode::Ascii, 0, [&calls]() { ++calls; });

  EXPECT_EQ(calls, 1);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], malformed);
}

TEST(SplitSentencesTest, ValidUtf8DoesNotFireTheInvalidCallback) {
  // Anti-vacuity for the two cases above: a callback that fired on every
  // input would satisfy them while telling us nothing about validation.
  int calls = 0;
  const auto result = piper::splitTextToSentencesIn(
      u8"こんにちは。ありがとう。", piper::SentenceSplitMode::OpenJTalk, 0,
      [&calls]() { ++calls; });

  EXPECT_EQ(calls, 0);
  EXPECT_EQ(result.size(), 2u);
}

// A missing callback must not crash: piper.cpp always passes one, but the
// adapters in this file and any future caller may not.
TEST(SplitSentencesTest, InvalidUtf8WithNoCallbackStillPassesThrough) {
  const std::string malformed = "x\xF0\x9F.";  // truncated 4-byte sequence
  const auto result = piper::splitTextToSentencesIn(
      malformed, piper::SentenceSplitMode::Ascii);

  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], malformed);
}

// The ellipsis (U+2026) is a boundary in Multilingual mode but NOT a
// terminator, so it only splits once the chunk has outgrown dynamicChunkSize.
// Nothing tested it: dropping it from the boundary set passed all 44 cases
// above (measured). Note U+2026 is absent from isPunctCodepoint, so the
// density here is 0 and dynamicChunkSize is baseSize * 3 = 30.
TEST(SplitSentencesTest, MultilingualEllipsisSplitsAnOvergrownChunk) {
  const std::string text = std::string(40, 'a') + u8"…" + std::string(10, 'b');
  const auto result = splitTextToSentences(text, MultilingualPhonemes,
                                           /*maxChunkSize=*/10);

  ASSERT_EQ(result.size(), 2u)
      << "the ellipsis did not act as a boundary, so the 51-codepoint text "
         "never split";
  EXPECT_EQ(result[0], std::string(40, 'a') + u8"…");
  EXPECT_EQ(result[1], std::string(10, 'b'));
}

// Anti-vacuity for the case above: below the chunk-size threshold the same
// ellipsis must NOT split, which is what makes it a boundary rather than a
// terminator. A mutation that promoted it to terminator would pass the case
// above and fail this one.
TEST(SplitSentencesTest, MultilingualEllipsisAloneDoesNotSplit) {
  const auto result =
      splitTextToSentences(u8"hola…mundo", MultilingualPhonemes);

  ASSERT_EQ(result.size(), 1u);
  EXPECT_EQ(result[0], u8"hola…mundo");
}
