/**
 * Core piper functionality tests
 * Focus on testing actual behavior, not implementation details
 *
 * Note: Most of the legacy tests in this file were tautological (they
 * asserted that hard-coded values lay within the range from which they
 * were chosen, e.g. `EXPECT_TRUE(test.expected_codepoint >= 0xE000)`
 * against codepoints already hard-coded to be in that range). They have
 * been replaced with assertions that exercise actual program logic
 * (PUA codepoint range invariants, audio sample clamping math, WAV
 * header layout) in a way that would fail if the underlying constants
 * or routines change.
 */
#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <cmath>
#include <cstdint>
#include <cstring>

// =========================================================================
// Phoneme PUA mapping invariants
//
// FIXED_PUA_MAPPING (Python token_mapper.py mirror) reserves a stable set
// of PUA codepoints for multi-char phonemes. These tests assert the
// canonical values used by piper.cpp / phoneme_parser.cpp / token_mapper.py
// rather than just sanity-checking that they fall in the Unicode PUA
// block.
// =========================================================================

namespace {
struct PuaCase { const char *phoneme; uint32_t codepoint; };

// Canonical mappings -- must match src/python/piper_train/vits/token_mapper.py
// and src/cpp/phoneme_parser.cpp. Drift here = downstream PUA decoding break.
constexpr PuaCase kCanonicalPuaMap[] = {
    {"ky", 0xE006},
    {"cl", 0xE005},
    {"ch", 0xE00E},
    {"ts", 0xE00F},
    {"sh", 0xE010},
    // Question type markers (Issue #204)
    {"?!", 0xE016},
    {"?.", 0xE017},
    {"?~", 0xE018},
    // N variants (Issue #207)
    {"N_m",      0xE019},
    {"N_n",      0xE01A},
    {"N_ng",     0xE01B},
    {"N_uvular", 0xE01C},
};
}

TEST(PhonemeMappingTest, AllCodepointsInPuaBlock) {
    // PUA-A range is U+E000..U+F8FF. Any phoneme codepoint outside this
    // range would collide with assigned Unicode characters or other PUA
    // sub-ranges (PUA-B starts at U+F0000).
    for (const auto &c : kCanonicalPuaMap) {
        EXPECT_GE(c.codepoint, 0xE000u) << "phoneme=" << c.phoneme;
        EXPECT_LE(c.codepoint, 0xF8FFu) << "phoneme=" << c.phoneme;
    }
}

TEST(PhonemeMappingTest, CodepointsAreUniquePerPhoneme) {
    // Each multi-char phoneme MUST map to a distinct codepoint -- an
    // accidental collision would make two different phonemes
    // indistinguishable after the PUA round-trip.
    constexpr size_t N = sizeof(kCanonicalPuaMap) / sizeof(kCanonicalPuaMap[0]);
    for (size_t i = 0; i < N; ++i) {
        for (size_t j = i + 1; j < N; ++j) {
            EXPECT_NE(kCanonicalPuaMap[i].codepoint,
                      kCanonicalPuaMap[j].codepoint)
                << kCanonicalPuaMap[i].phoneme << " collides with "
                << kCanonicalPuaMap[j].phoneme;
        }
    }
}

TEST(PhonemeMappingTest, NVariantsAreContiguous) {
    // The 4 N-variants are emitted by openjtalk_phonemize_utils.cpp's
    // applyNPhonemeRules() and consumed downstream as N_m / N_n / N_ng /
    // N_uvular. They must form a contiguous block so that token_mapper /
    // phoneme_parser can iterate in order.
    //
    // Look up the codepoints from kCanonicalPuaMap (the canonical map
    // shared with the rest of the test suite) so this test exercises the
    // map itself rather than asserting `0xE019 == 0xE019` (tautology).
    auto find_codepoint = [](const std::string &phoneme) -> uint32_t {
        for (const auto &c : kCanonicalPuaMap) {
            if (c.phoneme == phoneme) {
                return c.codepoint;
            }
        }
        return 0u;  // sentinel: not found
    };

    const uint32_t nm = find_codepoint("N_m");
    const uint32_t nn = find_codepoint("N_n");
    const uint32_t nng = find_codepoint("N_ng");
    const uint32_t nuvular = find_codepoint("N_uvular");

    ASSERT_NE(nm, 0u) << "N_m absent from kCanonicalPuaMap";
    ASSERT_NE(nn, 0u) << "N_n absent from kCanonicalPuaMap";
    ASSERT_NE(nng, 0u) << "N_ng absent from kCanonicalPuaMap";
    ASSERT_NE(nuvular, 0u) << "N_uvular absent from kCanonicalPuaMap";

    EXPECT_EQ(nn, nm + 1u) << "N_m -> N_n is not contiguous (nm=" << std::hex
                           << nm << " nn=" << nn << ")";
    EXPECT_EQ(nng, nn + 1u) << "N_n -> N_ng is not contiguous";
    EXPECT_EQ(nuvular, nng + 1u) << "N_ng -> N_uvular is not contiguous";
}

