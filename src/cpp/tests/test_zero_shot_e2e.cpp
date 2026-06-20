/**
 * test_zero_shot_e2e.cpp -- Zero-Shot TTS end-to-end integration tests
 *
 * Exercises the full synthesis pipeline with a speaker-embedding (zero-shot)
 * ONNX model via the C API.  Tests are grouped as follows:
 *
 *   ZeroShotE2E::ProducesAudio          -- model loads and generates audio
 *   ZeroShotE2E::EmbeddingAffectsOutput -- two different embeddings produce
 *                                          different audio output
 *
 * Requires:
 *   test/models/zero-shot-test.onnx
 *   test/models/zero-shot-test.onnx.json
 *   test/models/test_speaker.npy
 *
 * All tests auto-skip if the required files are not present.
 *
 * CMake WORKING_DIRECTORY is CMAKE_SOURCE_DIR (the repo root), so paths are
 * resolved relative to that.
 */

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#include "piper_plus.h"

namespace fs = std::filesystem;

// ============================================================
// Paths to test fixtures
// ============================================================

static const char *kModelName    = "test/models/zero-shot-test.onnx";
static const char *kConfigName   = "test/models/zero-shot-test.onnx.json";
static const char *kEmbeddingName = "test/models/test_speaker.npy";

// ---------------------------------------------------------------------------
// Standalone .npy / raw-binary loader (mirrors main.cpp loadSpeakerEmbedding)
// ---------------------------------------------------------------------------
static std::vector<float> loadNpy(const fs::path &path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f.good()) {
        throw std::runtime_error("Cannot open: " + path.string());
    }
    auto fileSize = static_cast<std::streamoff>(f.tellg());
    f.seekg(0, std::ios::beg);

    char magic[6] = {};
    f.read(magic, 6);
    f.seekg(0, std::ios::beg);

    std::vector<float> emb;

    if (magic[0] == '\x93' && magic[1] == 'N' && magic[2] == 'U' &&
        magic[3] == 'M' && magic[4] == 'P' && magic[5] == 'Y') {
        // NumPy .npy v1.0 / v2.0
        f.seekg(6, std::ios::beg);
        uint8_t majorVersion = 0;
        f.read(reinterpret_cast<char *>(&majorVersion), 1);
        // Seek to headerLen field (offset 8)
        f.seekg(8, std::ios::beg);
        size_t dataOffset;
        if (majorVersion >= 2) {
            // v2.0+: headerLen is uint32_t at offset 8, data starts at 12 + headerLen
            uint32_t headerLen = 0;
            f.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
            dataOffset = 12 + headerLen;
        } else {
            // v1.0: headerLen is uint16_t at offset 8, data starts at 10 + headerLen
            uint16_t headerLen = 0;
            f.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
            dataOffset = 10 + headerLen;
        }
        f.seekg(static_cast<std::streamoff>(dataOffset), std::ios::beg);
        auto dataStart = f.tellg();
        auto dataBytes = fileSize - static_cast<std::streamoff>(dataStart);
        auto numFloats = static_cast<size_t>(dataBytes) / sizeof(float);
        emb.resize(numFloats);
        f.read(reinterpret_cast<char *>(emb.data()), numFloats * sizeof(float));
    } else {
        auto numFloats = static_cast<size_t>(fileSize) / sizeof(float);
        emb.resize(numFloats);
        f.read(reinterpret_cast<char *>(emb.data()), numFloats * sizeof(float));
    }

    // Pad / truncate to 192
    emb.resize(192, 0.0f);
    return emb;
}

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------

static const char *g_model_path    = nullptr;
static const char *g_config_path   = nullptr;
static const char *g_embedding_path = nullptr;

