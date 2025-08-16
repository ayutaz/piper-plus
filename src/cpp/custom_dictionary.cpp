#include "custom_dictionary.hpp"

#include <fstream>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <regex>

// JSON parsing - we'll use a simple approach for now
// In production, consider using nlohmann/json or rapidjson
#include <iostream>

namespace piper {

// シンプルなJSON解析（実装の簡略化のため）
// 実際のプロダクションでは適切なJSONライブラリを使用してください
namespace {
    
std::unordered_map<std::string, std::string> parseSimpleJsonDict(const std::string& content) {
    std::unordered_map<std::string, std::string> result;
    
    // 非常に簡略化された解析 - "key": "value" のパターンを探す
    std::regex pattern("\"([^\"]+)\"\\s*:\\s*\"([^\"]+)\"");
    std::sregex_iterator it(content.begin(), content.end(), pattern);
    std::sregex_iterator end;
    
    for (; it != end; ++it) {
        result[(*it)[1]] = (*it)[2];
    }
    
    return result;
}

std::unordered_map<std::string, DictionaryEntry> parseJsonDictV2(const std::string& content) {
    std::unordered_map<std::string, DictionaryEntry> result;
    
    // "word": {"pronunciation": "...", "priority": N} のパターンを探す
    std::regex wordPattern("\"([^\"]+)\"\\s*:\\s*\\{([^}]+)\\}");
    std::regex pronPattern("\"pronunciation\"\\s*:\\s*\"([^\"]+)\"");
    std::regex prioPattern("\"priority\"\\s*:\\s*(\\d+)");
    
    std::sregex_iterator it(content.begin(), content.end(), wordPattern);
    std::sregex_iterator end;
    
    for (; it != end; ++it) {
        std::string word = (*it)[1];
        std::string entryContent = (*it)[2];
        
        // コメント行をスキップ
        if (word.substr(0, 2) == "//") {
            continue;
        }
        
        DictionaryEntry entry;
        
        // pronunciation を探す
        std::smatch pronMatch;
        if (std::regex_search(entryContent, pronMatch, pronPattern)) {
            entry.pronunciation = pronMatch[1];
        }
        
        // priority を探す
        std::smatch prioMatch;
        if (std::regex_search(entryContent, prioMatch, prioPattern)) {
            entry.priority = std::stoi(prioMatch[1]);
        } else {
            entry.priority = 5; // デフォルト値
        }
        
        if (!entry.pronunciation.empty()) {
            result[word] = entry;
        }
    }
    
    // 簡易的な文字列値も処理（後方互換性のため）
    std::regex simplePattern("\"([^\"]+)\"\\s*:\\s*\"([^\"]+)\"");
    std::sregex_iterator simpleIt(content.begin(), content.end(), simplePattern);
    
    for (; simpleIt != end; ++simpleIt) {
        std::string word = (*simpleIt)[1];
        std::string pronunciation = (*simpleIt)[2];
        
        // まだ登録されていない場合のみ追加
        if (result.find(word) == result.end() && word.substr(0, 2) != "//") {
            result[word] = DictionaryEntry(pronunciation, 5);
        }
    }
    
    return result;
}

} // anonymous namespace

CustomDictionary::CustomDictionary() {
    // デフォルト辞書ディレクトリを設定
    // 実行ファイルからの相対パスで設定
    defaultDictDir_ = std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() 
                      / "data" / "dictionaries";
    
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
    
    std::string content((std::istreambuf_iterator<char>(file)),
                       std::istreambuf_iterator<char>());
    
    // バージョンチェック（簡易的）
    bool isV2 = content.find("\"version\": \"2.0\"") != std::string::npos ||
                content.find("\"version\":\"2.0\"") != std::string::npos;
    
    if (isV2) {
        auto entries = parseJsonDictV2(content);
        for (const auto& [word, entry] : entries) {
            addEntry(word, entry);
        }
    } else {
        // V1形式として処理
        auto entries = parseSimpleJsonDict(content);
        for (const auto& [word, pronunciation] : entries) {
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
    
    file << "{\n";
    file << "  \"version\": \"2.0\",\n";
    file << "  \"description\": \"Custom dictionary exported from Piper\",\n";
    file << "  \"metadata\": {\n";
    file << "    \"created\": \"auto-generated\",\n";
    file << "    \"author\": \"Piper\",\n";
    file << "    \"license\": \"MIT\"\n";
    file << "  },\n";
    file << "  \"entries\": {\n";
    
    bool first = true;
    
    // すべてのエントリを出力
    for (const auto& [word, entry] : entries_) {
        if (!first) file << ",\n";
        file << "    \"" << word << "\": {";
        file << "\"pronunciation\": \"" << entry.pronunciation << "\", ";
        file << "\"priority\": " << entry.priority << "}";
        first = false;
    }
    
    for (const auto& [word, entry] : caseSensitiveEntries_) {
        if (!first) file << ",\n";
        file << "    \"" << word << "\": {";
        file << "\"pronunciation\": \"" << entry.pronunciation << "\", ";
        file << "\"priority\": " << entry.priority << "}";
        first = false;
    }
    
    file << "\n  }\n";
    file << "}\n";
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
    std::string patternStr = "\\b" + escapedWord + "\\b";
    
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