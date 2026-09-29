// Sentence splitting, shared by src/cpp/piper.cpp and
// src/cpp/tests/test_split_sentences.cpp.
//
// `isPunctCodepoint`, `calculateDynamicChunkSize` and `isClosingPunctuation`
// were `static` in piper.cpp -- internal linkage, so no test could reach them
// -- and `splitTextToSentences` was reachable in principle but only from a
// translation unit that links onnxruntime. test_split_sentences.cpp therefore
// carried hand-written copies of all four and said so:
//
//     // These tests mirror the algorithm in piper.cpp but are self-contained
//     // ---- Mirror of piper.cpp isPunctCodepoint ----
//     // ---- Mirror of piper.cpp calculateDynamicChunkSize ----
//     // ---- Mirror of piper.cpp isClosingPunctuation ----
//     // ---- Mirror of piper.cpp splitTextToSentences ----
//
// Its ~70 assertions ran against those copies. A mirror cannot catch drift in
// the thing it mirrors, and this one had already lost a guard: production
// rejects invalid UTF-8 up front (`utf8::is_valid`, because `toCodepoints`
// uses `utf8::unchecked` and walks off the end otherwise), and the replica
// had no such check -- so the one input that can crash the real function was
// the one the tests could not reach (issue #703).
//
// `SentenceSplitMode` exists because `PhonemeType` cannot express what this
// algorithm switches on. `usesOpenJTalk` is true for BOTH of its values, so
// production can never take the ASCII branch, and the replica had to invent
// `EnglishPhonemes = 99` to test it. The mode enum names the three branches
// directly; piper.cpp maps PhonemeType onto it with exactly the behaviour it
// had before (see phonemeTypeToSplitMode).
//
// Warnings are delivered through a callback rather than spdlog so this header
// stays dependency-free; piper.cpp passes a lambda that calls spdlog::warn.
//
// Depends only on utf8_utils.hpp / utf8.h and the standard library, so the
// test links neither onnxruntime nor spdlog.

#ifndef PIPER_PLUS_SENTENCE_SPLIT_HPP
#define PIPER_PLUS_SENTENCE_SPLIT_HPP

#include <cstddef>
#include <functional>
#include <string>
#include <vector>

#include "utf8.h"
#include "utf8_utils.hpp"

