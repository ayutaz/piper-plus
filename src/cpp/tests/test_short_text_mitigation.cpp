/**
 * Tests for short-text synthesis mitigation (Strategy A + B).
 *
 * Strategy A: Silence padding + post-trim
 * Strategy B: Dynamic scales adjustment
 *
 * These tests verify the helper logic without requiring an ONNX model.
 *
 * NOTE ON THE REPLICAS BELOW. The trim helpers in this file are hand-copies of
 * the `static` originals in src/cpp/piper.cpp, kept here so the arithmetic can
 * be tested without linking onnxruntime. They are pinned to the SINGLE-UNIT
 * behaviour only: production now takes a `baseOffset` and operates on
 * [baseOffset, size) so it cannot trim audio belonging to units the caller
 * already received (issue #655). The copies here are exercised with
 * baseOffset == 0 semantics, where the two are exactly equivalent -- verified
 * by exhaustive comparison of the old and new implementations over 67,820
 * parameter combinations.
 *
 * Consequences to be aware of:
 *   - DO NOT copy these back into piper.cpp: they are the pre-#655 shape.
 *   - The baseOffset != 0 paths are covered only by
 *     src/cpp/tests/test_synthesize_append_scope.cpp, which drives the real
 *     helpers through phonemesToAudio and needs the fixture model.
 *   - No gate compares this file against piper.cpp
 *     (`scripts/check_short_text_contract.py` checks only the numeric
 *     constants in the Python sources), so drift here is silent.
 */

#include <gtest/gtest.h>

#include "../trim_helpers.hpp"

using piper::padPhonemeIds;
using piper::PhonemeId;
using piper::trimEosRegion;
using piper::trimEosRegionFloat;
using piper::trimPaddingByDurations;
using piper::trimPaddingByDurationsFloat;
using piper::trimSilenceFloat;
using piper::trimSilenceInt16;
using piper::MIN_BODY_FOR_STRATEGY_A;
using piper::MIN_PHONEME_IDS;
using piper::TRIM_EOS_MAX_FRAMES;
using piper::TRIM_MIN_SAMPLES;
using piper::TRIM_THRESHOLD_RMS;
using piper::TRIM_WINDOW_SIZE;
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

// ---------------------------------------------------------------------------
// The trim helpers under test are the PRODUCTION ones, included from
// src/cpp/trim_helpers.hpp. They used to be hand-written copies here, which
// meant the absolute-sample-count assertions below tested the copies and not
// piper.cpp: five trim-boundary mutations in the real code (front erase off by
// one, back erase off by one, the float variant, an inverted erase order, and
// an extra sample off the EOS tail) passed every suite in the repository.
//
// padPhonemeIds moved to the same header, so its 12 cases below now also test
// the production implementation rather than a copy.
// ---------------------------------------------------------------------------



// ======================================================================
// Strategy A: padPhonemeIds tests
// ======================================================================

class PadPhonemeIdsTest : public ::testing::Test {};

TEST_F(PadPhonemeIdsTest, NoOpWhenAlreadyLongEnough) {
  // BOS + (MIN_PHONEME_IDS - 2) body + EOS = MIN_PHONEME_IDS elements
  std::vector<PhonemeId> ids;
  ids.push_back(1);  // BOS
  for (int i = 0; i < MIN_PHONEME_IDS - 2; i++) ids.push_back(10 + i);
  ids.push_back(2);  // EOS
  ASSERT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);

  bool padded = padPhonemeIds(ids);
  EXPECT_FALSE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, NoOpWhenLongerThanMinimum) {
  std::vector<PhonemeId> ids;
  ids.push_back(1);
  for (int i = 0; i < 50; i++) ids.push_back(10);
  ids.push_back(2);
  ASSERT_EQ(ids.size(), 52u);

  bool padded = padPhonemeIds(ids);
  EXPECT_FALSE(padded);
  EXPECT_EQ(ids.size(), 52u);
}

TEST_F(PadPhonemeIdsTest, PadsShortSequenceToMinLength) {
  // BOS + 5 body + EOS = 7 elements (body=5 >= MIN_BODY_FOR_STRATEGY_A).
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 13, 14, 2};
  ASSERT_EQ(ids.size(), 7u);

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, PreservesBosAndEos) {
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 2};

  padPhonemeIds(ids);
  EXPECT_EQ(ids.front(), 1);  // BOS preserved
  EXPECT_EQ(ids.back(), 2);   // EOS preserved
}

TEST_F(PadPhonemeIdsTest, BodyPreservedInOrder) {
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 13, 14, 2};
  std::vector<PhonemeId> originalBody = {10, 11, 12, 13, 14};

  padPhonemeIds(ids);

  // Extract non-zero, non-BOS, non-EOS elements
  std::vector<PhonemeId> body;
  for (size_t i = 1; i < ids.size() - 1; i++) {
    if (ids[i] != 0) {
      body.push_back(ids[i]);
    }
  }
  EXPECT_EQ(body, originalBody);
}

TEST_F(PadPhonemeIdsTest, PadTokensArePauseId) {
  // body must be >= MIN_BODY_FOR_STRATEGY_A so Strategy A applies.
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 2};

  padPhonemeIds(ids, /*padId=*/0);

  // Count pad tokens (0) between BOS and EOS
  int padCount = 0;
  for (size_t i = 1; i < ids.size() - 1; i++) {
    if (ids[i] == 0) padCount++;
  }
  EXPECT_GT(padCount, 0);
}

