#include <gtest/gtest.h>
#include <spdlog/spdlog.h>
#include <vector>
#include <string>
#include <chrono>
#include <filesystem>
#include <optional>
#include <sstream>

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

// ============================================================================
// phonemeIdsToWavFile (Phase 2: cross-runtime audio byte parity)
// ============================================================================
//
// PR #511 で追加した piper::phonemeIdsToWavFile API の単体テスト。 G2P を
// バイパスして phoneme IDs を直接渡す経路で、 Rust / Go / C# / Python /
// WASM と同一の入力契約 (docs/spec/audio-parity-contract.toml) を満たす
// ことを保証する。 fixture (tests/fixtures/audio-corpus/parity/
// phoneme_ids.jsonl) は `^ a _ i _ u _ e _ o _ $` = `[1,10,0,11,0,12,0,
// 13,0,14,0,2]` で固定されており、 ここでも同じ ID 列を直接 vector
// として組み立て canonical 入力として扱う。

namespace {

// Read a 32-bit little-endian unsigned int from a WAV byte buffer at offset.
uint32_t readU32LE(const std::string &buf, size_t offset) {
  return static_cast<uint32_t>(static_cast<unsigned char>(buf[offset])) |
         (static_cast<uint32_t>(static_cast<unsigned char>(buf[offset + 1])) << 8) |
         (static_cast<uint32_t>(static_cast<unsigned char>(buf[offset + 2])) << 16) |
         (static_cast<uint32_t>(static_cast<unsigned char>(buf[offset + 3])) << 24);
}

// Read a 16-bit little-endian unsigned int from a WAV byte buffer at offset.
uint16_t readU16LE(const std::string &buf, size_t offset) {
  return static_cast<uint16_t>(static_cast<unsigned char>(buf[offset])) |
         (static_cast<uint16_t>(static_cast<unsigned char>(buf[offset + 1])) << 8);
}

} // namespace

TEST_F(StreamingRawPhonemesTest, PhonemeIdsToWavBasicHeader) {
  // Canonical fixture phoneme IDs ("あいうえお" with PAD intersperse)
  std::vector<piper::PhonemeId> ids = {1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2};

  std::ostringstream wavStream(std::ios::binary);
  piper::SynthesisResult result;

  piper::phonemeIdsToWavFile(config, voice, ids, wavStream, result);

  const std::string wav = wavStream.str();
  ASSERT_GT(wav.size(), 44u) << "WAV must contain RIFF header + at least some PCM";

  // RIFF / WAVE / fmt / data magic bytes
  EXPECT_EQ(wav.substr(0, 4), "RIFF");
  EXPECT_EQ(wav.substr(8, 4), "WAVE");
  EXPECT_EQ(wav.substr(12, 4), "fmt ");
  EXPECT_EQ(wav.substr(36, 4), "data");

  // fmt chunk: PCM=1, mono=1, sample_rate=22050, bits=16
  EXPECT_EQ(readU16LE(wav, 20), 1) << "PCM format";
  EXPECT_EQ(readU16LE(wav, 22), 1) << "mono channel count";
  EXPECT_EQ(readU32LE(wav, 24), voice.synthesisConfig.sampleRate);
  EXPECT_EQ(readU16LE(wav, 34), voice.synthesisConfig.sampleWidth * 8u)
      << "bits per sample matches voice config";

  // data chunk size matches the actual sample bytes
  const uint32_t dataSize = readU32LE(wav, 40);
  EXPECT_EQ(dataSize, wav.size() - 44) << "data chunk size matches payload";
}

TEST_F(StreamingRawPhonemesTest, PhonemeIdsToWavSameLengthOnRepeat) {
  // VITS のサンプリングは stochastic (noise_scale > 0) なので、 同じ
  // phoneme IDs でも 2 回呼ぶと byte-identical な WAV にはならない。 これは
  // cross-runtime parity gate が tier 1 (SHA256) ではなく tier 2 (peak RMS)
  // / tier 3 (SNR) で吸収する設計の前提 (docs/spec/audio-parity-contract.toml
  // を参照)。 ここではより弱い不変条件 — 「同じ ID 列を渡せばフレーム数
  // (= audio 長さ) は同一」 — を assert することで Strategy A の padding 量と
  // EOS 切り捨ての挙動を pin する。
  std::vector<piper::PhonemeId> ids = {1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2};

  std::ostringstream firstStream(std::ios::binary);
  piper::SynthesisResult firstResult;
  piper::phonemeIdsToWavFile(config, voice, ids, firstStream, firstResult);

  std::ostringstream secondStream(std::ios::binary);
  piper::SynthesisResult secondResult;
  std::vector<piper::PhonemeId> ids2 = {1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2};
  piper::phonemeIdsToWavFile(config, voice, ids2, secondStream, secondResult);

  const std::string a = firstStream.str();
  const std::string b = secondStream.str();
  EXPECT_EQ(a.size(), b.size())
      << "same phoneme IDs must yield same number of audio samples";
  // Headers (44 bytes) and data chunk size declared in the header should
  // match byte-for-byte even when the PCM body diverges due to noise.
  EXPECT_EQ(a.substr(0, 44), b.substr(0, 44))
      << "WAV header layout must be deterministic for identical inputs";
}

TEST_F(StreamingRawPhonemesTest, PhonemeIdsToWavShortInputProducesAudio) {
  // Minimum viable input: BOS + single phoneme + EOS. Strategy A short-text
  // padding is applied inside synthesize() so the output is non-empty even
  // for a 3-ID input.
  std::vector<piper::PhonemeId> ids = {1, 10, 2};

  std::ostringstream wavStream(std::ios::binary);
  piper::SynthesisResult result;

  piper::phonemeIdsToWavFile(config, voice, ids, wavStream, result);

  const std::string wav = wavStream.str();
  EXPECT_GT(wav.size(), 44u) << "header + body";
  EXPECT_GT(readU32LE(wav, 40), 0u) << "non-empty data chunk";
}

TEST_F(StreamingRawPhonemesTest, PhonemeIdsToWavDifferentInputsDifferentOutputs) {
  // Two distinct phoneme ID sequences should produce distinct WAV payloads.
  // This guards against a regression where synthesize() inadvertently caches
  // / reuses output across calls (which would silently pass the parity gate).
  std::vector<piper::PhonemeId> idsA = {1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2};
  std::vector<piper::PhonemeId> idsB = {1, 14, 0, 13, 0, 12, 0, 11, 0, 10, 0, 2}; // reversed body

  std::ostringstream streamA(std::ios::binary);
  std::ostringstream streamB(std::ios::binary);
  piper::SynthesisResult resultA, resultB;

  piper::phonemeIdsToWavFile(config, voice, idsA, streamA, resultA);
  piper::phonemeIdsToWavFile(config, voice, idsB, streamB, resultB);

  const std::string wavA = streamA.str();
  const std::string wavB = streamB.str();
  EXPECT_GT(wavA.size(), 44u);
  EXPECT_GT(wavB.size(), 44u);
  // Headers can be identical (same length / sample rate) but the data
  // payload (offset 44 onward) must differ for different inputs.
  EXPECT_NE(wavA.substr(44), wavB.substr(44))
      << "different phoneme IDs must produce different audio data";
}

} // namespace piper
