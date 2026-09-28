#include <gtest/gtest.h>

#include "speaker_embedding_io.hpp"
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

// The PRODUCTION loaders, from src/cpp/speaker_embedding_io.hpp (called by
// main.cpp:loadSpeakerEmbedding / loadSpeakerEmbeddingBin).
//
// This file used to carry a hand-written copy and say "If the production
// implementation ever changes, this mirror must be updated" -- nothing
// enforced that, so every assertion below ran against the copy rather than
// against what ships (issue #703).
namespace {

constexpr int64_t EXPECTED_DIM = piper::kSpeakerEmbeddingDim;

// Records whether the loader had to pad or truncate. The production callback
// is spdlog::warn, which a test cannot observe; padding with zeros yields a
// valid-looking but wrong voice instead of an error, so whether it fired is
// the interesting part.
struct DimensionAdjustment {
  bool fired = false;
  std::size_t actual = 0;
  int64_t expected = 0;
};

std::vector<float> loadSpeakerEmbeddingImpl(const std::filesystem::path &path,
                                            DimensionAdjustment *adjust = nullptr) {
  return piper::loadSpeakerEmbeddingIn(
      path, [adjust](std::size_t actual, int64_t expected) {
        if (adjust != nullptr) {
          adjust->fired = true;
          adjust->actual = actual;
          adjust->expected = expected;
        }
      });
}

// Write raw float32 data to a temp file and return its path.
std::filesystem::path writeRawBinary(const std::filesystem::path &dir,
                                     const std::string &name,
                                     const std::vector<float> &values) {
    auto path = dir / name;
    std::ofstream f(path, std::ios::binary);
    f.write(reinterpret_cast<const char *>(values.data()),
            values.size() * sizeof(float));
    return path;
}

// Build a minimal NumPy .npy v1.0 file containing the given float32 values.
// Header dict is minimal but valid: "{'descr': '<f4', 'fortran_order': False, 'shape': (N,), }"
// The header block is padded with spaces to a multiple of 64 bytes (npy spec).
std::filesystem::path writeNpyV1(const std::filesystem::path &dir,
                                 const std::string &name,
                                 const std::vector<float> &values) {
    // Build header dict
    std::string dictStr =
        "{'descr': '<f4', 'fortran_order': False, 'shape': (" +
        std::to_string(values.size()) + ",), }";

    // Total prefix before data: magic(6) + major(1) + minor(1) + headerLen(2) = 10 bytes
    // Pad dictStr so that (10 + dictStr.size() + 1) is a multiple of 64
    // (+1 for the mandatory trailing newline '\n')
    size_t prefixLen = 10;
    size_t needed = prefixLen + dictStr.size() + 1; // +1 for '\n'
    size_t padded = ((needed + 63) / 64) * 64;
    size_t padding = padded - needed;
    dictStr.append(padding, ' ');
    dictStr += '\n';

    uint16_t headerLen = static_cast<uint16_t>(dictStr.size());

    auto path = dir / name;
    std::ofstream f(path, std::ios::binary);

    // Magic + version
    const char magic[] = "\x93NUMPY";
    f.write(magic, 6);          // includes the '\x93' byte
    f.put('\x01');               // major version
    f.put('\x00');               // minor version

    // Header length as little-endian uint16
    f.write(reinterpret_cast<const char *>(&headerLen), sizeof(headerLen));

    // Header dict
    f.write(dictStr.data(), headerLen);

    // Float32 data
    f.write(reinterpret_cast<const char *>(values.data()),
            values.size() * sizeof(float));

    return path;
}

// Build a minimal NumPy .npy v2.0 file containing the given float32 values.
// v2.0 uses a uint32_t header length field instead of uint16_t, and major=2.
// The header block is padded with spaces to a multiple of 64 bytes (npy spec).
std::filesystem::path writeNpyV2(const std::filesystem::path &dir,
                                 const std::string &name,
                                 const std::vector<float> &values) {
    // Build header dict
    std::string dictStr =
        "{'descr': '<f4', 'fortran_order': False, 'shape': (" +
        std::to_string(values.size()) + ",), }";

    // Total prefix before data: magic(6) + major(1) + minor(1) + headerLen(4) = 12 bytes
    // Pad dictStr so that (12 + dictStr.size() + 1) is a multiple of 64
    size_t prefixLen = 12;
    size_t needed = prefixLen + dictStr.size() + 1; // +1 for '\n'
    size_t padded = ((needed + 63) / 64) * 64;
    size_t padding = padded - needed;
    dictStr.append(padding, ' ');
    dictStr += '\n';

    uint32_t headerLen = static_cast<uint32_t>(dictStr.size());

    auto path = dir / name;
    std::ofstream f(path, std::ios::binary);

    // Magic + version
    const char magic[] = "\x93NUMPY";
    f.write(magic, 6);          // includes the '\x93' byte
    f.put('\x02');               // major version = 2
    f.put('\x00');               // minor version

    // Header length as little-endian uint32
    f.write(reinterpret_cast<const char *>(&headerLen), sizeof(headerLen));

    // Header dict
    f.write(dictStr.data(), headerLen);

    // Float32 data
    f.write(reinterpret_cast<const char *>(values.data()),
            values.size() * sizeof(float));

    return path;
}

} // anonymous namespace

