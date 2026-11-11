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

#include "library_path.h"
#include "download_validation.hpp"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

#include <spdlog/spdlog.h>
#ifndef _WIN32
#include <unistd.h>  // access(), X_OK — POSIX only; Windows uses PowerShell branch.
#endif
#include "json.hpp"
#include "model_manager.hpp"
#include "piper_proc_exec.h"
#include "safe_exec.h"

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
            "code": "ja_JP",
            "family": "ja",
            "region": "JP",
            "name_native": "日本語",
            "name_english": "Japanese",
            "country_english": "Japan"
        },
        "quality": "medium",
        "num_speakers": 1,
        "speaker_id_map": {},
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-tsukuyomi-chan",
        "files": {
            "tsukuyomi-chan-6lang-fp16.onnx": {
                "size_bytes": 39652717,
                "md5_digest": ""
            },
            "config.json": {
                "size_bytes": 6279,
                "md5_digest": ""
            }
        },
        "aliases": [
            "tsukuyomi",
            "tsukuyomi-chan",
            "ja-tsukuyomi",
            "ayousanz/piper-plus-tsukuyomi-chan"
        ],
        "description": "Tsukuyomi-chan 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT)",
        "notice": [
            "[piper-plus] つくよみちゃんモデルの利用条件 / Terms for the Tsukuyomi-chan model",
            "生成した音声を使うときは「Piper Plus:つくよみちゃん」のクレジット表記が必須です。",
            "Credit 'Piper Plus:つくよみちゃん' is required when you use the generated audio.",
            "非公式の作品です。夢前黎様は開発・サポートに携わっていません。お問い合わせは開発者へ。",
            "Unofficial work. Rei Yumesaki is not involved in development or support; contact the developer.",
            "禁止事項と規約 / Terms and prohibited uses: https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan"
        ],
        "notice_files": [
            "tsukuyomi-chan-6lang-fp16.onnx",
            "tsukuyomi.onnx"
        ]
    },
    "ja_JP-css10-6lang-medium": {
        "key": "ja_JP-css10-6lang-medium",
        "name": "css10-6lang",
        "language": {
            "code": "ja_JP",
            "family": "ja",
            "region": "JP",
            "name_native": "日本語",
            "name_english": "Japanese",
            "country_english": "Japan"
        },
        "quality": "medium",
        "num_speakers": 1,
        "speaker_id_map": {},
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-css10-ja-6lang",
        "files": {
            "css10-ja-6lang-fp16.onnx": {
                "size_bytes": 39652717,
                "md5_digest": ""
            },
            "config.json": {
                "size_bytes": 5912,
                "md5_digest": ""
            }
        },
        "aliases": [
            "css10",
            "css10-6lang",
            "css10-ja",
            "ja-css10",
            "ayousanz/piper-plus-css10-ja-6lang"
        ],
        "description": "CSS10 Japanese 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT, 6841 utterances)"
    },
    "multilingual-zero-shot-base-zs-v1": {
        "key": "multilingual-zero-shot-base-zs-v1",
        "name": "zero-shot-base-zs-v1",
        "language": {
            "code": "multilingual",
            "family": "multilingual",
            "region": "",
            "name_native": "Multilingual",
            "name_english": "Multilingual",
            "country_english": ""
        },
        "quality": "experimental",
        "num_speakers": 571,
        "speaker_id_map": {},
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-base",
        "revision": "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1",
        "files": {
            "releases/zs-v1/base.onnx": {
                "size_bytes": 40777457,
                "md5_digest": ""
            },
            "releases/zs-v1/base.onnx.json": {
                "size_bytes": 6417,
                "md5_digest": ""
            }
        },
        "aliases": [
            "base",
            "zero-shot-base-zs-v1",
            "ayousanz/piper-plus-base"
        ],
        "description": "Experimental zs-v1 base; requires a CAM++ 192-dimensional reference embedding. Python 2.0.0 public example verified; no quality approval."
    }
}
)JSON";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