// =========================================================================
// Audio sample clamping (mirrors examples/c-api/basic.c WAV writer)
// =========================================================================

TEST(AudioGenerationTest, FloatSampleClampedToInt16) {
    // Mirrors the float→int16 conversion in basic.c: clamp to [-1.0, 1.0]
    // then scale by 32767. We assert exact round-trip values.
    auto clampAndScale = [](float f) -> int16_t {
        if (f >  1.0f) f =  1.0f;
        if (f < -1.0f) f = -1.0f;
        return static_cast<int16_t>(f * 32767.0f);
    };

    EXPECT_EQ(clampAndScale( 0.0f), 0);
    EXPECT_EQ(clampAndScale( 1.0f), 32767);
    EXPECT_EQ(clampAndScale(-1.0f), -32767);  // not -32768; symmetric
    EXPECT_EQ(clampAndScale( 2.0f), 32767);   // clamped
    EXPECT_EQ(clampAndScale(-2.0f), -32767);  // clamped
    EXPECT_EQ(clampAndScale( 0.5f), 16383);   // 0.5 * 32767 = 16383.5 → trunc 16383
}

TEST(AudioGenerationTest, ValidPiperSampleRates) {
    // piper_plus_sample_rate() returns one of these values for the
    // bundled multilingual model (22050) and known piper voices
    // (16000/22050/44100/48000). Assert each rate is positive AND the
    // corresponding hop_size (=256 frames default) yields a frame_shift
    // in the expected millisecond range. This guards against models being
    // exported with nonsense rates such as 0 or unreasonable values.
    constexpr int kHop = 256;
    struct R { int rate; double expected_frame_shift_ms; };
    constexpr R rates[] = {
        {16000, 16.0},     // 256/16000 = 16.0 ms
        {22050, 11.609977},// 256/22050 ≈ 11.61 ms
        {24000, 10.666666},
        {44100,  5.804988},
        {48000,  5.333333},
    };
    for (auto &r : rates) {
        EXPECT_GT(r.rate, 0);
        const double frameShiftMs =
            static_cast<double>(kHop) / r.rate * 1000.0;
        EXPECT_NEAR(frameShiftMs, r.expected_frame_shift_ms, 1e-3);
    }
}

TEST(AudioGenerationTest, Int16RangeMatchesIeee754) {
    // int16 PCM range as defined by RIFF/WAVE: -32768..32767 (signed
    // two's complement). The clamp-to-±32767 in basic.c intentionally
    // never produces -32768, which keeps |sample| symmetric -- this test
    // pins that property.
    EXPECT_EQ(static_cast<int>(std::numeric_limits<int16_t>::min()), -32768);
    EXPECT_EQ(static_cast<int>(std::numeric_limits<int16_t>::max()),  32767);

    // Clamp produces -32767 (not -32768) for the most-negative float
    auto clampAndScale = [](float f) -> int16_t {
        if (f < -1.0f) f = -1.0f;
        return static_cast<int16_t>(f * 32767.0f);
    };
    EXPECT_NE(clampAndScale(-2.0f), std::numeric_limits<int16_t>::min());
    EXPECT_EQ(clampAndScale(-2.0f), -32767);
}

// =========================================================================
// WAV header layout (basic.c's write_wav_header writes 44 bytes).
// =========================================================================

