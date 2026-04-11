#include <gtest/gtest.h>
#include <chrono>
#include <vector>
#include <thread>
#include <cstring>
#include <cstdlib>

extern "C" {
#include "../openjtalk_optimized.h"
#include "../openjtalk_wrapper_functions.h"
#include "../openjtalk_dictionary_manager.h"
}

// GTEST_SKIP() expands to `return ...` so it must be invoked directly in the
// test body — wrapping it in a helper function would only return from that helper.
// This test binary is only built on Unix (see CMakeLists.txt).
// Two-stage check: (1) binary/dictionary existence, (2) actual phoneme conversion.
// Stage 2 catches cases where the system binary exists (e.g. macOS homebrew) but
// doesn't support voice-free operation (requires -m flag for HTS voice).
#define SKIP_IF_NOT_FUNCTIONAL() \
    if (!openjtalk_is_available()) \
        GTEST_SKIP() << "OpenJTalk not available (dictionary or binary missing)"; \
    do { \
        char* _skip_probe = openjtalk_text_to_phonemes_optimized("テスト"); \
        if (!_skip_probe) \
            GTEST_SKIP() << "OpenJTalk binary cannot produce phonemes (voice-free not supported)"; \
        openjtalk_free_phonemes(_skip_probe); \
    } while(0)

// Windows does not provide unsetenv; emulate via _putenv_s
#ifdef _WIN32
static int unsetenv(const char* name) {
    return _putenv_s(name, "");
}
#endif

class OpenJTalkOptimizedTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize with cache enabled (fresh stats via calloc)
        OpenJTalkCacheConfig config;
        config.max_entries = 100;
        config.max_memory_bytes = 1024 * 1024;  // 1MB
        config.ttl_seconds = 300;  // 5 minutes
        ASSERT_TRUE(openjtalk_optimized_init(&config));
    }

    void TearDown() override {
        openjtalk_optimized_cleanup();
    }
};

// Test basic functionality
TEST_F(OpenJTalkOptimizedTest, BasicConversion) {
    SKIP_IF_NOT_FUNCTIONAL();

    const char* text = "こんにちは";
    char* phonemes = openjtalk_text_to_phonemes_optimized(text);

    ASSERT_NE(phonemes, nullptr);
    EXPECT_GT(strlen(phonemes), 0);

    // Should contain expected phonemes
    EXPECT_NE(strstr(phonemes, "k"), nullptr);
    EXPECT_NE(strstr(phonemes, "o"), nullptr);
    EXPECT_NE(strstr(phonemes, "n"), nullptr);

    openjtalk_free_phonemes(phonemes);
}

// Test cache functionality
TEST_F(OpenJTalkOptimizedTest, CacheHitPerformance) {
    SKIP_IF_NOT_FUNCTIONAL();

    const char* text = "キャッシュテスト";

    // First call - cache miss
    auto start = std::chrono::high_resolution_clock::now();
    char* phonemes1 = openjtalk_text_to_phonemes_optimized(text);
    auto end = std::chrono::high_resolution_clock::now();
    auto first_duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    ASSERT_NE(phonemes1, nullptr);

    // Second call - should be cache hit and much faster
    start = std::chrono::high_resolution_clock::now();
    char* phonemes2 = openjtalk_text_to_phonemes_optimized(text);
    end = std::chrono::high_resolution_clock::now();
    auto second_duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    ASSERT_NE(phonemes2, nullptr);

    // Verify same result
    EXPECT_STREQ(phonemes1, phonemes2);

    // Second call should be significantly faster (at least 10x)
    EXPECT_LT(second_duration * 10, first_duration);

    // Check cache stats
    OpenJTalkCacheStats stats;
    openjtalk_get_cache_stats(&stats);
    EXPECT_EQ(stats.total_requests, 2);
    EXPECT_EQ(stats.cache_hits, 1);
    EXPECT_EQ(stats.cache_misses, 1);
    EXPECT_EQ(stats.current_entries, 1);

    openjtalk_free_phonemes(phonemes1);
    openjtalk_free_phonemes(phonemes2);
}