// Get the directory containing the running executable.
// Delegates to piper_plus_get_exe_dir() in library_path.c.
static fs::path getExeDir() {
    char buf[4096];
    if (piper_plus_get_exe_dir(buf, sizeof(buf)) == 0) {
        return fs::path(buf);
    }
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
    vi.revision = entry.value("revision", "main");

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

    // Usage notice (docs/reference/model-resolution.md §9)
    auto readStringArray = [&entry](const char* field, std::vector<std::string>& out) {
        if (entry.contains(field) && entry[field].is_array()) {
            for (const auto& item : entry[field]) {
                if (item.is_string()) {
                    out.push_back(item.get<std::string>());
                }
            }
        }
    };
    readStringArray("notice", vi.notice);
    readStringArray("notice_files", vi.noticeFiles);

    return vi;
}

// Parse only the embedded piper-plus catalog (no upstream voices.json).
static std::vector<VoiceInfo> loadEmbeddedCatalog() {
    std::vector<VoiceInfo> catalog;
    try {
        json piperPlusCatalog = json::parse(PIPER_PLUS_CATALOG_JSON);
        for (auto& [key, entry] : piperPlusCatalog.items()) {
            catalog.push_back(parseVoiceEntry(key, entry, "piper-plus"));
        }
    } catch (const json::exception& e) {
        spdlog::error("Failed to parse embedded piper-plus catalog: {}", e.what());
    }
    return catalog;
}

static bool isNoticeSpace(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f';
}

static std::string trimNoticeInput(const std::string& s) {
    size_t begin = 0;
    size_t end = s.size();
    while (begin < end && isNoticeSpace(s[begin])) ++begin;
    while (end > begin && isNoticeSpace(s[end - 1])) --end;
    return s.substr(begin, end - begin);
}

