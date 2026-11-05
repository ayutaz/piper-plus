#ifndef MODEL_MANAGER_H_
#define MODEL_MANAGER_H_

#include <string>
#include <vector>
#include <filesystem>
#include <optional>

namespace piper {

struct VoiceFileInfo {
    std::string relativePath;  // e.g., "ja/ja_JP/tsukuyomi-chan/medium/model.onnx"
    size_t sizeBytes;
    std::string md5Digest;
};

struct VoiceInfo {
    std::string key;           // e.g., "ja_JP-tsukuyomi-chan-medium"
    std::string name;          // e.g., "tsukuyomi-chan"
    std::string languageCode;  // e.g., "ja_JP"
    std::string languageFamily;// e.g., "ja"
    std::string languageNameNative;  // e.g., "日本語"
    std::string languageNameEnglish; // e.g., "Japanese"
    std::string quality;       // e.g., "medium"
    int numSpeakers;
    std::string source;        // "piper-plus" or "piper"
    std::string repoId;        // HuggingFace repo identifier (e.g., "ayousanz/piper-plus-tsukuyomi-chan")
    std::vector<VoiceFileInfo> files;
    std::vector<std::string> aliases;
    std::string revision = "main"; // Optional pinned HuggingFace revision
    // Usage notice shown by executables when this model is used
    // (docs/reference/model-resolution.md §9). Empty for most models.
    std::vector<std::string> notice;
    // File names (last path component) that identify this model for the notice.
    std::vector<std::string> noticeFiles;
};

// Line printed after a model notice, identical across runtimes.
inline constexpr const char* kModelNoticeFooter =
    "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / "
    "Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)";

// Environment variable that turns the model notice off.
inline constexpr const char* kModelNoticeDisableEnv =
    "PIPER_PLUS_DISABLE_MODEL_NOTICE";

// Get the default model directory (platform-specific)
// Windows: %APPDATA%\piper-plus\models
// Linux: ~/.local/share/piper-plus/models (or $XDG_DATA_HOME/piper-plus/models)
// macOS: ~/Library/Application Support/piper-plus/models
// Override: PIPER_PLUS_MODEL_DIR environment variable
std::filesystem::path getDefaultModelDir();

// Load and merge voice catalogs
// Loads built-in piper-plus voices and optionally cached upstream voices
std::vector<VoiceInfo> loadVoiceCatalog();

// List available voice models, optionally filtered by language
// Outputs to stderr in a human-readable format
void listModels(const std::string& languageFilter = "");

// Download a voice model by name or alias
// Returns true on success, false on failure
bool downloadModel(const std::string& modelName,
                   const std::filesystem::path& modelDir);

// Find a voice by key or alias
std::optional<VoiceInfo> findVoice(const std::string& nameOrAlias);

// Resolve a model name or alias to the downloaded .onnx file path.
// Returns nullopt if the voice is not found in the catalog or not downloaded.
std::optional<std::filesystem::path> resolveModelPath(
    const std::string& nameOrAlias,
    const std::filesystem::path& modelDir);

// Return the usage notice for a model name, alias, repo ID, URL or path
// (docs/reference/model-resolution.md §9), checked against the embedded
// piper-plus catalog. The input matches an entry with a notice when it equals
// the entry's key, an alias or its repo ID; when it is a URL ("://")
// containing "/<repo_id>/"; or when its file name (last component, '/' or
// '\\' separated) is one of the entry's notice files. Leading/trailing
// whitespace is ignored. Returns an empty vector when nothing matches.
// This never prints; the CLI prints the notice to stderr.
std::vector<std::string> getModelNotice(const std::string& nameOrPath);

// Pure parser for PIPER_PLUS_DISABLE_MODEL_NOTICE: true when the value is
// "1", "true" or "yes" (case-insensitive, surrounding whitespace ignored).
// A null value (unset) returns false.
bool parseModelNoticeDisabled(const char* value);

// Whether PIPER_PLUS_DISABLE_MODEL_NOTICE turns the notice off.
bool modelNoticeDisabled();

} // namespace piper

#endif // MODEL_MANAGER_H_
