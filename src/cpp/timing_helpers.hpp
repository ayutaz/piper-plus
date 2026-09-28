// Phoneme timing cursor walk, shared by src/cpp/piper.cpp and
// src/cpp/tests/test_phoneme_timing_parity.cpp.
//
// This lived inside piper.cpp, whose translation unit pulls in onnxruntime via
// piper.hpp. Linking it from a test therefore meant linking ORT, so
// test_phoneme_timing_parity.cpp took the other route and re-implemented the
// spec algorithm in its own file -- it said so in a comment:
//
//     To stay self-contained (no onnxruntime/espeak link), this test
//     re-implements the spec algorithm
//
// Every other runtime's parity test calls its production function (Python
// durations_to_timing, Rust durations_to_timing, Go DurationsToTiming, JS
// durationsToTiming, C# TimingWriter.CalculateTiming). C++ was the only one
// checking a copy, so the C++ column of the cross-runtime parity matrix
// asserted nothing about shipped behaviour. A change to piper.cpp's cursor
// walk -- or a failure to make one, which is what issue #653 is -- could not
// be detected here.
//
// Extracting it makes the existing parity fixture test the real thing. The
// header depends only on phoneme_ids.hpp (which is ORT-free) plus the standard
// library, so the test links no model runtime.
//
// The PUA display table and the two UTF-8 helpers come along because the walk
// resolves phoneme names as it goes; they are the same definitions piper.cpp
// used, moved rather than copied.

#ifndef PIPER_PLUS_TIMING_HELPERS_HPP
#define PIPER_PLUS_TIMING_HELPERS_HPP

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "phoneme_ids.hpp"
#include "utf8.h"

