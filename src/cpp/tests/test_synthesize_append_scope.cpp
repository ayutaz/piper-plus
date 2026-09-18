/**
 * test_synthesize_append_scope.cpp — synthesize() must only touch what it appends.
 *
 * `synthesize()` / `synthesizeFloat()` are APPEND APIs: callers accumulate
 * several units (sentences, phrases, inline phoneme segments) into one buffer
 * and the aggregating entry points measure how much each call grew it. Two
 * defects broke that contract:
 *
 * #655 — the padding post-trim slices from `audioBuffer.begin()`, i.e. the
 *   start of the WHOLE accumulated buffer, not of the samples this call added.
 *   With padding applied to a later unit the front cut lands on a PREVIOUS
 *   unit's audio, silently deleting the beginning of the utterance. Measured on
 *   dev: a phrase contributing 3840 samples removed 642 samples (29 ms) from
 *   the head of the buffer. `frontSum` always includes `durations[0]` (BOS), so
 *   this fires for every padded phrase, even with frontPad == 0.
 *
 * #654 — the same branches recompute `result.audioSeconds` from
 *   `audioBuffer.size()`, the whole accumulated buffer. Callers then do
 *   `result.audioSeconds += phraseResults[i].audioSeconds`, so phrase N reports
 *   the length of phrases 1..N and the sum grows quadratically in the phrase
 *   count. Measured on dev: 4.0081 s reported for a 1.5341 s WAV (2.6x).
 *
 * Both are tested through `phonemesToAudio`, which is public, appends, and
 * reaches `synthesize()` in one hop. The buffer is pre-filled with a sentinel
 * so the two questions become directly observable:
 *
 *   - are the caller's existing samples still there?  (#655)
 *   - does audioSeconds describe THIS call's output?   (#654)
 *
 * That makes the test deterministic despite the stochastic decoder: it asserts
 * sample COUNTS and the integrity of a known prefix, never waveform content.
 *
 * One case (GrowthIsIndependentOfPriorBufferContents) additionally compares
 * lengths across TWO separate inferences, which assumes the duration predictor
 * is deterministic run-to-run. That holds for this fixture -- its four
 * RandomNormalLike nodes feed the decoder's z noise, not the DP -- and was
 * checked over six consecutive runs. If a future fixture makes the DP
 * stochastic, that one case becomes flaky while the others stay valid, since
 * only it needs cross-run length equality.
 *
 * Detection power, measured by rebuilding against a reverted piper.cpp:
 * AudioSecondsDescribesOnlyThisCall and PaddedUnitDoesNotTrimTheCallersAudio
 * fail on the int16 path, the two FloatPath cases fail on the float path, and
 * the remaining three are pins that stay green (they are labelled as such).
 *
 * Requires the test model at test/models/multilingual-test-medium.onnx.
 * Auto-skips if it is absent.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

#include "../piper.hpp"

namespace fs = std::filesystem;

namespace {

// A value the decoder cannot plausibly emit at every index, so its survival is
// unambiguous evidence that the prefix was left alone.
constexpr int16_t kSentinel = 12345;
constexpr std::size_t kSentinelCount = 2048;

std::string g_model_path;
std::string g_config_path;
bool g_model_found = false;

} // namespace

class SynthesizeAppendScopeTest : public ::testing::Test {
protected:
    piper::PiperConfig config;
    piper::Voice voice;

    static void SetUpTestSuite() {
        const std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };
        for (const auto &path : searchPaths) {
            if (fs::exists(path)) {
                const std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_model_path = path;
                    g_config_path = configPath;
                    g_model_found = true;
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_model_found) {
            GTEST_SKIP() << "Test model not found; skipping append-scope tests";
        }

        std::optional<piper::SpeakerId> speakerId;
        loadVoice(config, g_model_path, g_config_path, voice, speakerId, "cpu");
        piper::initialize(config);

        if (!voice.modelConfig.languageIdMap ||
            voice.modelConfig.languageIdMap->count("es") == 0) {
            GTEST_SKIP() << "fixture model declares no 'es' language id";
        }
        voice.synthesisConfig.languageId =
            voice.modelConfig.languageIdMap->at("es");
    }

    void TearDown() override {
        if (g_model_found) {
            piper::terminate(config);
        }
    }

    int sampleRate() const { return voice.synthesisConfig.sampleRate; }

    // Phonemize `text` and return its first sentence.
    std::vector<piper::Phoneme> phonemesOf(const std::string &text) {
        piper::PhonemizeResult phonResult;
        piper::phonemizeText(voice, text, phonResult);
        if (phonResult.phonemes.empty()) {
            return {};
        }
        return phonResult.phonemes.front();
    }

    static std::vector<int16_t> sentinelBuffer() {
        return std::vector<int16_t>(kSentinelCount, kSentinel);
    }

    static void expectSentinelIntact(const std::vector<int16_t> &buffer,
                                     const char *what) {
        ASSERT_GE(buffer.size(), kSentinelCount)
            << what << ": the buffer shrank below the caller's prefix, so "
                       "previously accumulated audio was destroyed";
        for (std::size_t i = 0; i < kSentinelCount; ++i) {
            ASSERT_EQ(buffer[i], kSentinel)
                << what << ": sample " << i
                << " of the caller's existing audio was overwritten or shifted "
                   "(issue #655)";
        }
    }
};

TEST_F(SynthesizeAppendScopeTest, FixtureModelIsPresent) {
    EXPECT_TRUE(g_model_found)
        << "test/models/multilingual-test-medium.onnx must be present for "
           "these assertions to mean anything";
}

// #654. No padding needed: the EOS-region trim runs for every durations-capable
// model, and it is the recomputation after it that leaks the whole buffer's
// length into a per-call field.
TEST_F(SynthesizeAppendScopeTest, AudioSecondsDescribesOnlyThisCall) {
    const auto phonemes = phonemesOf("Hola, esta es una prueba de audio.");
    ASSERT_FALSE(phonemes.empty());

    std::vector<int16_t> audio = sentinelBuffer();
    piper::SynthesisResult result;
    piper::phonemesToAudio(config, voice, phonemes, audio, result);

    ASSERT_GT(audio.size(), kSentinelCount)
        << "no samples were appended";
    const std::size_t grown = audio.size() - kSentinelCount;
    const double expectedSeconds =
        static_cast<double>(grown) / static_cast<double>(sampleRate());

    EXPECT_NEAR(result.audioSeconds, expectedSeconds,
                1.0 / static_cast<double>(sampleRate()))
        << "audioSeconds is " << result.audioSeconds << " s but this call "
        << "appended " << grown << " samples (" << expectedSeconds << " s). "
        << "Reporting the whole accumulated buffer makes the caller's "
        << "`result.audioSeconds += phraseResults[i].audioSeconds` grow "
        << "quadratically in the phrase count (issue #654)";
}

// Derived-field consistency pin. NOT a #654 detector: realTimeFactor is
// computed as inferSeconds / audioSeconds right where audioSeconds is assigned,
// so this equality holds for the buggy value too -- verified GREEN against a
// fully reverted piper.cpp. What it pins is that a future change cannot start
// deriving realTimeFactor from a different length than the one it reports.
TEST_F(SynthesizeAppendScopeTest, RealTimeFactorMatchesReportedAudioSeconds) {
    const auto phonemes = phonemesOf("Hola, esta es una prueba de audio.");
    ASSERT_FALSE(phonemes.empty());

    std::vector<int16_t> audio = sentinelBuffer();
    piper::SynthesisResult result;
    piper::phonemesToAudio(config, voice, phonemes, audio, result);

    ASSERT_GT(result.audioSeconds, 0.0);
    EXPECT_NEAR(result.realTimeFactor,
                result.inferSeconds / result.audioSeconds, 1e-9);
}

// #655. A short body (3 <= body < MIN_PHONEME_IDS ids) triggers Strategy A
// padding, whose post-trim is the branch that slices from index 0.
TEST_F(SynthesizeAppendScopeTest, PaddedUnitDoesNotTrimTheCallersAudio) {
    // "Sol" is long enough to clear MIN_BODY_FOR_STRATEGY_A (3 body ids) and
    // short enough to stay under MIN_PHONEME_IDS (15 ids including BOS/EOS and
    // interspersed pads), which is exactly the padded window.
    const auto phonemes = phonemesOf("Sol");
    ASSERT_FALSE(phonemes.empty());

    std::vector<int16_t> audio = sentinelBuffer();
    piper::SynthesisResult result;
    piper::phonemesToAudio(config, voice, phonemes, audio, result);

    expectSentinelIntact(audio, "padded unit");
}

// No-regression pin, green BEFORE and after the fix — verified by running it
// against the unfixed build. It cannot detect #655 and must not be read as if
// it could: the buggy trim replaces the buffer with
// `[front, size - back)`, so the size drops by `front + back` whether the front
// cut lands on the caller's prefix or on this call's own samples. The growth is
// therefore identical in both cases and only the sentinel's CONTENT reveals the
// bug (see PaddedUnitDoesNotTrimTheCallersAudio). What this test does pin is
// that the fix keeps per-call growth independent of prior buffer contents, so a
// future change cannot start scaling the trim with the accumulated length.
TEST_F(SynthesizeAppendScopeTest, GrowthIsIndependentOfPriorBufferContents) {
    const auto phonemes = phonemesOf("Sol");
    ASSERT_FALSE(phonemes.empty());

    std::vector<int16_t> fromEmpty;
    piper::SynthesisResult emptyResult;
    piper::phonemesToAudio(config, voice, phonemes, fromEmpty, emptyResult);
    ASSERT_FALSE(fromEmpty.empty());

    std::vector<int16_t> fromPrefilled = sentinelBuffer();
    piper::SynthesisResult prefilledResult;
    piper::phonemesToAudio(config, voice, phonemes, fromPrefilled,
                           prefilledResult);
    ASSERT_GT(fromPrefilled.size(), kSentinelCount);

    const std::size_t grownFromPrefilled = fromPrefilled.size() - kSentinelCount;
    EXPECT_EQ(grownFromPrefilled, fromEmpty.size())
        << "the same unit appended " << grownFromPrefilled
        << " samples into a pre-filled buffer but " << fromEmpty.size()
        << " into an empty one. The trim is scoped to the whole buffer rather "
           "than to this call's range (issue #655)";
}

// Single-unit output must be bit-identical to the pre-fix behaviour: with an
// empty buffer the base offset is 0, so every computation is unchanged. This is
// the pin that keeps the fix from altering the common path.
TEST_F(SynthesizeAppendScopeTest, EmptyBufferCallIsUnaffected) {
    const auto phonemes = phonemesOf("Sol");
    ASSERT_FALSE(phonemes.empty());

    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    piper::phonemesToAudio(config, voice, phonemes, audio, result);

    ASSERT_FALSE(audio.empty());
    const double expectedSeconds =
        static_cast<double>(audio.size()) / static_cast<double>(sampleRate());
    EXPECT_NEAR(result.audioSeconds, expectedSeconds,
                1.0 / static_cast<double>(sampleRate()));
}

// ---------------------------------------------------------------------------
// Float path. synthesizeFloat / trimPaddingByDurationsFloat / trimSilenceFloat
// / trimEosRegionFloat received the same baseOffset treatment, and the C API
// iterator (synth_next) runs on it, so it needs its own coverage: the int16
// cases above would keep passing if only the float variants regressed.
//
// phonemesToAudioFloat appends "phrase audio + per-phrase silence + trailing
// sentenceSilenceSamples", so sentenceSilenceSeconds is zeroed for these cases.
// Leaving it at its default masked the bug: the trailing silence (0.2 s =
// 4410 samples at 22050 Hz) is larger than the sentinel prefix (2048), so the
// buggy `audioSeconds` -- which counts the sentinel -- still fitted under the
// inflated growth and the assertion passed. Verified by mutation: with the
// default silence the float audioSeconds case does NOT detect a reverted float
// path; with the silence zeroed it does.
// ---------------------------------------------------------------------------

namespace {

constexpr float kSentinelFloat = 0.4242f;

std::vector<float> sentinelBufferFloat() {
    return std::vector<float>(kSentinelCount, kSentinelFloat);
}

} // namespace

TEST_F(SynthesizeAppendScopeTest, FloatPathAudioSecondsDescribesOnlyThisCall) {
    const auto phonemes = phonemesOf("Hola, esta es una prueba de audio.");
    ASSERT_FALSE(phonemes.empty());

    // Remove the trailing silence so the growth equals exactly what
    // synthesizeFloat produced; otherwise the padding hides the defect.
    voice.synthesisConfig.sentenceSilenceSeconds = 0.0f;

    std::vector<float> audio = sentinelBufferFloat();
    piper::SynthesisResult result;
    piper::phonemesToAudioFloat(config, voice, phonemes, nullptr, audio, result);

    ASSERT_GT(audio.size(), kSentinelCount) << "no samples were appended";
    const std::size_t grown = audio.size() - kSentinelCount;
    const double expectedSeconds =
        static_cast<double>(grown) / static_cast<double>(sampleRate());

    EXPECT_NEAR(result.audioSeconds, expectedSeconds,
                1.0 / static_cast<double>(sampleRate()))
        << "audioSeconds is " << result.audioSeconds << " s but this call "
        << "appended " << grown << " samples (" << expectedSeconds << " s); "
        << "the float path is reporting the whole accumulated buffer "
        << "(issue #654)";
}

TEST_F(SynthesizeAppendScopeTest, FloatPathPaddedUnitDoesNotTrimCallersAudio) {
    const auto phonemes = phonemesOf("Sol");
    ASSERT_FALSE(phonemes.empty());

    std::vector<float> audio = sentinelBufferFloat();
    piper::SynthesisResult result;
    piper::phonemesToAudioFloat(config, voice, phonemes, nullptr, audio, result);

    ASSERT_GE(audio.size(), kSentinelCount)
        << "the buffer shrank below the caller's prefix";
    for (std::size_t i = 0; i < kSentinelCount; ++i) {
        ASSERT_FLOAT_EQ(audio[i], kSentinelFloat)
            << "float sample " << i
            << " of the caller's existing audio was overwritten or shifted "
               "(issue #655)";
    }
}
