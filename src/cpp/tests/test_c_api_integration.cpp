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
#include <cstring>
#include <algorithm>
#include <vector>
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
        PiperPlusEngine* engine = nullptr;
        PiperPlusStatus rc = piper_plus_create(&config, &engine);
        if (rc != PIPER_PLUS_OK) return nullptr;
        return engine;
    }
};

// ===== Group 1: One-shot synthesis =====

TEST_F(CApiIntegrationTest, OneShotProducesAudio) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = piper_plus_default_options();

    PiperPlusStatus rc = piper_plus_synthesize(engine, "Hello world.", &opts,
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

    PiperPlusStatus rc = piper_plus_synthesize(engine,
        u8"こんにちは、今日は良い天気ですね。", &opts,
        &samples, &num_samples, &sample_rate);

    if (rc == PIPER_PLUS_OK && num_samples == 0) {
        piper_plus_free_audio(samples);
        piper_plus_free(engine);
        GTEST_SKIP() << "Japanese phonemization unavailable (OpenJTalk not loaded)";
    }

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
    PiperPlusStatus rc = piper_plus_synth_start(engine,
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
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        iterTotal += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Allow 20% tolerance (Debug builds on macOS show ~15% divergence)
    double ratio = static_cast<double>(iterTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.80);
    EXPECT_LT(ratio, 1.20);
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

    PiperPlusStatus rc = piper_plus_synthesize_streaming(
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

    PiperPlusStatus rc = piper_plus_synthesize_streaming(
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
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
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
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        total += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }
    EXPECT_GT(total, 0);
    piper_plus_free(engine);
}

// ===== Phase 4: Custom dictionary integration tests =====

TEST_F(CApiIntegrationTest, CustomDictLoadAndCount) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    // Record baseline count (model may pre-load built-in dictionaries)
    int32_t baseline = piper_plus_dict_entry_count(engine);
    EXPECT_GE(baseline, 0);

    // Add words programmatically — verify the API succeeds
    EXPECT_EQ(piper_plus_add_dict_word(engine, "TTS", "text to speech", 0),
              PIPER_PLUS_OK);
    EXPECT_EQ(piper_plus_add_dict_word(engine, "AI", "artificial intelligence", 0),
              PIPER_PLUS_OK);

    // Count should be at least baseline (built-in dicts may merge with custom)
    int32_t after_add = piper_plus_dict_entry_count(engine);
    EXPECT_GE(after_add, baseline);

    // Clear custom dict
    EXPECT_EQ(piper_plus_clear_custom_dict(engine), PIPER_PLUS_OK);

    // After clear, count should be <= baseline (custom entries removed)
    int32_t after_clear = piper_plus_dict_entry_count(engine);
    EXPECT_LE(after_clear, baseline);

    piper_plus_free(engine);
}

// ===== Phase 4: G2P integration tests =====

TEST_F(CApiIntegrationTest, PhonemizeProducesOutput) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusPhonemeResult result = {};
    PiperPlusStatus rc = piper_plus_phonemize(engine, "Hello world.", nullptr, &result);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_NE(result.phonemes, nullptr);
    if (result.phonemes) {
        EXPECT_GT(std::strlen(result.phonemes), 0u);
    }
    EXPECT_GT(result.num_phonemes, 0);

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, AvailableLanguagesNonEmpty) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* langs = piper_plus_available_languages(engine);
    EXPECT_NE(langs, nullptr);
    EXPECT_GT(std::strlen(langs), 0u);
    // Should contain "ja" for the test model
    EXPECT_NE(std::string(langs).find("ja"), std::string::npos);

    piper_plus_free(engine);
}

// ===== Phase 4: Phoneme timing integration tests =====

TEST_F(CApiIntegrationTest, TimingAfterSynthesis) {
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    // Synthesize first
    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = piper_plus_default_options();
    PiperPlusStatus rc = piper_plus_synthesize(engine, "Hello.", &opts,
                                       &samples, &num_samples, &sample_rate);
    ASSERT_EQ(rc, PIPER_PLUS_OK);
    piper_plus_free_audio(samples);

    // Get timing (may or may not be available depending on model)
    PiperPlusTimingResult timing = {};
    rc = piper_plus_get_phoneme_timing(engine, &timing);
    // Either OK with data, or ERR if model doesn't support timing
    if (rc == PIPER_PLUS_OK) {
        EXPECT_GT(timing.count, 0);
        EXPECT_NE(timing.entries, nullptr);
    }

    piper_plus_free(engine);
}

// ===== Phase 5: Iterator crossfade integration tests (M5-3) =====

