/**
 * test_c_api_concurrent_ja.cpp — JA concurrent + Iterator parity stress tests.
 *
 * Issue #383 follow-up regression tests. The original Phase 1 work shipped two
 * latent bugs that were not caught by the existing unit suite:
 *
 *   1. C# `MeCabTokenizer` was not thread-safe → fixed in commit c567f5be.
 *      The C# `SentenceParallelEncoderTests` only exercised non-JA inputs so
 *      the race was missed at unit level.
 *   2. C++ `phonemesToAudioFloat` (Phase 1) dropped trailing sentence-silence,
 *      causing `IteratorVsOneShot` parity violation. Fixed in a8e776d9.
 *      The existing parity tests (`IteratorVsOneShot*`) only used English text;
 *      the JA path had no equivalent coverage.
 *
 * This file fills both gaps for the C++ runtime:
 *   - `ConcurrentJaSynthesis_NoCrash`        — 4 threads × per-thread engine
 *   - `ConcurrentJaSynthesis_DeterministicLength` — output length stays in tolerance
 *   - `IteratorVsOneShotJapanese`            — JA Iterator-vs-OneShot parity
 *
 * Per `piper_plus.h`, `PiperPlusEngine` is documented as NOT thread-safe ("use
 * one engine per thread"). These tests deliberately follow that contract: each
 * thread allocates its own engine. They still catch regressions in the shared
 * G2P backend (OpenJTalk / pyopenjtalk) which is what bit C# at `c567f5be`.
 *
 * Auto-skips when the test model is unavailable (mirrors the policy in
 * test_c_api_integration.cpp).
 */

#include <gtest/gtest.h>

#include <atomic>
#include <cstdint>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

#include "piper_plus.h"

namespace fs = std::filesystem;

namespace {

constexpr const char *kModelRel = "test/models/multilingual-test-medium.onnx";

// Multi-sentence JA text — Phase 1 only kicks in for >= 2 sentences, so the
// stress test deliberately uses several so the parallel G2P path is exercised.
constexpr const char *kJaMultiSentence =
    "\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf"
    "\xe3\x80\x82"  // こんにちは。
    "\xe6\x9d\xb1\xe4\xba\xac\xe9\xa7\x85\xe3\x81\x8b\xe3\x82\x89"
    "\xe6\x96\xb0\xe5\xb9\xb9\xe7\xb7\x9a\xe3\x81\xa7\xe5\xa4\xa7"
    // MSVC parses hex escapes greedily, so we split the literals where a
    // hex byte is immediately followed by an ASCII digit.
    "\xe9\x98\xaa\xe3\x81\xbe\xe3\x81\xa7\xe7\xb4\x84" "2\xe6\x99\x82"
    "\xe9\x96\x93" "30\xe5\x88\x86\xe3\x81\x8b\xe3\x81\x8b\xe3\x82\x8a"
    "\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"  // 東京駅から新幹線で大阪まで約2時間30分かかります。
    "\xe6\xa1\x9c\xe3\x81\xae\xe8\x8a\xb1\xe3\x81\x8c\xe6\xba\x80"
    "\xe9\x96\x8b\xe3\x81\xab\xe3\x81\xaa\xe3\x82\x8b\xe3\x81\xa8"
    "\xe5\xa4\x9a\xe3\x81\x8f\xe3\x81\xae\xe4\xba\xba\xe3\x80\x85"
    "\xe3\x81\x8c\xe5\x85\xac\xe5\x9c\x92\xe3\x81\xa7\xe3\x81\x8a"
    "\xe8\x8a\xb1\xe8\xa6\x8b\xe3\x82\x92\xe6\xa5\xbd\xe3\x81\x97"
    "\xe3\x81\xbf\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82";  // 桜の花が満開になると、多くの人々が公園でお花見を楽しみます。

bool ResolveModelPaths(std::string &model, std::string &config) {
    const std::vector<std::string> candidates = {
        kModelRel,
        std::string("../") + kModelRel,
        std::string("../../") + kModelRel,
    };
    for (const auto &p : candidates) {
        if (fs::exists(p) && fs::exists(p + ".json")) {
            model = p;
            config = p + ".json";
            return true;
        }
    }
    return false;
}

PiperPlusEngine *MakeEngine(const std::string &model, const std::string &config) {
    PiperPlusConfig cfg{};
    cfg.model_path = model.c_str();
    cfg.config_path = config.c_str();
    cfg.provider = "cpu";
    cfg.num_threads = 1;
    PiperPlusEngine *engine = nullptr;
    if (piper_plus_create(&cfg, &engine) != PIPER_PLUS_OK) {
        return nullptr;
    }
    return engine;
}

int32_t SynthesizeJaIterator(PiperPlusEngine *engine, const char *text) {
    auto opts = piper_plus_default_options();
    if (piper_plus_synth_start(engine, text, &opts) != PIPER_PLUS_OK) {
        return -1;
    }
    int32_t total = 0;
    while (true) {
        PiperPlusAudioChunk chunk{};
        PiperPlusStatus rc = piper_plus_synth_next(engine, &chunk);
        if (rc == PIPER_PLUS_ERR) {
            return -1;
        }
        total += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) {
            break;
        }
    }
    return total;
}

class ConcurrentJaTest : public ::testing::Test {
protected:
    static std::string s_model;
    static std::string s_config;

    static void SetUpTestSuite() {
        if (!ResolveModelPaths(s_model, s_config)) {
            s_model.clear();
            s_config.clear();
        }
    }

