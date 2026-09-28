// Direct tests for the PRODUCTION phoneme timing cursor walk
// (src/cpp/timing_helpers.hpp, called by piper.cpp:extractTimingsFromDurations).
//
// Why this file exists: until it did, the C++ timing arithmetic had no test at
// all. test_phoneme_timing_parity.cpp reads the cross-runtime golden fixture
// but re-implements the spec algorithm in its own translation unit -- it said
// so in a comment -- because piper.cpp pulls in onnxruntime and the parity test
// cannot link it. Every other runtime's parity test calls its production
// function, so C++ was the only column of the matrix asserting nothing about
// shipped behaviour.
//
// The fixture STILL cannot drive production directly, and that is a finding
// rather than an oversight: the fixture is token-based ("^", "k", "o", ...,
// "$") while production is id-based and skips PAD/BOS/EOS (ids 0/1/2) without
// emitting entries. The fixture's own `basic_konnichiwa` case contains "^" and
// "$", which a real model maps to ids 1 and 2. Python canonical emits entries
// for them; C++ production does not. That 4-vs-2 split across runtimes is
// issue #697 and is deliberately NOT papered over here.
//
// So: this file pins what production actually does, at the level of individual
// arithmetic decisions, so that changing any of them is a visible diff.

#include <gtest/gtest.h>

#include <cmath>
#include <string>
#include <vector>

#include "timing_helpers.hpp"

namespace {

using piper::computePhonemeTimings;
using piper::PhonemeId;
using piper::PhonemeIdMap;
using piper::TimingEntry;

constexpr int kHop = 256;
constexpr int kRate = 22050;

// Seconds per frame at the canonical hop/rate.
double frameSeconds() {
  return static_cast<double>(kHop) / static_cast<double>(kRate);
}

// A map with one single-codepoint phoneme per id. Ids start at 3 so nothing
// collides with PAD/BOS/EOS.
PhonemeIdMap simpleIdMap() {
  PhonemeIdMap m;
  m[U'a'] = {3};
  m[U'k'] = {4};
  m[U'o'] = {5};
  return m;
}

}  // namespace

// ---------------------------------------------------------------------------
// PAD / BOS / EOS handling
// ---------------------------------------------------------------------------

TEST(TimingHelpers, SkipsPadBosEosButStillAdvancesTheCursor) {
  // ids 1 (BOS) and 2 (EOS) bracket one real phoneme. Only the real one is
  // emitted, and it must start AFTER the BOS duration -- if the cursor did not
  // advance, start_time would be 0.
  const std::vector<float> durations = {3.0f, 5.0f, 4.0f};
  const std::vector<PhonemeId> ids = {1, 3, 2};

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, /*applyJapanese=*/false);

  ASSERT_EQ(out.size(), 1u) << "BOS/EOS must not produce entries";
  EXPECT_EQ(out[0].phoneme, "a");
  EXPECT_NEAR(out[0].start_time, 3.0 * frameSeconds(), 1e-6);
  EXPECT_NEAR(out[0].end_time, 8.0 * frameSeconds(), 1e-6);
  EXPECT_EQ(out[0].start_frame, 3);
  EXPECT_EQ(out[0].end_frame, 8);
}

TEST(TimingHelpers, PadIdZeroIsSkippedToo) {
  // Strategy A interspersed padding uses id 0. It occupies real audio frames,
  // so the cursor advances, but it is not a phoneme anyone can lip-sync to.
  const std::vector<float> durations = {2.0f, 6.0f};
  const std::vector<PhonemeId> ids = {0, 4};

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, false);

  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].phoneme, "k");
  EXPECT_NEAR(out[0].start_time, 2.0 * frameSeconds(), 1e-6);
}

// ---------------------------------------------------------------------------
// Duration arithmetic -- the values issue #653 will change
// ---------------------------------------------------------------------------

TEST(TimingHelpers, FractionalDurationsAreUsedRaw) {
  // PINS PRE-#653 BEHAVIOUR. The ONNX `durations` output is exported before
  // `torch.ceil`, but the decoder allocates ceil(d_i) frames to phoneme i, so
  // these times are systematically short (measured: 73-76% of real audio).
  // When #653 lands, this expectation must change to the ceil'd values --
  // that is the point of pinning it. Integer-only fixtures cannot catch the
  // difference because ceil(int) == int, which is exactly why the shared
  // golden matrix (all 7 cases integer) misses it.
  const std::vector<float> durations = {2.5f, 3.5f};
  const std::vector<PhonemeId> ids = {3, 4};

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, false);

  ASSERT_EQ(out.size(), 2u);
  EXPECT_NEAR(out[0].end_time, 2.5 * frameSeconds(), 1e-6)
      << "raw 2.5 frames, not ceil(2.5)=3";
  EXPECT_NEAR(out[1].end_time, 6.0 * frameSeconds(), 1e-6)
      << "raw 2.5+3.5, not ceil(2.5)+ceil(3.5)=7";
}

