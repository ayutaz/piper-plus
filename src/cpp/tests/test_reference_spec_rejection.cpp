/**
 * test_reference_spec_rejection.cpp — 参照spec入力付き ONNX の明示拒否
 *
 * 参照条件付き (ref_spec_v1) モデルは `reference_spec` [B, 513, T_ref] float32
 * と `reference_spec_lengths` [B] int64 を必須入力に持つ。C++ runtime は
 * この入力を組み立てないため、loadModel (session 作成直後の入力名検査) で
 * 「参照spectrogram入力が必要で、この runtime は未対応」と model path を含む
 * std::runtime_error を投げる。旧モデルは従来どおり読み込め、合成できる。
 *
 * Fixture: src/cpp/tests/fixtures/reference_spec_inputs/*.onnx + config.json
 * (generate.py の出力を commit 済み。Python runtime の test と共用し、
 * src/python_run/tests/test_reference_schema_rejection.py が生成 script との
 * 一致を検査する)。fixture が見つからない場合は skip ではなく FAIL にする
 * (commit 済みファイルの欠落は回帰であり、黙って緑にしない)。
 */

#include <gtest/gtest.h>

#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "../piper.hpp"

namespace fs = std::filesystem;

namespace {

// ctest の WORKING_DIRECTORY は repo root。build dir から直接実行した場合にも
// 備えて上位を順に探す。
fs::path findFixtureDir() {
    const fs::path rel = fs::path("src") / "cpp" / "tests" / "fixtures" /
                         "reference_spec_inputs";
    fs::path base = fs::current_path();
    for (int depth = 0; depth < 6; ++depth) {
        if (fs::exists(base / rel / "config.json")) {
            return base / rel;
        }
        if (!base.has_parent_path() || base.parent_path() == base) {
            break;
        }
        base = base.parent_path();
    }
    return {};
}

class ReferenceSpecRejectionTest : public ::testing::Test {
protected:
    fs::path fixtureDir;

    void SetUp() override {
        fixtureDir = findFixtureDir();
        ASSERT_FALSE(fixtureDir.empty())
            << "fixture dir src/cpp/tests/fixtures/reference_spec_inputs not "
               "found from " << fs::current_path().string();
    }

    std::string modelPath(const std::string& name) const {
        return (fixtureDir / (name + ".onnx")).string();
    }

    std::string configPath() const {
        return (fixtureDir / "config.json").string();
    }

    // loadVoice を実行し、投げられた std::runtime_error の message を返す。
    // 何も投げなければ std::nullopt。
    std::optional<std::string> loadErrorMessage(const std::string& name) {
        piper::PiperConfig config;
        piper::Voice voice;
        std::optional<piper::SpeakerId> speakerId;
        try {
            piper::loadVoice(config, modelPath(name), configPath(), voice,
                             speakerId, "cpu");
        } catch (const std::runtime_error& e) {
            return std::string(e.what());
        }
        return std::nullopt;
    }
};

}  // namespace

// ----------------------------------------------------------------------------
// 参照spec入力を宣言したモデルの拒否
// ----------------------------------------------------------------------------

TEST_F(ReferenceSpecRejectionTest, RejectsModelDeclaringReferenceSpecInputs) {
    piper::PiperConfig config;
    piper::Voice voice;
    std::optional<piper::SpeakerId> speakerId;
    EXPECT_THROW(piper::loadVoice(config, modelPath("ref_spec"), configPath(),
                                  voice, speakerId, "cpu"),
                 std::runtime_error);
}

TEST_F(ReferenceSpecRejectionTest, MessageSaysReferenceSpectrogramUnsupported) {
    auto message = loadErrorMessage("ref_spec");
    ASSERT_TRUE(message.has_value());
    EXPECT_NE(message->find("reference-spectrogram input"), std::string::npos)
        << *message;
    EXPECT_NE(message->find("does not support"), std::string::npos)
        << *message;
}

TEST_F(ReferenceSpecRejectionTest, MessageNamesTheDeclaredInputs) {
    auto message = loadErrorMessage("ref_spec");
    ASSERT_TRUE(message.has_value());
    EXPECT_NE(message->find("reference_spec,"), std::string::npos) << *message;
    EXPECT_NE(message->find("reference_spec_lengths"), std::string::npos)
        << *message;
}

