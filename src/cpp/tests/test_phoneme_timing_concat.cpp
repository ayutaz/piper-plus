/**
 * test_phoneme_timing_concat.cpp — unit tests for the phoneme-timing
 * concatenation cursor (issue #652).
 *
 * Issue #652: when one text->audio call ran more than one `synthesize()`
 * inference, the aggregating functions in `src/cpp/piper.cpp` dropped every
 * unit's phoneme timings instead of shifting and concatenating them. The fix
 * factors the shift into `piper_plus::timing::appendShifted` /
 * `ConcatCursor`; this file pins that arithmetic.
 *
 * This is NOT a #652 reproducer — it neither loads a model nor links
 * piper.cpp, so it stays green on `dev`. What it guards is the layer the
 * reproducers cannot localise: the half-fixes that compute frames without the
 * hop divide, advance the cursor past a skipped empty unit, pick the wrong
 * silence tier or divide by a zero-valued config field. Those show up here in
 * milliseconds instead of behind a 39 MB model load, and it keeps running in
 * sanitizer jobs and on machines without the fixture model.
 */

#include <gtest/gtest.h>

#include <cstddef>
#include <string>
#include <vector>

#include "phoneme_timing_concat.hpp"

namespace {

using piper_plus::timing::ConcatCursor;

// Stand-in for `piper::PhonemeInfo` (piper.hpp:135-141). Mirrored here on
// purpose: piper.hpp pulls in <onnxruntime_cxx_api.h>, which this model-free
// target deliberately does not link. `appendShifted` is templated so the
// production code instantiates it for the real type and this test for the
// stand-in.
struct Entry {
    std::string phoneme;
    float start_time = 0.0f;
    float end_time = 0.0f;
    int start_frame = 0;
    int end_frame = 0;
};

std::vector<Entry> makeUnit() {
    return {
        Entry{"o", 0.0f, 0.25f, 0, 21},
        Entry{"l", 0.25f, 0.50f, 21, 43},
    };
}

void expectEntryEq(const Entry &actual, const Entry &expected,
                   const std::string &where) {
    EXPECT_EQ(actual.phoneme, expected.phoneme) << where;
    EXPECT_EQ(actual.start_time, expected.start_time) << where;
    EXPECT_EQ(actual.end_time, expected.end_time) << where;
    EXPECT_EQ(actual.start_frame, expected.start_frame) << where;
    EXPECT_EQ(actual.end_frame, expected.end_frame) << where;
}

} // namespace

// Case 1: the first unit always carries a zero cursor, so single-unit output
// (every fixture and every other runtime) must stay bit-identical.
TEST(TimingConcatTest, ZeroCursorIsBitIdenticalIdentity) {
    const std::vector<Entry> unit = makeUnit();
    std::vector<Entry> out;

    piper_plus::timing::appendShifted(out, unit, ConcatCursor{});

    ASSERT_EQ(out.size(), unit.size());
    for (std::size_t i = 0; i < unit.size(); ++i) {
        expectEntryEq(out[i], unit[i], "entry " + std::to_string(i));
    }
}

// Case 2: a follower unit shifts by exactly samples / (sampleRate * channels)
// seconds — the inter-unit silence tier the aggregators actually emit.
TEST(TimingConcatTest, SecondUnitShiftsBySilenceSeconds) {
    const std::vector<Entry> unit = makeUnit();
    // 4410 samples == the 0.2 s default sentence silence at 22050 Hz mono.
    const ConcatCursor cursor{4410, 22050, 1, 256};
    EXPECT_DOUBLE_EQ(cursor.seconds(), 0.2);

    std::vector<Entry> out;
    piper_plus::timing::appendShifted(out, unit, cursor);

    ASSERT_EQ(out.size(), unit.size());
    const float offset = static_cast<float>(cursor.seconds());
    for (std::size_t i = 0; i < unit.size(); ++i) {
        EXPECT_FLOAT_EQ(out[i].start_time, unit[i].start_time + offset);
        EXPECT_FLOAT_EQ(out[i].end_time, unit[i].end_time + offset);
    }
}

