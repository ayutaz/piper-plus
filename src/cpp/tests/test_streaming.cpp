/**
 * test_streaming.cpp — Streaming synthesis integration tests (model required)
 *
 * Tests textToAudioStreaming with a real ONNX model.
 * Requires test model at test/models/multilingual-test-medium.onnx
 * Auto-skips if model not found.
 */

#include <gtest/gtest.h>
#include <filesystem>
#include <sstream>
#include <chrono>
#include <thread>
#include <atomic>
#include "../piper.hpp"

namespace fs = std::filesystem;

// Shared model state across all StreamingTest instances
static std::string g_streaming_model_path;
static std::string g_streaming_config_path;
static bool g_streaming_model_found = false;

class StreamingTest : public ::testing::Test {
protected:
    piper::PiperConfig config;
    piper::Voice voice;

    static void SetUpTestSuite() {
        std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };
        for (const auto& path : searchPaths) {
            if (fs::exists(path)) {
                std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_streaming_model_path = path;
                    g_streaming_config_path = configPath;
                    g_streaming_model_found = true;
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_streaming_model_found) {
            GTEST_SKIP() << "Test model not found; skipping streaming test";
        }

        std::optional<piper::SpeakerId> speakerId;
        loadVoice(config, g_streaming_model_path, g_streaming_config_path,
                  voice, speakerId, "cpu");
        piper::initialize(config);
    }

    void TearDown() override {
        if (g_streaming_model_found) {
            piper::terminate(config);
        }
    }
};

TEST_F(StreamingTest, ChunkCallbackIsCalledMultipleTimes) {
    std::string text = "Hello world. This is a test. Multiple sentences here!";
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    std::atomic<int> chunkCount(0);
    std::vector<size_t> chunkSizes;

    auto chunkCallback = [&](const std::vector<int16_t>& chunk) {
        chunkCount++;
        chunkSizes.push_back(chunk.size());
    };

    piper::textToAudioStreaming(config, voice, text, audioBuffer,
                                result, chunkCallback);

    EXPECT_GT(chunkCount, 1) << "Expected multiple chunks for multi-sentence text";
    EXPECT_GT(audioBuffer.size(), 0) << "Expected audio output";
}

TEST_F(StreamingTest, StreamingProducesAudioProgressively) {
    std::string text = "First sentence. Second sentence. Third sentence.";
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    std::vector<std::chrono::milliseconds> chunkTimes;
    auto startTime = std::chrono::steady_clock::now();

    auto chunkCallback = [&](const std::vector<int16_t>& chunk) {
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - startTime
        );
        chunkTimes.push_back(elapsed);
    };

    piper::textToAudioStreaming(config, voice, text, audioBuffer,
                                result, chunkCallback);

    ASSERT_GT(chunkTimes.size(), 1);
    for (size_t i = 1; i < chunkTimes.size(); i++) {
        EXPECT_GE(chunkTimes[i].count(), chunkTimes[i-1].count())
            << "Chunks should arrive progressively over time";
    }
}

TEST_F(StreamingTest, EmptyTextProducesNoAudio) {
    std::string text = "";
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    int chunkCount = 0;
    auto chunkCallback = [&](const std::vector<int16_t>& chunk) {
        chunkCount++;
    };

    piper::textToAudioStreaming(config, voice, text, audioBuffer,
                                result, chunkCallback);

    EXPECT_EQ(chunkCount, 0) << "Empty text should produce no chunks";
    EXPECT_EQ(audioBuffer.size(), 0) << "Empty text should produce no audio";
}

TEST_F(StreamingTest, SingleWordProducesOneChunk) {
    std::string text = "Hello";
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    int chunkCount = 0;
    auto chunkCallback = [&](const std::vector<int16_t>& chunk) {
        chunkCount++;
    };

    piper::textToAudioStreaming(config, voice, text, audioBuffer,
                                result, chunkCallback);

    EXPECT_EQ(chunkCount, 1) << "Single word should produce one chunk";
}

TEST_F(StreamingTest, StreamingAndRegularProduceSameAudio) {
    std::string text = "Test sentence for comparison.";

    // Regular synthesis
    std::vector<int16_t> regularBuffer;
    piper::SynthesisResult regularResult;

    // Streaming synthesis
    std::vector<int16_t> streamingBuffer;
    piper::SynthesisResult streamingResult;

    auto chunkCallback = [](const std::vector<int16_t>& chunk) {};

    piper::textToAudio(config, voice, text, regularBuffer, regularResult, nullptr);
    piper::textToAudioStreaming(config, voice, text, streamingBuffer,
                                streamingResult, chunkCallback);

    EXPECT_EQ(regularBuffer.size(), streamingBuffer.size())
        << "Both modes should produce same amount of audio";

    // Compare RTF within reasonable tolerance
    EXPECT_NEAR(regularResult.realTimeFactor, streamingResult.realTimeFactor, 0.5)
        << "Real-time factors should be similar";
}