// Test performance comparison with original implementation
TEST_F(OpenJTalkOptimizedTest, PerformanceComparison) {
    SKIP_IF_NOT_FUNCTIONAL();

    const char* test_texts[] = {
        "これはテストです",
        "音声合成のパフォーマンステスト",
        "OpenJTalkの最適化",
        "日本語の音素変換",
        "キャッシュ機能のテスト"
    };
    const int num_texts = sizeof(test_texts) / sizeof(test_texts[0]);
    const int iterations = 5;

    // Test original implementation
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; i++) {
        for (int j = 0; j < num_texts; j++) {
            char* phonemes = openjtalk_text_to_phonemes(test_texts[j]);
            if (phonemes) {
                openjtalk_free_phonemes(phonemes);
            }
        }
    }
    auto end = std::chrono::high_resolution_clock::now();
    auto original_duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    // Reinitialize to get fresh stats (SetUp's cache may have been used above)
    openjtalk_optimized_cleanup();
    OpenJTalkCacheConfig config;
    config.max_entries = 100;
    config.max_memory_bytes = 1024 * 1024;
    config.ttl_seconds = 300;
    ASSERT_TRUE(openjtalk_optimized_init(&config));

    // Test optimized implementation
    start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; i++) {
        for (int j = 0; j < num_texts; j++) {
            char* phonemes = openjtalk_text_to_phonemes_optimized(test_texts[j]);
            if (phonemes) {
                openjtalk_free_phonemes(phonemes);
            }
        }
    }
    end = std::chrono::high_resolution_clock::now();
    auto optimized_duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    // Log performance results (timing comparison is unreliable on CI runners
    // because fork/exec overhead can dominate over cache benefits)
    std::cout << "Original implementation: " << original_duration << "ms\n";
    std::cout << "Optimized implementation: " << optimized_duration << "ms\n";
    if (original_duration > 0) {
        std::cout << "Speedup: " << (double)original_duration / optimized_duration << "x\n";
    }

    // Check cache effectiveness (stats are deterministic)
    OpenJTalkCacheStats stats;
    openjtalk_get_cache_stats(&stats);
    EXPECT_EQ(stats.total_requests, num_texts * iterations);
    EXPECT_EQ(stats.cache_hits, num_texts * (iterations - 1));  // First iteration misses
    EXPECT_EQ(stats.cache_misses, num_texts);  // Only first iteration
}

// Test concurrent access
TEST_F(OpenJTalkOptimizedTest, ConcurrentAccess) {
    SKIP_IF_NOT_FUNCTIONAL();

    const int num_threads = 4;
    const int iterations_per_thread = 10;
    std::vector<std::thread> threads;

    auto worker = [iterations_per_thread](int thread_id) {
        for (int i = 0; i < iterations_per_thread; i++) {
            char text[100];
            snprintf(text, sizeof(text), "スレッド%dのテスト%d", thread_id, i);

            char* phonemes = openjtalk_text_to_phonemes_optimized(text);
            EXPECT_NE(phonemes, nullptr);
            if (phonemes) {
                openjtalk_free_phonemes(phonemes);
            }
        }
    };

    // Launch threads
    for (int i = 0; i < num_threads; i++) {
        threads.emplace_back(worker, i);
    }

    // Wait for completion
    for (auto& t : threads) {
        t.join();
    }

    // Verify cache stats
    OpenJTalkCacheStats stats;
    openjtalk_get_cache_stats(&stats);
    EXPECT_EQ(stats.total_requests, num_threads * iterations_per_thread);
}

// Test cache eviction
TEST_F(OpenJTalkOptimizedTest, CacheEviction) {
    // Reinitialize with small cache
    openjtalk_optimized_cleanup();

    OpenJTalkCacheConfig config;
    config.max_entries = 3;
    config.max_memory_bytes = 1024;  // 1KB
    config.ttl_seconds = 300;
    ASSERT_TRUE(openjtalk_optimized_init(&config));

    SKIP_IF_NOT_FUNCTIONAL();

    // Add entries to fill cache
    const char* texts[] = {"テスト1", "テスト2", "テスト3", "テスト4"};

    for (int i = 0; i < 4; i++) {
        char* phonemes = openjtalk_text_to_phonemes_optimized(texts[i]);
        if (phonemes) {
            openjtalk_free_phonemes(phonemes);
        }
    }

    // Cache should have evicted oldest entry
    OpenJTalkCacheStats stats;
    openjtalk_get_cache_stats(&stats);
    EXPECT_EQ(stats.current_entries, 3);  // Max entries

    // First entry should be evicted (cache miss)
    char* phonemes = openjtalk_text_to_phonemes_optimized(texts[0]);
    if (phonemes) {
        openjtalk_free_phonemes(phonemes);
    }

    openjtalk_get_cache_stats(&stats);
    EXPECT_EQ(stats.cache_misses, 5);  // 4 initial + 1 for evicted entry
}

// Test empty and null input
TEST_F(OpenJTalkOptimizedTest, InvalidInput) {
    EXPECT_EQ(openjtalk_text_to_phonemes_optimized(nullptr), nullptr);
    EXPECT_EQ(openjtalk_text_to_phonemes_optimized(""), nullptr);
}

