/**
 * Tests for short-text synthesis mitigation (Strategy A + B).
 *
 * Strategy A: Silence padding + post-trim
 * Strategy B: Dynamic scales adjustment
 *
 * These tests verify the helper logic without requiring an ONNX model.
 */

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

// ---------------------------------------------------------------------------
// Re-declare the constants and helpers identically to piper.cpp so the tests
// are self-contained (no piper.cpp linkage required).
// ---------------------------------------------------------------------------

using PhonemeId = int64_t;

constexpr int MIN_PHONEME_IDS = 40;
constexpr float TRIM_THRESHOLD_RMS = 0.01f;
constexpr int TRIM_MIN_SAMPLES = 2205;  // 22050 Hz * 0.1 s
constexpr int TRIM_WINDOW_SIZE = 256;

// Replica of padPhonemeIds from piper.cpp
static bool padPhonemeIds(std::vector<PhonemeId> &phonemeIds,
                          PhonemeId padId = 0) {
  const auto len = static_cast<int>(phonemeIds.size());
  if (len >= MIN_PHONEME_IDS) {
    return false;
  }

  const int needed = MIN_PHONEME_IDS - len;
  const int front = needed / 2;
  const int back = needed - front;

  if (phonemeIds.size() < 2) {
    phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(needed), padId);
    return true;
  }

  PhonemeId bos = phonemeIds.front();
  PhonemeId eos = phonemeIds.back();
  std::vector<PhonemeId> body(phonemeIds.begin() + 1, phonemeIds.end() - 1);

  phonemeIds.clear();
  phonemeIds.reserve(static_cast<size_t>(MIN_PHONEME_IDS));
  phonemeIds.push_back(bos);
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(front), padId);
  phonemeIds.insert(phonemeIds.end(), body.begin(), body.end());
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(back), padId);
  phonemeIds.push_back(eos);

  return true;
}

// Replica of trimSilenceInt16 from piper.cpp
static void trimSilenceInt16(std::vector<int16_t> &audioBuffer) {
  const auto totalSamples = static_cast<int>(audioBuffer.size());
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = static_cast<float>(audioBuffer[offset + s]) / 32767.0f;
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(TRIM_WINDOW_SIZE));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = w;
      }
      lastAbove = w;
    }
  }

  if (firstAbove < 0) {
    audioBuffer.resize(std::min(totalSamples, TRIM_MIN_SAMPLES));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    std::vector<int16_t> trimmed(audioBuffer.begin() + startSample,
                                 audioBuffer.begin() + endSample);
    audioBuffer = std::move(trimmed);
  }
}

// Replica of trimSilenceFloat from piper.cpp
static void trimSilenceFloat(std::vector<float> &audioBuffer) {
  const auto totalSamples = static_cast<int>(audioBuffer.size());
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = audioBuffer[offset + s];
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(TRIM_WINDOW_SIZE));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = w;
      }
      lastAbove = w;
    }
  }

  if (firstAbove < 0) {
    audioBuffer.resize(std::min(totalSamples, TRIM_MIN_SAMPLES));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    std::vector<float> trimmed(audioBuffer.begin() + startSample,
                               audioBuffer.begin() + endSample);
    audioBuffer = std::move(trimmed);
  }
}

// ======================================================================
// Strategy A: padPhonemeIds tests
// ======================================================================

class PadPhonemeIdsTest : public ::testing::Test {};

TEST_F(PadPhonemeIdsTest, NoOpWhenAlreadyLongEnough) {
  // BOS(1) + 38 body + EOS(2) = 40 elements
  std::vector<PhonemeId> ids;
  ids.push_back(1);  // BOS
  for (int i = 0; i < 38; i++) ids.push_back(10 + i);
  ids.push_back(2);  // EOS
  ASSERT_EQ(ids.size(), 40u);

  bool padded = padPhonemeIds(ids);
  EXPECT_FALSE(padded);
  EXPECT_EQ(ids.size(), 40u);
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
  // BOS + 5 body + EOS = 7 elements -> need 33 pads
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
  std::vector<PhonemeId> ids = {1, 10, 2};  // Very short

  padPhonemeIds(ids, /*padId=*/0);

  // Count pad tokens (0) between BOS and EOS
  int padCount = 0;
  for (size_t i = 1; i < ids.size() - 1; i++) {
    if (ids[i] == 0) padCount++;
  }
  EXPECT_GT(padCount, 0);
}

TEST_F(PadPhonemeIdsTest, FrontBackSplitIsBalanced) {
  // BOS + 3 body + EOS = 5, need 35 pads -> front=17, back=18
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
  std::vector<PhonemeId> ids = {42};

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, DegenerateEmpty) {
  std::vector<PhonemeId> ids;

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, MinimalBosEos) {
  // BOS + EOS = 2 elements, body is empty
  std::vector<PhonemeId> ids = {1, 2};

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
  EXPECT_EQ(ids.front(), 1);
  EXPECT_EQ(ids.back(), 2);
}

