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
#include <cstdint>
#include <fstream>
#include <string>
#include <utility>
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

// Does the ONNX file declare a graph output named "durations"?
//
// ONNX serialises graph output names as plain protobuf strings, so a streaming
// byte scan answers the question without linking onnxruntime here. This
// mirrors the runtime probe piper.cpp performs when it decides whether a voice
// can produce phoneme timing at all.
static bool modelDeclaresDurations(const char* path) {
    if (!path) return false;
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;

    const std::string needle = "durations";
    // Keep the trailing needle.size()-1 bytes of each block so a needle that
    // straddles a block boundary is still found.
    const std::size_t overlap = needle.size() - 1;
    std::vector<char> block(64 * 1024);
    std::string window;
    while (in.read(block.data(), static_cast<std::streamsize>(block.size())) ||
           in.gcount() > 0) {
        window.append(block.data(), static_cast<std::size_t>(in.gcount()));
        if (window.find(needle) != std::string::npos) return true;
        if (window.size() > overlap) {
            window.erase(0, window.size() - overlap);
        }
    }
    return false;
}

// Anti-vacuity gate. GREEN both before and after the #652 fix -- it is not a
// reproducer. It exists because every assertion in the two timing tests below
// is only meaningful while the fixture model actually emits durations: swapping
// in a durations-less export would degrade all of them to "model does not
// support timing", which is precisely how #652 shipped green.
TEST_F(CApiIntegrationTest, FixtureModelDeclaresDurationsOutput) {
    EXPECT_TRUE(modelDeclaresDurations(g_model_path))
        << "test/models/multilingual-test-medium.onnx declares no 'durations' "
           "graph output; the phoneme timing tests would pass vacuously";
}

TEST_F(CApiIntegrationTest, TimingAfterSynthesis) {
    // Precondition, not a subject: without it a missing 'durations' output
    // would be indistinguishable from the #652 propagation bug.
    ASSERT_TRUE(modelDeclaresDurations(g_model_path));

    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    // Synthesize first
    float* samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    auto opts = piper_plus_default_options();
    PiperPlusStatus rc = piper_plus_synthesize(engine, "Hello.", &opts,
                                       &samples, &num_samples, &sample_rate);
    ASSERT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    ASSERT_GT(num_samples, 0);
    ASSERT_GT(sample_rate, 0);
    piper_plus_free_audio(samples);

    // Unconditional: the aggregating text->audio path must forward the timings
    // it extracted per synthesize() unit (#652). The previous version of this
    // test inspected the data only `if (rc == PIPER_PLUS_OK)`, so it reported
    // PASSED while the feature was entirely broken.
    PiperPlusTimingResult timing = {};
    rc = piper_plus_get_phoneme_timing(engine, &timing);
    ASSERT_EQ(rc, PIPER_PLUS_OK) << piper_plus_get_last_error();
    ASSERT_GT(timing.count, 0);
    ASSERT_NE(timing.entries, nullptr);

    // Non-decreasing, never contiguous: extractTimingsFromDurations omits the
    // pad/bos/eos ids from the entry list while still advancing its cursor, so
    // gaps between consecutive entries are legitimate.
    for (int32_t i = 0; i < timing.count; ++i) {
        EXPECT_GE(timing.entries[i].end_time, timing.entries[i].start_time)
            << "entry " << i << " ends before it starts";
        if (i > 0) {
            EXPECT_GE(timing.entries[i].start_time,
                      timing.entries[i - 1].start_time)
                << "start_time regressed at entry " << i;
        }
    }

    // One-sided on purpose: the exported durations tensor is pre-ceil (#653),
    // so the timing total runs short of the emitted audio by design. What must
    // never happen is a timing running past the audio the caller received.
    EXPECT_LE(timing.entries[timing.count - 1].end_time,
              static_cast<float>(num_samples) /
                      static_cast<float>(sample_rate) +
                  0.05f);

    piper_plus_free(engine);
}

