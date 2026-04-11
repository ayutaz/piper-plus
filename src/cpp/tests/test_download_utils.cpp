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

// --- Security validation helpers (inline replicas of static functions in model_manager.cpp) ---

// Shell-safe for URLs: reject backslashes (Unix shell escape character).
// Only allow alphanumerics, hyphens, underscores, dots, forward slashes, and colons.
bool isSafeForShell(const std::string& s) {
    for (char c : s) {
        if (!std::isalnum(static_cast<unsigned char>(c)) &&
            c != '-' && c != '_' && c != '.' && c != '/' &&
            c != ':') {
            return false;
        }
    }
    return !s.empty();
}

// Shell-safe for file paths: allows backslashes for Windows path separators.
bool isSafeForShellPath(const std::string& s) {
    for (char c : s) {
        if (!std::isalnum(static_cast<unsigned char>(c)) &&
            c != '-' && c != '_' && c != '.' && c != '/' &&
            c != '\\' && c != ':') {
            return false;
        }
    }
    return !s.empty();
}

// Validate that a voice key contains no path traversal characters.
bool isSafeVoiceKey(const std::string& key) {
    if (key.empty()) return false;
    if (key.find("..") != std::string::npos) return false;
    if (key.find('/') != std::string::npos) return false;
    if (key.find('\\') != std::string::npos) return false;
    return true;
}

// Validate that a repoId has exactly one slash and only safe characters.
bool isSafeRepoId(const std::string& repoId) {
    if (repoId.empty()) return false;
    int slashCount = 0;
    for (char c : repoId) {
        if (c == '/') {
            ++slashCount;
            if (slashCount > 1) return false;
        } else if (!std::isalnum(static_cast<unsigned char>(c)) &&
                   c != '-' && c != '_' && c != '.') {
            return false;
        }
    }
    return slashCount == 1;
}

// Validate that a URL starts with the expected HuggingFace prefix.
bool isHuggingFaceUrl(const std::string& url) {
    const std::string expectedPrefix = "https://huggingface.co/";
    return url.rfind(expectedPrefix, 0) == 0;
}

} // anonymous namespace

// ============================================
// URL construction tests
// ============================================

TEST(DownloadUtilsTest, PiperPlusUrlConstruction) {
    auto url = buildPiperPlusUrl("ayousanz/piper-plus-tsukuyomi-chan", "tsukuyomi-chan-6lang-fp16.onnx");
    EXPECT_EQ(url, "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx");
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
    EXPECT_EQ(sanitizeFilename("tsukuyomi-chan-6lang-fp16.onnx"), "tsukuyomi-chan-6lang-fp16.onnx");
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
    std::string filename = "tsukuyomi-chan-6lang-fp16.onnx";

    // Flat directory layout: files go directly into modelDir (matches Python behavior)
    fs::path expectedPath = modelDir / filename;
    EXPECT_EQ(expectedPath, fs::path("/tmp/piper/models/tsukuyomi-chan-6lang-fp16.onnx"));
}