TEST_F(PadPhonemeIdsTest, FrontBackSplitIsBalanced) {
  // body=3 (== MIN_BODY_FOR_STRATEGY_A): Strategy A applies.
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 2};
  padPhonemeIds(ids);

  // Find where body starts (first non-zero after BOS)
  int frontPads = 0;
  for (size_t i = 1; i < ids.size(); i++) {
    if (ids[i] == 0) frontPads++;
    else break;
  }

  // Find where body ends (last non-zero before EOS)
  int backPads = 0;
  for (int i = static_cast<int>(ids.size()) - 2; i >= 0; i--) {
    if (ids[i] == 0) backPads++;
    else break;
  }

  // front = needed/2, back = needed - front; difference <= 1
  EXPECT_LE(std::abs(frontPads - backPads), 1);
}

TEST_F(PadPhonemeIdsTest, DegenerateSingleElement) {
  // body would be -1: Strategy A is skipped.
  std::vector<PhonemeId> ids = {42};
  std::vector<PhonemeId> original = ids;

  bool padded = padPhonemeIds(ids);
  EXPECT_FALSE(padded);
  EXPECT_EQ(ids, original);
}

TEST_F(PadPhonemeIdsTest, DegenerateEmpty) {
  std::vector<PhonemeId> ids;

  bool padded = padPhonemeIds(ids);
  EXPECT_FALSE(padded);
  EXPECT_TRUE(ids.empty());
}

TEST_F(PadPhonemeIdsTest, SkipsWhenBodyTooShort) {
  // body=0 (just BOS+EOS): Strategy A skipped (issue #356).
  {
    std::vector<PhonemeId> ids = {1, 2};
    std::vector<PhonemeId> original = ids;
    bool padded = padPhonemeIds(ids);
    EXPECT_FALSE(padded);
    EXPECT_EQ(ids, original);
  }
  // body=1
  {
    std::vector<PhonemeId> ids = {1, 10, 2};
    std::vector<PhonemeId> original = ids;
    bool padded = padPhonemeIds(ids);
    EXPECT_FALSE(padded);
    EXPECT_EQ(ids, original);
  }
  // body=2 (e.g. 「あ。」)
  {
    std::vector<PhonemeId> ids = {1, 10, 11, 2};
    std::vector<PhonemeId> original = ids;
    bool padded = padPhonemeIds(ids);
    EXPECT_FALSE(padded);
    EXPECT_EQ(ids, original);
  }
}

TEST_F(PadPhonemeIdsTest, BoundaryExactlyMinMinus1) {
  // MIN_PHONEME_IDS - 1 elements -> needs exactly 1 pad
  std::vector<PhonemeId> ids;
  ids.push_back(1);
  for (int i = 0; i < MIN_PHONEME_IDS - 3; i++) ids.push_back(10);
  ids.push_back(2);
  ASSERT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS - 1);

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, CustomPadId) {
  // body must be >= MIN_BODY_FOR_STRATEGY_A.
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 2};

  padPhonemeIds(ids, /*padId=*/99);

  int customPadCount = 0;
  for (size_t i = 1; i < ids.size() - 1; i++) {
    if (ids[i] == 99) customPadCount++;
  }
  EXPECT_GT(customPadCount, 0);
}

// ======================================================================
// Strategy A: trimSilenceInt16 tests
// ======================================================================

class TrimSilenceInt16Test : public ::testing::Test {};

TEST_F(TrimSilenceInt16Test, NoOpWhenShorterThanMinSamples) {
  std::vector<int16_t> audio(TRIM_MIN_SAMPLES - 1, 100);

  size_t original = audio.size();
  trimSilenceInt16(audio);
  EXPECT_EQ(audio.size(), original);
}

TEST_F(TrimSilenceInt16Test, NoOpWhenExactlyMinSamples) {
  std::vector<int16_t> audio(TRIM_MIN_SAMPLES, 100);

  size_t original = audio.size();
  trimSilenceInt16(audio);
  EXPECT_EQ(audio.size(), original);
}

TEST_F(TrimSilenceInt16Test, TrimsLeadingSilence) {
  // 3 windows of silence + 4 windows of audio + 3 windows of silence = 10
  // totalSamples = 10 * 256 = 2560 > TRIM_MIN_SAMPLES (2205)
  const int totalSamples = 10 * TRIM_WINDOW_SIZE;
  std::vector<int16_t> audio(totalSamples, 0);

  // Fill windows 3-6 with loud audio
  for (int i = 3 * TRIM_WINDOW_SIZE; i < 7 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 10000;
  }

  trimSilenceInt16(audio);

  // Result should be shorter than original
  EXPECT_LT(static_cast<int>(audio.size()), totalSamples);
  // Result should start around window 3 and end around window 7
  EXPECT_GE(static_cast<int>(audio.size()), 4 * TRIM_WINDOW_SIZE);
}

