/**
 * Test: Model Manager
 *
 * Tests for model catalog loading, voice lookup, and listing functionality
 * provided by model_manager.hpp/cpp.
 *
 * These tests do NOT perform network access (no actual downloads).
 */

#include <gtest/gtest.h>
#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <algorithm>
#include <cstdlib>
#include <cctype>
#include <sstream>
#include <iostream>

#ifdef _WIN32
#include <windows.h>
#endif

#include "model_manager.hpp"

// ============================================
// Helper: Environment variable RAII guard
// ============================================

class EnvVarGuard {
public:
    explicit EnvVarGuard(const std::string& name)
        : name_(name), hadValue_(false) {
        const char* val = std::getenv(name.c_str());
        if (val) {
            hadValue_ = true;
            originalValue_ = val;
        }
    }

    ~EnvVarGuard() { restore(); }

    void set(const std::string& value) {
#ifdef _WIN32
        SetEnvironmentVariableA(name_.c_str(), value.c_str());
        _putenv_s(name_.c_str(), value.c_str());
#else
        setenv(name_.c_str(), value.c_str(), 1);
#endif
    }

    void unset() {
#ifdef _WIN32
        SetEnvironmentVariableA(name_.c_str(), nullptr);
        _putenv_s(name_.c_str(), "");
#else
        unsetenv(name_.c_str());
#endif
    }

    void restore() {
        if (hadValue_) {
            set(originalValue_);
        } else {
            unset();
        }
    }

private:
    std::string name_;
    std::string originalValue_;
    bool hadValue_;
};

// ============================================
// getDefaultModelDir tests
// ============================================

TEST(ModelManagerTest, DefaultModelDirNotEmpty) {
    auto dir = piper::getDefaultModelDir();
    EXPECT_FALSE(dir.empty());
}

TEST(ModelManagerTest, DefaultModelDirContainsPiper) {
    auto dir = piper::getDefaultModelDir();
    // The path should contain "piper" somewhere
    EXPECT_NE(dir.string().find("piper"), std::string::npos)
        << "Default model dir does not contain 'piper': " << dir.string();
}

TEST(ModelManagerTest, DefaultModelDirEnvOverride) {
    EnvVarGuard guard("PIPER_PLUS_MODEL_DIR");

    std::string customPath = "/tmp/piper_test_custom_models";
    guard.set(customPath);

    auto dir = piper::getDefaultModelDir();
    EXPECT_EQ(dir.string(), customPath)
        << "PIPER_PLUS_MODEL_DIR override not respected. Got: " << dir.string();
}

TEST(ModelManagerTest, DefaultModelDirEnvOverrideEmpty) {
    // When PIPER_PLUS_MODEL_DIR is set to empty, should fall back to platform default
    EnvVarGuard guard("PIPER_PLUS_MODEL_DIR");
    guard.set("");

    auto dir = piper::getDefaultModelDir();
    // An empty env var should either return empty or fall back;
    // at minimum the function should not crash
    // (Implementation-dependent: some may treat "" as unset)
    EXPECT_NO_THROW(piper::getDefaultModelDir());
}

// ============================================
// loadVoiceCatalog tests
// ============================================

TEST(ModelManagerTest, CatalogNotEmpty) {
    auto catalog = piper::loadVoiceCatalog();
    EXPECT_GT(catalog.size(), 0u)
        << "Voice catalog is empty";
}

TEST(ModelManagerTest, CatalogContainsTsukuyomi) {
    auto catalog = piper::loadVoiceCatalog();
    bool found = false;
    for (const auto& voice : catalog) {
        if (voice.key == "ja_JP-tsukuyomi-chan-medium") {
            found = true;
            EXPECT_EQ(voice.name, "tsukuyomi-chan");
            EXPECT_EQ(voice.languageCode, "ja_JP");
            EXPECT_EQ(voice.languageFamily, "ja");
            EXPECT_EQ(voice.source, "piper-plus");
            EXPECT_EQ(voice.numSpeakers, 1);
            EXPECT_EQ(voice.quality, "medium");
            break;
        }
    }
    EXPECT_TRUE(found) << "ja_JP-tsukuyomi-chan-medium not found in catalog";
}