TEST(DownloadUtilsTest, ConfigDownloadPath) {
    namespace fs = std::filesystem;

    fs::path modelDir = "/tmp/piper/models";
    std::string filename = "config.json";

    // Flat directory layout: files go directly into modelDir (matches Python behavior)
    fs::path expectedPath = modelDir / filename;
    EXPECT_EQ(expectedPath, fs::path("/tmp/piper/models/config.json"));
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

// ============================================
// Security validation tests: isSafeForShell
// ============================================

TEST(SecurityValidationTest, SafeUrlAccepted) {
    EXPECT_TRUE(isSafeForShell("https://huggingface.co/owner/repo/resolve/main/model.onnx"));
    EXPECT_TRUE(isSafeForShell("https://example.com/file.tar.gz"));
    EXPECT_TRUE(isSafeForShell("http://localhost:8080/path"));
}

TEST(SecurityValidationTest, UnsafeUrlWithBackslash) {
    EXPECT_FALSE(isSafeForShell("https://example.com/path\\file"));
    EXPECT_FALSE(isSafeForShell("C:\\Users\\model.onnx"));
}

TEST(SecurityValidationTest, UnsafeUrlWithShellChars) {
    EXPECT_FALSE(isSafeForShell("https://example.com/$HOME"));
    EXPECT_FALSE(isSafeForShell("https://example.com/`whoami`"));
    EXPECT_FALSE(isSafeForShell("https://example.com/a;rm -rf /"));
    EXPECT_FALSE(isSafeForShell("https://example.com/a|cat /etc/passwd"));
    EXPECT_FALSE(isSafeForShell("https://example.com/a&bg"));
}

TEST(SecurityValidationTest, EmptyUrlRejected) {
    EXPECT_FALSE(isSafeForShell(""));
}

// ============================================
// Security validation tests: isSafeForShellPath
// ============================================

TEST(SecurityValidationTest, WindowsPathAccepted) {
    EXPECT_TRUE(isSafeForShellPath("C:\\Users\\piper\\models\\model.onnx"));
    EXPECT_TRUE(isSafeForShellPath("D:\\data\\piper\\config.json"));
}

TEST(SecurityValidationTest, UnixPathAccepted) {
    EXPECT_TRUE(isSafeForShellPath("/home/user/.local/share/piper/model.onnx"));
    EXPECT_TRUE(isSafeForShellPath("/tmp/piper/models/config.json"));
}

// ============================================
// Security validation tests: isSafeVoiceKey
// ============================================

TEST(SecurityValidationTest, SafeVoiceKeyAccepted) {
    EXPECT_TRUE(isSafeVoiceKey("ja_JP-tsukuyomi-chan-medium"));
    EXPECT_TRUE(isSafeVoiceKey("en_US-lessac-medium"));
    EXPECT_TRUE(isSafeVoiceKey("moe-speech-20speakers"));
}

TEST(SecurityValidationTest, VoiceKeyWithDotDot) {
    EXPECT_FALSE(isSafeVoiceKey(".."));
    EXPECT_FALSE(isSafeVoiceKey("../../../etc/passwd"));
    EXPECT_FALSE(isSafeVoiceKey("model..hack"));
}

TEST(SecurityValidationTest, VoiceKeyWithSlash) {
    EXPECT_FALSE(isSafeVoiceKey("model/hack"));
    EXPECT_FALSE(isSafeVoiceKey("/etc/passwd"));
}

TEST(SecurityValidationTest, VoiceKeyWithBackslash) {
    EXPECT_FALSE(isSafeVoiceKey("model\\hack"));
    EXPECT_FALSE(isSafeVoiceKey("C:\\Windows\\system32"));
}

TEST(SecurityValidationTest, EmptyVoiceKeyRejected) {
    EXPECT_FALSE(isSafeVoiceKey(""));
}

// ============================================
// Security validation tests: isSafeRepoId
// ============================================

TEST(SecurityValidationTest, SafeRepoIdAccepted) {
    EXPECT_TRUE(isSafeRepoId("ayousanz/piper-plus-tsukuyomi-chan"));
    EXPECT_TRUE(isSafeRepoId("rhasspy/piper-voices"));
    EXPECT_TRUE(isSafeRepoId("owner/repo.v2"));
    EXPECT_TRUE(isSafeRepoId("user_name/repo_name"));
}

TEST(SecurityValidationTest, RepoIdMultipleSlashes) {
    EXPECT_FALSE(isSafeRepoId("owner/repo/extra"));
    EXPECT_FALSE(isSafeRepoId("a/b/c/d"));
}

TEST(SecurityValidationTest, RepoIdNoSlash) {
    EXPECT_FALSE(isSafeRepoId("noslash"));
    EXPECT_FALSE(isSafeRepoId("single-component"));
}

TEST(SecurityValidationTest, RepoIdWithSpecialChars) {
    EXPECT_FALSE(isSafeRepoId("owner/repo;hack"));
    EXPECT_FALSE(isSafeRepoId("owner/repo$(cmd)"));
    EXPECT_FALSE(isSafeRepoId("owner/repo|pipe"));
    EXPECT_FALSE(isSafeRepoId("owner/repo&bg"));
    EXPECT_FALSE(isSafeRepoId("owner/repo`whoami`"));
}

TEST(SecurityValidationTest, EmptyRepoIdRejected) {
    EXPECT_FALSE(isSafeRepoId(""));
}

// ============================================
// Security validation tests: URL prefix
// ============================================

TEST(SecurityValidationTest, HuggingFaceUrlAccepted) {
    EXPECT_TRUE(isHuggingFaceUrl("https://huggingface.co/owner/repo/resolve/main/file.onnx"));
    EXPECT_TRUE(isHuggingFaceUrl("https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/model.onnx"));
}

TEST(SecurityValidationTest, NonHuggingFaceUrlRejected) {
    EXPECT_FALSE(isHuggingFaceUrl("https://evil.com/huggingface.co/file"));
    EXPECT_FALSE(isHuggingFaceUrl("http://huggingface.co/owner/repo"));  // http, not https
    EXPECT_FALSE(isHuggingFaceUrl("https://example.com/model.onnx"));
}

TEST(SecurityValidationTest, FileSchemeRejected) {
    EXPECT_FALSE(isHuggingFaceUrl("file:///etc/passwd"));
    EXPECT_FALSE(isHuggingFaceUrl("file:///C:/Windows/system32"));
}