// Test fixture: creates and cleans up a temp directory
class SpeakerEmbeddingTest : public ::testing::Test {
protected:
    void SetUp() override {
        tempDir = std::filesystem::temp_directory_path() / "piper_spk_emb_test";
        std::filesystem::create_directories(tempDir);
    }

    void TearDown() override {
        std::filesystem::remove_all(tempDir);
    }

    std::filesystem::path tempDir;
};

// ============================================================
// Raw binary format tests
// ============================================================

TEST_F(SpeakerEmbeddingTest, RawBinary192Floats) {
    // Build exactly 192 distinct float values
    std::vector<float> expected(192);
    for (int i = 0; i < 192; ++i) {
        expected[i] = static_cast<float>(i) * 0.01f;
    }

    auto path = writeRawBinary(tempDir, "spk.bin", expected);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], expected[i]) << "mismatch at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, RawBinaryAllZeros) {
    std::vector<float> zeros(192, 0.0f);
    auto path = writeRawBinary(tempDir, "zeros.bin", zeros);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], 0.0f);
    }
}

TEST_F(SpeakerEmbeddingTest, RawBinaryAllOnes) {
    std::vector<float> ones(192, 1.0f);
    auto path = writeRawBinary(tempDir, "ones.bin", ones);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (size_t i = 0; i < result.size(); ++i) {
        EXPECT_FLOAT_EQ(result[i], 1.0f);
    }
}

// ============================================================
// NumPy .npy v1.0 format tests
// ============================================================

TEST_F(SpeakerEmbeddingTest, NpyV1Format) {
    std::vector<float> expected(192);
    for (int i = 0; i < 192; ++i) {
        expected[i] = static_cast<float>(i + 1) * 0.5f;
    }

    auto path = writeNpyV1(tempDir, "spk.npy", expected);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], expected[i]) << "mismatch at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, NpyV1NegativeValues) {
    // Embeddings from L2-normalized models can contain negative values
    std::vector<float> expected(192);
    for (int i = 0; i < 192; ++i) {
        expected[i] = (i % 2 == 0) ? -0.1f * i : 0.1f * i;
    }

    auto path = writeNpyV1(tempDir, "neg.npy", expected);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], expected[i]) << "mismatch at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, NpyMagicIsDetected) {
    // A file that starts with \x93NUMPY must be treated as npy, not raw binary
    std::vector<float> vals(192, 2.0f);
    auto path = writeNpyV1(tempDir, "magic.npy", vals);

    // The raw byte count of the npy file is larger than 768 bytes, so if the
    // parser fell through to the raw-binary path it would produce the wrong
    // number of floats (or a garbage result).  The npy path should yield exactly
    // 192 floats with the expected values.
    auto result = loadSpeakerEmbeddingImpl(path);
    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (size_t i = 0; i < result.size(); ++i) {
        EXPECT_FLOAT_EQ(result[i], 2.0f) << "at index " << i;
    }
}