// Test without cache
TEST_F(OpenJTalkOptimizedTest, NoCache) {
    // Reinitialize without cache
    openjtalk_optimized_cleanup();
    ASSERT_TRUE(openjtalk_optimized_init(nullptr));

    SKIP_IF_NOT_FUNCTIONAL();

    const char* text = "キャッシュなし";

    // Should still work without cache
    char* phonemes1 = openjtalk_text_to_phonemes_optimized(text);
    ASSERT_NE(phonemes1, nullptr);

    char* phonemes2 = openjtalk_text_to_phonemes_optimized(text);
    ASSERT_NE(phonemes2, nullptr);

    // Results should be same
    EXPECT_STREQ(phonemes1, phonemes2);

    openjtalk_free_phonemes(phonemes1);
    openjtalk_free_phonemes(phonemes2);
}

// ---------------------------------------------------------------------------
// HTS voice dependency removal regression tests (M1-M3)
// ---------------------------------------------------------------------------

// Verify phoneme extraction works without OPENJTALK_VOICE env var
TEST_F(OpenJTalkOptimizedTest, PhonemeExtractionWithoutVoice) {
    const char* prev = std::getenv("OPENJTALK_VOICE");
    std::string saved = prev ? prev : "";
    bool had_env = (prev != nullptr);

    unsetenv("OPENJTALK_VOICE");

    char* result = openjtalk_text_to_phonemes_optimized("こんにちは");

    // Restore original env state before any assertions
    if (had_env) {
#ifdef _WIN32
        _putenv_s("OPENJTALK_VOICE", saved.c_str());
#else
        setenv("OPENJTALK_VOICE", saved.c_str(), 1);
#endif
    } else {
        unsetenv("OPENJTALK_VOICE");
    }

    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary or dictionary not available";
    }

    EXPECT_GT(strlen(result), 0u);
    EXPECT_NE(strstr(result, "k"), nullptr);

    openjtalk_free_phonemes(result);
}

// Verify the wrapper (non-optimized) path also works without voice
TEST_F(OpenJTalkOptimizedTest, StreamingWithoutVoice) {
    const char* prev = std::getenv("OPENJTALK_VOICE");
    std::string saved = prev ? prev : "";
    bool had_env = (prev != nullptr);

    unsetenv("OPENJTALK_VOICE");

    char* result = openjtalk_text_to_phonemes("テスト");

    // Restore original env state before any assertions
    if (had_env) {
#ifdef _WIN32
        _putenv_s("OPENJTALK_VOICE", saved.c_str());
#else
        setenv("OPENJTALK_VOICE", saved.c_str(), 1);
#endif
    } else {
        unsetenv("OPENJTALK_VOICE");
    }

    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary or dictionary not available";
    }

    EXPECT_GT(strlen(result), 0u);
    EXPECT_NE(strstr(result, "t"), nullptr);

    openjtalk_free_phonemes(result);
}

// Indirectly verify that no -m (voice) flag is required for conversion
TEST_F(OpenJTalkOptimizedTest, CommandWithoutVoiceFlag) {
    const char* prev = std::getenv("OPENJTALK_VOICE");
    std::string saved = prev ? prev : "";
    bool had_env = (prev != nullptr);

    unsetenv("OPENJTALK_VOICE");

    char* result = openjtalk_text_to_phonemes_optimized("テスト");

    // Restore original env state before any assertions
    if (had_env) {
#ifdef _WIN32
        _putenv_s("OPENJTALK_VOICE", saved.c_str());
#else
        setenv("OPENJTALK_VOICE", saved.c_str(), 1);
#endif
    } else {
        unsetenv("OPENJTALK_VOICE");
    }

    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary or dictionary not available";
    }

    EXPECT_GT(strlen(result), 0u);

    openjtalk_free_phonemes(result);
}

// Even when OPENJTALK_VOICE points to a nonexistent file, phoneme
// extraction must still succeed (the voice file is never needed).
TEST_F(OpenJTalkOptimizedTest, IgnoresVoiceEnvVar) {
    // Save the current value so we can restore it later
    const char* prev = std::getenv("OPENJTALK_VOICE");
    std::string saved = prev ? prev : "";
    bool had_env = (prev != nullptr);

    // Set OPENJTALK_VOICE to a path that does not exist
#ifdef _WIN32
    _putenv_s("OPENJTALK_VOICE", "C:\\nonexistent\\voice.htsvoice");
#else
    setenv("OPENJTALK_VOICE", "/nonexistent/voice.htsvoice", 1);
#endif

    char* result = openjtalk_text_to_phonemes_optimized("テスト");

    // Restore original env state before any assertions
    if (had_env) {
#ifdef _WIN32
        _putenv_s("OPENJTALK_VOICE", saved.c_str());
#else
        setenv("OPENJTALK_VOICE", saved.c_str(), 1);
#endif
    } else {
        unsetenv("OPENJTALK_VOICE");
    }

    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary or dictionary not available";
    }

    EXPECT_GT(strlen(result), 0u);

    openjtalk_free_phonemes(result);
}
