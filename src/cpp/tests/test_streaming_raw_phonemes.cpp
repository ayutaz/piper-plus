#include <gtest/gtest.h>
#include <spdlog/spdlog.h>
#include <vector>
#include <string>
#include <chrono>
#include <filesystem>
#include <optional>

#include "piper.hpp"
#include "phoneme_parser.hpp"

namespace fs = std::filesystem;

namespace piper {

// Shared model path resolved once per test suite
static const char* g_model_path = nullptr;
static const char* g_config_path = nullptr;

class StreamingRawPhonemesTest : public ::testing::Test {
protected:
  PiperConfig config;
  Voice voice;

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
      GTEST_SKIP() << "Test model not found; skipping streaming test";
      return;
    }

    // Load the model and config via loadVoice
    std::optional<SpeakerId> speakerId;
    loadVoice(config, std::string(g_model_path), std::string(g_config_path),
              voice, speakerId, "cpu", 0, 1);
  }
};

TEST_F(StreamingRawPhonemesTest, BasicStreamingTest) {

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
  
  // Both should produce non-empty audio
  EXPECT_GT(regularBuffer.size(), 0) << "Regular synthesis should produce audio";
  EXPECT_GT(streamingBuffer.size(), 0) << "Streaming synthesis should produce audio";

  // Streaming with small chunk sizes produces larger output because each chunk
  // is synthesized independently with its own VITS padding, so we only verify
  // that streaming output is at least as large as regular output.
  EXPECT_GE(streamingBuffer.size(), regularBuffer.size())
      << "Streaming output should be at least as large as regular output";

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