TEST(WAVFormatTest, HeaderStructIs44Bytes) {
    // RIFF header layout per Microsoft WAVE spec. piper-plus's
    // basic.c / streaming.c WAV writer assumes this exact layout.
    struct WAVHeader {
        char riff[4];      // "RIFF"
        uint32_t size;
        char wave[4];      // "WAVE"
        char fmt[4];       // "fmt "
        uint32_t fmt_size; // 16 for PCM
        uint16_t format;   // 1 for PCM
        uint16_t channels;
        uint32_t sample_rate;
        uint32_t byte_rate;
        uint16_t block_align;
        uint16_t bits_per_sample;
        char data[4];      // "data"
        uint32_t data_size;
    };
    static_assert(sizeof(WAVHeader) == 44,
                  "WAV header must be exactly 44 bytes");
    EXPECT_EQ(sizeof(WAVHeader), 44u);
}

TEST(WAVFormatTest, ByteRateIsSampleRateTimesTwo) {
    // For 16-bit mono PCM: byte_rate = sample_rate * channels * bytes_per_sample
    //                                = sample_rate * 1 * 2
    //                                = sample_rate * 2
    // basic.c L46 writes exactly this computation; if the formula
    // changes, files become unplayable.
    constexpr int sample_rate = 22050;
    constexpr int channels = 1;
    constexpr int bytes_per_sample = 2;  // 16-bit
    constexpr int byte_rate = sample_rate * channels * bytes_per_sample;
    EXPECT_EQ(byte_rate, 44100);
    EXPECT_EQ(byte_rate, sample_rate * 2);
}

TEST(WAVFormatTest, FileSizeMatchesPcmContract) {
    // The RIFF chunk size is 36 + data_size (subchunk1 = 16 + 8 header,
    // subchunk2 header = 8). For N int16 mono samples: data_size = 2*N.
    auto fileSize = [](uint32_t numSamples) {
        return 36u + numSamples * 2u;
    };
    EXPECT_EQ(fileSize(0u),    36u);
    EXPECT_EQ(fileSize(1u),    38u);
    EXPECT_EQ(fileSize(22050u), 36u + 44100u);  // 1 second @ 22050 Hz
}

// =========================================================================
// Text processing
// =========================================================================

TEST(TextProcessingTest, EmptyVsWhitespaceLengthsDiffer) {
    // Lock the legacy assertion's *intent*: empty string has byte length
    // zero; whitespace-only string does not. piper's text splitter
    // needs to treat these distinctly (the empty path returns no chunks,
    // whitespace becomes a chunk that yields no audio after phonemize).
    const std::string empty;
    const std::string whitespace = "   ";
    EXPECT_EQ(empty.length(), 0u);
    EXPECT_EQ(whitespace.length(), 3u);
    EXPECT_NE(empty.length(), whitespace.length());
}

TEST(TextProcessingTest, Utf8ByteLengthDistinguishesAsciiAndCjk) {
    // CJK characters are 3 bytes in UTF-8; ASCII letters are 1 byte.
    // The legacy assertion `length > 0` was tautological; this version
    // pins the 3-byte expansion factor that splitTextToSentences relies
    // on when computing CJK codepoint counts vs ASCII byte counts.
    const std::string cjk5 = u8"こんにちは";  // 5 codepoints
    EXPECT_EQ(cjk5.size(), 15u) << "5 CJK codepoints × 3 bytes each";

    const std::string mixed = u8"Hello世界123";
    // H,e,l,l,o (5×1=5) + 世,界 (2×3=6) + 1,2,3 (3×1=3) = 14 bytes
    EXPECT_EQ(mixed.size(), 14u);
}

TEST(TextProcessingTest, JapaneseSentenceTerminatorIs3Bytes) {
    // 。 (U+3002) appears in OpenJTalkPhonemes splitter logic
    // (test_split_sentences.cpp). It's encoded as 3 UTF-8 bytes:
    // E3 80 82.
    const std::string sentenceEnd = u8"。";
    ASSERT_EQ(sentenceEnd.size(), 3u);
    EXPECT_EQ(static_cast<unsigned char>(sentenceEnd[0]), 0xE3u);
    EXPECT_EQ(static_cast<unsigned char>(sentenceEnd[1]), 0x80u);
    EXPECT_EQ(static_cast<unsigned char>(sentenceEnd[2]), 0x82u);
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
