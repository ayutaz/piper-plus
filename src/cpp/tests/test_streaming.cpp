#include <gtest/gtest.h>
#include <sstream>
#include <chrono>
#include <thread>
#include <atomic>
#include "../piper.hpp"

class StreamingTest : public ::testing::Test {
protected:
    piper::PiperConfig config;
    piper::Voice voice;
    
    void SetUp() override {
        // Initialize with minimal config
        config.useESpeak = false;
        
        // Set up text phoneme voice config
        voice.phonemizeConfig.phonemeType = piper::TextPhonemes;
        
        // Minimal phoneme map for testing
        voice.phonemizeConfig.phonemeIdMap = {
            {'h', {1}}, {'e', {2}}, {'l', {3}}, {'o', {4}},
            {' ', {5}}, {'w', {6}}, {'r', {7}}, {'d', {8}},
            {'.', {9}}, {'!', {10}}, {'?', {11}}
        };
        
        // Set sample rate for audio duration calculations
        voice.synthesisConfig.sampleRate = 22050;
        voice.synthesisConfig.channels = 1;
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
    
    // Skip test - requires actual model
    GTEST_SKIP() << "Skipping streaming test - no model loaded";
    
    // This would be the actual test with a model:
    // piper::textToAudioStreaming(config, voice, text, audioBuffer, 
    //                             result, chunkCallback);
    // 
    // EXPECT_GT(chunkCount, 1) << "Expected multiple chunks for multi-sentence text";
    // EXPECT_GT(audioBuffer.size(), 0) << "Expected audio output";
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
    
    // Skip test - requires actual model
    GTEST_SKIP() << "Skipping streaming test - no model loaded";
    
    // This would verify progressive output:
    // piper::textToAudioStreaming(config, voice, text, audioBuffer, 
    //                             result, chunkCallback);
    // 
    // ASSERT_GT(chunkTimes.size(), 1);
    // for (size_t i = 1; i < chunkTimes.size(); i++) {
    //     EXPECT_GT(chunkTimes[i].count(), chunkTimes[i-1].count()) 
    //         << "Chunks should arrive progressively over time";
    // }
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
    
    // Skip test - requires actual model
    GTEST_SKIP() << "Skipping streaming test - no model loaded";
    
    // This would test single chunk:
    // piper::textToAudioStreaming(config, voice, text, audioBuffer, 
    //                             result, chunkCallback);
    // 
    // EXPECT_EQ(chunkCount, 1) << "Single word should produce one chunk";
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
    
    // Skip test - requires actual model
    GTEST_SKIP() << "Skipping streaming test - no model loaded";
    
    // This would compare outputs:
    // piper::textToAudio(config, voice, text, regularBuffer, regularResult, nullptr);
    // piper::textToAudioStreaming(config, voice, text, streamingBuffer, 
    //                             streamingResult, chunkCallback);
    // 
    // EXPECT_EQ(regularBuffer.size(), streamingBuffer.size()) 
    //     << "Both modes should produce same amount of audio";
    // 
    // Compare RTF within reasonable tolerance
    // EXPECT_NEAR(regularResult.realTimeFactor, streamingResult.realTimeFactor, 0.1)
    //     << "Real-time factors should be similar";
}