TEST(ModelManagerTest, CatalogContainsCss10) {
    auto catalog = piper::loadVoiceCatalog();
    bool found = false;
    for (const auto& voice : catalog) {
        if (voice.key == "ja_JP-css10-6lang-medium") {
            found = true;
            EXPECT_EQ(voice.name, "css10-6lang");
            EXPECT_EQ(voice.languageCode, "ja_JP");
            EXPECT_EQ(voice.languageFamily, "ja");
            EXPECT_EQ(voice.source, "piper-plus");
            EXPECT_EQ(voice.numSpeakers, 1);
            EXPECT_EQ(voice.quality, "medium");
            break;
        }
    }
    EXPECT_TRUE(found) << "ja_JP-css10-6lang-medium not found in catalog";
}

TEST(ModelManagerTest, CatalogVoicesHaveFiles) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        if (voice.source == "piper-plus") {
            EXPECT_GT(voice.files.size(), 0u)
                << "Voice " << voice.key << " has no files";

            // Check that at least one file is an ONNX model
            bool hasOnnx = false;
            for (const auto& file : voice.files) {
                if (file.relativePath.find(".onnx") != std::string::npos &&
                    file.relativePath.find(".json") == std::string::npos) {
                    hasOnnx = true;
                    break;
                }
            }
            EXPECT_TRUE(hasOnnx)
                << "Voice " << voice.key << " has no ONNX file";
        }
    }
}

TEST(ModelManagerTest, CatalogVoicesHaveConfigFile) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        if (voice.source == "piper-plus") {
            bool hasConfig = false;
            for (const auto& file : voice.files) {
                if (file.relativePath.find(".onnx.json") != std::string::npos ||
                    file.relativePath.find("config.json") != std::string::npos) {
                    hasConfig = true;
                    break;
                }
            }
            EXPECT_TRUE(hasConfig)
                << "Voice " << voice.key << " has no config/json file";
        }
    }
}

TEST(ModelManagerTest, CatalogVoicesHaveLanguage) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        EXPECT_FALSE(voice.languageCode.empty())
            << "Voice " << voice.key << " has empty language code";
        EXPECT_FALSE(voice.languageFamily.empty())
            << "Voice " << voice.key << " has empty language family";
    }
}

TEST(ModelManagerTest, CatalogVoicesHaveKey) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        EXPECT_FALSE(voice.key.empty())
            << "Found voice with empty key";
    }
}

TEST(ModelManagerTest, CatalogVoicesHaveQuality) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        EXPECT_FALSE(voice.quality.empty())
            << "Voice " << voice.key << " has empty quality";
    }
}

TEST(ModelManagerTest, CatalogVoiceFileSizesPositive) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        for (const auto& file : voice.files) {
            EXPECT_GT(file.sizeBytes, 0u)
                << "Voice " << voice.key << " file " << file.relativePath
                << " has zero size";
        }
    }
}

TEST(ModelManagerTest, CatalogKeysAreUnique) {
    auto catalog = piper::loadVoiceCatalog();
    std::vector<std::string> keys;
    keys.reserve(catalog.size());
    for (const auto& voice : catalog) {
        keys.push_back(voice.key);
    }
    std::sort(keys.begin(), keys.end());
    auto it = std::adjacent_find(keys.begin(), keys.end());
    EXPECT_EQ(it, keys.end())
        << "Duplicate key found: " << (it != keys.end() ? *it : "");
}

// ============================================
// findVoice tests
// ============================================

TEST(ModelManagerTest, FindByExactKey) {
    auto result = piper::findVoice("ja_JP-tsukuyomi-chan-medium");
    ASSERT_TRUE(result.has_value())
        << "findVoice failed for exact key ja_JP-tsukuyomi-chan-medium";
    EXPECT_EQ(result->key, "ja_JP-tsukuyomi-chan-medium");
}

TEST(ModelManagerTest, FindByAlias) {
    auto result = piper::findVoice("tsukuyomi");
    ASSERT_TRUE(result.has_value())
        << "findVoice failed for alias 'tsukuyomi'";
    EXPECT_EQ(result->key, "ja_JP-tsukuyomi-chan-medium");
}

TEST(ModelManagerTest, FindByAliasCss10) {
    auto result = piper::findVoice("css10");
    ASSERT_TRUE(result.has_value())
        << "findVoice failed for alias 'css10'";
    EXPECT_EQ(result->key, "ja_JP-css10-6lang-medium");
}

