/**
 * test_c_api_integration.cpp — C API integration tests (model required)
 *
 * Tests the full lifecycle: create -> synthesize -> free
 * Requires test model at test/models/multilingual-test-medium.onnx
 * Auto-skips if model not found.
 */

#include <gtest/gtest.h>
#include <filesystem>
#include <cmath>
#include <algorithm>
#include "piper_plus.h"

namespace fs = std::filesystem;

// Test model paths
static const char* g_model_path = nullptr;
static const char* g_config_path = nullptr;

class CApiIntegrationTest : public ::testing::Test {
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
                static std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_model_path = modelPath.c_str();
                    g_config_path = configPath.c_str();
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_model_path) {
            GTEST_SKIP() << "Test model not found; skipping integration test";
        }
    }

    PiperPlusEngine* createEngine() {
        PiperPlusConfig config = {};
        config.model_path = g_model_path;
        config.config_path = g_config_path;
        config.provider = "cpu";
        config.num_threads = 1;
        return piper_plus_create(&config);
    }
};

// ===== Group 1: One-shot synthesis =====

TEST_F(CApiIntegrationTest, OneShotProducesAudio) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = piper_plus_default_options();

    int32_t rc = piper_plus_synthesize(engine, "Hello world.", &opts,
                                       &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_NE(samples, nullptr);
    EXPECT_GT(num_samples, 0);
    EXPECT_GT(sample_rate, 0);

    // Samples in [-1.0, 1.0]
    for (int32_t i = 0; i < std::min(num_samples, (int32_t)1000); i++) {
        EXPECT_GE(samples[i], -1.0f);
        EXPECT_LE(samples[i], 1.0f);
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, OneShotJapanese) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = piper_plus_default_options();

    int32_t rc = piper_plus_synthesize(engine,
        u8"こんにちは、今日は良い天気ですね。", &opts,
        &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(num_samples, 0);

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

// ===== Group 2: Iterator =====

TEST_F(CApiIntegrationTest, IteratorProducesChunks) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    int32_t rc = piper_plus_synth_start(engine,
        "First sentence. Second sentence. Third sentence.", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_OK);

    int chunkCount = 0;
    int32_t totalSamples = 0;

    for (;;) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        ASSERT_NE(rc, PIPER_PLUS_ERR) << piper_plus_get_last_error();
        if (chunk.num_samples > 0) {
            chunkCount++;
            totalSamples += chunk.num_samples;
        }
        if (rc == PIPER_PLUS_DONE) {
            EXPECT_EQ(chunk.is_last, 1);
            break;
        }
    }

    EXPECT_GE(chunkCount, 1);
    EXPECT_GT(totalSamples, 0);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorVsOneShot) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* text = "Hello world.";
    auto opts = piper_plus_default_options();

    // One-shot
    float* samples = nullptr;
    int32_t oneShotCount = 0, rate = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, text, &opts,
              &samples, &oneShotCount, &rate), PIPER_PLUS_OK);
    ASSERT_GT(oneShotCount, 0);
    piper_plus_free_audio(samples);

    // Iterator
    ASSERT_EQ(piper_plus_synth_start(engine, text, &opts), PIPER_PLUS_OK);
    int32_t iterTotal = 0;
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        int32_t rc = piper_plus_synth_next(engine, &chunk);
        iterTotal += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Allow 10% tolerance
    double ratio = static_cast<double>(iterTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.9);
    EXPECT_LT(ratio, 1.1);
    piper_plus_free(engine);
}

// ===== Group 3: Callback =====

struct CallbackData {
    int callCount = 0;
    int32_t totalSamples = 0;
    int32_t sampleRate = 0;
};

static void testCallback(const float* /*samples*/, int32_t num_samples,
                         int32_t sample_rate, void* user_data) {
    auto* data = static_cast<CallbackData*>(user_data);
    data->callCount++;
    data->totalSamples += num_samples;
    data->sampleRate = sample_rate;
}

TEST_F(CApiIntegrationTest, CallbackInvoked) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    CallbackData cbData;

    int32_t rc = piper_plus_synthesize_streaming(
        engine, "Hello world.", &opts, testCallback, &cbData);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GE(cbData.callCount, 1);
    EXPECT_GT(cbData.totalSamples, 0);
    EXPECT_GT(cbData.sampleRate, 0);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, CallbackUserData) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    int32_t magic = 0;

    auto cb = [](const float*, int32_t, int32_t, void* ud) {
        *static_cast<int32_t*>(ud) = 42;
    };

    int32_t rc = piper_plus_synthesize_streaming(
        engine, "Hello.", &opts,
        reinterpret_cast<PiperPlusAudioCallback>(+cb), &magic);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_EQ(magic, 42);
    piper_plus_free(engine);
}

// ===== Group 4: Query API =====

TEST_F(CApiIntegrationTest, QuerySampleRate) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);
    int32_t sr = piper_plus_sample_rate(engine);
    EXPECT_GT(sr, 0);
    EXPECT_TRUE(sr == 16000 || sr == 22050 || sr == 44100 || sr == 48000);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, QueryNumSpeakers) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);
    EXPECT_GE(piper_plus_num_speakers(engine), 0);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, QueryNumLanguages) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);
    EXPECT_GE(piper_plus_num_languages(engine), 1);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, LanguageIdLookup) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);
    // "ja" should exist
    EXPECT_GE(piper_plus_language_id(engine, "ja"), 0);
    // "xx" should not
    EXPECT_EQ(piper_plus_language_id(engine, "xx"), -1);
    piper_plus_free(engine);
}

// ===== Group 5: Busy / reentry =====

TEST_F(CApiIntegrationTest, BusyDuringIterator) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    ASSERT_EQ(piper_plus_synth_start(engine, "Hello world.", &opts), PIPER_PLUS_OK);

    // One-shot during iterator -> BUSY
    float* s = nullptr; int32_t n = 0, r = 0;
    EXPECT_EQ(piper_plus_synthesize(engine, "x", &opts, &s, &n, &r),
              PIPER_PLUS_ERR_BUSY);

    // Streaming during iterator -> BUSY
    CallbackData cb;
    EXPECT_EQ(piper_plus_synthesize_streaming(engine, "x", &opts, testCallback, &cb),
              PIPER_PLUS_ERR_BUSY);

    // synth_start during iterator -> BUSY
    EXPECT_EQ(piper_plus_synth_start(engine, "x", &opts), PIPER_PLUS_ERR_BUSY);

    // Drain
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        int32_t rc = piper_plus_synth_next(engine, &chunk);
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // After drain, one-shot works
    EXPECT_EQ(piper_plus_synthesize(engine, "Hello.", &opts, &s, &n, &r),
              PIPER_PLUS_OK);
    EXPECT_GT(n, 0);
    piper_plus_free_audio(s);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorReuse) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();

    // First iteration
    ASSERT_EQ(piper_plus_synth_start(engine, "First.", &opts), PIPER_PLUS_OK);
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        if (piper_plus_synth_next(engine, &chunk) == PIPER_PLUS_DONE) break;
    }

    // Second iteration
    ASSERT_EQ(piper_plus_synth_start(engine, "Second.", &opts), PIPER_PLUS_OK);
    int32_t total = 0;
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        int32_t rc = piper_plus_synth_next(engine, &chunk);
        total += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }
    EXPECT_GT(total, 0);
    piper_plus_free(engine);
}