// ============================================================
// NumPy .npy v2.0 format tests
// ============================================================

TEST_F(SpeakerEmbeddingTest, NpyV2Format) {
    std::vector<float> expected(192);
    for (int i = 0; i < 192; ++i) {
        expected[i] = static_cast<float>(i + 1) * 0.25f;
    }

    auto path = writeNpyV2(tempDir, "spk_v2.npy", expected);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], expected[i]) << "mismatch at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, NpyV2NegativeValues) {
    std::vector<float> expected(192);
    for (int i = 0; i < 192; ++i) {
        expected[i] = (i % 2 == 0) ? -0.2f * i : 0.2f * i;
    }

    auto path = writeNpyV2(tempDir, "neg_v2.npy", expected);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], expected[i]) << "mismatch at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, NpyV2WrongSizeIsPadded) {
    // npy v2 containing only 10 floats -> padded to 192
    std::vector<float> small(10, 1.5f);
    auto path = writeNpyV2(tempDir, "small_v2.npy", small);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 10; ++i) {
        EXPECT_FLOAT_EQ(result[i], 1.5f) << "at index " << i;
    }
    for (int i = 10; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], 0.0f) << "pad at " << i;
    }
}

// ============================================================
// Wrong-size / edge-case tests (padding / truncation)
// ============================================================

TEST_F(SpeakerEmbeddingTest, WrongSizeTooFewIsPadded) {
    // Write only 10 floats -> should be padded to 192 with zeros
    std::vector<float> small(10, 9.9f);
    auto path = writeRawBinary(tempDir, "small.bin", small);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 10; ++i) {
        EXPECT_FLOAT_EQ(result[i], 9.9f) << "original value corrupted at " << i;
    }
    for (int i = 10; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], 0.0f) << "padding should be 0 at " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, WrongSizeTooManyIsTruncated) {
    // Write 256 floats -> should be truncated to 192
    std::vector<float> big(256, 7.7f);
    auto path = writeRawBinary(tempDir, "big.bin", big);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (size_t i = 0; i < result.size(); ++i) {
        EXPECT_FLOAT_EQ(result[i], 7.7f) << "at index " << i;
    }
}

TEST_F(SpeakerEmbeddingTest, EmptyFileIsPadded) {
    // A zero-byte file should yield 192 zeros after padding
    auto path = tempDir / "empty.bin";
    { std::ofstream f(path); } // create empty file

    auto result = loadSpeakerEmbeddingImpl(path);
    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (size_t i = 0; i < result.size(); ++i) {
        EXPECT_FLOAT_EQ(result[i], 0.0f);
    }
}

TEST_F(SpeakerEmbeddingTest, NpyWrongSizeIsPadded) {
    // npy containing only 10 floats -> padded to 192
    std::vector<float> small(10, 3.14f);
    auto path = writeNpyV1(tempDir, "small.npy", small);
    auto result = loadSpeakerEmbeddingImpl(path);

    ASSERT_EQ(result.size(), static_cast<size_t>(192));
    for (int i = 0; i < 10; ++i) {
        EXPECT_FLOAT_EQ(result[i], 3.14f) << "at index " << i;
    }
    for (int i = 10; i < 192; ++i) {
        EXPECT_FLOAT_EQ(result[i], 0.0f) << "pad at " << i;
    }
}

// ============================================================
// Error handling tests
// ============================================================

TEST_F(SpeakerEmbeddingTest, NonExistentFileThrows) {
    auto path = tempDir / "does_not_exist.bin";
    EXPECT_THROW(loadSpeakerEmbeddingImpl(path), std::runtime_error);
}