TEST(TimingHelpers, FrameIndicesTruncateWhileTimesDoNot) {
  // PINS A KNOWN INTERNAL INCONSISTENCY (issue #653): start_frame/end_frame
  // accumulate `static_cast<long long>(duration)` (truncation) while
  // start_time/end_time accumulate the raw value. For 2.7 frames the two
  // disagree: frame 2, time 2.7. Both should end up on the same ceil basis.
  const std::vector<float> durations = {2.7f};
  const std::vector<PhonemeId> ids = {3};

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, false);

  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].end_frame, 2) << "truncating cast";
  EXPECT_NEAR(out[0].end_time, 2.7 * frameSeconds(), 1e-6) << "raw float";
  // State the disagreement explicitly so a fix cannot land silently.
  EXPECT_NE(static_cast<double>(out[0].end_frame) * frameSeconds(),
            static_cast<double>(out[0].end_time));
}

TEST(TimingHelpers, NegativeDurationsAreNotClamped) {
  // PINS A DIVERGENCE. docs/spec/phoneme-timing-contract.toml
  // [calculation.negative_handling] says negative durations clamp to 0 with a
  // warning, and Python/Rust/Go/JS/C# all do. C++ does not: it adds the
  // negative value, moving the cursor BACKWARDS. Recorded here rather than
  // fixed under cover of an extraction.
  const std::vector<float> durations = {5.0f, -2.0f, 5.0f};
  const std::vector<PhonemeId> ids = {3, 4, 5};

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, false);

  ASSERT_EQ(out.size(), 3u);
  EXPECT_NEAR(out[1].end_time, 3.0 * frameSeconds(), 1e-6)
      << "5 + (-2) = 3: the cursor went backwards instead of clamping";
  EXPECT_LT(out[1].end_time, out[1].start_time)
      << "end before start -- the observable symptom";
}

// ---------------------------------------------------------------------------
// Accumulator width
// ---------------------------------------------------------------------------

TEST(TimingHelpers, AccumulatorIsDoubleNotFloat) {
  // The cursor used to be a float. Accumulating ~1150 frames of float32 drifts
  // ~2e-3 ms from the float64 reference that Python/Rust/Go/JS produce, which
  // is above the 1e-6 ms tolerance the cross-runtime parity test declares.
  // Storage stays float (PhonemeInfo is ABI-exported), so only the final
  // rounding remains -- one rounding per entry, not compounded.
  const std::size_t n = 400;
  std::vector<float> durations(n, 3.0f);
  std::vector<PhonemeId> ids(n, 3);

  const auto out = computePhonemeTimings(durations, ids, simpleIdMap(), kHop,
                                         kRate, false);
  ASSERT_EQ(out.size(), n);

  // Reference computed the same way Python does: one float64 accumulator.
  double reference = 0.0;
  for (std::size_t i = 0; i < n; ++i) {
    reference += 3.0 * frameSeconds();
  }

  // A float32 accumulator over this many steps lands well outside 1e-6 s.
  EXPECT_NEAR(out[n - 1].end_time, reference, 1e-6)
      << "float32 accumulation would miss this";
}

// ---------------------------------------------------------------------------
// Phoneme name resolution
// ---------------------------------------------------------------------------

TEST(TimingHelpers, UnknownIdFallsBackToQuestionMark) {
  const std::vector<float> durations = {4.0f};
  const std::vector<PhonemeId> ids = {9999};

  const auto out =
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, kRate, false);

  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].phoneme, "?");
}

TEST(TimingHelpers, PrintableAsciiIdDecodesToItsOwnCharacter) {
  // An id in (2, 128) with no map entry is treated as its own ASCII char.
  const std::vector<float> durations = {4.0f};
  const std::vector<PhonemeId> ids = {static_cast<PhonemeId>('z')};

  const auto out =
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, kRate, false);

  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].phoneme, "z");
}

TEST(TimingHelpers, AsciiFallbackMasksUnmappedIdsWithControlCharacters) {
  // PINS A SHARP EDGE. The "id > 2 && id < 128 -> that ASCII char" fallback
  // runs BEFORE the "?" fallback, so an unmapped id in that range yields a
  // control character rather than an obvious unknown marker. Id 7 becomes BEL.
  // Harmless for shipped models (ids 3..127 are all mapped) but it silently
  // produces an unprintable phoneme name for any that are not.
  const std::vector<float> durations = {4.0f};
  const std::vector<PhonemeId> ids = {7};

  const auto out =
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, kRate, false);

  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].phoneme, std::string(1, '\a'))
      << "not \"?\": the ASCII branch wins for 2 < id < 128";
}