namespace piper {

// Which punctuation set delimits a sentence. See the header comment for why
// this is not PhonemeType.
enum class SentenceSplitMode {
  Multilingual,  // CJK fullwidth + ASCII sentence-end + ellipsis
  OpenJTalk,     // fullwidth sentence-end + ideographic comma
  Ascii          // ASCII . ! ? , ; :  -- unreachable from PhonemeType today
};

// Punctuation counted when measuring density. Deliberately broader than the
// boundary sets: it is a "how punctuated is this text" estimate, not a
// boundary test, so it spans every mode.
inline bool isPunctCodepoint(char32_t c) {
  switch (c) {
    case U'。':  // 。
    case U'、':  // 、
    case U'！':  // ！
    case U'？':  // ？
    case U'.':
    case U'!':
    case U'?':
    case U',':
    case U';':
    case U':':
      return true;
    default:
      return false;
  }
}

// Chunk size from text characteristics, in CODEPOINTS (not bytes) so CJK is
// measured the same as Latin.
inline std::size_t calculateDynamicChunkSize(const std::vector<char32_t> &cps,
                                             std::size_t baseSize = 50) {
  const std::size_t cpLen = cps.size();

  // Short texts should not be chunked at all.
  if (cpLen < baseSize * 2) {
    return cpLen;
  }

  std::size_t punctCount = 0;
  for (const char32_t c : cps) {
    if (isPunctCodepoint(c)) {
      ++punctCount;
    }
  }

  const float punctDensity =
      static_cast<float>(punctCount) / static_cast<float>(cpLen);
  if (punctDensity > 0.05f) {  // heavily punctuated -> smaller chunks
    return baseSize;
  }
  if (punctDensity < 0.02f) {  // sparsely punctuated -> larger chunks
    return baseSize * 3;
  }
  return baseSize * 2;
}

// Closing brackets and quotes consumed after a sentence terminator, so
// 「こんにちは。」 stays in one chunk (issue #346, matches Rust/C#).
//
// 14 codepoints: the all-runtime superset covering the 8 supported languages,
// canonically defined in docs/spec/text-splitter-contract.toml. U+0022 and
// U+0027 are ambiguous (they open as well as close) but safe here, because
// this is only consulted after a terminator has been seen.
inline bool isClosingPunctuation(char32_t c) {
  switch (c) {
    case U')':       // U+0029  Right Parenthesis
    case U']':       // U+005D  Right Square Bracket
    case U'}':       // U+007D  Right Curly Bracket
    case U'"':       // U+0022  Quotation Mark
    case U'\'':      // U+0027  Apostrophe
    case U'」':  // 」 Right Corner Bracket
    case U'』':  // 』 Right White Corner Bracket
    case U'）':  // ） Fullwidth Right Parenthesis
    case U'］':  // ］ Fullwidth Right Square Bracket
    case U'】':  // 】 Right Black Lenticular Bracket
    case U'｣':  // ｣  Halfwidth Right Corner Bracket
    case U'”':  // "  Right Double Quotation Mark
    case U'’':  // '  Right Single Quotation Mark
    case U'»':  // »  Right-Pointing Double Angle Quotation Mark
      return true;
    default:
      return false;
  }
}

// A codepoint that ends a chunk when the chunk also grows too long.
inline bool isBoundaryPunct(char32_t c, SentenceSplitMode mode) {
  switch (mode) {
    case SentenceSplitMode::Multilingual:
      return c == U'。' || c == U'！' || c == U'？' ||
             c == U'．' || c == U'.' || c == U'!' || c == U'?' ||
             c == U'…';  // …
    case SentenceSplitMode::OpenJTalk:
      return c == U'。' || c == U'！' || c == U'？' ||
             c == U'、';  // 、
    case SentenceSplitMode::Ascii:
      return c == U'.' || c == U'!' || c == U'?' || c == U',' || c == U';' ||
             c == U':';
  }
  return false;
}

// A codepoint that ends a chunk immediately, regardless of length.
// For Japanese, 、 is a boundary but NOT a terminator.
inline bool isSentenceTerminator(char32_t c, SentenceSplitMode mode) {
  switch (mode) {
    case SentenceSplitMode::Multilingual:
      return c == U'。' || c == U'！' || c == U'？' ||
             c == U'．' || c == U'.' || c == U'!' || c == U'?';
    case SentenceSplitMode::OpenJTalk:
      return c == U'。' || c == U'！' || c == U'？';
    case SentenceSplitMode::Ascii:
      return c == U'.' || c == U'!' || c == U'?';
  }
  return false;
}

// Split text into sentences at natural boundaries. Iterates codepoints via
// utf8_utils so multibyte UTF-8 (CJK punctuation, etc.) is handled correctly
// (issue #343).
//
// `onInvalidUtf8` is invoked, when set, before returning the input unchanged:
// toCodepoints uses utf8::unchecked and requires well-formed input, so the
// only safe response is to hand the text back as a single chunk.
inline std::vector<std::string> splitTextToSentencesIn(
    const std::string &text, SentenceSplitMode mode,
    std::size_t maxChunkSize = 0,
    const std::function<void()> &onInvalidUtf8 = nullptr) {
  if (text.empty()) {
    return {};
  }

  if (!utf8::is_valid(text.begin(), text.end())) {
    if (onInvalidUtf8) {
      onInvalidUtf8();
    }
    return {text};
  }

  using utf8_util::cpsToUtf8;
  using utf8_util::toCodepoints;

  const std::vector<char32_t> cps = toCodepoints(text);
  const std::size_t cpLen = cps.size();

  const std::size_t baseSize = maxChunkSize > 0 ? maxChunkSize : 50;
  const std::size_t dynamicChunkSize = calculateDynamicChunkSize(cps, baseSize);

  std::vector<std::string> chunks;
  std::size_t sentenceStart = 0;

  for (std::size_t i = 0; i < cpLen; ++i) {
    if (!isBoundaryPunct(cps[i], mode)) {
      continue;
    }

    // Consume the entire run of boundary punctuation.
    bool hasTerminator = isSentenceTerminator(cps[i], mode);
    std::size_t punctEnd = i + 1;
    while (punctEnd < cpLen && isBoundaryPunct(cps[punctEnd], mode)) {
      if (isSentenceTerminator(cps[punctEnd], mode)) {
        hasTerminator = true;
      }
      ++punctEnd;
    }
    if (hasTerminator) {
      while (punctEnd < cpLen && isClosingPunctuation(cps[punctEnd])) {
        ++punctEnd;
      }
    }
    i = punctEnd - 1;  // the for-loop's ++ lands just past the run

    const std::size_t chunkLen = punctEnd - sentenceStart;
    if (hasTerminator || chunkLen > dynamicChunkSize) {
      std::string chunk = cpsToUtf8(cps, sentenceStart, chunkLen);
      if (!chunk.empty()) {
        chunks.push_back(std::move(chunk));
      }
      sentenceStart = punctEnd;
    }
  }

  if (sentenceStart < cpLen) {
    std::string remaining =
        cpsToUtf8(cps, sentenceStart, cpLen - sentenceStart);
    if (!remaining.empty()) {
      chunks.push_back(std::move(remaining));
    }
  }

  return chunks;
}

}  // namespace piper

#endif  // PIPER_PLUS_SENTENCE_SPLIT_HPP