namespace piper {

// One phoneme's span. Times are seconds, frames are hop-sized indices.
//
// The fields are float because piper.hpp's PhonemeInfo is float and this
// struct has to stay layout-compatible with it: PhonemeInfo is reachable from
// SynthesisResult, which the shared library exports, and widening it would
// change the struct layout that the `ABI diff (libpiper_plus.so head vs base)`
// gate compares via abi-dumper's DWARF records.
//
// The ACCUMULATOR is double regardless (see computePhonemeTimings). Only the
// per-entry store rounds to float, so the error is one rounding per entry
// instead of one per entry compounded across the whole utterance.
struct TimingEntry {
  std::string phoneme;
  float start_time = 0.0f;
  float end_time = 0.0f;
  int start_frame = 0;
  int end_frame = 0;
};

// Fallback display for an id with no entry in the model's phoneme_id_map.
inline const std::string kUnknownPhoneme = "?";

// Fraction of a geminate's own span that bleeds into the preceding phoneme.
inline constexpr double kJapaneseClOverlapRatio = 0.3;

// PUA to multi-char phoneme mapping for display.
inline const std::unordered_map<char32_t, std::string> &puaToPhonemeMap() {
  static const std::unordered_map<char32_t, std::string> kMap = {
      {0xE000, "a:"},  {0xE001, "i:"},  {0xE002, "u:"},  {0xE003, "e:"},
      {0xE004, "o:"},  {0xE005, "cl"},  {0xE006, "ky"},  {0xE007, "kw"},
      {0xE008, "gy"},  {0xE009, "gw"},  {0xE00A, "ty"},  {0xE00B, "dy"},
      {0xE00C, "py"},  {0xE00D, "by"},  {0xE00E, "ch"},  {0xE00F, "ts"},
      {0xE010, "sh"},  {0xE011, "zy"},  {0xE012, "hy"},  {0xE013, "ny"},
      {0xE014, "my"},  {0xE015, "ry"},
      // Question type markers (Issue #204)
      {0xE016, "?!"},  {0xE017, "?."},  {0xE018, "?~"},
      // N phoneme variants (Issue #207)
      {0xE019, "N_m"}, {0xE01A, "N_n"}, {0xE01B, "N_ng"}, {0xE01C, "N_uvular"},
      // Multilingual phoneme tokens
      {0xE01D, "rr"},  {0xE01E, "y_vowel"}};
  return kMap;
}

// True if the string is a single UTF-8 codepoint.
inline bool isSingleCodepointUtf8(const std::string &s) {
  return utf8::distance(s.begin(), s.end()) == 1;
}

// First UTF-8 codepoint of a string. Undefined for an empty string.
inline char32_t firstCodepointUtf8(const std::string &s) {
  utf8::iterator<std::string::const_iterator> it(s.begin(), s.begin(), s.end());
  return static_cast<char32_t>(*it);
}

// Build "phoneme id -> display string" from the model's phoneme_id_map.
//
// NOTE: only ids[0] of each key is registered, so a phoneme mapped to several
// ids resolves for its first id and falls back to "?" for the rest. That is
// the behaviour piper.cpp shipped; the same defect was fixed in C# under
// issue #656 and is tracked for C++ separately rather than being changed here
// under cover of an extraction.
inline std::unordered_map<PhonemeId, std::string>
buildPhonemeIdToStringMap(const PhonemeIdMap &idMap) {
  std::unordered_map<PhonemeId, std::string> out;
  for (const auto &[phonemeChar, ids] : idMap) {
    if (ids.empty()) {
      continue;
    }
    std::string phonemeUtf8;
    utf8::append(static_cast<uint32_t>(phonemeChar),
                 std::back_inserter(phonemeUtf8));
    out[ids[0]] = std::move(phonemeUtf8);
  }
  return out;
}

// PUA display rename + geminate overlap. Split out so a test can drive it
// directly instead of having to construct an OpenJTalk voice.
inline void applyJapanesePhonemeAdjustments(std::vector<TimingEntry> &timings) {
  const auto &pua = puaToPhonemeMap();
  for (std::size_t i = 0; i < timings.size(); ++i) {
    // Convert PUA mapped phonemes back to original.
    if (isSingleCodepointUtf8(timings[i].phoneme)) {
      auto it = pua.find(firstCodepointUtf8(timings[i].phoneme));
      if (it != pua.end()) {
        timings[i].phoneme = it->second;
      }
    }

    // 促音 (geminate) overlaps backwards into the previous phoneme.
    if (timings[i].phoneme == "cl" && i > 0) {
      const double overlap =
          (static_cast<double>(timings[i].end_time) - timings[i].start_time) *
          kJapaneseClOverlapRatio;
      timings[i - 1].end_time =
          static_cast<float>(timings[i - 1].end_time + overlap);
      timings[i].start_time = static_cast<float>(timings[i].start_time + overlap);
    }
  }
}

// Walk the durations, emitting one entry per non-special phoneme.
//
// PAD (0), BOS (1) and EOS (2) advance the cursor without producing an entry,
// per docs/spec/phoneme-timing-contract.toml [concatenation]
// forbidden_offset_sources: "the cursor walk advances over pad/bos/eos ids
// without emitting entries for them".
//
// `durations` are frame counts straight from the ONNX `durations` output.
// They are pre-`torch.ceil`, while the decoder allocates `ceil(d_i)` frames to
// phoneme i -- that discrepancy is issue #653 and is NOT addressed here; this
// extraction deliberately preserves the current arithmetic so the parity
// fixture keeps its present values and the change that fixes #653 shows up as
// a fixture diff rather than being folded into a refactor.
//
// `applyJapaneseAdjustments` controls the PUA rename + geminate overlap pass,
// which piper.cpp runs only for OpenJTalk phoneme types.
inline std::vector<TimingEntry> computePhonemeTimings(
    const std::vector<float> &durations,
    const std::vector<PhonemeId> &phonemeIds, const PhonemeIdMap &idMap,
    int hopSize, int sampleRate, bool applyJapaneseAdjustments) {
  std::vector<TimingEntry> timings;
  if (sampleRate <= 0 || hopSize <= 0) {
    return timings;
  }

  const std::unordered_map<PhonemeId, std::string> idToString =
      buildPhonemeIdToStringMap(idMap);

  // double accumulator, float storage -- see the TimingEntry comment.
  const double frameLength =
      static_cast<double>(hopSize) / static_cast<double>(sampleRate);
  double currentTime = 0.0;
  long long currentFrame = 0;

  const std::size_t n = std::min(phonemeIds.size(), durations.size());
  for (std::size_t i = 0; i < n; ++i) {
    const PhonemeId id = phonemeIds[i];
    const double duration = static_cast<double>(durations[i]);

    // Skip special tokens (PAD, BOS, EOS): advance the cursor only.
    if (id == 0 || id == 1 || id == 2) {
      currentFrame += static_cast<long long>(duration);
      currentTime += duration * frameLength;
      continue;
    }

    std::string phonemeStr = kUnknownPhoneme;
    auto it = idToString.find(id);
    if (it != idToString.end()) {
      phonemeStr = it->second;
    } else if (id > 2 && id < 128) {
      // Printable ASCII ids double as their own character.
      phonemeStr = std::string(1, static_cast<char>(id));
    }

    TimingEntry info;
    info.phoneme = std::move(phonemeStr);
    info.start_time = static_cast<float>(currentTime);
    info.start_frame = static_cast<int>(currentFrame);

    currentFrame += static_cast<long long>(duration);
    currentTime += duration * frameLength;

    info.end_time = static_cast<float>(currentTime);
    info.end_frame = static_cast<int>(currentFrame);

    timings.push_back(std::move(info));
  }

  if (applyJapaneseAdjustments) {
    applyJapanesePhonemeAdjustments(timings);
  }

  return timings;
}

}  // namespace piper

#endif  // PIPER_PLUS_TIMING_HELPERS_HPP