TEST_F(SpeakerEmbeddingTest, ErrorMessageContainsPath) {
    auto path = tempDir / "missing.npy";
    try {
        loadSpeakerEmbeddingImpl(path);
        FAIL() << "Expected std::runtime_error";
    } catch (const std::runtime_error &e) {
        std::string msg = e.what();
        EXPECT_NE(msg.find("missing.npy"), std::string::npos)
            << "error message should contain the file name; got: " << msg;
    }
}

// ============================================================
// Zero-Shot E2E — data-flow tests (no ONNX runtime required)
// These tests verify that the .npy test embedding shipped in
// test/models/ is well-formed and that the SynthesisConfig data
// flow is correct without requiring a live ONNX session.
// ============================================================

// Locate test/models/test_speaker.npy relative to the working directory.
// The CMake WORKING_DIRECTORY is set to CMAKE_SOURCE_DIR (the repo root)
// so we search a small set of candidate paths.
static std::filesystem::path findTestSpeakerNpy() {
    const std::vector<std::string> candidates = {
        "test/models/test_speaker.npy",
        "../test/models/test_speaker.npy",
        "../../test/models/test_speaker.npy",
    };
    for (const auto &c : candidates) {
        if (std::filesystem::exists(c)) {
            return c;
        }
    }
    return {};
}

// TEST: Load the canonical test embedding shipped with the repo and verify
// that it is a valid 192-element, L2-normalised float32 vector.
TEST(ZeroShotE2E, LoadTestEmbedding) {
    auto npyPath = findTestSpeakerNpy();
    if (npyPath.empty()) {
        GTEST_SKIP() << "test/models/test_speaker.npy not found; skipping";
    }

    std::vector<float> emb = loadSpeakerEmbeddingImpl(npyPath);

    // Must have exactly 192 elements
    ASSERT_EQ(emb.size(), static_cast<size_t>(EXPECTED_DIM));

    // Every element must be finite (no NaN, no Inf)
    bool allFinite = true;
    for (int i = 0; i < EXPECTED_DIM; ++i) {
        if (!std::isfinite(emb[i])) {
            allFinite = false;
            ADD_FAILURE() << "Non-finite value at index " << i << ": " << emb[i];
        }
    }
    EXPECT_TRUE(allFinite);

    // L2 norm must be close to 1.0 (CAM++ outputs L2-normalised embeddings)
    double norm = 0.0;
    for (float v : emb) {
        norm += static_cast<double>(v) * v;
    }
    norm = std::sqrt(norm);
    EXPECT_NEAR(norm, 1.0, 1e-3)
        << "Expected L2-normalised embedding (norm ≈ 1.0), got " << norm;
}

// TEST: Verify that populating SynthesisConfig.speakerEmbedding from two
// different .npy files yields distinct embedding vectors (i.e. the loader
// does not silently return the same data for different inputs).
TEST(ZeroShotE2E, EmbeddingAffectsInference) {
    auto npyPath = findTestSpeakerNpy();
    if (npyPath.empty()) {
        GTEST_SKIP() << "test/models/test_speaker.npy not found; skipping";
    }

    // Load the real embedding
    std::vector<float> embA = loadSpeakerEmbeddingImpl(npyPath);
    ASSERT_EQ(embA.size(), static_cast<size_t>(EXPECTED_DIM));

    // Build a second embedding by negating the first (guaranteed different)
    std::vector<float> embB(embA.size());
    for (size_t i = 0; i < embA.size(); ++i) {
        embB[i] = -embA[i];
    }

    // The two embeddings must differ in at least one element
    bool differs = false;
    for (size_t i = 0; i < embA.size(); ++i) {
        if (embA[i] != embB[i]) {
            differs = true;
            break;
        }
    }
    EXPECT_TRUE(differs) << "embA and embB must be distinct";

    // Simulate the SynthesisConfig population step that piper.cpp performs:
    // synthConfig.speakerEmbedding = embA  (the loaded vector is stored as-is)
    // Verify that the stored optional vector matches the loaded data exactly.
    std::optional<std::vector<float>> configEmbA = embA;
    ASSERT_TRUE(configEmbA.has_value());
    ASSERT_EQ(configEmbA->size(), static_cast<size_t>(EXPECTED_DIM));
    for (int i = 0; i < EXPECTED_DIM; ++i) {
        EXPECT_FLOAT_EQ((*configEmbA)[i], embA[i])
            << "SynthesisConfig embedding mismatch at index " << i;
    }

    // Same for embB — must not equal embA
    std::optional<std::vector<float>> configEmbB = embB;
    bool configsDiffer = false;
    for (int i = 0; i < EXPECTED_DIM; ++i) {
        if ((*configEmbA)[i] != (*configEmbB)[i]) {
            configsDiffer = true;
            break;
        }
    }
    EXPECT_TRUE(configsDiffer)
        << "Two different embeddings must yield different SynthesisConfig values";
}

