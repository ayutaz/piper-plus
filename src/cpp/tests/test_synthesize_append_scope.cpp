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
#include <fstream>
#include <iterator>
#include <optional>
#include <string>
#include <vector>

#include "../piper.hpp"

namespace fs = std::filesystem;

namespace {

// The prefix is an index-DEPENDENT pattern, not a constant. A constant prefix
// proves only that no sample was moved across the boundary: an in-place rewrite,
// or a reordering inside the prefix, would leave every value equal to the
// sentinel and pass. Making each sample a function of its index catches those
// too, at no cost.
constexpr std::size_t kSentinelCount = 2048;

int16_t sentinelAt(std::size_t index) {
    return static_cast<int16_t>((index * 37) % 30000 - 15000);
}

float sentinelFloatAt(std::size_t index) {
    return static_cast<float>(sentinelAt(index)) / 32768.0f;
}

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
        std::vector<int16_t> buffer(kSentinelCount);
        for (std::size_t i = 0; i < kSentinelCount; ++i) {
            buffer[i] = sentinelAt(i);
        }
        return buffer;
    }

    static void expectSentinelIntact(const std::vector<int16_t> &buffer,
                                     const char *what) {
        ASSERT_GE(buffer.size(), kSentinelCount)
            << what << ": the buffer shrank below the caller's prefix, so "
                       "previously accumulated audio was destroyed";
        for (std::size_t i = 0; i < kSentinelCount; ++i) {
            ASSERT_EQ(buffer[i], sentinelAt(i))
                << what << ": sample " << i
                << " of the caller's existing audio was overwritten, shifted "
                   "or reordered (issue #655)";
        }
    }

    // Assert that this phoneme sequence really does trigger Strategy A padding,
    // which is the only way to reach the front-trim branch. Without this the
    // padded cases degrade into duplicates of the unpadded ones the moment the
    // fixture's G2P output length changes.
    void expectPaddingWillTrigger(const std::vector<piper::Phoneme> &phonemes) {
        ASSERT_TRUE(voice.phonemizeConfig.interspersePad)
            << "this fixture no longer interleaves pad ids, so the id count is "
               "no longer 2x the phoneme count and the window below is wrong";
        // phonemeIds = one pad after every phoneme (interspersePad), so
        // len == 2 * phonemes. padPhonemeIds pads when
        // MIN_BODY_FOR_STRATEGY_A (3) <= len - 2 and len < MIN_PHONEME_IDS (15).
        const std::size_t ids = phonemes.size() * 2;
        ASSERT_GE(ids, 5u) << "only " << ids << " phoneme ids: body is shorter "
                              "than MIN_BODY_FOR_STRATEGY_A so Strategy A is "
                              "skipped and no front trim happens";
        ASSERT_LT(ids, 15u) << ids << " phoneme ids reaches MIN_PHONEME_IDS, so "
                               "no padding is applied and this case silently "
                               "stops exercising the trim";
    }
};

// ---------------------------------------------------------------------------
// Anti-vacuity gates. These are deliberately OUTSIDE the fixture: the fixture's
// SetUp() calls GTEST_SKIP() when the model is missing, and gtest applies a
// SetUp skip before the test body runs, so a gate declared as TEST_F can never
// fail -- with no model the whole suite reports `[ PASSED ] 0 tests` and exit
// code 0, and ctest calls that a pass. Measured by running the binary from a
// directory where the relative model path does not resolve.
//
// As bare TEST()s they do their own lookup and fail loudly instead.
// ---------------------------------------------------------------------------

namespace {

// Mirrors the fixture's search, without the skip.
std::string findFixtureModel() {
    const std::vector<std::string> searchPaths = {
        "test/models/multilingual-test-medium.onnx",
        "../test/models/multilingual-test-medium.onnx",
        "../../test/models/multilingual-test-medium.onnx",
    };
    for (const auto &path : searchPaths) {
        if (fs::exists(path) && fs::exists(path + ".json")) {
            return path;
        }
    }
    return {};
}

} // namespace

TEST(SynthesizeAppendScopeGate, FixtureModelIsPresent) {
    EXPECT_FALSE(findFixtureModel().empty())
        << "test/models/multilingual-test-medium.onnx (+ .json) must be "
           "present, otherwise every case in this file skips and the suite "
           "reports success while testing nothing";
}

// Without a `durations` output the model never takes the padding or EOS trim
// branches, so `audioSeconds` is only ever assigned by the per-call computation
// that was already correct -- AudioSecondsDescribesOnlyThisCall would then hold
// even on the unfixed code. Byte-scan the fixture rather than trust the config.
TEST(SynthesizeAppendScopeGate, FixtureModelDeclaresDurationsOutput) {
    const std::string model = findFixtureModel();
    if (model.empty()) {
        GTEST_SKIP() << "model absent; FixtureModelIsPresent reports that";
    }

    std::ifstream file(model, std::ios::binary);
    ASSERT_TRUE(file.is_open()) << "cannot open " << model;
    const std::string bytes((std::istreambuf_iterator<char>(file)),
                            std::istreambuf_iterator<char>());
    EXPECT_NE(bytes.find("durations"), std::string::npos)
        << model << " does not declare a 'durations' output, so the trim "
                    "branches this file exercises are unreachable and its "
                    "audioSeconds assertions become tautological";
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
    expectPaddingWillTrigger(phonemes);

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

std::vector<float> sentinelBufferFloat() {
    std::vector<float> buffer(kSentinelCount);
    for (std::size_t i = 0; i < kSentinelCount; ++i) {
        buffer[i] = sentinelFloatAt(i);
    }
    return buffer;
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
    expectPaddingWillTrigger(phonemes);

    std::vector<float> audio = sentinelBufferFloat();
    piper::SynthesisResult result;
    piper::phonemesToAudioFloat(config, voice, phonemes, nullptr, audio, result);

    ASSERT_GE(audio.size(), kSentinelCount)
        << "the buffer shrank below the caller's prefix";
    for (std::size_t i = 0; i < kSentinelCount; ++i) {
        ASSERT_FLOAT_EQ(audio[i], sentinelFloatAt(i))
            << "float sample " << i
            << " of the caller's existing audio was overwritten, shifted or "
               "reordered (issue #655)";
    }
}