TEST(ModelManagerTest, FindByAliasFullName) {
    auto result = piper::findVoice("tsukuyomi-chan");
    ASSERT_TRUE(result.has_value())
        << "findVoice failed for alias 'tsukuyomi-chan'";
    EXPECT_EQ(result->key, "ja_JP-tsukuyomi-chan-medium");
}

TEST(ModelManagerTest, FindNonExistent) {
    auto result = piper::findVoice("non-existent-model-xyz-12345");
    EXPECT_FALSE(result.has_value())
        << "findVoice should return empty for non-existent model";
}

TEST(ModelManagerTest, FindEmptyName) {
    auto result = piper::findVoice("");
    EXPECT_FALSE(result.has_value())
        << "findVoice should return empty for empty name";
}

TEST(ModelManagerTest, FindByExactKeyReturnsSameAsAlias) {
    auto byKey = piper::findVoice("ja_JP-tsukuyomi-chan-medium");
    auto byAlias = piper::findVoice("tsukuyomi");
    ASSERT_TRUE(byKey.has_value());
    ASSERT_TRUE(byAlias.has_value());
    EXPECT_EQ(byKey->key, byAlias->key)
        << "Exact key and alias should resolve to the same voice";
}

// ============================================
// listModels tests (verify no crash / no throw)
// ============================================

TEST(ModelManagerTest, ListAllModels) {
    EXPECT_NO_THROW(piper::listModels(""));
}

TEST(ModelManagerTest, ListJapaneseModels) {
    EXPECT_NO_THROW(piper::listModels("ja"));
}

TEST(ModelManagerTest, ListWithLanguageCode) {
    EXPECT_NO_THROW(piper::listModels("ja_JP"));
}

TEST(ModelManagerTest, ListNonExistentLanguage) {
    EXPECT_NO_THROW(piper::listModels("zz"));
}

TEST(ModelManagerTest, ListEnglishModels) {
    EXPECT_NO_THROW(piper::listModels("en"));
}

// ============================================
// VoiceInfo structure tests
// ============================================

TEST(ModelManagerTest, PiperPlusSource) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        if (voice.key.find("tsukuyomi") != std::string::npos ||
            voice.key.find("css10") != std::string::npos) {
            EXPECT_EQ(voice.source, "piper-plus")
                << "Voice " << voice.key << " should have source 'piper-plus'";
        }
    }
}

TEST(ModelManagerTest, VoiceSourceIsValid) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        EXPECT_TRUE(voice.source == "piper-plus" || voice.source == "piper")
            << "Voice " << voice.key << " has unexpected source: " << voice.source;
    }
}

TEST(ModelManagerTest, VoiceHasAliases) {
    auto voice = piper::findVoice("ja_JP-tsukuyomi-chan-medium");
    ASSERT_TRUE(voice.has_value());
    EXPECT_GT(voice->aliases.size(), 0u)
        << "tsukuyomi-chan voice should have at least one alias";

    // Check specific alias
    bool hasTsukuyomi = false;
    for (const auto& alias : voice->aliases) {
        if (alias == "tsukuyomi") hasTsukuyomi = true;
    }
    EXPECT_TRUE(hasTsukuyomi)
        << "'tsukuyomi' alias not found in tsukuyomi-chan voice";
}

TEST(ModelManagerTest, VoiceNumSpeakersNonNegative) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        EXPECT_GE(voice.numSpeakers, 1)
            << "Voice " << voice.key << " has invalid numSpeakers: "
            << voice.numSpeakers;
    }
}

TEST(ModelManagerTest, VoiceRepoIdNotEmpty) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        if (voice.source == "piper-plus") {
            EXPECT_FALSE(voice.repoId.empty())
                << "Voice " << voice.key << " has empty repoId";
        }
    }
}

TEST(ModelManagerTest, VoiceFileRelativePathNotEmpty) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        for (const auto& file : voice.files) {
            EXPECT_FALSE(file.relativePath.empty())
                << "Voice " << voice.key << " has a file with empty relativePath";
        }
    }
}

