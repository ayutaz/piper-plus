#ifndef PIPER_CUSTOM_DICTIONARY_HPP
#define PIPER_CUSTOM_DICTIONARY_HPP

#include <string>
#include <unordered_map>
#include <vector>
#include <memory>
#include <regex>
#include <optional>
#include <filesystem>

namespace piper {

/**
 * カスタム辞書エントリ
 */
struct DictionaryEntry {
    std::string pronunciation;  // カタカナ読み
    int priority = 5;          // 優先度（0-10）
    
    DictionaryEntry() = default;
    DictionaryEntry(const std::string& pron, int pri = 5) 
        : pronunciation(pron), priority(pri) {}
};

/**
 * カスタム辞書クラス
 * 技術用語や固有名詞の読みを管理し、テキスト前処理を行う
 */
class CustomDictionary {
public:
    CustomDictionary();
    explicit CustomDictionary(const std::string& dictPath);
    explicit CustomDictionary(const std::vector<std::string>& dictPaths);
    
    // 辞書の読み込み
    void loadDictionary(const std::string& dictPath);
    void loadDefaultDictionaries();
    
    // テキスト処理
    std::string applyToText(const std::string& text) const;
    
    // 単語管理
    void addWord(const std::string& word, const std::string& pronunciation, int priority = 5);
    bool removeWord(const std::string& word);
    std::optional<std::string> getPronunciation(const std::string& word) const;
    
    // 辞書の保存
    void saveDictionary(const std::string& outputPath) const;
    
    // 統計情報
    struct Stats {
        size_t totalEntries;
        size_t caseInsensitiveEntries;
        size_t caseSensitiveEntries;
    };
    Stats getStats() const;

private:
    // 大文字小文字を区別しないエントリ（正規化済み）
    std::unordered_map<std::string, DictionaryEntry> entries_;
    
    // 大文字小文字を区別するエントリ
    std::unordered_map<std::string, DictionaryEntry> caseSensitiveEntries_;
    
    // 正規表現パターンのキャッシュ
    mutable std::unordered_map<std::string, std::regex> patternCache_;
    
    // デフォルト辞書ディレクトリ
    std::filesystem::path defaultDictDir_;
    
    // ヘルパー関数
    void addEntry(const std::string& word, const DictionaryEntry& entry);
    std::string toLowerCase(const std::string& str) const;
    bool isMixedCase(const std::string& str) const;
    std::regex getWordPattern(const std::string& word, bool caseSensitive) const;
    void loadDictionaryV1(const std::string& dictPath, const void* jsonData);
    void loadDictionaryV2(const std::string& dictPath, const void* jsonData);
};

// 便利な関数
std::unique_ptr<CustomDictionary> createDefaultDictionary();
std::string applyCustomDictionary(const std::string& text, 
                                 const std::vector<std::string>& dictPaths = {});

} // namespace piper

#endif // PIPER_CUSTOM_DICTIONARY_HPP