TEST_F(TrimSilenceInt16Test, AllSilenceKeepsMinSamples) {
  std::vector<int16_t> audio(5000, 0);  // All zeros, > TRIM_MIN_SAMPLES

  trimSilenceInt16(audio);
  EXPECT_EQ(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
}

TEST_F(TrimSilenceInt16Test, NoSilenceKeepsAll) {
  // All windows above threshold
  // totalSamples = 10 * 256 = 2560 > TRIM_MIN_SAMPLES (2205)
  const int totalSamples = 10 * TRIM_WINDOW_SIZE;
  std::vector<int16_t> audio(totalSamples, 5000);

  trimSilenceInt16(audio);

  // Should keep everything (all windows have audio)
  EXPECT_EQ(static_cast<int>(audio.size()), totalSamples);
}

TEST_F(TrimSilenceInt16Test, ShortAudioRegionExpandedToMinSamples) {
  // 10 windows of silence, 1 window of audio, 10 windows of silence
  const int totalSamples = 21 * TRIM_WINDOW_SIZE;
  std::vector<int16_t> audio(totalSamples, 0);

  // Only 1 window of audio -- shorter than TRIM_MIN_SAMPLES
  for (int i = 10 * TRIM_WINDOW_SIZE; i < 11 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 8000;
  }

  trimSilenceInt16(audio);

  // Should be at least TRIM_MIN_SAMPLES
  EXPECT_GE(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
}

// ======================================================================
// Strategy A: trimSilenceFloat tests
// ======================================================================

class TrimSilenceFloatTest : public ::testing::Test {};

TEST_F(TrimSilenceFloatTest, NoOpWhenShorterThanMinSamples) {
  std::vector<float> audio(TRIM_MIN_SAMPLES - 1, 0.5f);

  size_t original = audio.size();
  trimSilenceFloat(audio);
  EXPECT_EQ(audio.size(), original);
}

TEST_F(TrimSilenceFloatTest, TrimsLeadingSilence) {
  // 3 windows of silence + 4 windows of audio + 3 windows of silence = 10
  // totalSamples = 10 * 256 = 2560 > TRIM_MIN_SAMPLES (2205)
  const int totalSamples = 10 * TRIM_WINDOW_SIZE;
  std::vector<float> audio(totalSamples, 0.0f);

  // Fill windows 3-6 with loud audio
  for (int i = 3 * TRIM_WINDOW_SIZE; i < 7 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 0.5f;
  }

  trimSilenceFloat(audio);

  EXPECT_LT(static_cast<int>(audio.size()), totalSamples);
  EXPECT_GE(static_cast<int>(audio.size()), 4 * TRIM_WINDOW_SIZE);
}

TEST_F(TrimSilenceFloatTest, AllSilenceKeepsMinSamples) {
  std::vector<float> audio(5000, 0.0f);

  trimSilenceFloat(audio);
  EXPECT_EQ(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
}

TEST_F(TrimSilenceFloatTest, NoSilenceKeepsAll) {
  // totalSamples = 10 * 256 = 2560 > TRIM_MIN_SAMPLES (2205)
  const int totalSamples = 10 * TRIM_WINDOW_SIZE;
  std::vector<float> audio(totalSamples, 0.5f);

  trimSilenceFloat(audio);
  EXPECT_EQ(static_cast<int>(audio.size()), totalSamples);
}

// ======================================================================
// Strategy B: Dynamic Scales Adjustment tests
// ======================================================================

class DynamicScalesTest : public ::testing::Test {};

TEST_F(DynamicScalesTest, NoAdjustmentForLongInput) {
  const int len = MIN_PHONEME_IDS + 10;
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  // No adjustment when len >= MIN_PHONEME_IDS
  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  // ratio > 1.0 gets clamped to 1.0
  EXPECT_FLOAT_EQ(ratio, 1.0f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale);
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW);
}

TEST_F(DynamicScalesTest, AdjustsForShortInput) {
  // Half of MIN_PHONEME_IDS — noise_scale floor (0.5) engages exactly.
  const int len = MIN_PHONEME_IDS / 2;
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale * std::max(0.5f, ratio));
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW * std::max(0.4f, ratio));
}

TEST_F(DynamicScalesTest, FloorClampForVeryShortInput) {
  const int len = 1;  // Far below both floors
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  // Both floors clamp.
  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale * 0.5f);
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW * 0.4f);
}

TEST_F(DynamicScalesTest, RatioIsZeroForEmptyInput) {
  const int len = 0;
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  EXPECT_FLOAT_EQ(ratio, 0.0f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  // Floor clamps kick in
  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale * 0.5f);
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW * 0.4f);
}

TEST_F(DynamicScalesTest, GradualScaling) {
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  // Test that scales increase monotonically with length
  float prevNS = 0.0f;
  float prevNW = 0.0f;

  for (int len = 1; len <= MIN_PHONEME_IDS; len++) {
    float ratio = std::clamp(static_cast<float>(len) /
                                  static_cast<float>(MIN_PHONEME_IDS),
                              0.0f, 1.0f);
    float ns = noiseScale * std::max(0.5f, ratio);
    float nw = noiseW * std::max(0.4f, ratio);

    EXPECT_GE(ns, prevNS);
    EXPECT_GE(nw, prevNW);
    prevNS = ns;
    prevNW = nw;
  }
}

TEST_F(DynamicScalesTest, ExactBoundaryAtMinPhonemeIds) {
  const int len = MIN_PHONEME_IDS;
  float noiseScale = 0.4f;
  float noiseW = 0.5f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  EXPECT_FLOAT_EQ(ratio, 1.0f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  // At boundary, no reduction
  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale);
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW);
}

// ======================================================================
// Integration: combined A + B behavior
// ======================================================================

class ShortTextIntegrationTest : public ::testing::Test {};

