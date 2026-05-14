// Voice Cloning CLI argument parse tests (parity gate with Python/Rust/Go/C#/WASM).
//
// These tests verify the CLI argument parsing logic for the three voice cloning
// flags: --reference-audio, --speaker-embedding, --speaker-encoder-model.
//
// Following the same pattern as test_text_input.cpp: a local `testParseArgs`
// mirrors the main.cpp argument-parsing logic so the tests do not require
// loading an ONNX model. Full E2E (with an actual encoder model) is gated by
// test_speaker_encoder_e2e.cpp / test_speaker_embedding_inference.cpp.

#include <gtest/gtest.h>

#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct TestRunConfig {
    std::optional<std::filesystem::path> referenceAudioPath;
    std::optional<std::filesystem::path> speakerEmbeddingPath;
    std::optional<std::filesystem::path> speakerEncoderModelPath;
};

// Mirrors the argument-parsing logic + validation in src/cpp/main.cpp for the
// three voice cloning flags. Keep this in sync with parseArgs() over there.
void testParseArgs(const std::vector<std::string>& args, TestRunConfig& cfg) {
    for (size_t i = 0; i < args.size(); ++i) {
        const auto& arg = args[i];
        if (arg == "--reference-audio" || arg == "--reference_audio") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --reference-audio");
            cfg.referenceAudioPath = std::filesystem::path(args[++i]);
        } else if (arg == "--speaker-embedding" || arg == "--speaker_embedding") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --speaker-embedding");
            cfg.speakerEmbeddingPath = std::filesystem::path(args[++i]);
        } else if (arg == "--speaker-encoder-model" || arg == "--speaker_encoder_model") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --speaker-encoder-model");
            cfg.speakerEncoderModelPath = std::filesystem::path(args[++i]);
        }
    }

    // Mutually exclusive: --reference-audio / --speaker-embedding
    if (cfg.referenceAudioPath && cfg.speakerEmbeddingPath) {
        throw std::runtime_error("--reference-audio and --speaker-embedding are mutually exclusive");
    }
    // --reference-audio requires --speaker-encoder-model
    if (cfg.referenceAudioPath && !cfg.speakerEncoderModelPath) {
        throw std::runtime_error("--speaker-encoder-model is required when using --reference-audio");
    }
}

// Mirror of loadSpeakerEmbeddingBin() in main.cpp. Reads a raw float32 LE blob.
std::vector<float> testLoadSpeakerEmbeddingBin(const std::filesystem::path& path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f.good()) {
        throw std::runtime_error("Failed to open speaker embedding file: " + path.string());
    }
    auto bytes = static_cast<std::streamsize>(f.tellg());
    if (bytes < 0) {
        throw std::runtime_error("Failed to stat speaker embedding file: " + path.string());
    }
    if (bytes % 4 != 0) {
        throw std::runtime_error("Speaker embedding file size is not a multiple of 4 (float32)");
    }
    f.seekg(0, std::ios::beg);
    std::vector<float> floats(static_cast<size_t>(bytes) / sizeof(float));
    if (!floats.empty()) {
        f.read(reinterpret_cast<char*>(floats.data()), bytes);
        if (!f) {
            throw std::runtime_error("Failed to read speaker embedding file");
        }
    }
    return floats;
}

// Write 256 random-looking float32 LE values to a temp file. Returns the path.
std::filesystem::path writeFakeEmbeddingFile(size_t dim, float seed) {
    auto path = std::filesystem::temp_directory_path() /
                ("piper_test_emb_" + std::to_string(static_cast<int>(seed * 1000)) + ".bin");
    std::ofstream f(path, std::ios::binary);
    for (size_t i = 0; i < dim; ++i) {
        float v = seed + 0.001f * static_cast<float>(i);
        f.write(reinterpret_cast<const char*>(&v), sizeof(float));
    }
    return path;
}

} // namespace

// ============================================
// CLI flag parsing
// ============================================

TEST(VoiceCloningCliTest, ParseReferenceAudio) {
    TestRunConfig cfg;
    testParseArgs(
        {"--reference-audio", "/tmp/ref.wav",
            "--speaker-encoder-model", "/tmp/enc.onnx"},
        cfg);
    ASSERT_TRUE(cfg.referenceAudioPath.has_value());
    EXPECT_EQ(cfg.referenceAudioPath->string(), "/tmp/ref.wav");
    ASSERT_TRUE(cfg.speakerEncoderModelPath.has_value());
    EXPECT_EQ(cfg.speakerEncoderModelPath->string(), "/tmp/enc.onnx");
}

