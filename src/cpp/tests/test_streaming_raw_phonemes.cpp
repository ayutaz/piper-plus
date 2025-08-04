#include <gtest/gtest.h>
#include <spdlog/spdlog.h>
#include <vector>
#include <string>
#include <chrono>

#include "piper.hpp"
#include "phoneme_parser.hpp"

namespace piper {

class StreamingRawPhonemesTest : public ::testing::Test {
protected:
  PiperConfig config;
  Voice voice;
  std::string modelPath;
  
  void SetUp() override {
    // Use the test model if available
    modelPath = "test/models/text_voice.onnx";
    
    // Initialize minimal voice configuration
    voice.phonemizeConfig.phonemeType = PHONEME_TYPE_ESPEAK;
    voice.phonemizeConfig.interspersePad = true;
    
    // Create basic phoneme map
    voice.phonemizeConfig.phonemeIdMap[PHONEME_PAD] = 0;
    voice.phonemizeConfig.phonemeIdMap[PHONEME_BOS] = 1;
    voice.phonemizeConfig.phonemeIdMap[PHONEME_EOS] = 2;
    
    // Add some basic phonemes for testing
    PhonemeId id = 3;
    for (char c = 'a'; c <= 'z'; c++) {
      voice.phonemizeConfig.phonemeIdMap[c] = id++;
    }
    
    // Set synthesis config
    voice.synthesisConfig.sampleRate = 22050;
    voice.synthesisConfig.sampleWidth = 2;
    voice.synthesisConfig.channels = 1;
  }
};

TEST_F(StreamingRawPhonemesTest, BasicStreamingTest) {
  // Skip if no model is loaded
  if (!std::filesystem::exists(modelPath)) {
    GTEST_SKIP() << "Skipping streaming test - no model at " << modelPath;
  }
  
  // Test phoneme string
  std::string phonemeString = "h ə l oʊ w ɜː l d";
  auto phonemes = parsePhonemeString(phonemeString, PHONEME_TYPE_ESPEAK);
  
  std::vector<int16_t> audioBuffer;
  SynthesisResult result;
  
  // Track chunks received
  size_t chunksReceived = 0;
  std::vector<size_t> chunkSizes;
  
  auto chunkCallback = [&](const std::vector<int16_t>& chunk) {
    chunksReceived++;
    chunkSizes.push_back(chunk.size());
  };
  
  // Test streaming synthesis
  phonemesToAudioStreaming(config, voice, phonemes, audioBuffer, result, 
                           chunkCallback, 5); // 5 phonemes per chunk
  
  // Verify we received chunks
  EXPECT_GT(chunksReceived, 0) << "Should receive at least one chunk";
  
  // Verify audio was generated
  EXPECT_GT(audioBuffer.size(), 0) << "Should generate audio";
  
  // Verify chunks match expected count (8 phonemes / 5 per chunk = 2 chunks)
  size_t expectedChunks = (phonemes.size() + 4) / 5;
  EXPECT_EQ(chunksReceived, expectedChunks) << "Should receive expected number of chunks";
}

TEST_F(StreamingRawPhonemesTest, CompareStreamingVsRegular) {
  // Skip if no model is loaded
  if (!std::filesystem::exists(modelPath)) {
    GTEST_SKIP() << "Skipping streaming test - no model at " << modelPath;
  }
  
  std::string phonemeString = "t ɛ s t ɪ ŋ s t r iː m ɪ ŋ";
  auto phonemes = parsePhonemeString(phonemeString, PHONEME_TYPE_ESPEAK);
  
  // Regular synthesis
  std::vector<int16_t> regularBuffer;
  SynthesisResult regularResult;
  phonemesToAudio(config, voice, phonemes, regularBuffer, regularResult);
  
  // Streaming synthesis
  std::vector<int16_t> streamingBuffer;
  SynthesisResult streamingResult;
  size_t chunks = 0;
  
  phonemesToAudioStreaming(config, voice, phonemes, streamingBuffer, 
                           streamingResult, 
                           [&](const std::vector<int16_t>&) { chunks++; },
                           4); // Small chunks for testing
  
  // Audio sizes should be similar (streaming might have slight variations)
  EXPECT_NEAR(regularBuffer.size(), streamingBuffer.size(), 
              regularBuffer.size() * 0.1) // Allow 10% variation
      << "Streaming and regular audio should have similar sizes";
  
  // Verify we got multiple chunks
  EXPECT_GT(chunks, 1) << "Should receive multiple chunks for streaming";
}

TEST_F(StreamingRawPhonemesTest, EmptyPhonemesTest) {
  std::vector<Phoneme> phonemes; // Empty
  std::vector<int16_t> audioBuffer;
  SynthesisResult result;
  
  size_t chunksReceived = 0;
  auto chunkCallback = [&](const std::vector<int16_t>&) {
    chunksReceived++;
  };
  
  // Should handle empty phonemes gracefully
  phonemesToAudioStreaming(config, voice, phonemes, audioBuffer, result, 
                           chunkCallback);
  
  EXPECT_EQ(audioBuffer.size(), 0) << "Empty phonemes should produce no audio";
  EXPECT_EQ(chunksReceived, 0) << "Empty phonemes should produce no chunks";
}

TEST_F(StreamingRawPhonemesTest, PerformanceTest) {
  // Skip if no model is loaded
  if (!std::filesystem::exists(modelPath)) {
    GTEST_SKIP() << "Skipping performance test - no model at " << modelPath;
  }
  
  // Create a longer phoneme sequence
  std::string longPhonemeString = "p ɜː f ɔː m ə n s t ɛ s t ";
  for (int i = 0; i < 5; i++) {
    longPhonemeString += longPhonemeString;
  }
  
  auto phonemes = parsePhonemeString(longPhonemeString, PHONEME_TYPE_ESPEAK);
  
  std::vector<int16_t> audioBuffer;
  SynthesisResult result;
  
  // Measure time to first chunk
  std::chrono::steady_clock::time_point firstChunkTime;
  bool firstChunk = true;
  
  auto start = std::chrono::steady_clock::now();
  
  phonemesToAudioStreaming(config, voice, phonemes, audioBuffer, result,
                           [&](const std::vector<int16_t>&) {
                             if (firstChunk) {
                               firstChunkTime = std::chrono::steady_clock::now();
                               firstChunk = false;
                             }
                           },
                           10);
  
  auto end = std::chrono::steady_clock::now();
  
  // Calculate latencies
  auto timeToFirstChunk = std::chrono::duration_cast<std::chrono::milliseconds>(
      firstChunkTime - start).count();
  auto totalTime = std::chrono::duration_cast<std::chrono::milliseconds>(
      end - start).count();
  
  spdlog::info("Streaming performance: {} phonemes, {}ms to first chunk, {}ms total",
               phonemes.size(), timeToFirstChunk, totalTime);
  
  // Verify streaming provides lower latency to first audio
  EXPECT_LT(timeToFirstChunk, totalTime / 2) 
      << "First chunk should arrive before half the total processing time";
}

} // namespace piper