TEST_F(ShortTextIntegrationTest, PaddingAndScalesApplyTogether) {
  // Simulate the flow: short input -> pad -> adjust scales
  std::vector<PhonemeId> ids = {1, 10, 11, 12, 2};  // 5 elements
  const int originalLen = static_cast<int>(ids.size());

  // Strategy A
  bool wasPadded = padPhonemeIds(ids);
  EXPECT_TRUE(wasPadded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);

  // Strategy B: use original length for ratio (before padding made it 40)
  float ratio = std::clamp(static_cast<float>(originalLen) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  float noiseScale = 0.4f * std::max(0.5f, ratio);
  float noiseW = 0.5f * std::max(0.4f, ratio);

  // Both should be reduced
  EXPECT_LT(noiseScale, 0.4f);
  EXPECT_LT(noiseW, 0.5f);
}

TEST_F(ShortTextIntegrationTest, LongInputUnchanged) {
  std::vector<PhonemeId> ids;
  ids.push_back(1);
  for (int i = 0; i < 50; i++) ids.push_back(10);
  ids.push_back(2);
  const int originalLen = static_cast<int>(ids.size());

  bool wasPadded = padPhonemeIds(ids);
  EXPECT_FALSE(wasPadded);
  EXPECT_EQ(static_cast<int>(ids.size()), originalLen);

  // Scales untouched
  float ratio = std::clamp(static_cast<float>(originalLen) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  EXPECT_FLOAT_EQ(ratio, 1.0f);
}

TEST_F(ShortTextIntegrationTest, TrimPreservesMinSamplesAfterPadding) {
  // After padding + inference, we'd get audio with silence.
  // Simulate: silence + signal + silence
  const int totalSamples = 10 * TRIM_WINDOW_SIZE;
  std::vector<int16_t> audio(totalSamples, 0);

  // Small signal in the middle
  for (int i = 4 * TRIM_WINDOW_SIZE; i < 6 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 5000;
  }

  trimSilenceInt16(audio);

  // Trimmed but not below minimum
  EXPECT_GE(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
  EXPECT_LT(static_cast<int>(audio.size()), totalSamples);
}

// ======================================================================
// Bug fix: phoneme timing must use pre-padding phonemeIds
// ======================================================================

class PhonemeTimingPaddingTest : public ::testing::Test {};

TEST_F(PhonemeTimingPaddingTest, OriginalIdsPreservedBeforePadding) {
  // Simulate the fix: save originalPhonemeIds before padding
  std::vector<PhonemeId> phonemeIds = {1, 10, 11, 12, 13, 14, 2};  // 7 elements
  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);

  bool wasPadded = padPhonemeIds(phonemeIds);
  EXPECT_TRUE(wasPadded);

  // After padding, phonemeIds is now 40 elements
  EXPECT_EQ(static_cast<int>(phonemeIds.size()), MIN_PHONEME_IDS);

  // originalPhonemeIds must still be the original 7 elements
  EXPECT_EQ(originalPhonemeIds.size(), 7u);
  EXPECT_EQ(originalPhonemeIds[0], 1);   // BOS
  EXPECT_EQ(originalPhonemeIds[1], 10);
  EXPECT_EQ(originalPhonemeIds[6], 2);   // EOS
}

TEST_F(PhonemeTimingPaddingTest, OriginalIdsUnchangedWhenNoPadding) {
  // Long enough input -- no padding occurs
  std::vector<PhonemeId> phonemeIds;
  phonemeIds.push_back(1);
  for (int i = 0; i < 48; i++) phonemeIds.push_back(10 + i);
  phonemeIds.push_back(2);
  ASSERT_EQ(phonemeIds.size(), 50u);

  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);

  bool wasPadded = padPhonemeIds(phonemeIds);
  EXPECT_FALSE(wasPadded);

  // Both should be identical
  EXPECT_EQ(phonemeIds.size(), originalPhonemeIds.size());
  EXPECT_EQ(phonemeIds, originalPhonemeIds);
}

TEST_F(PhonemeTimingPaddingTest, OriginalSizeSmallerThanPadded) {
  // The key invariant: originalPhonemeIds.size() <= phonemeIds.size()
  // and for short inputs, strictly less.
  std::vector<PhonemeId> phonemeIds = {1, 5, 6, 7, 2};  // 5 elements
  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);

  padPhonemeIds(phonemeIds);

  // original is 5, padded is 40
  EXPECT_EQ(originalPhonemeIds.size(), 5u);
  EXPECT_EQ(static_cast<int>(phonemeIds.size()), MIN_PHONEME_IDS);
  EXPECT_LT(originalPhonemeIds.size(), phonemeIds.size());
}

TEST_F(PhonemeTimingPaddingTest, DurationVecAlignmentWithOriginal) {
  // Simulate: duration output from the model has the same length as the
  // input phoneme sequence (padded). The original phonemeIds is shorter.
  // extractTimingsFromDurations iterates min(phonemeIds.size(), durations.size())
  // so passing the original IDs correctly bounds the iteration.
  std::vector<PhonemeId> phonemeIds = {1, 10, 11, 12, 2};  // 5 elements
  const std::vector<PhonemeId> originalPhonemeIds(phonemeIds);

  padPhonemeIds(phonemeIds);
  ASSERT_EQ(static_cast<int>(phonemeIds.size()), MIN_PHONEME_IDS);

  // Model returns durations for the padded input (40 elements)
  std::vector<float> durationVec(static_cast<size_t>(MIN_PHONEME_IDS), 5.0f);

  // When using originalPhonemeIds (size=5), iteration is bounded to 5
  size_t iterCount = std::min(originalPhonemeIds.size(), durationVec.size());
  EXPECT_EQ(iterCount, 5u);

  // When incorrectly using padded phonemeIds (size=MIN_PHONEME_IDS),
  // iteration covers all of them.
  size_t badIterCount = std::min(phonemeIds.size(), durationVec.size());
  EXPECT_EQ(badIterCount, static_cast<size_t>(MIN_PHONEME_IDS));

  // The fix ensures we use the smaller, correct count
  EXPECT_LT(iterCount, badIterCount);
}

// ======================================================================
// Bug fix: trimSilence partial window handling
// ======================================================================

class TrimPartialWindowInt16Test : public ::testing::Test {};

TEST_F(TrimPartialWindowInt16Test, AudioInPartialWindowDetected) {
  // Create buffer where all full windows are silence, but the partial
  // window at the end contains loud audio.
  // 3 full windows (768 samples) + 100 partial samples = 868 total
  // But we need > TRIM_MIN_SAMPLES (2205), so use more full windows.
  const int nFullWindows = 10;  // 2560 samples
  const int partialSize = 100;
  const int totalSamples = nFullWindows * TRIM_WINDOW_SIZE + partialSize;
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);

  std::vector<int16_t> audio(totalSamples, 0);  // All silence

  // Put loud audio only in the partial window at the end
  for (int i = nFullWindows * TRIM_WINDOW_SIZE; i < totalSamples; i++) {
    audio[i] = 10000;
  }

  trimSilenceInt16(audio);

  // The partial window audio should be detected and preserved.
  // Without the fix, lastAbove would be -1 (all-silence path) and the
  // buffer would be truncated to TRIM_MIN_SAMPLES with no guarantee of
  // preserving the partial window content.
  // With the fix, the loud partial window is found and included.
  bool hasLoudSample = false;
  for (auto s : audio) {
    if (std::abs(s) > 5000) {
      hasLoudSample = true;
      break;
    }
  }
  EXPECT_TRUE(hasLoudSample);
}