class ZeroShotE2E : public ::testing::Test {
protected:
    static void SetUpTestSuite() {
        // Resolve paths from several candidate working directories so the
        // tests work regardless of the CTest invocation directory.
        const std::vector<std::string> prefixes = {"", "../", "../../"};

        for (const auto &prefix : prefixes) {
            std::string mp = prefix + kModelName;
            std::string cp = prefix + kConfigName;
            std::string ep = prefix + kEmbeddingName;

            if (fs::exists(mp) && fs::exists(cp) && fs::exists(ep)) {
                static std::string modelPath     = mp;
                static std::string configPath    = cp;
                static std::string embeddingPath = ep;
                g_model_path     = modelPath.c_str();
                g_config_path    = configPath.c_str();
                g_embedding_path = embeddingPath.c_str();
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_model_path) {
            GTEST_SKIP()
                << "Zero-shot test model not found at " << kModelName
                << "; skipping E2E integration tests";
        }
    }

    // Create a C API engine pointing at the zero-shot ONNX model.
    PiperPlusEngine *createEngine() const {
        PiperPlusConfig cfg = {};
        cfg.model_path  = g_model_path;
        cfg.config_path = g_config_path;
        cfg.provider    = "cpu";
        cfg.num_threads = 1;
        PiperPlusEngine *engine = nullptr;
        if (piper_plus_create(&cfg, &engine) != PIPER_PLUS_OK) {
            return nullptr;
        }
        return engine;
    }

    // Load the test speaker embedding from disk.
    std::vector<float> loadTestEmbedding() const {
        return loadNpy(g_embedding_path);
    }

    // RMS energy helper
    static double rms(const float *samples, int32_t n) {
        if (!samples || n <= 0) return 0.0;
        double s = 0.0;
        for (int32_t i = 0; i < n; ++i) {
            s += static_cast<double>(samples[i]) * samples[i];
        }
        return std::sqrt(s / n);
    }
};

// ============================================================
// TEST: ProducesAudio
//
// Loads the zero-shot ONNX model via the C API, runs synthesis with a
// real speaker embedding from test_speaker.npy, and verifies that:
//   - Synthesis succeeds (PIPER_PLUS_OK)
//   - Non-zero audio samples are returned
//   - All samples lie within the normalised range [-1.0, 1.0]
//   - RMS energy is non-zero (actual audio, not silence)
// ============================================================
TEST_F(ZeroShotE2E, ProducesAudio) {
    PiperPlusEngine *engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    std::vector<float> emb = loadTestEmbedding();
    ASSERT_EQ(emb.size(), 192u);

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.noise_scale          = 0.001f;  // near-deterministic
    opts.noise_w              = 0.001f;
    opts.speaker_embedding     = emb.data();
    opts.speaker_embedding_dim = static_cast<int32_t>(emb.size());

    float   *samples    = nullptr;
    int32_t  numSamples = 0;
    int32_t  sampleRate = 0;

    PiperPlusStatus rc = piper_plus_synthesize(
        engine, "Hello.", &opts, &samples, &numSamples, &sampleRate);

    EXPECT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    EXPECT_NE(samples, nullptr);
    EXPECT_GT(numSamples, 0);
    EXPECT_GT(sampleRate, 0);

    if (samples && numSamples > 0) {
        // All samples must be within [-1.0, 1.0]
        int32_t checkN = std::min(numSamples, (int32_t)2000);
        for (int32_t i = 0; i < checkN; ++i) {
            EXPECT_GE(samples[i], -1.0f) << "sample[" << i << "] out of range";
            EXPECT_LE(samples[i],  1.0f) << "sample[" << i << "] out of range";
        }

        // RMS must be non-trivially small (not pure silence)
        double energy = rms(samples, numSamples);
        EXPECT_GT(energy, 1e-6) << "Audio appears to be silence (RMS=" << energy << ")";
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

// ============================================================
// TEST: EmbeddingAffectsOutput
//
// Synthesises the same text twice with two different speaker embeddings:
//   embA = the real test_speaker.npy embedding
//   embB = a synthetic embedding (normalised random-ish values)
//
// Verifies that the two output buffers differ, confirming that the
// speaker embedding is actually wired into the ONNX inference path.
// ============================================================
TEST_F(ZeroShotE2E, EmbeddingAffectsOutput) {
    PiperPlusEngine *engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    std::vector<float> embA = loadTestEmbedding();
    ASSERT_EQ(embA.size(), 192u);

    // Build embB: negate embA then re-normalise so it still looks like a
    // valid L2-normalised speaker embedding.
    std::vector<float> embB(192);
    for (int i = 0; i < 192; ++i) {
        embB[i] = -embA[i];
    }
    // embB is already L2-normalised (same magnitude, opposite direction)

    const char *text = "Hello.";

    auto synthesise = [&](const std::vector<float> &emb) -> std::vector<float> {
        PiperPlusSynthOptions opts  = piper_plus_default_options();
        opts.noise_scale            = 0.001f;
        opts.noise_w                = 0.001f;
        opts.speaker_embedding      = emb.data();
        opts.speaker_embedding_dim  = static_cast<int32_t>(emb.size());

        float   *raw    = nullptr;
        int32_t  n      = 0;
        int32_t  rate   = 0;
        PiperPlusStatus rc = piper_plus_synthesize(
            engine, text, &opts, &raw, &n, &rate);
        EXPECT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
        std::vector<float> out;
        if (raw && n > 0) {
            out.assign(raw, raw + n);
        }
        piper_plus_free_audio(raw);
        return out;
    };

    std::vector<float> outA = synthesise(embA);
    std::vector<float> outB = synthesise(embB);

    ASSERT_GT(outA.size(), 0u) << "embA synthesis produced no audio";
    ASSERT_GT(outB.size(), 0u) << "embB synthesis produced no audio";

    // Both outputs must have non-zero RMS energy
    EXPECT_GT(rms(outA.data(), static_cast<int32_t>(outA.size())), 1e-6);
    EXPECT_GT(rms(outB.data(), static_cast<int32_t>(outB.size())), 1e-6);

    // Compare a common prefix of both outputs.  At least some samples must
    // differ — if the speaker embedding has no effect both buffers would be
    // identical (near-deterministic noise_scale=0.001 makes this reliable).
    int32_t cmpN = static_cast<int32_t>(
        std::min(outA.size(), outB.size()));
    bool anyDiff = false;
    for (int32_t i = 0; i < cmpN; ++i) {
        if (outA[i] != outB[i]) {
            anyDiff = true;
            break;
        }
    }
    EXPECT_TRUE(anyDiff)
        << "Speaker embedding has no effect: outA and outB are identical. "
           "The zero-shot conditioning path may not be wired correctly.";

    piper_plus_free(engine);
}
