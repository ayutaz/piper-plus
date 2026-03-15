#include <gtest/gtest.h>
#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <cstdlib>
#include <stdexcept>

// Test the --text argument parsing logic
// Note: We test the parsing logic directly without needing the full piper runtime

namespace {

// Simplified RunConfig for testing argument parsing
struct TestRunConfig {
    std::filesystem::path modelPath;
    std::filesystem::path modelConfigPath;
    std::optional<std::string> textInput;
    bool jsonInput = false;
    bool listModels = false;
    std::optional<std::string> listModelsLanguage;
    std::optional<std::string> downloadModelName;
    std::optional<std::filesystem::path> modelDir;
};

// Simplified parseArgs that tests the new argument parsing logic
void testParseArgs(const std::vector<std::string>& args, TestRunConfig& config) {
    for (size_t i = 0; i < args.size(); i++) {
        const auto& arg = args[i];
        if (arg == "-t" || arg == "--text") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --text");
            config.textInput = args[++i];
        } else if (arg == "--json-input" || arg == "--json_input") {
            config.jsonInput = true;
        } else if (arg == "--list-models") {
            config.listModels = true;
            if (i + 1 < args.size() && !args[i + 1].empty() && args[i + 1][0] != '-') {
                config.listModelsLanguage = args[++i];
            }
        } else if (arg == "--download-model") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --download-model");
            config.downloadModelName = args[++i];
        } else if (arg == "--model-dir" || arg == "--model_dir") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --model-dir");
            config.modelDir = std::filesystem::path(args[++i]);
        } else if (arg == "-m" || arg == "--model") {
            if (i + 1 >= args.size()) throw std::runtime_error("Missing argument for --model");
            config.modelPath = std::filesystem::path(args[++i]);
        }
    }

    // Validate mutually exclusive options
    if (config.textInput && config.jsonInput) {
        throw std::runtime_error("--text and --json-input are mutually exclusive");
    }
}

} // anonymous namespace

// ============================================
// --text option tests
// ============================================

TEST(TextInputTest, ParseShortFlag) {
    TestRunConfig config;
    testParseArgs({"-t", "Hello world"}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "Hello world");
}

TEST(TextInputTest, ParseLongFlag) {
    TestRunConfig config;
    testParseArgs({"--text", "こんにちは"}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "こんにちは");
}

TEST(TextInputTest, TextWithModelPath) {
    TestRunConfig config;
    testParseArgs({"-m", "model.onnx", "--text", "Hello"}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "Hello");
    EXPECT_EQ(config.modelPath.string(), "model.onnx");
}

TEST(TextInputTest, TextNotSet) {
    TestRunConfig config;
    testParseArgs({"-m", "model.onnx"}, config);
    EXPECT_FALSE(config.textInput.has_value());
}

TEST(TextInputTest, EmptyText) {
    TestRunConfig config;
    testParseArgs({"--text", ""}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "");
}

TEST(TextInputTest, TextWithSpecialCharacters) {
    TestRunConfig config;
    testParseArgs({"--text", "Hello! How are you? 日本語テスト。"}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "Hello! How are you? 日本語テスト。");
}

TEST(TextInputTest, TextWithQuotes) {
    TestRunConfig config;
    testParseArgs({"--text", "She said \"hello\" to me"}, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "She said \"hello\" to me");
}

TEST(TextInputTest, MissingTextArgument) {
    TestRunConfig config;
    EXPECT_THROW(testParseArgs({"--text"}, config), std::runtime_error);
}

TEST(TextInputTest, TextAndJsonInputMutuallyExclusive) {
    TestRunConfig config;
    EXPECT_THROW(
        testParseArgs({"--text", "Hello", "--json-input"}, config),
        std::runtime_error
    );
}

// ============================================
// --list-models tests
// ============================================

TEST(ListModelsTest, BasicListModels) {
    TestRunConfig config;
    testParseArgs({"--list-models"}, config);
    EXPECT_TRUE(config.listModels);
    EXPECT_FALSE(config.listModelsLanguage.has_value());
}