// Case 3: frame fields shift by samples / (hopSize * channels), with hopSize
// defaulting to the VITS 256 when the config does not declare one.
TEST(TimingConcatTest, FramesShiftByHopSizeWithDefaultFallback) {
    EXPECT_EQ(ConcatCursor{}.hopSize, 256);

    const std::vector<Entry> unit = makeUnit();
    // hopSize is left to its default, as the aggregators do when
    // configRoot["audio"]["hop_size"] is absent.
    const ConcatCursor cursor{9990, 22050, 1};
    ASSERT_EQ(cursor.hopSize, 256);
    EXPECT_EQ(cursor.frames(), 9990u / 256u);

    std::vector<Entry> out;
    piper_plus::timing::appendShifted(out, unit, cursor);

    ASSERT_EQ(out.size(), unit.size());
    const int offsetFrames = static_cast<int>(cursor.frames());
    EXPECT_EQ(offsetFrames, 39);
    for (std::size_t i = 0; i < unit.size(); ++i) {
        EXPECT_EQ(out[i].start_frame, unit[i].start_frame + offsetFrames);
        EXPECT_EQ(out[i].end_frame, unit[i].end_frame + offsetFrames);
    }
}

// Case 4: an empty unit (the `phrasePhonemes[q]->size() <= 0` continue guard
// in the phrase loops) must append nothing and disturb nothing.
TEST(TimingConcatTest, EmptyUnitIsANoOp) {
    std::vector<Entry> out = {Entry{"a", 0.1f, 0.2f, 8, 17}};
    const std::vector<Entry> before = out;
    const std::vector<Entry> empty;

    piper_plus::timing::appendShifted(out, empty, ConcatCursor{12345, 22050, 1, 256});

    ASSERT_EQ(out.size(), before.size());
    expectEntryEq(out[0], before[0], "entry 0");
}

// Case 5: appending onto a non-empty destination leaves the earlier entries
// untouched and keeps start_time non-decreasing across the unit boundary.
TEST(TimingConcatTest, AppendingOntoNonEmptyOutPreservesMonotonicity) {
    const std::vector<Entry> unit = makeUnit();
    std::vector<Entry> out;

    piper_plus::timing::appendShifted(out, unit, ConcatCursor{});
    const std::vector<Entry> firstUnit = out;
    piper_plus::timing::appendShifted(out, unit, ConcatCursor{9990, 22050, 1, 256});

    ASSERT_EQ(out.size(), 2 * unit.size());
    for (std::size_t i = 0; i < firstUnit.size(); ++i) {
        expectEntryEq(out[i], firstUnit[i], "preserved entry " + std::to_string(i));
    }
    for (std::size_t i = 1; i < out.size(); ++i) {
        EXPECT_GE(out[i].start_time, out[i - 1].start_time)
            << "start_time regressed at entry " << i;
        EXPECT_GE(out[i].start_frame, out[i - 1].start_frame)
            << "start_frame regressed at entry " << i;
    }
}

// Case 6: `channels` sits in both divisors because the aggregators count
// interleaved samples (`seconds * sampleRate * channels`). Doubling the
// channel count therefore halves the offset for the same sample count.
TEST(TimingConcatTest, StereoHalvesTheOffsetForTheSameSampleCount) {
    const ConcatCursor mono{8820, 22050, 1, 256};
    const ConcatCursor stereo{8820, 22050, 2, 256};

    EXPECT_DOUBLE_EQ(mono.seconds(), 0.4);
    EXPECT_DOUBLE_EQ(stereo.seconds(), 0.2);
    EXPECT_DOUBLE_EQ(stereo.seconds(), mono.seconds() / 2.0);
    EXPECT_EQ(mono.frames(), 8820u / 256u);
    EXPECT_EQ(stereo.frames(), 8820u / 512u);
}

// Case 7: a non-positive divisor returns 0 rather than dividing, so a
// malformed config cannot turn a timing offset into UB.
TEST(TimingConcatTest, NonPositiveDivisorsReturnZero) {
    EXPECT_DOUBLE_EQ((ConcatCursor{9990, 0, 1, 256}).seconds(), 0.0);
    EXPECT_DOUBLE_EQ((ConcatCursor{9990, -22050, 1, 256}).seconds(), 0.0);
    EXPECT_EQ((ConcatCursor{9990, 22050, 1, 0}).frames(), 0u);
    EXPECT_EQ((ConcatCursor{9990, 22050, 1, -256}).frames(), 0u);

    const std::vector<Entry> unit = makeUnit();
    std::vector<Entry> out;
    piper_plus::timing::appendShifted(out, unit, ConcatCursor{9990, 0, 1, 0});

    ASSERT_EQ(out.size(), unit.size());
    for (std::size_t i = 0; i < unit.size(); ++i) {
        expectEntryEq(out[i], unit[i], "entry " + std::to_string(i));
    }
}
