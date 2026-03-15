#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <unordered_set>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#elif defined(__APPLE__)
#include <mach-o/dyld.h>
#include <climits>
#else
#include <climits>
#endif

#include <spdlog/spdlog.h>
#include "json.hpp"
#include "model_manager.hpp"

using json = nlohmann::json;
namespace fs = std::filesystem;

namespace piper {

// ---------------------------------------------------------------------------
// Embedded piper-plus voice catalog
// ---------------------------------------------------------------------------

static const char* PIPER_PLUS_CATALOG_JSON = R"JSON(
{
    "ja_JP-tsukuyomi-chan-medium": {
        "key": "ja_JP-tsukuyomi-chan-medium",
        "name": "tsukuyomi-chan",
        "language": {
            "code": "ja_JP", "family": "ja",
            "name_native": "日本語", "name_english": "Japanese"
        },
        "quality": "medium",
        "num_speakers": 1,
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-tsukuyomi-chan",
        "files": {
            "tsukuyomi-wavlm-300epoch.onnx": {
                "size_bytes": 77594624,
                "md5_digest": ""
            },
            "config.json": {
                "size_bytes": 3072,
                "md5_digest": ""
            }
        },
        "aliases": ["tsukuyomi", "tsukuyomi-chan", "ja-tsukuyomi"]
    },
    "ja_JP-moe-speech-20speakers-medium": {
        "key": "ja_JP-moe-speech-20speakers-medium",
        "name": "moe-speech-20speakers",
        "language": {
            "code": "ja_JP", "family": "ja",
            "name_native": "日本語", "name_english": "Japanese"
        },
        "quality": "medium",
        "num_speakers": 20,
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-base",
        "files": {
            "moe-speech-20speakers-v2.onnx": {
                "size_bytes": 77594624,
                "md5_digest": ""
            },
            "config.json": {
                "size_bytes": 4096,
                "md5_digest": ""
            }
        },
        "aliases": ["moe-speech", "moe-20speakers", "ja-base", "ja-20speakers"]
    }
}
)JSON";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

// Get the directory containing the running executable
static fs::path getExeDir() {
#ifdef _WIN32
    char buf[MAX_PATH] = {0};
    DWORD len = GetModuleFileNameA(nullptr, buf, sizeof(buf));
    if (len > 0 && len < sizeof(buf)) {
        return fs::path(buf).parent_path();
    }
#elif defined(__APPLE__)
    char buf[PATH_MAX] = {0};
    uint32_t size = sizeof(buf);
    if (_NSGetExecutablePath(buf, &size) == 0) {
        return fs::path(buf).parent_path();
    }
#else
    try {
        return fs::canonical("/proc/self/exe").parent_path();
    } catch (...) {
        // fall through
    }
#endif
    return fs::current_path();
}

// Parse a single voice entry from JSON into VoiceInfo
static VoiceInfo parseVoiceEntry(const std::string& key,
                                 const json& entry,
                                 const std::string& defaultSource) {
    VoiceInfo vi;
    vi.key = key;
    vi.name = entry.value("name", "");
    vi.quality = entry.value("quality", "");
    vi.numSpeakers = entry.value("num_speakers", 1);
    vi.source = entry.value("source", defaultSource);

    // HuggingFace repo (piper-plus voices)
    vi.repoId = entry.value("repo", "");

    // Language block
    if (entry.contains("language") && entry["language"].is_object()) {
        const auto& lang = entry["language"];
        vi.languageCode = lang.value("code", "");
        vi.languageFamily = lang.value("family", "");
        vi.languageNameNative = lang.value("name_native", "");
        vi.languageNameEnglish = lang.value("name_english", "");
    }

    // Files
    if (entry.contains("files") && entry["files"].is_object()) {
        for (auto& [filePath, fileInfo] : entry["files"].items()) {
            VoiceFileInfo vfi;
            vfi.relativePath = filePath;
            vfi.sizeBytes = fileInfo.value("size_bytes", (size_t)0);
            vfi.md5Digest = fileInfo.value("md5_digest", "");
            vi.files.push_back(std::move(vfi));
        }
    }

    // Aliases
    if (entry.contains("aliases") && entry["aliases"].is_array()) {
        for (const auto& alias : entry["aliases"]) {
            if (alias.is_string()) {
                vi.aliases.push_back(alias.get<std::string>());
            }
        }
    }

    return vi;
}

