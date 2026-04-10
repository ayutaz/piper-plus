/**
 * test_c_api_audio_regression.cpp -- C API audio regression tests (M5-21)
 *
 * Verifies that C API synthesis output does not regress across refactors
 * and version updates. Uses near-deterministic synthesis (noise_scale=0.001,
 * noise_w=0.001) and checks:
 *   1. Sample count is within expected range
 *   2. RMS energy is non-zero and within plausible bounds
 *   3. Streaming vs one-shot produce similar sample counts
 *
 * NOTE: noise_scale=0.0 is replaced with defaults by the C API zero-init
 * safety logic, so we use 0.001 for near-deterministic output.
 *
 * Requires test model at test/models/multilingual-test-medium.onnx
 * Auto-skips if model not found.
 */

#include <gtest/gtest.h>
#include <filesystem>
#include <cmath>
#include <cstring>
#include <algorithm>
#include <numeric>
#include <vector>
#include "piper_plus.h"

namespace fs = std::filesystem;

// Test model paths (shared across all tests in this file)
static const char* g_model_path = nullptr;
static const char* g_config_path = nullptr;

class AudioRegressionTest : public ::testing::Test {
protected:
    static void SetUpTestSuite() {
        std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };
        for (const auto& path : searchPaths) {
            if (fs::exists(path)) {
                static std::string modelPath = path;
                g_model_path = modelPath.c_str();
                // config_path is optional; piper_plus_create defaults to model_path + ".json"
                static std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_config_path = configPath.c_str();
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_model_path) {
            GTEST_SKIP() << "Test model not found; skipping audio regression test";
        }
    }

    PiperPlusEngine* createEngine() {
        PiperPlusConfig config = {};
        config.model_path = g_model_path;
        config.config_path = g_config_path;
        config.provider = "cpu";
        config.num_threads = 1;
        PiperPlusEngine* engine = nullptr;
        PiperPlusStatus rc = piper_plus_create(&config, &engine);
        if (rc != PIPER_PLUS_OK) return nullptr;
        return engine;
    }

    /**
     * Create synthesis options for near-deterministic output.
     * noise_scale=0.001, noise_w=0.001 produce nearly identical output
     * across runs while avoiding the zero-init default replacement.
     */
    PiperPlusSynthOptions deterministicOptions(int32_t language_id = -1) {
        PiperPlusSynthOptions opts = piper_plus_default_options();
        opts.noise_scale = 0.001f;
        opts.noise_w = 0.001f;
        opts.language_id = language_id;
        opts.speaker_id = 0;
        return opts;
    }

    /**
     * Compute RMS (root mean square) energy of audio samples.
     */
    static double computeRMS(const float* samples, int32_t num_samples) {
        if (!samples || num_samples <= 0) return 0.0;
        double sum_sq = 0.0;
        for (int32_t i = 0; i < num_samples; i++) {
            sum_sq += static_cast<double>(samples[i]) * samples[i];
        }
        return std::sqrt(sum_sq / num_samples);
    }
};

// ===== Test 1: Japanese greeting -- sample count and RMS =====