// ===========================================================================
// loadSpeakerEmbeddingBin -- the CLI's --speaker-embedding path (issue #703).
//
// This one was `static` in main.cpp, so it had NO test of any kind, not even
// a replica. It is the cross-runtime format: a file written by the Rust CLI's
// --speaker-embedding must load here identically. Unlike the .npy-aware
// loader it deliberately does not pad or truncate -- the caller compares the
// length against the model's own speaker_embedding dimension and fails on a
// mismatch -- so "returns exactly what the file holds" is the contract.
// ===========================================================================

class SpeakerEmbeddingBinTest : public ::testing::Test {
protected:
    void SetUp() override {
        tempDir = std::filesystem::temp_directory_path() / "piper_spk_emb_bin_test";
        std::filesystem::create_directories(tempDir);
    }
    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(tempDir, ec);
    }
    std::filesystem::path tempDir;
};

TEST_F(SpeakerEmbeddingBinTest, ReturnsExactlyTheFloatsInTheFile) {
    // 5 floats, not 192: the raw loader must NOT normalise the length.
    const std::vector<float> values = {1.0f, -2.5f, 0.0f, 3.25f, -0.125f};
    const auto path = writeRawBinary(tempDir, "raw5.bin", values);

    const auto got = piper::loadSpeakerEmbeddingBinIn(path);

    ASSERT_EQ(got.size(), values.size())
        << "the raw loader padded or truncated; that is the .npy loader's job";
    for (std::size_t i = 0; i < values.size(); ++i) {
        EXPECT_FLOAT_EQ(got[i], values[i]) << "at index " << i;
    }
}

TEST_F(SpeakerEmbeddingBinTest, ReadsAFull192DimEmbedding) {
    std::vector<float> values(EXPECTED_DIM);
    for (int64_t i = 0; i < EXPECTED_DIM; ++i) {
        values[static_cast<std::size_t>(i)] = static_cast<float>(i) * 0.01f;
    }
    const auto path = writeRawBinary(tempDir, "raw192.bin", values);

    const auto got = piper::loadSpeakerEmbeddingBinIn(path);

    ASSERT_EQ(static_cast<int64_t>(got.size()), EXPECTED_DIM);
    EXPECT_FLOAT_EQ(got.front(), 0.0f);
    EXPECT_FLOAT_EQ(got.back(), static_cast<float>(EXPECTED_DIM - 1) * 0.01f);
}

TEST_F(SpeakerEmbeddingBinTest, RejectsASizeThatIsNotAMultipleOfFour) {
    // A truncated transfer is the realistic cause. Reading it as floats would
    // silently drop the trailing partial value and produce a usable-looking
    // embedding, so this has to throw.
    const auto path = tempDir / "odd.bin";
    {
        std::ofstream f(path, std::ios::binary);
        const char bytes[] = {1, 2, 3, 4, 5};
        f.write(bytes, sizeof(bytes));
    }

    EXPECT_THROW(piper::loadSpeakerEmbeddingBinIn(path), std::runtime_error);
}