TEST_F(PadPhonemeIdsTest, BoundaryExactlyMinMinus1) {
  // 39 elements -> needs exactly 1 pad
  std::vector<PhonemeId> ids;
  ids.push_back(1);
  for (int i = 0; i < 37; i++) ids.push_back(10);
  ids.push_back(2);
  ASSERT_EQ(ids.size(), 39u);

  bool padded = padPhonemeIds(ids);
  EXPECT_TRUE(padded);
  EXPECT_EQ(static_cast<int>(ids.size()), MIN_PHONEME_IDS);
}

TEST_F(PadPhonemeIdsTest, CustomPadId) {
  std::vector<PhonemeId> ids = {1, 10, 2};

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
  // 2 windows of silence + 2 windows of audio + 2 windows of silence
  const int totalSamples = 6 * TRIM_WINDOW_SIZE;
  std::vector<int16_t> audio(totalSamples, 0);

  // Fill windows 2-3 with loud audio
  for (int i = 2 * TRIM_WINDOW_SIZE; i < 4 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 10000;
  }

  trimSilenceInt16(audio);

  // Result should be shorter than original
  EXPECT_LT(static_cast<int>(audio.size()), totalSamples);
  // Result should start around window 2 and end around window 4
  EXPECT_GE(static_cast<int>(audio.size()), 2 * TRIM_WINDOW_SIZE);
}

TEST_F(TrimSilenceInt16Test, AllSilenceKeepsMinSamples) {
  std::vector<int16_t> audio(5000, 0);  // All zeros, > TRIM_MIN_SAMPLES

  trimSilenceInt16(audio);
  EXPECT_EQ(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
}

TEST_F(TrimSilenceInt16Test, NoSilenceKeepsAll) {
  // All windows above threshold
  const int totalSamples = 4 * TRIM_WINDOW_SIZE;
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
  const int totalSamples = 6 * TRIM_WINDOW_SIZE;
  std::vector<float> audio(totalSamples, 0.0f);

  // Fill windows 2-3 with loud audio
  for (int i = 2 * TRIM_WINDOW_SIZE; i < 4 * TRIM_WINDOW_SIZE; i++) {
    audio[i] = 0.5f;
  }

  trimSilenceFloat(audio);

  EXPECT_LT(static_cast<int>(audio.size()), totalSamples);
  EXPECT_GE(static_cast<int>(audio.size()), 2 * TRIM_WINDOW_SIZE);
}

TEST_F(TrimSilenceFloatTest, AllSilenceKeepsMinSamples) {
  std::vector<float> audio(5000, 0.0f);

  trimSilenceFloat(audio);
  EXPECT_EQ(static_cast<int>(audio.size()), TRIM_MIN_SAMPLES);
}

TEST_F(TrimSilenceFloatTest, NoSilenceKeepsAll) {
  const int totalSamples = 4 * TRIM_WINDOW_SIZE;
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
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

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
  const int len = 20;  // Half of MIN_PHONEME_IDS
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  EXPECT_FLOAT_EQ(ratio, 0.5f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  // noiseScale * max(0.5, 0.5) = noiseScale * 0.5
  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale * 0.5f);
  // noiseW * max(0.4, 0.5) = noiseW * 0.5
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW * 0.5f);
}

TEST_F(DynamicScalesTest, FloorClampForVeryShortInput) {
  const int len = 5;  // Very short
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

  float ratio = std::clamp(static_cast<float>(len) /
                                static_cast<float>(MIN_PHONEME_IDS),
                            0.0f, 1.0f);
  EXPECT_NEAR(ratio, 0.125f, 0.001f);

  float adjustedNoiseScale = noiseScale * std::max(0.5f, ratio);
  float adjustedNoiseW = noiseW * std::max(0.4f, ratio);

  // max(0.5, 0.125) = 0.5 -> noiseScale * 0.5
  EXPECT_FLOAT_EQ(adjustedNoiseScale, noiseScale * 0.5f);
  // max(0.4, 0.125) = 0.4 -> noiseW * 0.4
  EXPECT_FLOAT_EQ(adjustedNoiseW, noiseW * 0.4f);
}

TEST_F(DynamicScalesTest, RatioIsZeroForEmptyInput) {
  const int len = 0;
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

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
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

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
  float noiseScale = 0.667f;
  float noiseW = 0.8f;

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
  float noiseScale = 0.667f * std::max(0.5f, ratio);
  float noiseW = 0.8f * std::max(0.4f, ratio);

  // Both should be reduced
  EXPECT_LT(noiseScale, 0.667f);
  EXPECT_LT(noiseW, 0.8f);
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

int main(int argc, char **argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
