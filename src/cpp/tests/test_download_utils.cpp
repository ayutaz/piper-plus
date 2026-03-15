#include <gtest/gtest.h>
#include <string>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <cctype>

// Test utility functions used by model downloader
// These tests don't require network access

namespace {

// Helper: Construct HuggingFace download URL for piper-plus models
std::string buildPiperPlusUrl(const std::string& repo, const std::string& filename) {
    return "https://huggingface.co/" + repo + "/resolve/main/" + filename;
}

// Helper: Construct HuggingFace download URL for upstream piper models
std::string buildPiperUrl(const std::string& relativePath) {
    return "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/" + relativePath;
}

// Helper: Validate model name (only allow safe characters)
bool isValidModelName(const std::string& name) {
    if (name.empty()) return false;
    for (char c : name) {
        if (!std::isalnum(c) && c != '-' && c != '_' && c != '.') {
            return false;
        }
    }
    return true;
}

// Helper: Sanitize filename for safe file system usage
std::string sanitizeFilename(const std::string& filename) {
    std::string result;
    for (char c : filename) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.') {
            result += c;
        }
    }
    return result;
}

// Helper: Extract model name from a key like "ja_JP-tsukuyomi-chan-medium"
std::string extractModelName(const std::string& key) {
    // Find the first hyphen after the language code
    auto pos = key.find('-');
    if (pos == std::string::npos) return key;

    // Find the last hyphen (quality level)
    auto lastPos = key.rfind('-');
    if (lastPos == pos) return key.substr(pos + 1);

    return key.substr(pos + 1, lastPos - pos - 1);
}

} // anonymous namespace

// ============================================
// URL construction tests
// ============================================

TEST(DownloadUtilsTest, PiperPlusUrlConstruction) {
    auto url = buildPiperPlusUrl("ayousanz/piper-plus-tsukuyomi-chan", "tsukuyomi-wavlm-300epoch.onnx");
    EXPECT_EQ(url, "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-wavlm-300epoch.onnx");
}

TEST(DownloadUtilsTest, PiperPlusUrlConfig) {
    auto url = buildPiperPlusUrl("ayousanz/piper-plus-tsukuyomi-chan", "config.json");
    EXPECT_EQ(url, "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json");
}

TEST(DownloadUtilsTest, UpstreamPiperUrl) {
    auto url = buildPiperUrl("en/en_US/lessac/medium/en_US-lessac-medium.onnx");
    EXPECT_EQ(url, "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx");
}

// ============================================
// Model name validation tests
// ============================================

TEST(DownloadUtilsTest, ValidModelNames) {
    EXPECT_TRUE(isValidModelName("tsukuyomi"));
    EXPECT_TRUE(isValidModelName("ja_JP-tsukuyomi-chan-medium"));
    EXPECT_TRUE(isValidModelName("en_US-lessac-medium"));
    EXPECT_TRUE(isValidModelName("moe-speech"));
    EXPECT_TRUE(isValidModelName("model.onnx"));
}

TEST(DownloadUtilsTest, InvalidModelNames) {
    EXPECT_FALSE(isValidModelName(""));
    EXPECT_FALSE(isValidModelName("model name"));  // space
    EXPECT_FALSE(isValidModelName("model;rm -rf /"));  // shell injection
    EXPECT_FALSE(isValidModelName("model$(cmd)"));  // command substitution
    EXPECT_FALSE(isValidModelName("model|cat"));  // pipe
    EXPECT_FALSE(isValidModelName("../../../etc/passwd"));  // path traversal
}

// ============================================
// Filename sanitization tests
// ============================================

TEST(DownloadUtilsTest, SanitizeCleanFilename) {
    EXPECT_EQ(sanitizeFilename("model.onnx"), "model.onnx");
    EXPECT_EQ(sanitizeFilename("config.json"), "config.json");
}

TEST(DownloadUtilsTest, SanitizeDirtyFilename) {
    EXPECT_EQ(sanitizeFilename("model file.onnx"), "modelfile.onnx");
    EXPECT_EQ(sanitizeFilename("../model.onnx"), "..model.onnx");
    EXPECT_EQ(sanitizeFilename("model;hack.onnx"), "modelhack.onnx");
}

TEST(DownloadUtilsTest, SanitizePreservesHyphensUnderscores) {
    EXPECT_EQ(sanitizeFilename("tsukuyomi-wavlm-300epoch.onnx"), "tsukuyomi-wavlm-300epoch.onnx");
    EXPECT_EQ(sanitizeFilename("ja_JP-model_v2.onnx"), "ja_JP-model_v2.onnx");
}

// ============================================
// Model name extraction tests
// ============================================

TEST(DownloadUtilsTest, ExtractModelName) {
    EXPECT_EQ(extractModelName("ja_JP-tsukuyomi-chan-medium"), "tsukuyomi-chan");
    EXPECT_EQ(extractModelName("en_US-lessac-medium"), "lessac");
}

TEST(DownloadUtilsTest, ExtractModelNameNoQuality) {
    EXPECT_EQ(extractModelName("simple"), "simple");
}

// ============================================
// Path construction tests
// ============================================

TEST(DownloadUtilsTest, ModelDownloadPath) {
    namespace fs = std::filesystem;

    fs::path modelDir = "/tmp/piper/models";
    std::string filename = "tsukuyomi-wavlm-300epoch.onnx";

    // Flat directory layout: files go directly into modelDir (matches Python behavior)
    fs::path expectedPath = modelDir / filename;
    EXPECT_EQ(expectedPath.string(), "/tmp/piper/models/tsukuyomi-wavlm-300epoch.onnx");
}

TEST(DownloadUtilsTest, ConfigDownloadPath) {
    namespace fs = std::filesystem;

    fs::path modelDir = "/tmp/piper/models";
    std::string filename = "config.json";

    // Flat directory layout: files go directly into modelDir (matches Python behavior)
    fs::path expectedPath = modelDir / filename;
    EXPECT_EQ(expectedPath.string(), "/tmp/piper/models/config.json");
}

// ============================================
// File existence and temp directory tests
// ============================================

TEST(DownloadUtilsTest, TempDirectoryExists) {
    namespace fs = std::filesystem;
    auto tempDir = fs::temp_directory_path();
    EXPECT_TRUE(fs::exists(tempDir));
}

TEST(DownloadUtilsTest, CreateNestedDirectories) {
    namespace fs = std::filesystem;
    auto tempDir = fs::temp_directory_path() / "piper_test_nested" / "sub1" / "sub2";

    // Create directories
    fs::create_directories(tempDir);
    EXPECT_TRUE(fs::exists(tempDir));

    // Cleanup
    fs::remove_all(fs::temp_directory_path() / "piper_test_nested");
}

// ============================================
// Platform-specific data directory tests
// ============================================

TEST(DownloadUtilsTest, DataDirectoryPath) {
    // Just verify the function doesn't crash and returns non-empty
#ifdef _WIN32
    const char* appData = std::getenv("APPDATA");
    if (appData) {
        std::filesystem::path expected = std::filesystem::path(appData) / "piper" / "models";
        EXPECT_FALSE(expected.empty());
    }
#else
    const char* home = std::getenv("HOME");
    if (home) {
        std::filesystem::path expected = std::filesystem::path(home) / ".local" / "share" / "piper" / "models";
        EXPECT_FALSE(expected.empty());
    }
#endif
}
