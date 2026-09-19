// Strategy A padding + Issue #499 post-trim helpers, shared by src/cpp/piper.cpp and
// src/cpp/tests/test_short_text_mitigation.cpp.
//
// These lived as `static` functions inside piper.cpp, which made them
// unreachable from any test. The test file therefore carried hand-written
// copies, and the absolute-sample-count assertions it already had -- 16 cases
// across TrimPaddingByDurationsTest / TrimEosRegionTest / TrimSilence*Test --
// were exercising those copies, not the production code. Measured consequence:
// five trim-boundary mutations in piper.cpp (front erase off by one, back erase
// off by one, the float variant, an INVERTED erase order, and an extra sample
// off the EOS tail) all passed every suite in the repository. The erase-order
// one is a failure mode that only exists because the trim became two erases,
// so the change that introduced it shipped with no detector.
//
// Extracting them here makes those existing assertions test the real thing. It
// also gives trimSilenceInt16 / trimSilenceFloat their first coverage: every
// in-tree fixture declares a `durations` output, so the `haveDurations == false`
// fallback they implement is unreachable through any model-driven test
// (verified with an stderr probe: zero hits across ten suites).
//
// Header-only and inline so piper.cpp keeps a single definition and the test
// needs no extra translation unit. spdlog is used for one debug line per
// function, so consumers must link it.

#ifndef PIPER_PLUS_TRIM_HELPERS_HPP
#define PIPER_PLUS_TRIM_HELPERS_HPP

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

#include <spdlog/spdlog.h>

// PhonemeId only; this header is deliberately free of onnxruntime so the test
// that includes it stays model-free.
#include "phoneme_ids.hpp"

namespace piper {

// Short-text mitigation thresholds (Strategy A/B). Kept next to the helpers
// that consume them so the two cannot drift.
//
// MIN_PHONEME_IDS was 40 but tsukuyomi 6lang testing showed padding that
// aggressive degrades quality; 15 keeps Strategy A active for genuinely tiny
// inputs only, and MIN_BODY_FOR_STRATEGY_A = 3 skips it when the body is
// shorter than that (issue #356).
constexpr int MIN_PHONEME_IDS = 15;
constexpr int MIN_BODY_FOR_STRATEGY_A = 3;
constexpr float TRIM_THRESHOLD_RMS = 0.01f;
constexpr int TRIM_MIN_SAMPLES = 2205;  // 22050 Hz * 0.1 s
constexpr int TRIM_WINDOW_SIZE = 256;
// Issue #499: the EOS region carries decoder leakage that sounds like the final
// syllable was repeated, so none of it is kept.
constexpr int TRIM_EOS_MAX_FRAMES = 0;

// ---------------------------------------------------------------------------

// Pad short phoneme ID sequences with silence tokens (pause ID = 0) after BOS
// and before EOS to reach MIN_PHONEME_IDS length. Returns true if padding was
// applied. Strategy A is also skipped when the body (= phoneme IDs minus
// BOS/EOS) is shorter than MIN_BODY_FOR_STRATEGY_A — see issue #356.
//
// When padding is applied, *frontPadOut and *backPadOut (when non-null)
// receive the number of pad tokens inserted after BOS and before EOS
// respectively, so the durations-based trim can locate them precisely.
static bool padPhonemeIds(std::vector<PhonemeId> &phonemeIds,
                          PhonemeId padId = 0,
                          int *frontPadOut = nullptr,
                          int *backPadOut = nullptr) {
  if (frontPadOut) *frontPadOut = 0;
  if (backPadOut) *backPadOut = 0;
  const auto len = static_cast<int>(phonemeIds.size());
  const int bodyLen = len - 2; // exclude BOS / EOS
  if (bodyLen < MIN_BODY_FOR_STRATEGY_A) {
    return false;
  }
  if (len >= MIN_PHONEME_IDS) {
    return false;
  }

  const int needed = MIN_PHONEME_IDS - len;
  const int front = needed / 2;
  const int back = needed - front;

  // phonemeIds layout: [BOS, ...body..., EOS]
  // We need at least 2 elements (BOS + EOS) to split safely.
  if (phonemeIds.size() < 2) {
    // Degenerate case: just pad at the end
    phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(needed), padId);
    if (frontPadOut) *frontPadOut = front;
    if (backPadOut) *backPadOut = back;
    return true;
  }