TEST(ModelManagerTest, VoiceFileMd5DigestFormat) {
    auto catalog = piper::loadVoiceCatalog();
    for (const auto& voice : catalog) {
        for (const auto& file : voice.files) {
            if (!file.md5Digest.empty()) {
                // MD5 digest should be 32 hex characters
                EXPECT_EQ(file.md5Digest.size(), 32u)
                    << "Voice " << voice.key << " file " << file.relativePath
                    << " has MD5 digest of unexpected length: "
                    << file.md5Digest.size();
                // All characters should be hex digits
                for (char c : file.md5Digest) {
                    EXPECT_TRUE(std::isxdigit(static_cast<unsigned char>(c)))
                        << "Voice " << voice.key << " file " << file.relativePath
                        << " has non-hex character in MD5 digest: " << c;
                }
            }
        }
    }
}

// ============================================
// JSON parsing test (catalog loads without error)
// ============================================

TEST(ModelManagerTest, CatalogJsonParsingSucceeds) {
    // loadVoiceCatalog internally parses the embedded JSON catalog.
    // If parsing fails it would throw or return empty.
    EXPECT_NO_THROW({
        auto catalog = piper::loadVoiceCatalog();
        EXPECT_GT(catalog.size(), 0u)
            << "Catalog JSON parsing resulted in empty catalog";
    });
}

TEST(ModelManagerTest, CatalogLoadIsIdempotent) {
    auto catalog1 = piper::loadVoiceCatalog();
    auto catalog2 = piper::loadVoiceCatalog();
    EXPECT_EQ(catalog1.size(), catalog2.size())
        << "Loading catalog twice should produce same number of entries";
    for (size_t i = 0; i < catalog1.size() && i < catalog2.size(); ++i) {
        EXPECT_EQ(catalog1[i].key, catalog2[i].key)
            << "Catalog entry " << i << " differs between loads";
    }
}

// ============================================
// Model usage notice (docs/reference/model-resolution.md §9)
// ============================================

namespace {

// Copied from test/model_resolution_vectors.json (voice_catalog notice).
const std::vector<std::string> kTsukuyomiNotice = {
    "[piper-plus] つくよみちゃんモデルの利用条件 / Terms for the Tsukuyomi-chan model",
    "生成した音声を使うときは「Piper Plus:つくよみちゃん」のクレジット表記が必須です。",
    "Credit 'Piper Plus:つくよみちゃん' is required when you use the generated audio.",
    "非公式の作品です。夢前黎様は開発・サポートに携わっていません。お問い合わせは開発者へ。",
    "Unofficial work. Rei Yumesaki is not involved in development or support; contact the developer.",
    "禁止事項と規約 / Terms and prohibited uses: https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan",
};

}  // namespace

TEST(ModelNoticeTest, CatalogEntryCarriesNotice) {
    auto voice = piper::findVoice("ja_JP-tsukuyomi-chan-medium");
    ASSERT_TRUE(voice.has_value());
    EXPECT_EQ(voice->notice, kTsukuyomiNotice);
    EXPECT_EQ(voice->noticeFiles,
              (std::vector<std::string>{"tsukuyomi-chan-6lang-fp16.onnx",
                                        "tsukuyomi.onnx"}));

    auto css10 = piper::findVoice("css10");
    ASSERT_TRUE(css10.has_value());
    EXPECT_TRUE(css10->notice.empty());
    EXPECT_TRUE(css10->noticeFiles.empty());
}

TEST(ModelNoticeTest, DetectsTsukuyomiInputs) {
    const std::vector<std::string> inputs = {
        // catalog key, each alias, repo id
        "ja_JP-tsukuyomi-chan-medium",
        "tsukuyomi",
        "tsukuyomi-chan",
        "ja-tsukuyomi",
        "ayousanz/piper-plus-tsukuyomi-chan",
        "  tsukuyomi  ",
        // URLs containing /<repo_id>/
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx",
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json",
        // paths whose file name is a notice file
        "tsukuyomi-chan-6lang-fp16.onnx",
        "tsukuyomi.onnx",
        "/home/user/models/tsukuyomi-chan-6lang-fp16.onnx",
        "./releases/zs-v1/tsukuyomi.onnx",
        "C:\\Users\\user\\AppData\\Roaming\\piper-plus\\models\\tsukuyomi-chan-6lang-fp16.onnx",
        "C:\\models\\zs-v1\\tsukuyomi.onnx",
        "C:/models/tsukuyomi.onnx",
    };
    for (const auto& input : inputs) {
        EXPECT_EQ(piper::getModelNotice(input), kTsukuyomiNotice)
            << "expected a notice for: " << input;
    }
}