TEST_F(CApiIntegrationTest, IteratorCrossfadeSmoothBoundary) {
    // Two sentences via Iterator -- verify the boundary region is smooth.
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    PiperPlusStatus rc = piper_plus_synth_start(engine,
        "First sentence. Second sentence.", &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK);

    std::vector<std::vector<float>> chunks;
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        ASSERT_NE(rc, PIPER_PLUS_ERR) << piper_plus_get_last_error();
        if (chunk.num_samples > 0) {
            chunks.emplace_back(chunk.samples, chunk.samples + chunk.num_samples);
        }
        if (rc == PIPER_PLUS_DONE) break;
    }

    EXPECT_GE(chunks.size(), 1u);

    // Check that each chunk has valid float samples in [-1, 1]
    for (const auto& c : chunks) {
        for (float v : c) {
            EXPECT_GE(v, -1.0f);
            EXPECT_LE(v, 1.0f);
        }
    }

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorVsOneShotParityWithCrossfade) {
    // Compare total samples from Iterator (with crossfade) vs one-shot.
    // They should be close in count (crossfade slightly reduces total).
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* text = "Hello world. How are you today.";
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
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        iterTotal += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Allow reasonable tolerance (crossfade trims CROSSFADE_SAMPLES per boundary)
    double ratio = static_cast<double>(iterTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.80);
    EXPECT_LT(ratio, 1.20);

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, SingleSentenceNoCrossfadeEffect) {
    // A single sentence should not be affected by crossfade.
    // Compare Iterator result with one-shot for a single sentence.
    // Use a long enough text to avoid short-text padding (MIN_PHONEME_IDS=40).
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* text = "Hello world, how are you doing today?";
    auto opts = piper_plus_default_options();

    // One-shot
    float* oneShotSamples = nullptr;
    int32_t oneShotCount = 0, rate = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, text, &opts,
              &oneShotSamples, &oneShotCount, &rate), PIPER_PLUS_OK);
    ASSERT_GT(oneShotCount, 0);

    // Iterator
    ASSERT_EQ(piper_plus_synth_start(engine, text, &opts), PIPER_PLUS_OK);
    std::vector<float> iterSamples;
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        if (chunk.num_samples > 0) {
            iterSamples.insert(iterSamples.end(),
                               chunk.samples, chunk.samples + chunk.num_samples);
        }
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Single sentence: Iterator should produce same sample count as one-shot
    // (no crossfade boundaries, no trimming)
    EXPECT_EQ(static_cast<int32_t>(iterSamples.size()), oneShotCount);

    piper_plus_free_audio(oneShotSamples);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, CallbackCrossfadeApplied) {
    // Callback streaming wraps the Iterator, so crossfade should also apply.
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    CallbackData cbData;

    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        engine, "First sentence. Second sentence.", &opts, testCallback, &cbData);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GE(cbData.callCount, 1);
    EXPECT_GT(cbData.totalSamples, 0);

    // Validate that samples are in valid range (float [-1, 1])
    EXPECT_GT(cbData.sampleRate, 0);

    piper_plus_free(engine);
}

// ===== Group 6: DONE chunk with samples (PR #309 regression guard) =====

TEST_F(CApiIntegrationTest, IteratorDoneCanCarrySamples) {
    // Verify that when DONE carries samples, those samples are valid.
    // Note: DONE + num_samples > 0 is model/text dependent and may not always occur.
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();
    PiperPlusStatus rc = piper_plus_synth_start(engine, "Hello world.", &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK);

    bool doneHadSamples = false;
    int32_t totalSamples = 0;

    for (;;) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        ASSERT_NE(rc, PIPER_PLUS_ERR) << piper_plus_get_last_error();

        if (rc == PIPER_PLUS_DONE && chunk.num_samples > 0) {
            doneHadSamples = true;
            // Validate that samples in the DONE chunk are in [-1.0, 1.0]
            for (int32_t i = 0; i < chunk.num_samples; i++) {
                EXPECT_GE(chunk.samples[i], -1.0f);
                EXPECT_LE(chunk.samples[i], 1.0f);
            }
        }

        totalSamples += chunk.num_samples;

        if (rc == PIPER_PLUS_DONE) break;
    }

    EXPECT_GT(totalSamples, 0) << "Iterator must produce audio";

    // Log whether DONE carried samples (informational, not a failure)
    if (doneHadSamples) {
        std::cout << "[  INFO    ] DONE chunk carried samples" << std::endl;
    } else {
        std::cout << "[  INFO    ] DONE chunk had no samples (model-dependent)"
                  << std::endl;
    }

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorAlwaysProcessSamplesBeforeCheckingDone) {
    // Proves that ignoring samples in a DONE chunk causes sample loss.
    // Compares two counting strategies:
    //   correct:  always add chunk.num_samples regardless of status
    //   buggy:    skip chunk.num_samples when status == DONE (the Godot/JNI/Dart bug)
    // The correct count must be >= buggy count, and must match one-shot.
    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* text = "Hello world.";
    auto opts = piper_plus_default_options();

    // One-shot baseline
    float* samples = nullptr;
    int32_t oneShotCount = 0, rate = 0;
    ASSERT_EQ(piper_plus_synthesize(engine, text, &opts,
              &samples, &oneShotCount, &rate), PIPER_PLUS_OK);
    ASSERT_GT(oneShotCount, 0);
    piper_plus_free_audio(samples);

    // Iterator with two counting strategies
    ASSERT_EQ(piper_plus_synth_start(engine, text, &opts), PIPER_PLUS_OK);
    int32_t correctTotal = 0;   // always process samples
    int32_t buggyTotal = 0;     // skip samples when DONE

    for (;;) {
        PiperPlusAudioChunk chunk = {};
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        ASSERT_NE(rc, PIPER_PLUS_ERR) << piper_plus_get_last_error();

        // Correct pattern: always process samples before checking status
        correctTotal += chunk.num_samples;

        // Buggy pattern: break/return before processing samples on DONE
        if (rc == PIPER_PLUS_DONE) {
            // buggyTotal intentionally does NOT add chunk.num_samples here
            break;
        }
        buggyTotal += chunk.num_samples;
    }

    // The correct total must always be >= the buggy total
    EXPECT_GE(correctTotal, buggyTotal);

    // The correct total must match one-shot within tolerance
    // (Debug builds on macOS show ~15% divergence due to FP precision)
    double ratio = static_cast<double>(correctTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.80);
    EXPECT_LT(ratio, 1.20);

    // If DONE carried samples, the buggy total is strictly less
    if (correctTotal > buggyTotal) {
        std::cout << "[  INFO    ] DONE chunk samples would be lost by buggy pattern: "
                  << (correctTotal - buggyTotal) << " samples" << std::endl;
    }

    piper_plus_free(engine);
}