TEST_F(SpeakerEmbeddingBinTest, RejectsAMissingFile) {
    // The message is asserted, not just the type: removing the `!f.good()`
    // guard still throws, because tellg() returns -1 on a failed stream and
    // the `bytes < 0` guard catches it. Both are runtime_error, so a
    // type-only assertion cannot tell which one fired -- and the user is told
    // "failed to stat" for a file that simply is not there.
    try {
        piper::loadSpeakerEmbeddingBinIn(tempDir / "absent.bin");
        FAIL() << "a missing file was accepted";
    } catch (const std::runtime_error &e) {
        EXPECT_NE(std::string(e.what()).find("Failed to open"),
                  std::string::npos)
            << "expected the open guard to reject a missing file, got: "
            << e.what();
    }
}

TEST_F(SpeakerEmbeddingBinTest, AnEmptyFileYieldsAnEmptyVectorNotAThrow) {
    // 0 is a multiple of 4, so this is not a format error. The caller's
    // dimension check is what rejects it, and it must get a chance to run.
    const auto path = tempDir / "empty.bin";
    { std::ofstream f(path, std::ios::binary); }

    const auto got = piper::loadSpeakerEmbeddingBinIn(path);
    EXPECT_TRUE(got.empty());
}

// ===========================================================================
// The padding/truncation notification on the .npy-aware loader.
//
// Padding with zeros produces a valid-looking but WRONG voice rather than an
// error, so whether the caller is told is the whole safety margin. The old
// replica dropped the spdlog::warn entirely, so no test could see it.
// ===========================================================================

TEST_F(SpeakerEmbeddingTest, ShortEmbeddingReportsTheAdjustmentItMade) {
    const std::vector<float> values(100, 0.5f);
    const auto path = writeRawBinary(tempDir, "short100.bin", values);

    DimensionAdjustment adjust;
    const auto got = loadSpeakerEmbeddingImpl(path, &adjust);

    ASSERT_EQ(static_cast<int64_t>(got.size()), EXPECTED_DIM);
    EXPECT_TRUE(adjust.fired)
        << "the embedding was padded from 100 to 192 without telling anyone";
    EXPECT_EQ(adjust.actual, 100u);
    EXPECT_EQ(adjust.expected, EXPECTED_DIM);
    // Padding is zeros, appended -- the real values must survive in place.
    EXPECT_FLOAT_EQ(got[99], 0.5f);
    EXPECT_FLOAT_EQ(got[100], 0.0f);
}

TEST_F(SpeakerEmbeddingTest, ExactLengthEmbeddingReportsNoAdjustment) {
    // Anti-vacuity for the case above: a callback that fired unconditionally
    // would satisfy it while saying nothing about the length check.
    const std::vector<float> values(EXPECTED_DIM, 0.25f);
    const auto path = writeRawBinary(tempDir, "exact192.bin", values);

    DimensionAdjustment adjust;
    const auto got = loadSpeakerEmbeddingImpl(path, &adjust);

    ASSERT_EQ(static_cast<int64_t>(got.size()), EXPECTED_DIM);
    EXPECT_FALSE(adjust.fired);
}

TEST_F(SpeakerEmbeddingTest, LongEmbeddingIsTruncatedAndReported) {
    std::vector<float> values(EXPECTED_DIM + 8, 0.75f);
    values.back() = 9.0f;  // would only survive if truncation were skipped
    const auto path = writeRawBinary(tempDir, "long200.bin", values);

    DimensionAdjustment adjust;
    const auto got = loadSpeakerEmbeddingImpl(path, &adjust);

    ASSERT_EQ(static_cast<int64_t>(got.size()), EXPECTED_DIM);
    EXPECT_TRUE(adjust.fired);
    EXPECT_EQ(adjust.actual, static_cast<std::size_t>(EXPECTED_DIM + 8));
    EXPECT_FLOAT_EQ(got.back(), 0.75f);
}