TEST(ModelNoticeTest, NoNoticeForOtherInputs) {
    const std::vector<std::string> inputs = {
        "",
        "   ",
        // other catalog models
        "ja_JP-css10-6lang-medium",
        "css10",
        "css10-6lang",
        "ayousanz/piper-plus-css10-ja-6lang",
        "multilingual-zero-shot-base-zs-v1",
        "base",
        "ayousanz/piper-plus-base",
        "https://huggingface.co/ayousanz/piper-plus-base/resolve/main/releases/zs-v1/base.onnx",
        "/models/css10-ja-6lang-fp16.onnx",
        "C:\\models\\base.onnx",
        // near misses
        "Tsukuyomi",
        "tsukuyomi-chan-medium",
        "/models/my-tsukuyomi.onnx",
        "/models/tsukuyomi.onnx.json",
        "/models/config.json",
        // repo without a URL scheme is not a URL
        "/data/ayousanz/piper-plus-tsukuyomi-chan/model.onnx",
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan-v2/resolve/main/model.onnx",
    };
    for (const auto& input : inputs) {
        EXPECT_TRUE(piper::getModelNotice(input).empty())
            << "expected no notice for: '" << input << "'";
    }
}

TEST(ModelNoticeTest, FooterText) {
    EXPECT_STREQ(piper::kModelNoticeFooter,
                 "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / "
                 "Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)");
    EXPECT_STREQ(piper::kModelNoticeDisableEnv,
                 "PIPER_PLUS_DISABLE_MODEL_NOTICE");
}

TEST(ModelNoticeTest, ParseDisabledValues) {
    EXPECT_TRUE(piper::parseModelNoticeDisabled("1"));
    EXPECT_TRUE(piper::parseModelNoticeDisabled("true"));
    EXPECT_TRUE(piper::parseModelNoticeDisabled(" TRUE "));
    EXPECT_TRUE(piper::parseModelNoticeDisabled("yes"));
    EXPECT_TRUE(piper::parseModelNoticeDisabled("Yes\n"));
    EXPECT_FALSE(piper::parseModelNoticeDisabled(nullptr));
    EXPECT_FALSE(piper::parseModelNoticeDisabled(""));
    EXPECT_FALSE(piper::parseModelNoticeDisabled("0"));
    EXPECT_FALSE(piper::parseModelNoticeDisabled("false"));
    EXPECT_FALSE(piper::parseModelNoticeDisabled("no"));
    EXPECT_FALSE(piper::parseModelNoticeDisabled("on"));
    EXPECT_FALSE(piper::parseModelNoticeDisabled("y"));
}

TEST(ModelNoticeTest, DisabledReadsEnvironment) {
    EnvVarGuard guard("PIPER_PLUS_DISABLE_MODEL_NOTICE");

    guard.unset();
    EXPECT_FALSE(piper::modelNoticeDisabled());

    guard.set(" TRUE ");
    EXPECT_TRUE(piper::modelNoticeDisabled());

    guard.set("yes");
    EXPECT_TRUE(piper::modelNoticeDisabled());

    guard.set("1");
    EXPECT_TRUE(piper::modelNoticeDisabled());

    guard.set("0");
    EXPECT_FALSE(piper::modelNoticeDisabled());

    guard.set("");
    EXPECT_FALSE(piper::modelNoticeDisabled());
}

// ============================================
// Main
// ============================================

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

TEST(ModelManager, PublicBasePinnedPair) {
    for (const auto& alias : {"base", "zero-shot-base-zs-v1", "ayousanz/piper-plus-base"}) {
        auto voice = piper::findVoice(alias);
        ASSERT_TRUE(voice.has_value());
        EXPECT_EQ(voice->revision, "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1");
        EXPECT_EQ(voice->quality, "experimental");
        EXPECT_EQ(voice->numSpeakers, 571);
        ASSERT_EQ(voice->files.size(), 2u);
        EXPECT_EQ(voice->files[0].relativePath, "releases/zs-v1/base.onnx");
        EXPECT_EQ(voice->files[1].relativePath, "releases/zs-v1/base.onnx.json");
    }
}