// Try to locate the upstream voices.json file near the executable
static std::optional<fs::path> findUpstreamVoicesJson() {
    fs::path exeDir = getExeDir();

    // Search paths relative to executable
    std::vector<fs::path> candidates = {
        exeDir / "voices.json",
        exeDir / ".." / "share" / "voices.json",
        exeDir / ".." / "share" / "piper" / "voices.json",
    };

    for (const auto& p : candidates) {
        std::error_code ec;
        if (fs::exists(p, ec)) {
            auto canon = fs::canonical(p, ec);
            if (!ec && fs::exists(canon)) {
                return canon;
            }
        }
    }

    return std::nullopt;
}

// Shell-safe: confirm a string contains no dangerous characters.
// Only allow alphanumerics, hyphens, underscores, dots, slashes, and colons.
static bool isSafeForShell(const std::string& s) {
    for (char c : s) {
        if (!std::isalnum(static_cast<unsigned char>(c)) &&
            c != '-' && c != '_' && c != '.' && c != '/' &&
            c != '\\' && c != ':') {
            return false;
        }
    }
    return !s.empty();
}

// Download a single file using system() with curl/wget/PowerShell
static bool downloadFile(const std::string& url,
                         const fs::path& outputPath) {
    // Validate url and path for shell safety
    if (!isSafeForShell(url)) {
        spdlog::error("URL contains unsafe characters: {}", url);
        return false;
    }

    std::string outStr = outputPath.string();
    // Allow spaces in output path (they are quoted) but reject other specials
    for (char c : outStr) {
        if (!std::isalnum(static_cast<unsigned char>(c)) &&
            c != '-' && c != '_' && c != '.' && c != '/' &&
            c != '\\' && c != ':' && c != ' ') {
            spdlog::error("Output path contains unsafe characters: {}", outStr);
            return false;
        }
    }

    std::string cmd;

#ifdef _WIN32
    cmd = "powershell -NoProfile -Command \"Invoke-WebRequest -Uri '"
        + url + "' -OutFile '" + outStr + "'\"";
#else
    // Prefer curl, fall back to wget
    if (std::system("which curl > /dev/null 2>&1") == 0) {
        cmd = "curl -L -# -o \"" + outStr + "\" \"" + url + "\"";
    } else if (std::system("which wget > /dev/null 2>&1") == 0) {
        cmd = "wget -O \"" + outStr + "\" \"" + url + "\"";
    } else {
        spdlog::error("Neither curl nor wget is available for downloading");
        return false;
    }
#endif

    spdlog::info("Downloading {} ...", url);
    int rc = std::system(cmd.c_str());
    return rc == 0;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::filesystem::path getDefaultModelDir() {
    // Environment variable takes precedence
    const char* envDir = std::getenv("PIPER_MODEL_DIR");
    if (envDir && envDir[0] != '\0') {
        return fs::path(envDir);
    }

#ifdef _WIN32
    const char* appData = std::getenv("APPDATA");
    if (appData) {
        return fs::path(appData) / "piper" / "models";
    }
    return fs::path("models");
#elif defined(__APPLE__)
    const char* home = std::getenv("HOME");
    if (home) {
        return fs::path(home) / "Library" / "Application Support"
               / "piper" / "models";
    }
    return fs::path("models");
#else
    const char* xdgData = std::getenv("XDG_DATA_HOME");
    if (xdgData) {
        return fs::path(xdgData) / "piper" / "models";
    }
    const char* home = std::getenv("HOME");
    if (home) {
        return fs::path(home) / ".local" / "share" / "piper" / "models";
    }
    return fs::path("models");
#endif
}

std::vector<VoiceInfo> loadVoiceCatalog() {
    std::vector<VoiceInfo> catalog;

    // 1. Parse embedded piper-plus catalog
    try {
        json piperPlusCatalog = json::parse(PIPER_PLUS_CATALOG_JSON);
        for (auto& [key, entry] : piperPlusCatalog.items()) {
            catalog.push_back(parseVoiceEntry(key, entry, "piper-plus"));
        }
        spdlog::debug("Loaded {} piper-plus voices from embedded catalog",
                       catalog.size());
    } catch (const json::exception& e) {
        spdlog::error("Failed to parse embedded piper-plus catalog: {}",
                       e.what());
    }

    // 2. Try to load upstream voices.json
    auto upstreamPath = findUpstreamVoicesJson();
    if (upstreamPath) {
        try {
            std::ifstream ifs(upstreamPath.value());
            json upstreamCatalog = json::parse(ifs);

            // Build a set of existing keys for O(1) duplicate lookup
            std::unordered_set<std::string> existingKeys;
            existingKeys.reserve(catalog.size());
            for (const auto& existing : catalog) {
                existingKeys.insert(existing.key);
            }

            size_t count = 0;
            for (auto& [key, entry] : upstreamCatalog.items()) {
                // Skip if already present (piper-plus overrides upstream)
                if (existingKeys.count(key) == 0) {
                    catalog.push_back(parseVoiceEntry(key, entry, "piper"));
                    existingKeys.insert(key);
                    ++count;
                }
            }
            spdlog::debug("Loaded {} upstream voices from {}",
                           count, upstreamPath.value().string());
        } catch (const std::exception& e) {
            spdlog::warn("Failed to load upstream voices.json ({}): {}",
                          upstreamPath.value().string(), e.what());
        }
    } else {
        spdlog::debug("No upstream voices.json found; "
                       "using piper-plus catalog only");
    }

    // Sort by language code, then by key
    std::sort(catalog.begin(), catalog.end(),
              [](const VoiceInfo& a, const VoiceInfo& b) {
                  if (a.languageCode != b.languageCode)
                      return a.languageCode < b.languageCode;
                  return a.key < b.key;
              });

    return catalog;
}

std::optional<VoiceInfo> findVoice(const std::string& nameOrAlias) {
    auto catalog = loadVoiceCatalog();

    // 1. Exact key match
    for (const auto& voice : catalog) {
        if (voice.key == nameOrAlias) {
            return voice;
        }
    }

    // 2. Alias match
    for (const auto& voice : catalog) {
        for (const auto& alias : voice.aliases) {
            if (alias == nameOrAlias) {
                return voice;
            }
        }
    }

    // 3. Partial match (key contains the search term)
    for (const auto& voice : catalog) {
        if (voice.key.find(nameOrAlias) != std::string::npos) {
            return voice;
        }
    }

    return std::nullopt;
}

void listModels(const std::string& languageFilter) {
    auto catalog = loadVoiceCatalog();

    if (catalog.empty()) {
        std::cerr << "No voice models found." << std::endl;
        return;
    }

    // Filter by language if specified
    std::vector<VoiceInfo> filtered;
    if (languageFilter.empty()) {
        filtered = catalog;
    } else {
        for (const auto& voice : catalog) {
            if (voice.languageFamily == languageFilter ||
                voice.languageCode == languageFilter) {
                filtered.push_back(voice);
            }
        }
    }

    if (filtered.empty()) {
        std::cerr << "No voice models found for language: "
                  << languageFilter << std::endl;
        return;
    }

    std::cerr << std::endl;
    std::cerr << "Available voice models:" << std::endl;

    // Group by language code
    std::string currentLang;
    for (const auto& voice : filtered) {
        if (voice.languageCode != currentLang) {
            currentLang = voice.languageCode;
            std::cerr << std::endl;
            std::cerr << "  " << voice.languageNameEnglish;
            if (!voice.languageNameNative.empty() &&
                voice.languageNameNative != voice.languageNameEnglish) {
                std::cerr << " (" << voice.languageNameNative << ")";
            }
            std::cerr << " [" << voice.languageCode << "]:" << std::endl;
        }

        // Format: key  [source]  N speaker(s)  quality
        std::cerr << "    " << voice.key;

        // Pad to 40 chars for alignment
        int padLen = 40 - static_cast<int>(voice.key.size());
        if (padLen > 0) {
            std::cerr << std::string(padLen, ' ');
        } else {
            std::cerr << "  ";
        }

        std::cerr << "[" << voice.source << "]  ";
        std::cerr << voice.numSpeakers << " speaker"
                  << (voice.numSpeakers != 1 ? "s" : "") << "   ";
        std::cerr << voice.quality << std::endl;
    }

    std::cerr << std::endl;
    std::cerr << "Use --download-model <name> to download a model."
              << std::endl;
    std::cerr << std::endl;
}

bool downloadModel(const std::string& modelName,
                   const fs::path& modelDir) {
    // Look up the voice in the catalog
    auto maybeVoice = findVoice(modelName);
    if (!maybeVoice) {
        spdlog::error("Model '{}' not found. "
                       "Use --list-models to see available models.",
                       modelName);
        return false;
    }

    const VoiceInfo& voice = maybeVoice.value();
    spdlog::info("Downloading model: {} ({})", voice.key, voice.source);

    // Create target directory: modelDir / key  (e.g., models/ja_JP-tsukuyomi-chan-medium/)
    fs::path targetDir = modelDir / voice.key;
    std::error_code ec;
    fs::create_directories(targetDir, ec);
    if (ec) {
        spdlog::error("Failed to create directory {}: {}",
                       targetDir.string(), ec.message());
        return false;
    }

    // Build base URL depending on source
    std::string baseUrl;
    if (voice.source == "piper-plus") {
        // https://huggingface.co/{repo}/resolve/main/{filename}
        baseUrl = "https://huggingface.co/" + voice.repoId + "/resolve/main/";
    } else {
        // Upstream piper:
        // https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{file_path}
        baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/";
    }

    // Download each file
    bool allOk = true;
    for (const auto& file : voice.files) {
        std::string url = baseUrl + file.relativePath;
        // Use just the filename (last component) as the local name
        fs::path localName = fs::path(file.relativePath).filename();
        fs::path localPath = targetDir / localName;

        // Skip if file already exists with correct size
        if (fs::exists(localPath, ec) && file.sizeBytes > 0) {
            auto existingSize = fs::file_size(localPath, ec);
            if (!ec && existingSize == file.sizeBytes) {
                spdlog::info("  {} already exists, skipping",
                              localName.string());
                continue;
            }
        }

        if (!downloadFile(url, localPath)) {
            spdlog::error("  Failed to download {}", file.relativePath);
            allOk = false;
        } else {
            spdlog::info("  Downloaded {}", localName.string());
        }
    }

    if (allOk) {
        // Find the .onnx file to show the --model path
        std::string onnxFile;
        for (const auto& file : voice.files) {
            fs::path fn = fs::path(file.relativePath).filename();
            if (fn.extension() == ".onnx") {
                onnxFile = (targetDir / fn).string();
                break;
            }
        }

        std::cerr << std::endl;
        std::cerr << "Model downloaded successfully!" << std::endl;
        if (!onnxFile.empty()) {
            std::cerr << "Use with:  --model " << onnxFile << std::endl;
        }
        std::cerr << std::endl;
    }

    return allOk;
}

} // namespace piper