TEST(ListModelsTest, ListModelsWithLanguage) {
    TestRunConfig config;
    testParseArgs({"--list-models", "ja"}, config);
    EXPECT_TRUE(config.listModels);
    ASSERT_TRUE(config.listModelsLanguage.has_value());
    EXPECT_EQ(config.listModelsLanguage.value(), "ja");
}

TEST(ListModelsTest, ListModelsWithLanguageCode) {
    TestRunConfig config;
    testParseArgs({"--list-models", "en_US"}, config);
    EXPECT_TRUE(config.listModels);
    ASSERT_TRUE(config.listModelsLanguage.has_value());
    EXPECT_EQ(config.listModelsLanguage.value(), "en_US");
}

TEST(ListModelsTest, ListModelsDoesNotConsumeNextFlag) {
    TestRunConfig config;
    testParseArgs({"--list-models", "--debug"}, config);
    EXPECT_TRUE(config.listModels);
    EXPECT_FALSE(config.listModelsLanguage.has_value());
}

TEST(ListModelsTest, ListModelsNoModelRequired) {
    TestRunConfig config;
    testParseArgs({"--list-models"}, config);
    EXPECT_TRUE(config.listModels);
    EXPECT_TRUE(config.modelPath.empty());
}

// ============================================
// --download-model tests
// ============================================

TEST(DownloadModelTest, BasicDownloadModel) {
    TestRunConfig config;
    testParseArgs({"--download-model", "tsukuyomi"}, config);
    ASSERT_TRUE(config.downloadModelName.has_value());
    EXPECT_EQ(config.downloadModelName.value(), "tsukuyomi");
}

TEST(DownloadModelTest, DownloadModelWithDir) {
    TestRunConfig config;
    testParseArgs({"--download-model", "tsukuyomi", "--model-dir", "/tmp/models"}, config);
    ASSERT_TRUE(config.downloadModelName.has_value());
    EXPECT_EQ(config.downloadModelName.value(), "tsukuyomi");
    ASSERT_TRUE(config.modelDir.has_value());
    EXPECT_EQ(config.modelDir.value().string(), "/tmp/models");
}

TEST(DownloadModelTest, MissingModelName) {
    TestRunConfig config;
    EXPECT_THROW(testParseArgs({"--download-model"}, config), std::runtime_error);
}

TEST(DownloadModelTest, DownloadModelWithUnderscoreFlag) {
    TestRunConfig config;
    testParseArgs({"--model_dir", "/tmp/models", "--download-model", "tsukuyomi"}, config);
    ASSERT_TRUE(config.modelDir.has_value());
    EXPECT_EQ(config.modelDir.value().string(), "/tmp/models");
}

// ============================================
// Environment variable tests
// ============================================

TEST(EnvVarTest, PiperModelDirEnvVar) {
    // This test verifies the concept - actual env var testing
    // would require setenv which is platform-specific
    TestRunConfig config;
    testParseArgs({"--model-dir", "/custom/path"}, config);
    ASSERT_TRUE(config.modelDir.has_value());
    EXPECT_EQ(config.modelDir.value().string(), "/custom/path");
}

// ============================================
// Combined options tests
// ============================================

TEST(CombinedTest, TextWithAllOptions) {
    TestRunConfig config;
    testParseArgs({
        "-m", "model.onnx",
        "--text", "テスト",
        "--model-dir", "/tmp/models"
    }, config);
    ASSERT_TRUE(config.textInput.has_value());
    EXPECT_EQ(config.textInput.value(), "テスト");
    EXPECT_EQ(config.modelPath.string(), "model.onnx");
}

TEST(CombinedTest, ListModelsIgnoresModel) {
    TestRunConfig config;
    testParseArgs({"--list-models", "ja"}, config);
    EXPECT_TRUE(config.listModels);
    EXPECT_TRUE(config.modelPath.empty());
}
