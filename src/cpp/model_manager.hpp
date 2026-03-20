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
};

// Get the default model directory (platform-specific)
// Windows: %APPDATA%\piper\models
// Linux: ~/.local/share/piper/models (or $XDG_DATA_HOME/piper/models)
// macOS: ~/Library/Application Support/piper/models
// Override: PIPER_MODEL_DIR environment variable
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

} // namespace piper

#endif // MODEL_MANAGER_H_
