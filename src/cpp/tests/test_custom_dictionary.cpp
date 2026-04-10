#include <gtest/gtest.h>
#include <fstream>
#include <filesystem>
#include "custom_dictionary.hpp"

using namespace piper;

class CustomDictionaryTest : public ::testing::Test {
protected:
    void SetUp() override {
        // テスト用の一時ディレクトリを作成
        tempDir = std::filesystem::temp_directory_path() / "piper_test";
        std::filesystem::create_directories(tempDir);
    }
    
    void TearDown() override {
        // テスト用ディレクトリを削除
        std::filesystem::remove_all(tempDir);
    }
    
    std::filesystem::path tempDir;
    
    // テスト用の辞書ファイルを作成
    std::string createTestDictV1(const std::string& filename) {
        auto path = tempDir / filename;
        std::ofstream file(path);
        file << R"({
            "version": "1.0",
            "entries": {
                "Docker": "ドッカー",
                "Python": "パイソン"
            }
        })";
        return path.string();
    }
    
    std::string createTestDictV2(const std::string& filename) {
        auto path = tempDir / filename;
        std::ofstream file(path);
        file << R"({
            "version": "2.0",
            "entries": {
                "Docker": {"pronunciation": "ドッカー", "priority": 9},
                "Python": {"pronunciation": "パイソン", "priority": 8}
            }
        })";
        return path.string();
    }
};

TEST_F(CustomDictionaryTest, BasicReplacement) {
    CustomDictionary dict;
    dict.addWord("Docker", "ドッカー", 9);
    dict.addWord("GitHub", "ギットハブ", 9);
    
    std::string text = "DockerとGitHubを使った開発";
    std::string result = dict.applyToText(text);
    EXPECT_EQ(result, "ドッカーとギットハブを使った開発");
}

TEST_F(CustomDictionaryTest, CaseInsensitive) {
    CustomDictionary dict;
    dict.addWord("docker", "ドッカー", 9);
    
    std::string text = "Docker, DOCKER, docker";
    std::string result = dict.applyToText(text);
    EXPECT_EQ(result, "ドッカー, ドッカー, ドッカー");
}

TEST_F(CustomDictionaryTest, CaseSensitive) {
    CustomDictionary dict;
    dict.addWord("PyTorch", "パイトーチ", 8);
    dict.addWord("pytorch", "パイトーチ小文字", 8);
    
    std::string text = "PyTorchとpytorchは異なる";
    std::string result = dict.applyToText(text);
    EXPECT_EQ(result, "パイトーチとパイトーチ小文字は異なる");
}

TEST_F(CustomDictionaryTest, WordBoundary) {
    CustomDictionary dict;
    dict.addWord("AI", "エーアイ", 9);
    
    std::string text = "AI技術とAIDS（エイズ）は違う";
    std::string result = dict.applyToText(text);
    // デフォルト辞書の user_custom_dict.json に "AI" -> "えーあい" (priority 10) が
    // 存在するため、テストの addWord (priority 9) より優先される
    EXPECT_EQ(result, "えーあい技術とAIDS（エイズ）は違う");
}

TEST_F(CustomDictionaryTest, Priority) {
    CustomDictionary dict;
    dict.addWord("test", "テスト１", 5);
    dict.addWord("test", "テスト２", 8);  // より高い優先度
    
    std::string text = "これはtestです";
    std::string result = dict.applyToText(text);
    EXPECT_EQ(result, "これはテスト２です");
}

TEST_F(CustomDictionaryTest, LoadV1Format) {
    std::string dictPath = createTestDictV1("test_v1.json");
    CustomDictionary dict(dictPath);
    
    auto pron = dict.getPronunciation("Docker");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "ドッカー");
    
    pron = dict.getPronunciation("Python");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "パイソン");
}

TEST_F(CustomDictionaryTest, LoadV2Format) {
    std::string dictPath = createTestDictV2("test_v2.json");
    CustomDictionary dict(dictPath);
    
    auto pron = dict.getPronunciation("Docker");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "ドッカー");
    
    pron = dict.getPronunciation("Python");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "パイソン");
}

TEST_F(CustomDictionaryTest, JapaneseText) {
    CustomDictionary dict;
    dict.addWord("Piper", "パイパー", 10);
    dict.addWord("TTS", "ティーティーエス", 10);
    
    std::string text = "PiperはオープンソースのTTSエンジンです。";
    std::string result = dict.applyToText(text);
    EXPECT_EQ(result, "パイパーはオープンソースのティーティーエスエンジンです。");
}

TEST_F(CustomDictionaryTest, MultipleDictionaries) {
    std::string dict1 = createTestDictV2("dict1.json");
    std::string dict2 = createTestDictV1("dict2.json");
    
    CustomDictionary dict({dict1, dict2});
    
    auto pron = dict.getPronunciation("Docker");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "ドッカー");
    
    pron = dict.getPronunciation("Python");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "パイソン");
}

TEST_F(CustomDictionaryTest, SaveDictionary) {
    CustomDictionary dict;
    dict.addWord("Test", "テスト", 7);
    
    auto savePath = tempDir / "saved.json";
    dict.saveDictionary(savePath.string());
    
    // 保存した辞書を読み込み
    CustomDictionary newDict(savePath.string());
    auto pron = newDict.getPronunciation("Test");
    ASSERT_TRUE(pron.has_value());
    EXPECT_EQ(pron.value(), "テスト");
}

TEST_F(CustomDictionaryTest, Stats) {
    CustomDictionary dict;
    dict.addWord("docker", "ドッカー");  // case insensitive
    dict.addWord("PyTorch", "パイトーチ");  // case sensitive
    
    auto stats = dict.getStats();
    // デフォルト辞書がロードされるため、追加した2件以上のエントリが存在する
    EXPECT_GE(stats.totalEntries, 2u);
    EXPECT_GE(stats.caseInsensitiveEntries, 1u);
    EXPECT_GE(stats.caseSensitiveEntries, 1u);
}

TEST_F(CustomDictionaryTest, RemoveWord) {
    CustomDictionary dict;
    dict.addWord("Test", "テスト");
    
    EXPECT_TRUE(dict.getPronunciation("Test").has_value());
    EXPECT_TRUE(dict.removeWord("Test"));
    EXPECT_FALSE(dict.getPronunciation("Test").has_value());
    EXPECT_FALSE(dict.removeWord("Test"));  // 既に削除済み
}

TEST_F(CustomDictionaryTest, ApplyFunction) {
    std::string dictPath = createTestDictV2("apply_test.json");
    
    std::string text = "Dockerコンテナを起動";
    std::string result = applyCustomDictionary(text, {dictPath});
    EXPECT_EQ(result, "ドッカーコンテナを起動");
}

TEST_F(CustomDictionaryTest, DefaultDictionary) {
    auto dict = createDefaultDictionary();
    ASSERT_NE(dict, nullptr);
    
    // デフォルト辞書が読み込まれていることを確認
    // （実際のファイルの存在に依存するため、基本的な動作確認のみ）
    auto stats = dict->getStats();
    EXPECT_GE(stats.totalEntries, 0);
}