// Last path component, splitting on both '/' and '\\' so Windows paths
// are handled the same way on every platform. Trailing separators are
// ignored ("dir/model.onnx/" -> "model.onnx").
static std::string noticeFileName(const std::string& value) {
    size_t end = value.find_last_not_of("/\\");
    if (end == std::string::npos) {
        return "";
    }
    std::string trimmed = value.substr(0, end + 1);
    size_t sep = trimmed.find_last_of("/\\");
    return sep == std::string::npos ? trimmed : trimmed.substr(sep + 1);
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

// Download a single file using system() with curl/wget/PowerShell
static bool downloadFile(const std::string& url,
                         const fs::path& outputPath) {
    // Validate url and path for shell safety
    if (!isSafeForShell(url)) {
        spdlog::error("URL contains unsafe characters: {}", url);
        return false;
    }

    std::string outStr = outputPath.string();
    // Allow isSafeForShellPath characters plus spaces (paths are quoted in commands).
    if (!isSafeForShellPath(outStr)) {
        // isSafeForShellPath rejects spaces; check if spaces are the only extras
        bool safeWithSpaces = !outStr.empty();
        for (char c : outStr) {
            if (c != ' ' && !std::isalnum(static_cast<unsigned char>(c)) &&
                c != '-' && c != '_' && c != '.' && c != '/' &&
                c != '\\' && c != ':') {
                safeWithSpaces = false;
                break;
            }
        }
        if (!safeWithSpaces) {
            spdlog::error("Output path contains unsafe characters: {}", outStr);
            return false;
        }
    }

    // Note: on Apple embedded platforms (iOS / tvOS / watchOS / visionOS),
    // this entire translation unit is excluded from piper_common via
    // cmake/PiperCommon.cmake (issue #377) — std::system() / popen() / fork()
    // are unavailable in the App Sandbox. Apple-embedded consumers must
    // pre-download models via URLSession and pass the local file path.
    spdlog::info("Downloading {} ...", url);

#ifdef _WIN32
    // PowerShell's -Command does NOT bind trailing positional arguments to
    // $args (only -File does). The previous "-Uri $args[0] -OutFile $args[1]"
    // form therefore left both empty, and Invoke-WebRequest failed with
    // "Cannot validate argument on parameter 'Uri'. The argument is null or
    // empty." — breaking --download-model on Windows entirely.
    //
    // Pass URL / OutFile via environment variables instead: the _spawnvp child
    // inherits the parent environment, and env values are never re-parsed as
    // code (injection-safe, so no shell-quoting concerns). The variables are
    // cleared immediately after the spawn returns.
    _putenv_s("PIPER_PLUS_DL_URI", url.c_str());
    _putenv_s("PIPER_PLUS_DL_OUT", outStr.c_str());
    const char* argv[] = {
        "powershell", "-NoProfile", "-Command",
        "Invoke-WebRequest -Uri $env:PIPER_PLUS_DL_URI -OutFile $env:PIPER_PLUS_DL_OUT",
        nullptr,
    };
    int rc = piper_run_argv(argv);
    _putenv_s("PIPER_PLUS_DL_URI", "");
    _putenv_s("PIPER_PLUS_DL_OUT", "");
    return rc == 0;
#else
    // Prefer curl, fall back to wget. Look up the binary on PATH locations
    // directly via access(X_OK) — invoking `which` via system() would re-
    // introduce a shell taint sink that CodeQL flags.
    static const char* const CURL_PATHS[] = {
        "/usr/bin/curl", "/usr/local/bin/curl", "/opt/homebrew/bin/curl",
        "/bin/curl", nullptr,
    };
    static const char* const WGET_PATHS[] = {
        "/usr/bin/wget", "/usr/local/bin/wget", "/opt/homebrew/bin/wget",
        "/bin/wget", nullptr,
    };
    // CodeQL cpp/no-raw-arrays-in-interfaces: take a pointer-to-pointer
    // explicitly rather than letting array-to-pointer decay happen across
    // the lambda boundary. Behavior is identical (still NULL-terminated).
    auto find_tool = [](const char* const* paths) -> const char* {
        for (size_t i = 0; paths[i]; ++i) {
            if (access(paths[i], X_OK) == 0) return paths[i];
        }
        return nullptr;
    };

    if (const char* curl = find_tool(CURL_PATHS); curl != nullptr) {
        const char* argv[] = {
            curl, "-L", "-#", "-o", outStr.c_str(), url.c_str(), nullptr,
        };
        return piper_run_argv(argv) == 0;
    }
    if (const char* wget = find_tool(WGET_PATHS); wget != nullptr) {
        const char* argv[] = {
            wget, "-O", outStr.c_str(), url.c_str(), nullptr,
        };
        return piper_run_argv(argv) == 0;
    }
    spdlog::error("Neither curl nor wget is available for downloading");
    return false;
#endif
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::filesystem::path getDefaultModelDir() {
    // Environment variable takes precedence
    const char* envDir = std::getenv("PIPER_PLUS_MODEL_DIR");
    if (envDir && envDir[0] != '\0') {
        return fs::path(envDir);
    }

#ifdef _WIN32
    const char* appData = std::getenv("APPDATA");
    if (appData) {
        return fs::path(appData) / "piper-plus" / "models";
    }
    return fs::path("models");
#elif defined(__APPLE__)
    const char* home = std::getenv("HOME");
    if (home) {
        return fs::path(home) / "Library" / "Application Support"
               / "piper-plus" / "models";
    }
    return fs::path("models");
#else
    const char* xdgData = std::getenv("XDG_DATA_HOME");
    if (xdgData) {
        return fs::path(xdgData) / "piper-plus" / "models";
    }
    const char* home = std::getenv("HOME");
    if (home) {
        return fs::path(home) / ".local" / "share" / "piper-plus" / "models";
    }
    return fs::path("models");
#endif
}

std::vector<VoiceInfo> loadVoiceCatalog() {
    // 1. Parse embedded piper-plus catalog
    std::vector<VoiceInfo> catalog = loadEmbeddedCatalog();
    spdlog::debug("Loaded {} piper-plus voices from embedded catalog", catalog.size());

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
                    // Validate repoId from external JSON to reject malicious entries
                    std::string repo = entry.value("repo", "");
                    if (!repo.empty() && !isSafeRepoId(repo)) {
                        spdlog::warn("Skipping upstream entry '{}': "
                                     "unsafe repoId '{}'", key, repo);
                        continue;
                    }
                    std::string revision = entry.value("revision", "main");
                    if (revision.empty() || revision.find("..") != std::string::npos ||
                        !std::all_of(revision.begin(), revision.end(), [](unsigned char c) {
                            return std::isalnum(c) || c == '-' || c == '_' || c == '.';
                        })) {
                        spdlog::warn("Skipping upstream entry with unsafe revision: {}", key);
                        continue;
                    }
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

    // 2. Alias match (no partial matching -- aliases provide sufficient coverage)
    for (const auto& voice : catalog) {
        for (const auto& alias : voice.aliases) {
            if (alias == nameOrAlias) {
                return voice;
            }
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

        // Format: key  [source]  N speaker(s)  quality  (aliases)
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
        std::cerr << voice.quality;

        if (!voice.aliases.empty()) {
            std::cerr << "   (";
            for (size_t i = 0; i < voice.aliases.size(); ++i) {
                if (i > 0) std::cerr << ", ";
                std::cerr << voice.aliases[i];
            }
            std::cerr << ")";
        }
        std::cerr << std::endl;
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

    // Reject voice.key with path traversal characters (fix: path traversal prevention)
    if (!isSafeVoiceKey(voice.key)) {
        spdlog::error("Voice key '{}' contains unsafe path characters", voice.key);
        return false;
    }

    // Flat directory layout matching Python: files go directly into modelDir/
    fs::path targetDir = modelDir;
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
        baseUrl = "https://huggingface.co/" + voice.repoId + "/resolve/" + voice.revision + "/";
    } else {
        // Upstream piper:
        // https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{file_path}
        baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/";
    }

    // Download each file
    bool allOk = true;
    for (const auto& file : voice.files) {
        std::string url = baseUrl + file.relativePath;

        // Validate that URL starts with expected HuggingFace prefix
        const std::string expectedPrefix = "https://huggingface.co/";
        if (url.rfind(expectedPrefix, 0) != 0) {
            spdlog::error("Rejecting URL with unexpected scheme/domain: {}", url);
            allOk = false;
            continue;
        }

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

std::optional<fs::path> resolveModelPath(
    const std::string& nameOrAlias,
    const fs::path& modelDir) {
    auto maybeVoice = findVoice(nameOrAlias);
    if (!maybeVoice) {
        return std::nullopt;
    }

    const VoiceInfo& voice = maybeVoice.value();

    // Find the .onnx file in the voice's file list
    for (const auto& file : voice.files) {
        fs::path fn = fs::path(file.relativePath).filename();
        if (fn.extension() == ".onnx") {
            fs::path candidate = modelDir / fn;
            if (fs::exists(candidate)) {
                return candidate;
            }
        }
    }

    return std::nullopt;
}

std::vector<std::string> getModelNotice(const std::string& nameOrPath) {
    const std::string value = trimNoticeInput(nameOrPath);
    if (value.empty()) {
        return {};
    }

    static const std::vector<VoiceInfo> embedded = loadEmbeddedCatalog();
    const std::string fileName = noticeFileName(value);
    const bool isUrl = value.find("://") != std::string::npos;

    for (const auto& voice : embedded) {
        if (voice.notice.empty()) {
            continue;
        }
        bool match = value == voice.key || std::find(voice.aliases.begin(), voice.aliases.end(),
                                                     value) != voice.aliases.end();
        if (!match && !voice.repoId.empty()) {
            match = value == voice.repoId ||
                    (isUrl && value.find("/" + voice.repoId + "/") != std::string::npos);
        }
        if (!match && !fileName.empty()) {
            match = std::find(voice.noticeFiles.begin(), voice.noticeFiles.end(), fileName) !=
                    voice.noticeFiles.end();
        }
        if (match) {
            return voice.notice;
        }
    }
    return {};
}

bool parseModelNoticeDisabled(const char* value) {
    if (value == nullptr) {
        return false;
    }
    std::string v = trimNoticeInput(value);
    std::transform(v.begin(), v.end(), v.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return v == "1" || v == "true" || v == "yes";
}

bool modelNoticeDisabled() { return parseModelNoticeDisabled(std::getenv(kModelNoticeDisableEnv)); }

} // namespace piper