    void SetUp() override {
        if (s_model.empty()) {
            GTEST_SKIP() << "Test model not found; skipping JA concurrent tests";
        }
        // Pre-warm one engine to ensure JA G2P backend (OpenJTalk dictionary,
        // pyopenjtalk-plus equivalent) is loaded once before the multi-thread
        // section so threads don't race during one-time init.
        PiperPlusEngine *warm = MakeEngine(s_model, s_config);
        if (warm) {
            int32_t total = SynthesizeJaIterator(warm, kJaMultiSentence);
            piper_plus_free(warm);
            if (total <= 0) {
                GTEST_SKIP()
                    << "JA synthesis returned no audio in warmup; OpenJTalk "
                       "dictionary likely unavailable on this build.";
            }
        } else {
            GTEST_SKIP() << "Could not create engine for warmup: "
                         << (piper_plus_get_last_error()
                                 ? piper_plus_get_last_error()
                                 : "unknown");
        }
    }
};

std::string ConcurrentJaTest::s_model;
std::string ConcurrentJaTest::s_config;

// One engine per thread. The C API documents PiperPlusEngine as NOT
// thread-safe, so we follow the documented contract. The shared G2P backend
// (OpenJTalk) is exercised concurrently across threads, which is the surface
// that C# `c567f5be` showed could harbor data races.
TEST_F(ConcurrentJaTest, ConcurrentJaSynthesis_NoCrash) {
    constexpr int kThreads = 4;
    std::atomic<int> succeeded{0};
    std::vector<std::thread> workers;
    workers.reserve(kThreads);

    for (int i = 0; i < kThreads; ++i) {
        workers.emplace_back([&]() {
            PiperPlusEngine *engine = MakeEngine(s_model, s_config);
            if (!engine) {
                return;
            }
            int32_t total = SynthesizeJaIterator(engine, kJaMultiSentence);
            if (total > 0) {
                succeeded.fetch_add(1, std::memory_order_relaxed);
            }
            piper_plus_free(engine);
        });
    }
    for (auto &t : workers) {
        t.join();
    }

    EXPECT_EQ(succeeded.load(), kThreads)
        << "Concurrent JA synthesis lost samples or crashed; investigate the "
           "G2P backend for shared mutable state (cf. issue #383 / commit "
           "c567f5be on the C# side).";
}

// VITS-derived models are stochastic by default (noise_scale, noise_w in
// `piper_plus_default_options`), so per-thread output samples can differ in
// amplitude. Length should still be near-deterministic since the duration
// predictor uses the same length_scale across threads. Allow ±20% tolerance
// to match the existing IteratorVsOneShot policy.
TEST_F(ConcurrentJaTest, ConcurrentJaSynthesis_DeterministicLength) {
    constexpr int kThreads = 4;
    std::vector<int32_t> lengths(kThreads, 0);
    std::vector<std::thread> workers;
    workers.reserve(kThreads);

    for (int i = 0; i < kThreads; ++i) {
        workers.emplace_back([&, i]() {
            PiperPlusEngine *engine = MakeEngine(s_model, s_config);
            if (!engine) {
                return;
            }
            lengths[i] = SynthesizeJaIterator(engine, kJaMultiSentence);
            piper_plus_free(engine);
        });
    }
    for (auto &t : workers) {
        t.join();
    }

    int32_t minLen = lengths[0];
    int32_t maxLen = lengths[0];
    for (int32_t v : lengths) {
        ASSERT_GT(v, 0) << "One thread produced no audio";
        if (v < minLen) minLen = v;
        if (v > maxLen) maxLen = v;
    }
    const double ratio = static_cast<double>(maxLen) / minLen;
    EXPECT_LT(ratio, 1.20)
        << "Per-thread output length differs by more than 20% (min=" << minLen
        << ", max=" << maxLen << "); G2P backend may have non-deterministic "
        << "shared state.";
}

// JA equivalent of the existing English IteratorVsOneShot parity test. Would
// have caught the missing sentence-silence regression that landed in 5e0597c5
// and was fixed in a8e776d9, before the C++ ORT environment was healthy enough
// to run the existing English parity test.
TEST_F(ConcurrentJaTest, IteratorVsOneShotJapanese) {
    PiperPlusEngine *engine = MakeEngine(s_model, s_config);
    ASSERT_NE(engine, nullptr);

    auto opts = piper_plus_default_options();

    // One-shot
    float *samples = nullptr;
    int32_t oneShot = 0;
    int32_t rate = 0;
    PiperPlusStatus rc = piper_plus_synthesize(engine, kJaMultiSentence, &opts,
                                               &samples, &oneShot, &rate);
    if (rc != PIPER_PLUS_OK || oneShot == 0) {
        if (samples) piper_plus_free_audio(samples);
        piper_plus_free(engine);
        GTEST_SKIP() << "JA one-shot synthesis returned no audio";
    }
    piper_plus_free_audio(samples);

    // Iterator
    int32_t iterTotal = SynthesizeJaIterator(engine, kJaMultiSentence);
    piper_plus_free(engine);

    ASSERT_GT(iterTotal, 0);
    const double ratio = static_cast<double>(iterTotal) / oneShot;
    EXPECT_GT(ratio, 0.80)
        << "Iterator output is too short vs one-shot (ratio=" << ratio
        << "); regression of phonemesToAudioFloat sentence-silence (a8e776d9)?";
    EXPECT_LT(ratio, 1.20)
        << "Iterator output is too long vs one-shot (ratio=" << ratio << ")";
}

}  // namespace
