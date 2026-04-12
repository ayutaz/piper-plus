// Comprehensive unit tests for splitTextToSentences() codepoint-based
// implementation (Issue #343 fix).
//
// These tests mirror the algorithm in piper.cpp but are self-contained
// (no ONNX Runtime dependency). The integration path is covered by
// test_streaming.cpp which calls textToAudioStreaming() -> splitTextToSentences().

#include <gtest/gtest.h>
#include <string>
#include <vector>
#include <cstdint>
#include <functional>

#include "utf8_utils.hpp"

// Local copies of PhonemeType / usesOpenJTalk to avoid pulling in piper.hpp
// (which requires onnxruntime_cxx_api.h).
namespace {

enum TestPhonemeType {
  OpenJTalkPhonemes = 0,
  MultilingualPhonemes = 1,
  // Synthetic value for English-only tests
  EnglishPhonemes = 99,
};

bool usesOpenJTalk(TestPhonemeType type) {
  return type == OpenJTalkPhonemes || type == MultilingualPhonemes;
}

// ---- Mirror of piper.cpp isPunctCodepoint ----
bool isPunctCodepoint(char32_t c) {
  switch (c) {
    case U'\u3002': case U'\u3001': case U'\uFF01': case U'\uFF1F':
    case U'.': case U'!': case U'?': case U',': case U';': case U':':
      return true;
    default:
      return false;
  }
}

// ---- Mirror of piper.cpp calculateDynamicChunkSize ----
size_t calculateDynamicChunkSize(const std::vector<char32_t>& cps,
                                  size_t baseSize = 50) {
  size_t cpLen = cps.size();
  if (cpLen < baseSize * 2) return cpLen;
  size_t punctCount = 0;
  for (char32_t c : cps) {
    if (isPunctCodepoint(c)) punctCount++;
  }
  float punctDensity = static_cast<float>(punctCount) / static_cast<float>(cpLen);
  if (punctDensity > 0.05f) return baseSize;
  if (punctDensity < 0.02f) return baseSize * 3;
  return baseSize * 2;
}

// ---- Mirror of piper.cpp isClosingPunctuation (Issue #346, M1) ----
bool isClosingPunctuation(char32_t c) {
  switch (c) {
    case U')': case U']': case U'}': case U'"': case U'\'':
    case U'\u300D': // 」 Right Corner Bracket
    case U'\u300F': // 』 Right White Corner Bracket
    case U'\uFF09': // ） Fullwidth Right Parenthesis
    case U'\uFF3D': // ］ Fullwidth Right Square Bracket
    case U'\u3011': // 】 Right Black Lenticular Bracket
    case U'\uFF63': // ｣  Halfwidth Right Corner Bracket
    case U'\u201D': // "  Right Double Quotation Mark
    case U'\u2019': // '  Right Single Quotation Mark
    case U'\u00BB': // »  Right-Pointing Double Angle Quotation Mark
      return true;
    default:
      return false;
  }
}

// ---- Mirror of piper.cpp splitTextToSentences ----
std::vector<std::string> splitTextToSentences(
    const std::string &text,
    TestPhonemeType phonemeType,
    size_t maxChunkSize = 0) {

  if (text.empty()) return {};

  using piper::utf8_util::toCodepoints;
  using piper::utf8_util::cpsToUtf8;

  auto cps = toCodepoints(text);
  size_t cpLen = cps.size();

  size_t baseSize = maxChunkSize > 0 ? maxChunkSize : 50;
  size_t dynamicChunkSize = calculateDynamicChunkSize(cps, baseSize);

  auto isBoundaryPunct = [&](char32_t c) -> bool {
    if (phonemeType == MultilingualPhonemes) {
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\uFF0E' || c == U'.' || c == U'!' || c == U'?' ||
             c == U'\u2026';
    } else if (usesOpenJTalk(phonemeType)) {
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\u3001';
    } else {
      return c == U'.' || c == U'!' || c == U'?' || c == U',' ||
             c == U';' || c == U':';
    }
  };

  auto isSentenceTerminator = [&](char32_t c) -> bool {
    if (phonemeType == MultilingualPhonemes) {
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F' ||
             c == U'\uFF0E' || c == U'.' || c == U'!' || c == U'?';
    } else if (usesOpenJTalk(phonemeType)) {
      return c == U'\u3002' || c == U'\uFF01' || c == U'\uFF1F';
    } else {
      return c == U'.' || c == U'!' || c == U'?';
    }
  };

  std::vector<std::string> chunks;
  size_t sentenceStart = 0;

  for (size_t i = 0; i < cpLen; ++i) {
    char32_t c = cps[i];
    if (isBoundaryPunct(c)) {
      bool hasTerminator = isSentenceTerminator(c);
      size_t punctEnd = i + 1;
      while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd])) {
        if (isSentenceTerminator(cps[punctEnd])) hasTerminator = true;
        punctEnd++;
      }
      // Issue #346: Consume closing brackets/quotes after sentence terminator
      if (hasTerminator) {
        while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
          punctEnd++;
        }
      }
      i = punctEnd - 1;
      size_t chunkLen = punctEnd - sentenceStart;
      if (hasTerminator || chunkLen > dynamicChunkSize) {
        std::string chunk = cpsToUtf8(cps, sentenceStart, chunkLen);
        if (!chunk.empty()) chunks.push_back(chunk);
        sentenceStart = punctEnd;
      }
    }
  }

  if (sentenceStart < cpLen) {
    std::string remaining = cpsToUtf8(cps, sentenceStart, cpLen - sentenceStart);
    if (!remaining.empty()) chunks.push_back(remaining);
  }

  return chunks;
}

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
