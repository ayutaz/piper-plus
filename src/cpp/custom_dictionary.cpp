#include "custom_dictionary.hpp"

#include <fstream>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <regex>
#include <iostream>

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

#include "json.hpp"

using json = nlohmann::json;
namespace fs = std::filesystem;

namespace piper {

// Get the directory containing the running executable (same logic as model_manager.cpp)
static fs::path getDictExeDir() {
#ifdef _WIN32
    wchar_t wbuf[MAX_PATH] = {0};
    DWORD len = GetModuleFileNameW(nullptr, wbuf, MAX_PATH);
    if (len > 0 && len < MAX_PATH) {
        return fs::path(wbuf).parent_path();
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

// Find the dictionaries directory: try exe-relative paths first, then
// fall back to the compile-time __FILE__-based path for development builds.
static fs::path findDictDir() {
    fs::path exeDir = getDictExeDir();
    std::error_code ec;

    // Exe-relative candidates (installed / packaged layout)
    std::vector<fs::path> candidates = {
        exeDir / "data" / "dictionaries",
        exeDir / ".." / "data" / "dictionaries",
        exeDir / ".." / "share" / "piper" / "dictionaries",
    };

    for (const auto& p : candidates) {
        if (fs::is_directory(p, ec)) {
            return fs::canonical(p, ec);
        }
    }

    // Compile-time fallback (development builds only)
    fs::path compilePath = fs::path(__FILE__).parent_path().parent_path().parent_path()
                           / "data" / "dictionaries";
    if (fs::is_directory(compilePath, ec)) {
        return compilePath;
    }

    // Last resort: return the first candidate (will simply fail to find files)
    return candidates.front();
}

CustomDictionary::CustomDictionary() {
    // デフォルト辞書ディレクトリを設定
    // 実行ファイルからの相対パスを優先、フォールバックで __FILE__ ベース
    defaultDictDir_ = findDictDir();

    loadDefaultDictionaries();
}

CustomDictionary::CustomDictionary(const std::string& dictPath) : CustomDictionary() {
    loadDictionary(dictPath);
}

CustomDictionary::CustomDictionary(const std::vector<std::string>& dictPaths) : CustomDictionary() {
    for (const auto& path : dictPaths) {
        loadDictionary(path);
    }
}

void CustomDictionary::loadDefaultDictionaries() {
    std::vector<std::string> defaultDicts = {
        "default_tech_dict.json",
        "default_common_dict.json",
        "additional_tech_dict.json",  // 最新トレンドの技術用語
        "user_custom_dict.json"        // ユーザーカスタム辞書（日本語発音修正用）
    };
    
    for (const auto& dictName : defaultDicts) {
        auto dictPath = defaultDictDir_ / dictName;
        if (std::filesystem::exists(dictPath)) {
            try {
                loadDictionary(dictPath.string());
            } catch (const std::exception& e) {
                std::cerr << "Warning: Failed to load default dictionary " 
                          << dictPath << ": " << e.what() << std::endl;
            }
        }
    }
}

void CustomDictionary::loadDictionary(const std::string& dictPath) {
    if (!std::filesystem::exists(dictPath)) {
        throw std::runtime_error("Dictionary file not found: " + dictPath);
    }

    std::ifstream file(dictPath);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open dictionary file: " + dictPath);
    }

    json j;
    try {
        j = json::parse(file);
    } catch (const json::parse_error& e) {
        throw std::runtime_error("Failed to parse dictionary JSON: " + dictPath + ": " + e.what());
    }

    // バージョンチェック
    std::string version = "1.0";
    if (j.contains("version") && j["version"].is_string()) {
        version = j["version"].get<std::string>();
    }

    // エントリの取得（"entries" キーがあればその中、なければトップレベル）
    const json& entries = j.contains("entries") && j["entries"].is_object()
                          ? j["entries"] : j;

    for (auto it = entries.begin(); it != entries.end(); ++it) {
        const std::string& word = it.key();

        // メタデータキーをスキップ
        if (word == "version" || word == "description" || word == "metadata") {
            continue;
        }

        if (it.value().is_object()) {
            // V2形式: {"pronunciation": "...", "priority": N}
            const json& obj = it.value();
            if (obj.contains("pronunciation") && obj["pronunciation"].is_string()) {
                std::string pronunciation = obj["pronunciation"].get<std::string>();
                int priority = 5;
                if (obj.contains("priority") && obj["priority"].is_number_integer()) {
                    priority = obj["priority"].get<int>();
                }
                addEntry(word, DictionaryEntry(pronunciation, priority));
            }
        } else if (it.value().is_string()) {
            // V1形式: "word": "pronunciation"
            std::string pronunciation = it.value().get<std::string>();
            addEntry(word, DictionaryEntry(pronunciation, 5));
        }
    }
}

void CustomDictionary::addEntry(const std::string& word, const DictionaryEntry& entry) {
    if (isMixedCase(word)) {
        // 大文字小文字が混在している場合は区別する
        caseSensitiveEntries_[word] = entry;
    } else {
        // 全て大文字または小文字の場合は正規化
        std::string normalizedWord = toLowerCase(word);
        
        // 既存エントリとの優先度比較
        auto it = entries_.find(normalizedWord);
        if (it != entries_.end()) {
            if (entry.priority <= it->second.priority) {
                return; // 既存の方が優先度が高い
            }
        }
        
        entries_[normalizedWord] = entry;
    }
}

std::string CustomDictionary::applyToText(const std::string& text) const {
    std::string result = text;
    
    // エントリを長さでソート（長い単語から処理）
    std::vector<std::pair<std::string, DictionaryEntry>> sortedCaseSensitive(
        caseSensitiveEntries_.begin(), caseSensitiveEntries_.end());
    std::sort(sortedCaseSensitive.begin(), sortedCaseSensitive.end(),
              [](const auto& a, const auto& b) { return a.first.length() > b.first.length(); });
    
    std::vector<std::pair<std::string, DictionaryEntry>> sortedEntries(
        entries_.begin(), entries_.end());
    std::sort(sortedEntries.begin(), sortedEntries.end(),
              [](const auto& a, const auto& b) { return a.first.length() > b.first.length(); });
    
    // 大文字小文字を区別するエントリを処理
    for (const auto& [word, entry] : sortedCaseSensitive) {
        std::regex pattern = getWordPattern(word, true);
        result = std::regex_replace(result, pattern, entry.pronunciation);
    }
    
    // 大文字小文字を区別しないエントリを処理
    for (const auto& [word, entry] : sortedEntries) {
        std::regex pattern = getWordPattern(word, false);
        result = std::regex_replace(result, pattern, entry.pronunciation);
    }
    
    return result;
}

void CustomDictionary::addWord(const std::string& word, const std::string& pronunciation, int priority) {
    addEntry(word, DictionaryEntry(pronunciation, priority));
    patternCache_.clear(); // キャッシュをクリア
}

bool CustomDictionary::removeWord(const std::string& word) {
    bool removed = false;
    
    if (caseSensitiveEntries_.erase(word) > 0) {
        removed = true;
    }
    
    std::string normalizedWord = toLowerCase(word);
    if (entries_.erase(normalizedWord) > 0) {
        removed = true;
    }
    
    if (removed) {
        patternCache_.clear();
    }
    
    return removed;
}

std::optional<std::string> CustomDictionary::getPronunciation(const std::string& word) const {
    // 大文字小文字を区別してチェック
    auto it = caseSensitiveEntries_.find(word);
    if (it != caseSensitiveEntries_.end()) {
        return it->second.pronunciation;
    }
    
    // 正規化してチェック
    std::string normalizedWord = toLowerCase(word);
    auto it2 = entries_.find(normalizedWord);
    if (it2 != entries_.end()) {
        return it2->second.pronunciation;
    }
    
    return std::nullopt;
}

void CustomDictionary::saveDictionary(const std::string& outputPath) const {
    std::ofstream file(outputPath);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open output file: " + outputPath);
    }

    // Use nlohmann::json to build the output so that keys and values
    // (which may contain " or \) are properly escaped.
    json root;
    root["version"] = "2.0";
    root["description"] = "Custom dictionary exported from Piper";
    root["metadata"] = {
        {"created", "auto-generated"},
        {"author", "Piper"},
        {"license", "MIT"}
    };

    json entries = json::object();

    for (const auto& [word, entry] : entries_) {
        entries[word] = {
            {"pronunciation", entry.pronunciation},
            {"priority", entry.priority}
        };
    }

    for (const auto& [word, entry] : caseSensitiveEntries_) {
        entries[word] = {
            {"pronunciation", entry.pronunciation},
            {"priority", entry.priority}
        };
    }

    root["entries"] = entries;

    file << root.dump(2) << "\n";
}

CustomDictionary::Stats CustomDictionary::getStats() const {
    return {
        entries_.size() + caseSensitiveEntries_.size(),
        entries_.size(),
        caseSensitiveEntries_.size()
    };
}

std::string CustomDictionary::toLowerCase(const std::string& str) const {
    std::string result = str;
    std::transform(result.begin(), result.end(), result.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return result;
}

bool CustomDictionary::isMixedCase(const std::string& str) const {
    bool hasUpper = false;
    bool hasLower = false;
    
    for (char c : str) {
        if (std::isupper(c)) hasUpper = true;
        if (std::islower(c)) hasLower = true;
        if (hasUpper && hasLower) return true;
    }
    
    return false;
}

std::regex CustomDictionary::getWordPattern(const std::string& word, bool caseSensitive) const {
    std::string cacheKey = word + "_" + (caseSensitive ? "1" : "0");
    
    auto it = patternCache_.find(cacheKey);
    if (it != patternCache_.end()) {
        return it->second;
    }
    
    // エスケープ処理
    std::string escapedWord;
    for (char c : word) {
        if (std::string(".^$*+?{}[]|()\\").find(c) != std::string::npos) {
            escapedWord += '\\';
        }
        escapedWord += c;
    }
    
    // 単語境界を考慮したパターン
    // 日本語等のマルチバイトUTF-8文字では \b が正しく動作しないため、
    // 先頭バイトが非ASCIIの場合はワードバウンダリを付けない
    std::string patternStr;
    if (!word.empty() && static_cast<unsigned char>(word[0]) > 0x7F) {
        patternStr = escapedWord;  // マルチバイト: バウンダリなし
    } else {
        patternStr = "\\b" + escapedWord + "\\b";  // ASCII: 従来通り
    }
    
    auto flags = std::regex::ECMAScript;
    if (!caseSensitive) {
        flags |= std::regex::icase;
    }
    
    std::regex pattern(patternStr, flags);
    patternCache_[cacheKey] = pattern;
    
    return pattern;
}

// 便利な関数の実装
std::unique_ptr<CustomDictionary> createDefaultDictionary() {
    return std::make_unique<CustomDictionary>();
}

std::string applyCustomDictionary(const std::string& text, 
                                 const std::vector<std::string>& dictPaths) {
    CustomDictionary dict(dictPaths);
    return dict.applyToText(text);
}

} // namespace piper