  // Split: bos = first element, body = middle, eos = last element
  PhonemeId bos = phonemeIds.front();
  PhonemeId eos = phonemeIds.back();
  std::vector<PhonemeId> body(phonemeIds.begin() + 1, phonemeIds.end() - 1);

  // Reconstruct: BOS + front_pad + body + back_pad + EOS
  phonemeIds.clear();
  phonemeIds.reserve(static_cast<size_t>(MIN_PHONEME_IDS));
  phonemeIds.push_back(bos);
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(front), padId);
  phonemeIds.insert(phonemeIds.end(), body.begin(), body.end());
  phonemeIds.insert(phonemeIds.end(), static_cast<size_t>(back), padId);
  phonemeIds.push_back(eos);

  spdlog::debug("Short-text padding: {} -> {} phoneme IDs ({} pad tokens added)",
                len, phonemeIds.size(), needed);
  if (frontPadOut) *frontPadOut = front;
  if (backPadOut) *backPadOut = back;
  return true;
}

// Strategy A precise post-trim using the model's duration output.
// Mirrors the Python reference (src/python_run/piper_plus/voice.py
// _trim_padding_by_durations) so all runtimes produce byte-equal output for
// the same inputs (issue #356, cross-runtime contract).
//
// Layout: [BOS, pad×frontPad, ...body..., pad×backPad, EOS]
//
// Trimming policy:
//   - BOS + front padding: stripped completely
//   - Back padding: stripped completely
//   - EOS: keep only `eosMaxFrames` frames (default TRIM_EOS_MAX_FRAMES = 0)
//
// All frame→sample conversions use static_cast<int>(...) on a float product
// (truncation toward zero), matching int() in the Python implementation.
//
// Falls through unchanged when arguments are inconsistent.
// `baseOffset` is the size the caller's buffer had before this inference
// appended to it. Everything below [0, baseOffset) belongs to previously
// emitted units and MUST NOT be touched: synthesize() appends, so
// audioBuffer.begin() is the start of the whole utterance, not of this unit
// (issue #655). Trimming from index 0 deleted the head of the utterance
// whenever a later phrase was padded -- and since `frontSum` always includes
// durations[0] (BOS), that happened for every padded phrase, even at
// frontPad == 0.
inline void trimPaddingByDurations(std::vector<int16_t> &audioBuffer,
                                   const std::vector<float> &durations,
                                   int frontPad,
                                   int backPad,
                                   int hopSize,
                                   int eosMaxFrames = TRIM_EOS_MAX_FRAMES,
                                   std::size_t baseOffset = 0) {
  if (frontPad <= 0 && backPad <= 0) return;
  if (durations.empty() || hopSize <= 0) return;
  const int expectedLen = 1 + frontPad + backPad + 1; // BOS + pads + EOS
  if (static_cast<int>(durations.size()) < expectedLen) return;

  // Front: BOS + front padding samples (truncated).
  float frontSum = 0.0f;
  for (int i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const int frontSamples = static_cast<int>(frontSum * static_cast<float>(hopSize));

  // Back: back padding samples + EOS excess (over eosMaxFrames).
  float backPadSum = 0.0f;
  if (backPad > 0) {
    // durations[-(1+backPad) : -1] in Python = [size-1-backPad, size-1)
    const int start = static_cast<int>(durations.size()) - 1 - backPad;
    for (int i = start; i < static_cast<int>(durations.size()) - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const int backPadSamples =
      static_cast<int>(backPadSum * static_cast<float>(hopSize));
  const float eosFrames = durations.back();
  float eosExcess = eosFrames - static_cast<float>(eosMaxFrames);
  if (eosExcess < 0.0f) eosExcess = 0.0f;
  const int backSamples =
      backPadSamples +
      static_cast<int>(eosExcess * static_cast<float>(hopSize));

  // Operate on [baseOffset, size) only. `erase` keeps the caller's prefix in
  // place instead of rebuilding the buffer from an absolute slice.
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) return;
  const int unitSamples = static_cast<int>(bufferSize - baseOffset);
  int start = frontSamples < 0 ? 0 : frontSamples;
  int end = unitSamples - backSamples;
  if (end < start) end = start;
  if (start >= unitSamples || end <= 0 || start >= end) return;

  if (end < unitSamples) {
    audioBuffer.erase(audioBuffer.begin() + baseOffset + end,
                      audioBuffer.end());
  }
  if (start > 0) {
    audioBuffer.erase(audioBuffer.begin() + baseOffset,
                      audioBuffer.begin() + baseOffset + start);
  }
}

// Float32 variant of trimPaddingByDurations. Identical sample-count logic;
// only the buffer element type differs.
inline void trimPaddingByDurationsFloat(std::vector<float> &audioBuffer,
                                        const std::vector<float> &durations,
                                        int frontPad,
                                        int backPad,
                                        int hopSize,
                                        int eosMaxFrames = TRIM_EOS_MAX_FRAMES,
                                        std::size_t baseOffset = 0) {
  if (frontPad <= 0 && backPad <= 0) return;
  if (durations.empty() || hopSize <= 0) return;
  const int expectedLen = 1 + frontPad + backPad + 1;
  if (static_cast<int>(durations.size()) < expectedLen) return;

  float frontSum = 0.0f;
  for (int i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const int frontSamples = static_cast<int>(frontSum * static_cast<float>(hopSize));

  float backPadSum = 0.0f;
  if (backPad > 0) {
    const int start = static_cast<int>(durations.size()) - 1 - backPad;
    for (int i = start; i < static_cast<int>(durations.size()) - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const int backPadSamples =
      static_cast<int>(backPadSum * static_cast<float>(hopSize));
  const float eosFrames = durations.back();
  float eosExcess = eosFrames - static_cast<float>(eosMaxFrames);
  if (eosExcess < 0.0f) eosExcess = 0.0f;
  const int backSamples =
      backPadSamples +
      static_cast<int>(eosExcess * static_cast<float>(hopSize));

  // Operate on [baseOffset, size) only. `erase` keeps the caller's prefix in
  // place instead of rebuilding the buffer from an absolute slice.
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) return;
  const int unitSamples = static_cast<int>(bufferSize - baseOffset);
  int start = frontSamples < 0 ? 0 : frontSamples;
  int end = unitSamples - backSamples;
  if (end < start) end = start;
  if (start >= unitSamples || end <= 0 || start >= end) return;

  if (end < unitSamples) {
    audioBuffer.erase(audioBuffer.begin() + baseOffset + end,
                      audioBuffer.end());
  }
  if (start > 0) {
    audioBuffer.erase(audioBuffer.begin() + baseOffset,
                      audioBuffer.begin() + baseOffset + start);
  }
}

// Tier 1 workaround for Issue #499: trim the EOS region from the tail for
// every inference path (long-text included).
//
// VITS's infer() expands attention with ceil(w) but exposes the raw float w
// as the durations output. The EOS frame(s) generated under ceil carry
// decoder leakage that sounds like the final syllable was repeated —
// clearly audible on fine-tuned models such as piper-plus-tsukuyomi-chan.
// trimPaddingByDurations already drops the EOS region only when Strategy A
// short-text padding was applied; this helper applies the same drop to
// every other inference path so long-text outputs do not retain the
// audible doubled tail.
//
// Mirrors src/python_run/piper_plus/voice.py _trim_eos_region so every runtime
// produces byte-equal output for the same (audio, durations.back(),
// hopSize, eosMaxFrames) tuple. The sample-count conversion uses
// static_cast<int>(...) truncation to match Python's int(...) semantics.
//
// Falls through unchanged when arguments are inconsistent.
inline void trimEosRegion(std::vector<int16_t> &audioBuffer,
                          const std::vector<float> &durations,
                          int hopSize,
                          int eosMaxFrames = TRIM_EOS_MAX_FRAMES,
                          std::size_t baseOffset = 0) {
  if (hopSize <= 0 || durations.empty()) return;
  const float eosFrames = durations.back();
  const int eosCeil = static_cast<int>(std::ceil(eosFrames));
  const int eosExcess = std::max(0, eosCeil - eosMaxFrames);
  if (eosExcess <= 0) return;
  const int trimSamples = eosExcess * hopSize;
  // Unreachable from a sane model (it needs durations.back() > 8.4M frames at
  // hop 256) but guarded explicitly: on overflow `trimSamples` goes negative
  // and `bufferSize - static_cast<std::size_t>(trimSamples)` wraps into a
  // gigabyte-scale resize. The pre-existing code had the same exposure via
  // `resize(totalSamples - trimSamples)`; the guard is free, so it is added
  // while this function is being touched rather than left as a latent trap.
  if (trimSamples < 0) return;
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) return;
  // Measure against THIS call's samples. `resize` only removes from the tail,
  // so the caller's prefix was never rewritten -- but the guard used the whole
  // buffer's length, so a trim larger than the unit would have eaten into the
  // preceding unit instead of being skipped (issue #655).
  const int unitSamples = static_cast<int>(bufferSize - baseOffset);
  if (trimSamples >= unitSamples) return;
  audioBuffer.resize(bufferSize - static_cast<std::size_t>(trimSamples));
}

// Float32 variant of trimEosRegion. Identical sample-count logic; only the
// buffer element type differs.
inline void trimEosRegionFloat(std::vector<float> &audioBuffer,
                               const std::vector<float> &durations,
                               int hopSize,
                               int eosMaxFrames = TRIM_EOS_MAX_FRAMES,
                               std::size_t baseOffset = 0) {
  if (hopSize <= 0 || durations.empty()) return;
  const float eosFrames = durations.back();
  const int eosCeil = static_cast<int>(std::ceil(eosFrames));
  const int eosExcess = std::max(0, eosCeil - eosMaxFrames);
  if (eosExcess <= 0) return;
  const int trimSamples = eosExcess * hopSize;
  // Unreachable from a sane model (it needs durations.back() > 8.4M frames at
  // hop 256) but guarded explicitly: on overflow `trimSamples` goes negative
  // and `bufferSize - static_cast<std::size_t>(trimSamples)` wraps into a
  // gigabyte-scale resize. The pre-existing code had the same exposure via
  // `resize(totalSamples - trimSamples)`; the guard is free, so it is added
  // while this function is being touched rather than left as a latent trap.
  if (trimSamples < 0) return;
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) return;
  // Measure against THIS call's samples. `resize` only removes from the tail,
  // so the caller's prefix was never rewritten -- but the guard used the whole
  // buffer's length, so a trim larger than the unit would have eaten into the
  // preceding unit instead of being skipped (issue #655).
  const int unitSamples = static_cast<int>(bufferSize - baseOffset);
  if (trimSamples >= unitSamples) return;
  audioBuffer.resize(bufferSize - static_cast<std::size_t>(trimSamples));
}

// Trim leading/trailing silence from int16 audio using windowed RMS.
// Preserves at least TRIM_MIN_SAMPLES samples.
inline void trimSilenceInt16(std::vector<int16_t> &audioBuffer,
                             std::size_t baseOffset = 0) {
  // Scoped to [baseOffset, size): synthesize() appends, so scanning from index
  // 0 would measure RMS over -- and slice away -- audio belonging to units the
  // caller already received (issue #655). This is the fallback path for models
  // without a durations output; the durations-based trim above has the same
  // constraint.
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) {
    return;
  }
  const std::size_t base = baseOffset;
  const auto totalSamples = static_cast<int>(bufferSize - base);
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  // Find first and last window above RMS threshold
  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = static_cast<float>(audioBuffer[base + offset + s]) / 32767.0f;
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

  // Check partial window (remainder samples after the last full window)
  const int remainder = totalSamples % TRIM_WINDOW_SIZE;
  if (remainder > 0) {
    float sumSq = 0.0f;
    const int offset = nWindows * TRIM_WINDOW_SIZE;
    for (int s = 0; s < remainder; s++) {
      float sample = static_cast<float>(audioBuffer[base + offset + s]) / 32767.0f;
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(remainder));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = nWindows;  // virtual window index for the partial
      }
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    // All silence -- keep minimum
    audioBuffer.resize(base + static_cast<std::size_t>(
                                  std::min(totalSamples, TRIM_MIN_SAMPLES)));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  // Ensure minimum length
  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    spdlog::debug("Trimming silence: [{}, {}) from {} samples",
                  startSample, endSample, totalSamples);
    if (endSample < totalSamples) {
      audioBuffer.erase(audioBuffer.begin() + base + endSample,
                        audioBuffer.end());
    }
    if (startSample > 0) {
      audioBuffer.erase(audioBuffer.begin() + base,
                        audioBuffer.begin() + base + startSample);
    }
  }
}