TEST_F(AudioRegressionTest, JA_Greeting) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = deterministicOptions(/*language_id=*/0);  // JA

    PiperPlusStatus rc = piper_plus_synthesize(engine,
        u8"こんにちは", &opts,
        &samples, &num_samples, &sample_rate);

    if (rc == PIPER_PLUS_OK && num_samples == 0) {
        piper_plus_free_audio(samples);
        piper_plus_free(engine);
        GTEST_SKIP() << "Japanese phonemization unavailable (OpenJTalk not loaded)";
    }

    EXPECT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    EXPECT_NE(samples, nullptr);

    // Sample count within expected range (baseline: 10000-50000)
    EXPECT_GE(num_samples, 10000)
        << "JA greeting produced too few samples: " << num_samples;
    EXPECT_LE(num_samples, 50000)
        << "JA greeting produced too many samples: " << num_samples;

    // Sample rate should be 22050 Hz
    EXPECT_EQ(sample_rate, 22050);

    // RMS energy check: should be non-zero (not silence)
    double rms = computeRMS(samples, num_samples);
    EXPECT_GT(rms, 0.001)
        << "JA greeting RMS too low (near silence): " << rms;
    // RMS should not be unreasonably high (clipped audio)
    EXPECT_LT(rms, 0.5)
        << "JA greeting RMS too high (possible clipping): " << rms;

    // All samples should be in [-1.0, 1.0]
    for (int32_t i = 0; i < num_samples; i++) {
        EXPECT_GE(samples[i], -1.0f);
        EXPECT_LE(samples[i], 1.0f);
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

// ===== Test 2: English greeting -- sample count and RMS =====

TEST_F(AudioRegressionTest, EN_Greeting) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = deterministicOptions(/*language_id=*/-1);  // auto-detect

    PiperPlusStatus rc = piper_plus_synthesize(engine,
        "Hello", &opts,
        &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    EXPECT_NE(samples, nullptr);

    // Sample count within expected range (baseline: 5000-30000)
    EXPECT_GE(num_samples, 5000)
        << "EN greeting produced too few samples: " << num_samples;
    EXPECT_LE(num_samples, 30000)
        << "EN greeting produced too many samples: " << num_samples;

    // Sample rate should be 22050 Hz
    EXPECT_EQ(sample_rate, 22050);

    // RMS energy check
    double rms = computeRMS(samples, num_samples);
    EXPECT_GT(rms, 0.001)
        << "EN greeting RMS too low (near silence): " << rms;
    EXPECT_LT(rms, 0.5)
        << "EN greeting RMS too high (possible clipping): " << rms;

    // All samples should be in [-1.0, 1.0]
    for (int32_t i = 0; i < num_samples; i++) {
        EXPECT_GE(samples[i], -1.0f);
        EXPECT_LE(samples[i], 1.0f);
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

// ===== Test 3: Streaming vs one-shot parity =====

TEST_F(AudioRegressionTest, Streaming_vs_OneShot) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    // Use multi-sentence text long enough to avoid short-text padding
    // (MIN_PHONEME_IDS=40 in piper.cpp). Short texts trigger pad+trim in
    // one-shot but not streaming, causing sample count divergence.
    const char* text = u8"Hello world, how are you doing today? This is a test of the synthesis engine.";
    auto opts = deterministicOptions(/*language_id=*/-1);  // auto-detect

    // --- One-shot synthesis ---
    float* samples = nullptr;
    int32_t oneShotCount = 0, sample_rate = 0;
    PiperPlusStatus rc = piper_plus_synthesize(engine, text, &opts,
        &samples, &oneShotCount, &sample_rate);
    ASSERT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    ASSERT_GT(oneShotCount, 0);

    // Compute one-shot RMS for comparison
    double oneShotRMS = computeRMS(samples, oneShotCount);
    piper_plus_free_audio(samples);

    // --- Streaming (iterator) synthesis ---
    rc = piper_plus_synth_start(engine, text, &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();

    int32_t streamTotal = 0;
    std::vector<float> streamSamples;

    for (;;) {
        PiperPlusAudioChunk chunk = {};
        PiperPlusStatus chunkRc = piper_plus_synth_next(engine, &chunk);
        ASSERT_GE(chunkRc, 0) << "synth_next failed: " << piper_plus_get_last_error();
        if (chunk.num_samples > 0) {
            streamTotal += chunk.num_samples;
            streamSamples.insert(streamSamples.end(),
                chunk.samples, chunk.samples + chunk.num_samples);
        }
        if (chunkRc == PIPER_PLUS_DONE) break;
    }

    EXPECT_GT(streamTotal, 0);

    // Sample counts should be within 20% of each other
    // (Debug builds on macOS show ~15% divergence due to FP precision)
    double ratio = static_cast<double>(streamTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.80)
        << "Streaming produced significantly fewer samples than one-shot: "
        << streamTotal << " vs " << oneShotCount;
    EXPECT_LT(ratio, 1.20)
        << "Streaming produced significantly more samples than one-shot: "
        << streamTotal << " vs " << oneShotCount;

    // RMS values should be in the same ballpark
    double streamRMS = computeRMS(streamSamples.data(),
                                   static_cast<int32_t>(streamSamples.size()));
    if (oneShotRMS > 0.001) {
        double rmsRatio = streamRMS / oneShotRMS;
        EXPECT_GT(rmsRatio, 0.5)
            << "Streaming RMS significantly lower than one-shot: "
            << streamRMS << " vs " << oneShotRMS;
        EXPECT_LT(rmsRatio, 2.0)
            << "Streaming RMS significantly higher than one-shot: "
            << streamRMS << " vs " << oneShotRMS;
    }

    piper_plus_free(engine);
}

// ===== Test 4: Deterministic consistency =====

TEST_F(AudioRegressionTest, DeterministicConsistency) {
    // Two runs with identical parameters should produce very similar output.
    // With noise_scale=0.001, noise_w=0.001, variation should be minimal.
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    auto opts = deterministicOptions(/*language_id=*/0);

    // Run 1
    float* samples1 = nullptr;
    int32_t count1 = 0, rate1 = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, u8"テスト", &opts,
              &samples1, &count1, &rate1), PIPER_PLUS_OK);

    // Run 2
    float* samples2 = nullptr;
    int32_t count2 = 0, rate2 = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, u8"テスト", &opts,
              &samples2, &count2, &rate2), PIPER_PLUS_OK);

    // Sample counts should be identical for near-deterministic synthesis
    EXPECT_EQ(count1, count2)
        << "Deterministic runs produced different sample counts";

    // If counts match, compare RMS
    double rms1 = computeRMS(samples1, count1);
    double rms2 = computeRMS(samples2, count2);
    if (rms1 > 0.001 && rms2 > 0.001) {
        double rmsRatio = rms1 / rms2;
        EXPECT_GT(rmsRatio, 0.95)
            << "Deterministic runs have divergent RMS: " << rms1 << " vs " << rms2;
        EXPECT_LT(rmsRatio, 1.05)
            << "Deterministic runs have divergent RMS: " << rms1 << " vs " << rms2;
    }

    piper_plus_free_audio(samples1);
    piper_plus_free_audio(samples2);
    piper_plus_free(engine);
}