TEST_F(ReferenceSpecRejectionTest, MessageIncludesModelPath) {
    auto message = loadErrorMessage("ref_spec");
    ASSERT_TRUE(message.has_value());
    EXPECT_NE(message->find(modelPath("ref_spec")), std::string::npos)
        << *message;
}

TEST_F(ReferenceSpecRejectionTest, RejectsReferenceSpecWithoutLengths) {
    auto message = loadErrorMessage("ref_spec_without_lengths");
    ASSERT_TRUE(message.has_value());
    EXPECT_NE(message->find("(reference_spec;"), std::string::npos) << *message;
}

TEST_F(ReferenceSpecRejectionTest, RejectsReferenceSpecLengthsOnly) {
    auto message = loadErrorMessage("ref_spec_lengths_only");
    ASSERT_TRUE(message.has_value());
    EXPECT_NE(message->find("(reference_spec_lengths;"), std::string::npos)
        << *message;
}

// 専用型で投げる: C API は message の文字列 (path を含む) ではなく型で
// PIPER_PLUS_ERR_MODEL に分類する。std::runtime_error 派生なので既存の
// catch (const std::runtime_error&) もそのまま受けられる。
TEST_F(ReferenceSpecRejectionTest, ThrowsUnsupportedModelInputError) {
    piper::PiperConfig config;
    piper::Voice voice;
    std::optional<piper::SpeakerId> speakerId;
    EXPECT_THROW(piper::loadVoice(config, modelPath("ref_spec"), configPath(),
                                  voice, speakerId, "cpu"),
                 piper::UnsupportedModelInputError);
}

// C API の error code 分類 (PIPER_PLUS_ERR_MODEL) は test_c_api.cpp の
// CApiReferenceSpecModel が piper_plus_create を実際に呼んで検査する。

// ----------------------------------------------------------------------------
// 旧モデルは不変
// ----------------------------------------------------------------------------

TEST_F(ReferenceSpecRejectionTest, LegacyFullModelLoads) {
    EXPECT_EQ(loadErrorMessage("legacy_full"), std::nullopt);
}

TEST_F(ReferenceSpecRejectionTest, LegacyFullModelInputDetectionUnchanged) {
    piper::PiperConfig config;
    piper::Voice voice;
    std::optional<piper::SpeakerId> speakerId;
    piper::loadVoice(config, modelPath("legacy_full"), configPath(), voice,
                     speakerId, "cpu");
    // zs-v1 と同じ並び (speaker_embedding / lid / prosody_features、mask なし)。
    EXPECT_TRUE(voice.session.hasSpeakerEmbedding);
    EXPECT_FALSE(voice.session.hasSpeakerEmbeddingInput);
    EXPECT_TRUE(voice.session.hasLidInput);
    EXPECT_TRUE(voice.session.hasProsodyInput);
    EXPECT_FALSE(voice.session.hasMultiSpeaker);
    EXPECT_FALSE(voice.session.hasDurationOutput);
}

TEST_F(ReferenceSpecRejectionTest, LegacyMinimalModelLoads) {
    EXPECT_EQ(loadErrorMessage("legacy_minimal"), std::nullopt);
}

TEST_F(ReferenceSpecRejectionTest, LegacyMinimalModelSynthesizes) {
    piper::PiperConfig config;
    piper::Voice voice;
    std::optional<piper::SpeakerId> speakerId;
    piper::loadVoice(config, modelPath("legacy_minimal"), configPath(), voice,
                     speakerId, "cpu");
    piper::initialize(config);

    // MIN_PHONEME_IDS (15) を超える長さにして padding/trim を避ける。
    std::vector<piper::Phoneme> phonemes;
    for (char32_t cp = U'a'; cp <= U't'; ++cp) {
        phonemes.push_back(cp);
    }
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;
    EXPECT_NO_THROW(
        piper::phonemesToAudio(config, voice, phonemes, audioBuffer, result));
    piper::terminate(config);

    ASSERT_FALSE(audioBuffer.empty());
    bool anyNonZero = false;
    for (auto s : audioBuffer) {
        if (s != 0) {
            anyNonZero = true;
            break;
        }
    }
    EXPECT_TRUE(anyNonZero);
}