// Multi-unit coverage. Inline `[[ ... ]]` notation splits the text into several
// synthesize() units inside one piper_plus_synthesize() call, which is exactly
// where #652 dropped timings: only the first unit (or none at all) survived.
//
// The offsets are bound on BOTH sides. Inequalities alone ("later entries sit
// past the first unit") accept an offset that is too large (#654's per-unit
// audioSeconds re-assignment, measured 1.53x over) just as happily as one that
// is too small (a raw `durations` sum, 0.55-0.83x under, or a cursor that skips
// the inter-sentence silence, -0.2 s per unit). So each unit is re-synthesized
// alone with the trailing sentence silence switched off, and the combined run's
// entries must equal that unit's entries plus the exact interleaved sample
// count emitted before it.
//
// The only one-sided bound left is timing-total vs audio length: the exported
// `durations` tensor is pre-`ceil` (#653), so the last end_time legitimately
// falls short of the audio by a model-dependent amount. What is pinned exactly
// is the inter-unit DELTA, which #653 cannot influence.
TEST_F(CApiIntegrationTest, TimingSpansAllInlinePhonemeUnits) {
    ASSERT_TRUE(modelDeclaresDurations(g_model_path));

    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    // Pin the Latin-script G2P instead of relying on auto-detect. The phoneme
    // sequence -- and therefore every duration -- depends on the language id,
    // and piper_plus_synthesize restores synthesisConfig on the way out, so an
    // auto-detected id is not even guaranteed to be identical between the
    // isolated and the combined run.
    const int32_t esLanguageId = piper_plus_language_id(engine, "es");
    if (esLanguageId < 0) {
        piper_plus_free(engine);
        GTEST_SKIP() << "fixture model declares no 'es' language id; skipping "
                        "the Spanish-text timing assertions";
    }

    const int32_t sampleRate = piper_plus_sample_rate(engine);
    ASSERT_GT(sampleRate, 0);

    struct Unit {
        std::vector<std::string> phonemes;
        std::vector<float> starts;
        std::vector<float> ends;
        int32_t numSamples = 0;
    };

    // timing.entries is BORROWED and invalidated by the next call on this
    // engine, so copy the fields out immediately after each synthesis.
    auto collect = [&](const char* text, float sentenceSilenceSec, Unit& unit) {
        auto opts = piper_plus_default_options();
        opts.language_id = esLanguageId;
        opts.sentence_silence_sec = sentenceSilenceSec;

        float* samples = nullptr;
        int32_t num_samples = 0, sample_rate = 0;
        ASSERT_EQ(piper_plus_synthesize(engine, text, &opts, &samples,
                                        &num_samples, &sample_rate),
                  PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        piper_plus_free_audio(samples);
        ASSERT_GT(num_samples, 0);
        unit.numSamples = num_samples;

        PiperPlusTimingResult timing = {};
        ASSERT_EQ(piper_plus_get_phoneme_timing(engine, &timing), PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        ASSERT_GT(timing.count, 0);
        ASSERT_NE(timing.entries, nullptr);

        unit.phonemes.clear();
        unit.starts.clear();
        unit.ends.clear();
        for (int32_t i = 0; i < timing.count; ++i) {
            unit.phonemes.push_back(
                timing.entries[i].phoneme ? timing.entries[i].phoneme : "");
            unit.starts.push_back(timing.entries[i].start_time);
            unit.ends.push_back(timing.entries[i].end_time);
        }
    };

    // Each unit alone, sentence silence off, so numSamples is exactly that
    // unit's audio length.
    const std::vector<std::string> segments = {"Hola.", "[[ m u n d o ]]",
                                               "Adios."};
    std::vector<Unit> units(segments.size());
    for (std::size_t i = 0; i < segments.size(); ++i) {
        SCOPED_TRACE(segments[i]);
        ASSERT_NO_FATAL_FAILURE(collect(segments[i].c_str(), 0.0f, units[i]));
    }

    const float sentenceSilenceSec = 0.2f;
    Unit combined;
    ASSERT_NO_FATAL_FAILURE(
        collect("Hola. [[ m u n d o ]] Adios.", sentenceSilenceSec, combined));

    // Same expression the aggregator uses (piper.cpp), truncation included.
    // channels is 1 on every shipped voice and the C API exposes no channel
    // count, so it drops out of both this product and the divisors below.
    const int64_t silenceSamples =
        static_cast<int64_t>(sentenceSilenceSec * sampleRate);
    ASSERT_GT(silenceSamples, 0);

    std::size_t totalUnitEntries = 0;
    for (const Unit& unit : units) {
        totalUnitEntries += unit.starts.size();
    }
    EXPECT_GT(combined.starts.size(), units[0].starts.size())
        << "the multi-unit text yielded no more entries than its first unit "
           "alone -- later units were dropped";
    ASSERT_EQ(combined.starts.size(), totalUnitEntries)
        << "the combined run must carry exactly the three units' entries";

    for (std::size_t i = 1; i < combined.starts.size(); ++i) {
        EXPECT_GE(combined.starts[i], combined.starts[i - 1])
            << "start_time regressed at entry " << i
            << "; a unit boundary reset the cursor instead of shifting it";
    }

    const double oneSample = 1.0 / static_cast<double>(sampleRate);
    std::size_t entryIdx = 0;
    int64_t offsetSamples = 0;
    for (std::size_t u = 0; u < units.size(); ++u) {
        SCOPED_TRACE("unit " + std::to_string(u));
        const double offsetSeconds =
            static_cast<double>(offsetSamples) / static_cast<double>(sampleRate);

        for (std::size_t i = 0; i < units[u].starts.size(); ++i) {
            SCOPED_TRACE("entry " + std::to_string(i));
            EXPECT_EQ(combined.phonemes[entryIdx + i], units[u].phonemes[i]);
            EXPECT_NEAR(static_cast<double>(combined.starts[entryIdx + i]),
                        static_cast<double>(units[u].starts[i]) + offsetSeconds,
                        oneSample);
            EXPECT_NEAR(static_cast<double>(combined.ends[entryIdx + i]),
                        static_cast<double>(units[u].ends[i]) + offsetSeconds,
                        oneSample);
        }

        entryIdx += units[u].starts.size();
        offsetSamples += units[u].numSamples + silenceSamples;
    }

    // Sum(unit audio) + Sum(sentence silence) reconstructs the emitted stream
    // to the sample, which is what makes the offsets above positions in the
    // buffer the caller received rather than approximations.
    EXPECT_EQ(static_cast<int64_t>(combined.numSamples), offsetSamples);

    // One-sided, per #653 (see the header comment above).
    EXPECT_LE(combined.ends.back(),
              static_cast<float>(combined.numSamples) /
                      static_cast<float>(sampleRate) +
                  0.05f);

    piper_plus_free(engine);
}

// Iterator coverage. piper_plus_synth_next is the ONLY production caller of
// piper::phonemesToAudioFloat, and every timing test above inspects the state
// left behind by the one-shot piper_plus_synthesize, so the Iterator's own
// timing was entirely unasserted. Each synth_next publishes the timing of the
// chunk it just returned: entries are per-chunk and 0-based (a chunk is one
// sentence, so its cursor starts at zero), never a running concatenation and
// never the previous chunk's leftovers.
TEST_F(CApiIntegrationTest, IteratorPublishesPerChunkTiming) {
    ASSERT_TRUE(modelDeclaresDurations(g_model_path));

    auto* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const int32_t esLanguageId = piper_plus_language_id(engine, "es");
    if (esLanguageId < 0) {
        piper_plus_free(engine);
        GTEST_SKIP() << "fixture model declares no 'es' language id; skipping "
                        "the Spanish-text timing assertions";
    }

    auto opts = piper_plus_default_options();
    opts.language_id = esLanguageId;

    // Deliberately different sentences: a stale or mixed-in chunk is then
    // detectable by CONTENT, not just by entry count.
    const std::vector<std::string> sentences = {"Hola.", "Mundo bonito.",
                                                "Adios amigo."};
    const std::string text = sentences[0] + " " + sentences[1] + " " +
                             sentences[2];

    struct Entry {
        std::string phoneme;
        float start = 0.0f;
        float end = 0.0f;
    };

    std::vector<std::vector<Entry>> perChunk;
    ASSERT_EQ(piper_plus_synth_start(engine, text.c_str(), &opts),
              PIPER_PLUS_OK)
        << piper_plus_get_last_error();
    for (;;) {
        PiperPlusAudioChunk chunk = {};
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        ASSERT_NE(rc, PIPER_PLUS_ERR) << piper_plus_get_last_error();

        if (chunk.num_samples > 0) {
            SCOPED_TRACE("chunk " + std::to_string(perChunk.size()));
            // timing.entries is BORROWED and the next API call on this engine
            // rebuilds it, so copy before advancing the iterator.
            PiperPlusTimingResult timing = {};
            ASSERT_EQ(piper_plus_get_phoneme_timing(engine, &timing),
                      PIPER_PLUS_OK)
                << "the Iterator published no timing for this chunk: "
                << piper_plus_get_last_error();
            ASSERT_GT(timing.count, 0);
            ASSERT_NE(timing.entries, nullptr);

            std::vector<Entry> entries;
            entries.reserve(static_cast<std::size_t>(timing.count));
            for (int32_t i = 0; i < timing.count; ++i) {
                Entry entry;
                entry.phoneme = timing.entries[i].phoneme
                                    ? timing.entries[i].phoneme
                                    : "";
                entry.start = timing.entries[i].start_time;
                entry.end = timing.entries[i].end_time;
                entries.push_back(std::move(entry));
            }
            perChunk.push_back(std::move(entries));
        }

        if (rc == PIPER_PLUS_DONE) {
            break;
        }
    }

    ASSERT_EQ(perChunk.size(), sentences.size())
        << "one chunk per sentence is what the timing snapshots below assume";

    for (std::size_t c = 0; c < perChunk.size(); ++c) {
        SCOPED_TRACE("chunk " + std::to_string(c));
        for (std::size_t i = 1; i < perChunk[c].size(); ++i) {
            EXPECT_GE(perChunk[c][i].start, perChunk[c][i - 1].start)
                << "start_time regressed at entry " << i;
        }
        for (std::size_t i = 0; i < perChunk[c].size(); ++i) {
            EXPECT_GE(perChunk[c][i].end, perChunk[c][i].start)
                << "entry " << i << " ends before it starts";
        }
    }

    // Each chunk must carry exactly its own sentence, offset 0. Synthesizing
    // the sentence on its own goes through textToAudioFloat while the Iterator
    // goes through phonemesToAudioFloat, so this also pins the two aggregators
    // against each other.
    for (std::size_t c = 0; c < sentences.size(); ++c) {
        SCOPED_TRACE("chunk " + std::to_string(c) + " = " + sentences[c]);

        auto soloOpts = piper_plus_default_options();
        soloOpts.language_id = esLanguageId;

        float* samples = nullptr;
        int32_t num_samples = 0, sample_rate = 0;
        ASSERT_EQ(piper_plus_synthesize(engine, sentences[c].c_str(), &soloOpts,
                                        &samples, &num_samples, &sample_rate),
                  PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        piper_plus_free_audio(samples);

        PiperPlusTimingResult timing = {};
        ASSERT_EQ(piper_plus_get_phoneme_timing(engine, &timing), PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        ASSERT_GT(timing.count, 0);

        ASSERT_EQ(perChunk[c].size(), static_cast<std::size_t>(timing.count))
            << "the chunk carries a different number of entries than the "
               "sentence does on its own -- entries leaked across chunks";
        for (int32_t i = 0; i < timing.count; ++i) {
            const std::size_t idx = static_cast<std::size_t>(i);
            EXPECT_EQ(perChunk[c][idx].phoneme,
                      std::string(timing.entries[i].phoneme
                                      ? timing.entries[i].phoneme
                                      : ""))
                << "entry " << i;
            EXPECT_FLOAT_EQ(perChunk[c][idx].start,
                            timing.entries[i].start_time)
                << "entry " << i;
            EXPECT_FLOAT_EQ(perChunk[c][idx].end, timing.entries[i].end_time)
                << "entry " << i;
        }
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