TEST_F(TrimPartialWindowInt16Test, FullWindowsPlusPartialSilence) {
  // Full windows have audio, partial window is silence -- should behave
  // the same as before the fix (partial silence doesn't affect lastAbove).
  const int nFullWindows = 9;  // 9 * 256 = 2304 > TRIM_MIN_SAMPLES (2205)
  const int partialSize = 50;
  const int totalSamples = nFullWindows * TRIM_WINDOW_SIZE + partialSize;
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);

  std::vector<int16_t> audio(totalSamples, 5000);  // All loud

  // Make the partial window silent
  for (int i = nFullWindows * TRIM_WINDOW_SIZE; i < totalSamples; i++) {
    audio[i] = 0;
  }

  trimSilenceInt16(audio);

  // All full windows are loud, so firstAbove=0, lastAbove=8.
  // endSample = min(9*256, totalSamples) = 2304, which is < totalSamples.
  // Trailing silence in partial window should be trimmed.
  EXPECT_LE(static_cast<int>(audio.size()), totalSamples);
}

TEST_F(TrimPartialWindowInt16Test, ExactMultipleUnchanged) {
  // When buffer size is exact multiple of TRIM_WINDOW_SIZE, no partial
  // window exists -- behavior unchanged from before the fix.
  const int totalSamples = 9 * TRIM_WINDOW_SIZE;  // 2304 > TRIM_MIN_SAMPLES
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);
  ASSERT_EQ(totalSamples % TRIM_WINDOW_SIZE, 0);

  std::vector<int16_t> audio(totalSamples, 5000);

  trimSilenceInt16(audio);

  EXPECT_EQ(static_cast<int>(audio.size()), totalSamples);
}

class TrimPartialWindowFloatTest : public ::testing::Test {};

TEST_F(TrimPartialWindowFloatTest, AudioInPartialWindowDetected) {
  const int nFullWindows = 10;
  const int partialSize = 100;
  const int totalSamples = nFullWindows * TRIM_WINDOW_SIZE + partialSize;
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);

  std::vector<float> audio(totalSamples, 0.0f);

  // Put loud audio only in the partial window
  for (int i = nFullWindows * TRIM_WINDOW_SIZE; i < totalSamples; i++) {
    audio[i] = 0.5f;
  }

  trimSilenceFloat(audio);

  bool hasLoudSample = false;
  for (auto s : audio) {
    if (std::abs(s) > 0.1f) {
      hasLoudSample = true;
      break;
    }
  }
  EXPECT_TRUE(hasLoudSample);
}

TEST_F(TrimPartialWindowFloatTest, FullWindowsPlusPartialSilence) {
  const int nFullWindows = 9;  // 9 * 256 = 2304 > TRIM_MIN_SAMPLES (2205)
  const int partialSize = 50;
  const int totalSamples = nFullWindows * TRIM_WINDOW_SIZE + partialSize;
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);

  std::vector<float> audio(totalSamples, 0.5f);

  for (int i = nFullWindows * TRIM_WINDOW_SIZE; i < totalSamples; i++) {
    audio[i] = 0.0f;
  }

  trimSilenceFloat(audio);

  EXPECT_LE(static_cast<int>(audio.size()), totalSamples);
}

TEST_F(TrimPartialWindowFloatTest, ExactMultipleUnchanged) {
  const int totalSamples = 9 * TRIM_WINDOW_SIZE;  // 2304 > TRIM_MIN_SAMPLES
  ASSERT_GT(totalSamples, TRIM_MIN_SAMPLES);
  ASSERT_EQ(totalSamples % TRIM_WINDOW_SIZE, 0);

  std::vector<float> audio(totalSamples, 0.5f);

  trimSilenceFloat(audio);

  EXPECT_EQ(static_cast<int>(audio.size()), totalSamples);
}

// ======================================================================
// Strategy A: trimPaddingByDurations (precise post-trim, issue #356)
// ======================================================================
// Mirrors src/python_run/tests/test_short_text_mitigation.py and ensures
// every runtime trims by the same number of samples for the same inputs.

class TrimPaddingByDurationsTest : public ::testing::Test {};