// Trim leading/trailing silence from float32 audio using windowed RMS.
// Audio is assumed normalized to [-1.0, 1.0].
// Preserves at least TRIM_MIN_SAMPLES samples.
inline void trimSilenceFloat(std::vector<float> &audioBuffer,
                             std::size_t baseOffset = 0) {
  // Scoped to [baseOffset, size): synthesize() appends, so scanning from index
  // 0 would measure RMS over -- and slice away -- audio belonging to units the
  // caller already received (issue #655). This is the fallback path for models
  // without a durations output; the durations-based trim above has the same
  // constraint.
  const std::size_t bufferSize = audioBuffer.size();
  if (baseOffset > bufferSize) {
    return;
  }
  const std::size_t base = baseOffset;
  const auto totalSamples = static_cast<int>(bufferSize - base);
  if (totalSamples <= TRIM_MIN_SAMPLES) {
    return;
  }

  const int nWindows = totalSamples / TRIM_WINDOW_SIZE;
  if (nWindows == 0) {
    return;
  }

  // Find first and last window above RMS threshold
  int firstAbove = -1;
  int lastAbove = -1;

  for (int w = 0; w < nWindows; w++) {
    float sumSq = 0.0f;
    const int offset = w * TRIM_WINDOW_SIZE;
    for (int s = 0; s < TRIM_WINDOW_SIZE; s++) {
      float sample = audioBuffer[base + offset + s];
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

  // Check partial window (remainder samples after the last full window)
  const int remainder = totalSamples % TRIM_WINDOW_SIZE;
  if (remainder > 0) {
    float sumSq = 0.0f;
    const int offset = nWindows * TRIM_WINDOW_SIZE;
    for (int s = 0; s < remainder; s++) {
      float sample = audioBuffer[base + offset + s];
      sumSq += sample * sample;
    }
    float rms = std::sqrt(sumSq / static_cast<float>(remainder));
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = nWindows;  // virtual window index for the partial
      }
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    // All silence -- keep minimum
    audioBuffer.resize(base + static_cast<std::size_t>(
                                  std::min(totalSamples, TRIM_MIN_SAMPLES)));
    return;
  }

  int startSample = firstAbove * TRIM_WINDOW_SIZE;
  int endSample = std::min((lastAbove + 1) * TRIM_WINDOW_SIZE, totalSamples);

  // Ensure minimum length
  int length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    int center = (startSample + endSample) / 2;
    startSample = std::max(0, center - TRIM_MIN_SAMPLES / 2);
    endSample = std::min(totalSamples, startSample + TRIM_MIN_SAMPLES);
    startSample = std::max(0, endSample - TRIM_MIN_SAMPLES);
  }

  if (startSample > 0 || endSample < totalSamples) {
    spdlog::debug("Trimming silence (float): [{}, {}) from {} samples",
                  startSample, endSample, totalSamples);
    if (endSample < totalSamples) {
      audioBuffer.erase(audioBuffer.begin() + base + endSample,
                        audioBuffer.end());
    }
    if (startSample > 0) {
      audioBuffer.erase(audioBuffer.begin() + base,
                        audioBuffer.begin() + base + startSample);
    }
  }
}

} // namespace piper

#endif // PIPER_PLUS_TRIM_HELPERS_HPP