// ===== Test 5: Callback streaming vs one-shot parity =====

namespace {
struct RegressionCallbackData {
    int32_t totalSamples = 0;
    double sumSquares = 0.0;
    int32_t sampleRate = 0;
};

void regressionCallback(const float* samples, int32_t num_samples,
                         int32_t sample_rate, void* user_data) {
    auto* data = static_cast<RegressionCallbackData*>(user_data);
    data->totalSamples += num_samples;
    data->sampleRate = sample_rate;
    for (int32_t i = 0; i < num_samples; i++) {
        data->sumSquares += static_cast<double>(samples[i]) * samples[i];
    }
}
} // anonymous namespace

TEST_F(AudioRegressionTest, CallbackStreaming_vs_OneShot) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    // Use text long enough to avoid short-text padding (MIN_PHONEME_IDS=40)
    const char* text = u8"Hello world, how are you doing today? This is a test of the synthesis engine.";
    auto opts = deterministicOptions(/*language_id=*/-1);

    // One-shot
    float* samples = nullptr;
    int32_t oneShotCount = 0, rate = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, text, &opts,
              &samples, &oneShotCount, &rate), PIPER_PLUS_OK);
    ASSERT_GT(oneShotCount, 0);
    piper_plus_free_audio(samples);

    // Callback streaming
    RegressionCallbackData cbData;
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        engine, text, &opts, regressionCallback, &cbData);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(cbData.totalSamples, 0);

    // Sample counts should be within 20%
    // (Debug builds on macOS show ~15% divergence due to FP precision)
    double ratio = static_cast<double>(cbData.totalSamples) / oneShotCount;
    EXPECT_GT(ratio, 0.80)
        << "Callback streaming produced significantly fewer samples: "
        << cbData.totalSamples << " vs " << oneShotCount;
    EXPECT_LT(ratio, 1.20)
        << "Callback streaming produced significantly more samples: "
        << cbData.totalSamples << " vs " << oneShotCount;

    piper_plus_free(engine);
}