TEST_F(TrimPaddingByDurationsTest, NoOpWhenNoPadding) {
  std::vector<int16_t> audio(1000);
  for (int i = 0; i < 1000; i++) audio[i] = static_cast<int16_t>(i);
  std::vector<float> durations = {1.0f, 1.0f, 1.0f, 1.0f, 1.0f};

  trimPaddingByDurations(audio, durations, /*frontPad=*/0, /*backPad=*/0,
                         /*hopSize=*/256, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimPaddingByDurationsTest, TrimsFrontPaddingOnly) {
  // Layout: BOS=2, pad×3 (3+3+3), body=4, EOS=1 → 19 frames total.
  std::vector<float> durations = {2.0f, 3.0f, 3.0f, 3.0f, 4.0f, 1.0f};
  const int hop = 100;
  const int total = 1900;
  std::vector<int16_t> audio(total);

  trimPaddingByDurations(audio, durations, /*frontPad=*/3, /*backPad=*/0,
                         hop, /*eosMaxFrames=*/6);

  // BOS + front padding samples = (2+3+3+3) * 100 = 1100
  EXPECT_EQ(static_cast<int>(audio.size()), total - 1100);
}

TEST_F(TrimPaddingByDurationsTest, DefaultStripsEosCompletely) {
  std::vector<float> durations = {2.0f, 5.0f, 5.0f, 4.0f, 4.0f, 5.0f, 5.0f, 8.0f};
  const int hop = 100;
  const int total = 3800;
  std::vector<int16_t> audio(total);

  trimPaddingByDurations(audio, durations, /*frontPad=*/2, /*backPad=*/2,
                         hop, TRIM_EOS_MAX_FRAMES);

  // BOS + front padding = (2+5+5)*100 = 1200
  // back padding + entire EOS = (5+5+8)*100 = 1800
  EXPECT_EQ(static_cast<int>(audio.size()), total - 1200 - 1800);
}

TEST_F(TrimPaddingByDurationsTest, ClampsInflatedEos) {
  std::vector<float> durations = {2.0f, 3.0f, 3.0f, 4.0f, 3.0f, 3.0f, 10.0f};
  const int hop = 100;
  const int total = 2800;
  std::vector<int16_t> audio(total);

  trimPaddingByDurations(audio, durations, /*frontPad=*/2, /*backPad=*/2,
                         hop, /*eosMaxFrames=*/6);

  // BOS + front padding = (2+3+3) * 100 = 800
  // back padding + EOS excess = (3+3 + (10-6)) * 100 = 1000
  EXPECT_EQ(static_cast<int>(audio.size()), total - 800 - 1000);
}

TEST_F(TrimPaddingByDurationsTest, ReturnsInputWhenDurationsTooShort) {
  std::vector<int16_t> audio(1000);
  std::vector<float> durations = {1.0f, 1.0f, 1.0f};

  trimPaddingByDurations(audio, durations, /*frontPad=*/5, /*backPad=*/5,
                         /*hopSize=*/256, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimPaddingByDurationsTest, ReturnsInputWhenHopSizeZero) {
  std::vector<int16_t> audio(1000);
  std::vector<float> durations(8, 1.0f);

  trimPaddingByDurations(audio, durations, /*frontPad=*/2, /*backPad=*/2,
                         /*hopSize=*/0, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimPaddingByDurationsTest, TruncationMatchesIntCast) {
  // Layout (frontPad=1, backPad=1, body=3):
  //   [BOS=0.701, pad=0.701, body=2, body=2, body=2, pad=0.703, EOS=0.701]
  // Front trim = static_cast<int>((0.701+0.701)*100) = 140
  // Back trim  = static_cast<int>(0.703*100) + static_cast<int>(0.701*100)
  //            = 70 + 70 = 140
  // A round() implementation would diverge → cross-runtime drift.
  std::vector<float> durations = {0.701f, 0.701f, 2.0f, 2.0f, 2.0f, 0.703f, 0.701f};
  const int hop = 100;
  float sum = 0.0f;
  for (auto d : durations) sum += d;
  const int total = static_cast<int>(sum * static_cast<float>(hop));
  std::vector<int16_t> audio(total);

  trimPaddingByDurations(audio, durations, /*frontPad=*/1, /*backPad=*/1,
                         hop, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), total - 140 - 140);
}

// ======================================================================
// Tier 1 (Issue #499): trimEosRegion — drop EOS region for ALL inputs
// ======================================================================
// Mirrors src/python_run/tests/test_short_text_mitigation.py::TestTrimEosRegion
// so every runtime gets identical behavioral coverage
// (cross-runtime contract — Issue #499).

class TrimEosRegionTest : public ::testing::Test {};

TEST_F(TrimEosRegionTest, DefaultStripsFullEosRegion) {
  // EOS = 2.0 frames → ceil = 2 → 200 samples (hop=100)
  std::vector<float> durations = {1.0f, 2.0f, 3.0f, 2.0f};
  const int hop = 100;
  const int total = 800;
  std::vector<int16_t> audio(total);
  for (int i = 0; i < total; i++) audio[i] = static_cast<int16_t>(i);

  trimEosRegion(audio, durations, hop, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), total - 200);
  for (int i = 0; i < 600; i++) EXPECT_EQ(audio[i], static_cast<int16_t>(i));
}

TEST_F(TrimEosRegionTest, AppliesCeilToFractionalDuration) {
  // durations[-1]=1.99 must trim ceil(1.99)=2 frames, not 1.
  std::vector<float> durations = {1.0f, 1.0f, 1.0f, 1.99f};
  const int hop = 256;
  std::vector<int16_t> audio(2048);

  trimEosRegion(audio, durations, hop, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 2048 - 512);
}

TEST_F(TrimEosRegionTest, EosMaxFramesOverrideKeepsHeadOfEos) {
  // EOS=10 raw, eosMaxFrames=6 → excess = ceil(10) - 6 = 4 frames
  std::vector<float> durations = {2.0f, 3.0f, 3.0f, 10.0f};
  const int hop = 100;
  std::vector<int16_t> audio(2000);

  trimEosRegion(audio, durations, hop, /*eosMaxFrames=*/6);

  EXPECT_EQ(static_cast<int>(audio.size()), 2000 - 400);
}

TEST_F(TrimEosRegionTest, NoOpWhenEosBelowMax) {
  // ceil(1.99)=2 ≤ eosMaxFrames=4 → no trim
  std::vector<float> durations = {1.0f, 1.0f, 1.99f};
  const int hop = 256;
  std::vector<int16_t> audio(1024);

  trimEosRegion(audio, durations, hop, /*eosMaxFrames=*/4);

  EXPECT_EQ(static_cast<int>(audio.size()), 1024);
}

TEST_F(TrimEosRegionTest, ReturnsInputWhenDurationsEmpty) {
  std::vector<int16_t> audio(1000);
  std::vector<float> durations;

  trimEosRegion(audio, durations, /*hopSize=*/256, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimEosRegionTest, ReturnsInputWhenHopSizeZero) {
  std::vector<int16_t> audio(1000);
  std::vector<float> durations = {1.0f, 2.0f, 3.0f};

  trimEosRegion(audio, durations, /*hopSize=*/0, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimEosRegionTest, ReturnsInputWhenTrimExceedsAudio) {
  // EOS=5 frames * 100 hop = 500 samples, audio has 200 samples
  std::vector<float> durations = {1.0f, 5.0f};
  std::vector<int16_t> audio(200);

  trimEosRegion(audio, durations, /*hopSize=*/100, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 200);
}

TEST_F(TrimEosRegionTest, IntegerDurationUnaffectedByCeil) {
  // ceil(2.0) == 2 — integer-valued durations trim int(d) frames.
  std::vector<float> durations = {1.0f, 1.0f, 2.0f};
  const int hop = 100;
  std::vector<int16_t> audio(400);

  trimEosRegion(audio, durations, hop, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 400 - 200);
}

int main(int argc, char **argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

// ======================================================================
// Float mirrors + baseOffset coverage (issues #654 / #655)
// ======================================================================
// Two gaps these close, both measured by mutation against the production
// helpers now that this file includes them instead of copies:
//
//   1. The float variants had NO absolute-length assertions. An off-by-one in
//      trimPaddingByDurationsFloat's front erase passed every suite in the
//      repository, while the same mutation in the int16 variant failed 8 cases.
//      The float path is what the C API iterator (synth_next) runs on.
//
//   2. Nothing exercised baseOffset != 0 at the unit level. That parameter is
//      the whole of the #655 fix: synthesize() appends, so a trim scoped to the
//      entire buffer deletes audio belonging to units the caller already
//      received. The model-driven test (test_synthesize_append_scope.cpp) covers
//      it end to end, but only for whatever offsets that fixture happens to
//      produce; these cases pin the arithmetic directly.

class TrimPaddingByDurationsFloatTest : public ::testing::Test {};

TEST_F(TrimPaddingByDurationsFloatTest, NoOpWhenNoPadding) {
  std::vector<float> audio(1000, 0.5f);
  std::vector<float> durations = {1.0f, 1.0f, 1.0f, 1.0f, 1.0f};

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/0, /*backPad=*/0,
                              /*hopSize=*/256, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1000);
}

TEST_F(TrimPaddingByDurationsFloatTest, TrimsFrontPaddingOnly) {
  std::vector<float> durations = {2.0f, 3.0f, 3.0f, 3.0f, 4.0f, 1.0f};
  const int hop = 100;
  const int total = 1900;
  std::vector<float> audio(total, 0.5f);

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/3, /*backPad=*/0,
                              hop, /*eosMaxFrames=*/6);

  // BOS + front padding samples = (2+3+3+3) * 100 = 1100
  EXPECT_EQ(static_cast<int>(audio.size()), total - 1100);
}

TEST_F(TrimPaddingByDurationsFloatTest, DefaultStripsEosCompletely) {
  std::vector<float> durations = {2.0f, 5.0f, 5.0f, 4.0f, 4.0f, 5.0f, 5.0f, 8.0f};
  const int hop = 100;
  const int total = 3800;
  std::vector<float> audio(total, 0.5f);

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/2, /*backPad=*/2,
                              hop, TRIM_EOS_MAX_FRAMES);

  // front = (2+5+5)*100 = 1200, back = (5+5)*100 + eos 8*100 = 1800
  EXPECT_EQ(static_cast<int>(audio.size()), total - 1200 - 1800);
}

TEST_F(TrimPaddingByDurationsFloatTest, ReturnsInputWhenDurationsTooShort) {
  std::vector<float> durations = {1.0f, 1.0f};
  std::vector<float> audio(500, 0.5f);

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/3, /*backPad=*/3,
                              /*hopSize=*/256, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 500);
}