TEST(TimingHelpers, OnlyTheFirstIdOfAMultiIdKeyResolves) {
  // PINS A KNOWN DEFECT. buildPhonemeIdToStringMap registers ids[0] only, so a
  // phoneme carrying several ids resolves for the first and falls back to "?"
  // for the rest. The identical bug was fixed in C# under issue #656; C++ is
  // tracked separately. Pinned so the fix is a deliberate, visible change.
  // Ids are >= 128 on purpose: for 2 < id < 128 the walk falls back to
  // decoding the id as its own ASCII character, which would mask the defect
  // behind a plausible-looking (but wrong) single-char name. Id 7 renders as
  // BEL, not "?" -- verified by running this test with {6, 7}.
  PhonemeIdMap m;
  m[U'b'] = {200, 201};
  const std::vector<float> durations = {4.0f, 4.0f};
  const std::vector<PhonemeId> ids = {200, 201};

  const auto out = computePhonemeTimings(durations, ids, m, kHop, kRate, false);

  ASSERT_EQ(out.size(), 2u);
  EXPECT_EQ(out[0].phoneme, "b");
  EXPECT_EQ(out[1].phoneme, "?") << "second id of the same key is unresolved";
}

TEST(TimingHelpers, PuaRenameOnlyAppliesWhenJapaneseAdjustmentsAreOn) {
  PhonemeIdMap m;
  m[static_cast<char32_t>(0xE019)] = {10};  // N_m
  const std::vector<float> durations = {4.0f};
  const std::vector<PhonemeId> ids = {10};

  const auto off = computePhonemeTimings(durations, ids, m, kHop, kRate, false);
  ASSERT_EQ(off.size(), 1u);
  EXPECT_NE(off[0].phoneme, "N_m") << "raw PUA codepoint when the pass is off";

  const auto on = computePhonemeTimings(durations, ids, m, kHop, kRate, true);
  ASSERT_EQ(on.size(), 1u);
  EXPECT_EQ(on[0].phoneme, "N_m");
}

TEST(TimingHelpers, GeminateOverlapMovesTheBoundaryBackwards) {
  // 'cl' (促音) bleeds 30% of its own span into the previous phoneme: the
  // previous entry's end and the geminate's start both move later by that
  // amount, so the boundary between them shifts.
  PhonemeIdMap m;
  m[U'a'] = {3};
  m[static_cast<char32_t>(0xE005)] = {11};  // cl
  const std::vector<float> durations = {10.0f, 10.0f};
  const std::vector<PhonemeId> ids = {3, 11};

  const auto plain = computePhonemeTimings(durations, ids, m, kHop, kRate, false);
  const auto adjusted = computePhonemeTimings(durations, ids, m, kHop, kRate, true);
  ASSERT_EQ(plain.size(), 2u);
  ASSERT_EQ(adjusted.size(), 2u);

  const double span = 10.0 * frameSeconds();
  const double overlap = span * 0.3;
  EXPECT_NEAR(adjusted[0].end_time, plain[0].end_time + overlap, 1e-6);
  EXPECT_NEAR(adjusted[1].start_time, plain[1].start_time + overlap, 1e-6);
  // The geminate's END is untouched, so its span shrinks.
  EXPECT_NEAR(adjusted[1].end_time, plain[1].end_time, 1e-6);
}

// ---------------------------------------------------------------------------
// Degenerate inputs
// ---------------------------------------------------------------------------

TEST(TimingHelpers, NonPositiveRateOrHopReturnsEmpty) {
  const std::vector<float> durations = {4.0f};
  const std::vector<PhonemeId> ids = {3};
  EXPECT_TRUE(
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, 0, false).empty());
  EXPECT_TRUE(
      computePhonemeTimings(durations, ids, simpleIdMap(), 0, kRate, false).empty());
}

TEST(TimingHelpers, WalkStopsAtTheShorterOfIdsAndDurations) {
  // Strategy A can leave the two out of step; the walk must not read past
  // either end.
  const std::vector<float> durations = {4.0f, 4.0f, 4.0f};
  const std::vector<PhonemeId> ids = {3, 4};

  const auto out =
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, kRate, false);
  EXPECT_EQ(out.size(), 2u);
}

TEST(TimingHelpers, EmptyInputProducesNoEntries) {
  EXPECT_TRUE(computePhonemeTimings({}, {}, simpleIdMap(), kHop, kRate, false)
                  .empty());
}

// ---------------------------------------------------------------------------
// Anti-vacuity: the suite must fail if the helper stops doing anything.
// ---------------------------------------------------------------------------

TEST(TimingHelpersGate, HelperProducesNonTrivialOutput) {
  // A stub returning {} would satisfy several assertions above by accident
  // (the ASSERT_EQ size checks catch it, but only if they run). This is a
  // bare TEST so no fixture SetUp can skip it.
  const std::vector<float> durations = {1.0f, 2.0f, 3.0f};
  const std::vector<PhonemeId> ids = {3, 4, 5};
  const auto out =
      computePhonemeTimings(durations, ids, simpleIdMap(), kHop, kRate, false);
  ASSERT_EQ(out.size(), 3u);
  EXPECT_GT(out[2].end_time, 0.0f);
  EXPECT_GT(out[2].end_time, out[0].end_time);
}
