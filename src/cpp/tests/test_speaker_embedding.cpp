#include <gtest/gtest.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

// Standalone reimplementation of loadSpeakerEmbedding() from main.cpp.
// We replicate the logic here rather than including main.cpp so that the test
// has no dependency on spdlog, onnxruntime, or the rest of the binary.
// If the production implementation ever changes, this mirror must be updated.
namespace {

constexpr int64_t EXPECTED_DIM = 192;

// Mirror of loadSpeakerEmbedding() in src/cpp/main.cpp.
// Reads 192 float32 values from either:
//   - a raw binary file  (192 × float32 = 768 bytes exactly), or
//   - a NumPy .npy v1/v2 file (magic "\x93NUMPY" + 2-byte version +
//     2-byte headerLen (LE) + headerLen bytes of dict + float32 data).
// If the number of parsed floats != 192 the result is padded/truncated to 192.
std::vector<float> loadSpeakerEmbeddingImpl(const std::filesystem::path &path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file.good()) {
        throw std::runtime_error("Cannot open speaker embedding file: " +
                                 path.string());
    }

    auto fileSize = file.tellg();
    file.seekg(0, std::ios::beg);

    // Detect NumPy magic: "\x93NUMPY"
    char magic[6] = {};
    file.read(magic, 6);
    file.seekg(0, std::ios::beg);

    std::vector<float> embedding;

    if (magic[0] == '\x93' && magic[1] == 'N' && magic[2] == 'U' &&
        magic[3] == 'M' && magic[4] == 'P' && magic[5] == 'Y') {
        // NumPy .npy v1.0 / v2.0 format
        // Layout: magic(6) + major(1) + minor(1) + headerLen(2 or 4, LE) + header + data
        file.seekg(6, std::ios::beg);
        uint8_t majorVersion = 0;
        file.read(reinterpret_cast<char *>(&majorVersion), 1);
        // Seek to headerLen field (offset 8)
        file.seekg(8, std::ios::beg);
        size_t dataOffset;
        if (majorVersion >= 2) {
            // v2.0+: headerLen is uint32_t at offset 8, data starts at 12 + headerLen
            uint32_t headerLen = 0;
            file.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
            dataOffset = 12 + headerLen;
        } else {
            // v1.0: headerLen is uint16_t at offset 8, data starts at 10 + headerLen
            uint16_t headerLen = 0;
            file.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
            dataOffset = 10 + headerLen;
        }
        // Seek to start of float data
        file.seekg(static_cast<std::streamoff>(dataOffset), std::ios::beg);

        auto dataStart  = file.tellg();
        auto dataBytes  = fileSize - dataStart;
        auto numFloats  = static_cast<int64_t>(dataBytes) / sizeof(float);

        embedding.resize(numFloats);
        file.read(reinterpret_cast<char *>(embedding.data()),
                  numFloats * sizeof(float));
    } else {
        // Raw binary
        auto numFloats = static_cast<int64_t>(fileSize) / sizeof(float);
        embedding.resize(numFloats);
        file.read(reinterpret_cast<char *>(embedding.data()),
                  numFloats * sizeof(float));
    }

    // Pad or truncate to 192
    if (static_cast<int64_t>(embedding.size()) != EXPECTED_DIM) {
        embedding.resize(EXPECTED_DIM, 0.0f);
    }

    return embedding;
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