TEST_F(TrimPaddingByDurationsFloatTest, ReturnsInputWhenHopSizeZero) {
  std::vector<float> durations = {2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
  std::vector<float> audio(500, 0.5f);

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/1, /*backPad=*/1,
                              /*hopSize=*/0, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 500);
}

TEST_F(TrimPaddingByDurationsFloatTest, TruncationMatchesIntCast) {
  // 2.7 + 3.3 = 6.0 exactly? No: float arithmetic gives 5.9999995, and the
  // int cast truncates, so the front cut is 599 and not 600. The int16 variant
  // pins the same value; keeping both honest is the point of this mirror.
  std::vector<float> durations = {2.7f, 3.3f, 4.0f, 1.0f};
  const int hop = 100;
  std::vector<float> audio(1100, 0.5f);

  trimPaddingByDurationsFloat(audio, durations, /*frontPad=*/1, /*backPad=*/0,
                              hop, /*eosMaxFrames=*/1);

  const int frontSamples = static_cast<int>((2.7f + 3.3f) * hop);
  EXPECT_EQ(static_cast<int>(audio.size()), 1100 - frontSamples);
}

class TrimEosRegionFloatTest : public ::testing::Test {};

TEST_F(TrimEosRegionFloatTest, DefaultStripsFullEosRegion) {
  std::vector<float> durations = {2.0f, 4.0f, 6.0f};
  const int hop = 100;
  std::vector<float> audio(1200, 0.5f);

  trimEosRegionFloat(audio, durations, hop, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 1200 - 600);
}

TEST_F(TrimEosRegionFloatTest, AppliesCeilToFractionalDuration) {
  std::vector<float> durations = {2.0f, 4.0f, 5.2f};
  const int hop = 100;
  std::vector<float> audio(1200, 0.5f);

  trimEosRegionFloat(audio, durations, hop, TRIM_EOS_MAX_FRAMES);

  // ceil(5.2) = 6 frames
  EXPECT_EQ(static_cast<int>(audio.size()), 1200 - 600);
}