TEST(VoiceCloningCliTest, ParseSpeakerEmbedding) {
    TestRunConfig cfg;
    testParseArgs({"--speaker-embedding", "/tmp/emb.bin"}, cfg);
    ASSERT_TRUE(cfg.speakerEmbeddingPath.has_value());
    EXPECT_EQ(cfg.speakerEmbeddingPath->string(), "/tmp/emb.bin");
    EXPECT_FALSE(cfg.referenceAudioPath.has_value());
}

TEST(VoiceCloningCliTest, ParseUnderscoreAliases) {
    TestRunConfig cfg;
    testParseArgs(
        {"--reference_audio", "/tmp/ref.wav",
            "--speaker_encoder_model", "/tmp/enc.onnx"},
        cfg);
    ASSERT_TRUE(cfg.referenceAudioPath.has_value());
    ASSERT_TRUE(cfg.speakerEncoderModelPath.has_value());
}

TEST(VoiceCloningCliTest, ParseSpeakerEmbeddingUnderscore) {
    TestRunConfig cfg;
    testParseArgs({"--speaker_embedding", "/tmp/emb.bin"}, cfg);
    ASSERT_TRUE(cfg.speakerEmbeddingPath.has_value());
}

// ============================================
// Mutex validation
// ============================================

TEST(VoiceCloningCliTest, ReferenceAudioAndSpeakerEmbeddingMutuallyExclusive) {
    TestRunConfig cfg;
    EXPECT_THROW(
        testParseArgs(
            {"--reference-audio", "/tmp/ref.wav",
                "--speaker-encoder-model", "/tmp/enc.onnx",
                "--speaker-embedding", "/tmp/emb.bin"},
            cfg),
        std::runtime_error);
}

TEST(VoiceCloningCliTest, ReferenceAudioRequiresEncoderModel) {
    TestRunConfig cfg;
    EXPECT_THROW(
        testParseArgs({"--reference-audio", "/tmp/ref.wav"}, cfg),
        std::runtime_error
    );
}

TEST(VoiceCloningCliTest, SpeakerEmbeddingAloneIsValid) {
    TestRunConfig cfg;
    testParseArgs({"--speaker-embedding", "/tmp/emb.bin"}, cfg);
    EXPECT_TRUE(cfg.speakerEmbeddingPath.has_value());
    EXPECT_FALSE(cfg.referenceAudioPath.has_value());
}

TEST(VoiceCloningCliTest, NoFlagsIsValid) {
    TestRunConfig cfg;
    testParseArgs({}, cfg);
    EXPECT_FALSE(cfg.referenceAudioPath.has_value());
    EXPECT_FALSE(cfg.speakerEmbeddingPath.has_value());
    EXPECT_FALSE(cfg.speakerEncoderModelPath.has_value());
}

TEST(VoiceCloningCliTest, MissingArgumentValueThrows) {
    TestRunConfig cfg;
    EXPECT_THROW(testParseArgs({"--reference-audio"}, cfg), std::runtime_error);
    EXPECT_THROW(testParseArgs({"--speaker-embedding"}, cfg), std::runtime_error);
    EXPECT_THROW(testParseArgs({"--speaker-encoder-model"}, cfg), std::runtime_error);
}

// ============================================
// Embedding loader (raw float32 LE binary format)
// ============================================

TEST(VoiceCloningEmbeddingLoaderTest, Load256DimEmbedding) {
    auto path = writeFakeEmbeddingFile(256, 0.5f);
    auto emb = testLoadSpeakerEmbeddingBin(path);
    EXPECT_EQ(emb.size(), 256u);
    // Spot-check first / last values match the seed formula.
    EXPECT_FLOAT_EQ(emb[0], 0.5f);
    EXPECT_FLOAT_EQ(emb[255], 0.5f + 0.001f * 255.0f);
    std::filesystem::remove(path);
}

TEST(VoiceCloningEmbeddingLoaderTest, MissingFileThrows) {
    EXPECT_THROW(
        testLoadSpeakerEmbeddingBin("/nonexistent/path/to/emb.bin"),
        std::runtime_error
    );
}

TEST(VoiceCloningEmbeddingLoaderTest, OddByteCountThrows) {
    auto path = std::filesystem::temp_directory_path() / "piper_test_emb_odd.bin";
    {
        std::ofstream f(path, std::ios::binary);
        // 5 bytes — not divisible by 4.
        const char junk[] = {0x01, 0x02, 0x03, 0x04, 0x05};
        f.write(junk, sizeof(junk));
    }
    EXPECT_THROW(testLoadSpeakerEmbeddingBin(path), std::runtime_error);
    std::filesystem::remove(path);
}