TEST_F(TrimEosRegionFloatTest, NoOpWhenEosBelowMax) {
  std::vector<float> durations = {2.0f, 4.0f, 3.0f};
  std::vector<float> audio(1200, 0.5f);

  trimEosRegionFloat(audio, durations, /*hopSize=*/100, /*eosMaxFrames=*/4);

  EXPECT_EQ(static_cast<int>(audio.size()), 1200);
}

TEST_F(TrimEosRegionFloatTest, ReturnsInputWhenTrimExceedsAudio) {
  std::vector<float> durations = {2.0f, 4.0f, 100.0f};
  std::vector<float> audio(500, 0.5f);

  trimEosRegionFloat(audio, durations, /*hopSize=*/100, TRIM_EOS_MAX_FRAMES);

  EXPECT_EQ(static_cast<int>(audio.size()), 500);
}

// ---- baseOffset != 0 ----

class TrimBaseOffsetTest : public ::testing::Test {
protected:
  // A prefix whose samples are a function of their index, so a shift shows up
  // even when the shifted-in values are in range.
  static std::vector<int16_t> prefixed(std::size_t prefix, std::size_t unit) {
    std::vector<int16_t> buffer(prefix + unit);
    for (std::size_t i = 0; i < buffer.size(); ++i) {
      buffer[i] = static_cast<int16_t>((i * 31) % 20000 - 10000);
    }
    return buffer;
  }

  static void expectPrefixIntact(const std::vector<int16_t> &buffer,
                                 std::size_t prefix) {
    ASSERT_GE(buffer.size(), prefix);
    for (std::size_t i = 0; i < prefix; ++i) {
      ASSERT_EQ(buffer[i], static_cast<int16_t>((i * 31) % 20000 - 10000))
          << "prefix sample " << i << " was altered";
    }
  }
};

TEST_F(TrimBaseOffsetTest, PaddingTrimCutsOnlyInsideTheUnit) {
  const std::size_t prefix = 700;
  const std::size_t unit = 1900;
  auto audio = prefixed(prefix, unit);
  std::vector<float> durations = {2.0f, 3.0f, 3.0f, 3.0f, 4.0f, 1.0f};

  trimPaddingByDurations(audio, durations, /*frontPad=*/3, /*backPad=*/0,
                         /*hopSize=*/100, /*eosMaxFrames=*/6, prefix);

  // Same 1100-sample front cut as the offset-0 case, taken out of the unit.
  EXPECT_EQ(audio.size(), prefix + unit - 1100);
  expectPrefixIntact(audio, prefix);
}

TEST_F(TrimBaseOffsetTest, PaddingTrimFrontAndBackInsideTheUnit) {
  const std::size_t prefix = 512;
  const std::size_t unit = 3800;
  auto audio = prefixed(prefix, unit);
  std::vector<float> durations = {2.0f, 5.0f, 5.0f, 4.0f, 4.0f, 5.0f, 5.0f, 8.0f};

  trimPaddingByDurations(audio, durations, /*frontPad=*/2, /*backPad=*/2,
                         /*hopSize=*/100, TRIM_EOS_MAX_FRAMES, prefix);

  EXPECT_EQ(audio.size(), prefix + unit - 1200 - 1800);
  expectPrefixIntact(audio, prefix);
}

TEST_F(TrimBaseOffsetTest, EosTrimMeasuresAgainstTheUnitNotTheBuffer) {
  // trimSamples (600) exceeds the unit (500) but not the whole buffer, so the
  // guard must decline. Measuring against the buffer would have eaten 100
  // samples of the caller's prefix.
  const std::size_t prefix = 1000;
  const std::size_t unit = 500;
  auto audio = prefixed(prefix, unit);
  std::vector<float> durations = {2.0f, 4.0f, 6.0f};

  trimEosRegion(audio, durations, /*hopSize=*/100, TRIM_EOS_MAX_FRAMES, prefix);

  EXPECT_EQ(audio.size(), prefix + unit);
  expectPrefixIntact(audio, prefix);
}

TEST_F(TrimBaseOffsetTest, SilenceTrimScansOnlyTheUnit) {
  // The prefix is loud and the unit is silent. Scanning the whole buffer would
  // find audio in the prefix and keep everything; scoped correctly, the unit
  // collapses to TRIM_MIN_SAMPLES.
  const std::size_t prefix = 4096;
  const std::size_t unit = 3 * TRIM_MIN_SAMPLES;
  std::vector<int16_t> audio(prefix + unit, 0);
  for (std::size_t i = 0; i < prefix; ++i) {
    audio[i] = static_cast<int16_t>((i % 2 == 0) ? 12000 : -12000);
  }

  trimSilenceInt16(audio, prefix);

  EXPECT_EQ(audio.size(), prefix + static_cast<std::size_t>(TRIM_MIN_SAMPLES));
  for (std::size_t i = 0; i < prefix; ++i) {
    ASSERT_EQ(audio[i], static_cast<int16_t>((i % 2 == 0) ? 12000 : -12000))
        << "prefix sample " << i << " was altered by the silence trim";
  }
}

TEST_F(TrimBaseOffsetTest, SilenceTrimFloatScansOnlyTheUnit) {
  const std::size_t prefix = 4096;
  const std::size_t unit = 3 * TRIM_MIN_SAMPLES;
  std::vector<float> audio(prefix + unit, 0.0f);
  for (std::size_t i = 0; i < prefix; ++i) {
    audio[i] = (i % 2 == 0) ? 0.4f : -0.4f;
  }

  trimSilenceFloat(audio, prefix);

  EXPECT_EQ(audio.size(), prefix + static_cast<std::size_t>(TRIM_MIN_SAMPLES));
  for (std::size_t i = 0; i < prefix; ++i) {
    ASSERT_FLOAT_EQ(audio[i], (i % 2 == 0) ? 0.4f : -0.4f)
        << "prefix sample " << i << " was altered by the float silence trim";
  }
}
