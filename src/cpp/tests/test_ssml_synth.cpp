/**
 * test_ssml_synth.cpp — SSML segment synthesis produces audio (model required).
 *
 * Issue #659: `synthesizeSsmlToBuffer` passed a do-nothing lambda as
 * `textToAudio`'s audioCallback. `textToAudio` clears the output buffer after
 * every sentence when a callback is installed, on the contract that the
 * callback has already copied the samples out; a `[](){}` satisfies the
 * `if (audioCallback)` test without copying anything, so the per-segment
 * buffer came back empty and every SSML CLI invocation wrote a WAV holding
 * only the `<break>` silence. Measured on dev before the fix:
 * `<speak>Hola mundo</speak>` -> 0 frames, and
 * `<speak>Hola<break time="200ms"/>mundo</speak>` -> 4410 frames, i.e. exactly
 * the 200 ms break and no speech at all.
 *
 * `src/cpp/tests/test_ssml.cpp` could not catch this: it covers the parser
 * only, and the parser was correct throughout. These tests drive the
 * synthesis loop itself, which is why it now lives in its own translation
 * unit (`src/cpp/ssml_synth.cpp`) instead of being a `static` function inside
 * main.cpp that no test can reach.
 *
 * Assertions are on SAMPLE COUNTS and on the presence of non-zero samples,
 * never on waveform content: the decoder is stochastic, so two runs of the
 * same text agree on length but not on samples.
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
#include "../ssml_synth.hpp"

namespace fs = std::filesystem;

static std::string g_ssml_model_path;
static std::string g_ssml_config_path;
static bool g_ssml_model_found = false;

namespace {

// Does the buffer hold anything other than silence? A fix that restored the
// sample COUNT but appended zeros would still be broken, so every
// audio-producing assertion checks this rather than just `!empty()`.
bool hasNonZeroSample(const std::vector<int16_t> &audio) {
    return std::any_of(audio.begin(), audio.end(),
                       [](int16_t s) { return s != 0; });
}

} // namespace

class SsmlSynthTest : public ::testing::Test {
protected:
    piper::PiperConfig config;
    piper::Voice voice;

    static void SetUpTestSuite() {
        std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };
        for (const auto &path : searchPaths) {
            if (fs::exists(path)) {
                std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_ssml_model_path = path;
                    g_ssml_config_path = configPath;
                    g_ssml_model_found = true;
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_ssml_model_found) {
            GTEST_SKIP() << "Test model not found; skipping SSML synthesis test";
        }

        std::optional<piper::SpeakerId> speakerId;
        loadVoice(config, g_ssml_model_path, g_ssml_config_path, voice,
                  speakerId, "cpu");
        piper::initialize(config);

        // Pin the Latin-script G2P the way the CLI's `--language es` does, so
        // the fixture text does not route through the English CMU path.
        if (!voice.modelConfig.languageIdMap ||
            voice.modelConfig.languageIdMap->count("es") == 0) {
            GTEST_SKIP() << "fixture model declares no 'es' language id; "
                            "skipping the Spanish-text SSML assertions";
        }
        voice.synthesisConfig.languageId =
            voice.modelConfig.languageIdMap->at("es");
    }

    void TearDown() override {
        if (g_ssml_model_found) {
            piper::terminate(config);
        }
    }

    int sampleRate() const { return voice.synthesisConfig.sampleRate; }

    // Run one SSML document through the production synthesis loop.
    std::size_t synthesizeSsml(const std::string &ssml,
                               std::vector<int16_t> &audio,
                               piper::SynthesisResult &result) {
        audio.clear();
        piper::synthesizeSsmlToBuffer(ssml, config, voice, result, audio);
        return audio.size();
    }
};

// The fixture is only meaningful while it can actually synthesize. Without
// this the whole suite could degrade to a silent pass if the model went
// missing — the same "the gate goes green when its subject disappears" shape
// that let #659 ship behind a parser-only test suite.
TEST_F(SsmlSynthTest, FixtureModelIsPresent) {
    EXPECT_TRUE(g_ssml_model_found)
        << "test/models/multilingual-test-medium.onnx must be present for the "
           "SSML synthesis assertions to mean anything";
}

// The #659 reproducer. RED on dev: audio.size() == 0.
TEST_F(SsmlSynthTest, SpeakOnlyDocumentProducesAudio) {
    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    const std::size_t samples =
        synthesizeSsml("<speak>Hola mundo</speak>", audio, result);

    ASSERT_GT(samples, 0u) << "SSML synthesis emitted no samples at all";
    EXPECT_TRUE(hasNonZeroSample(audio))
        << "SSML synthesis emitted " << samples << " samples of pure silence";
}

// A single-segment SSML document must carry the same audio as the same text
// submitted directly, since it runs the identical textToAudio call. RED on
// dev: the SSML side is 0 while the direct call is not.
TEST_F(SsmlSynthTest, SingleSegmentMatchesDirectTextToAudio) {
    std::vector<int16_t> ssmlAudio;
    piper::SynthesisResult ssmlResult;
    synthesizeSsml("<speak>Hola mundo</speak>", ssmlAudio, ssmlResult);

    std::vector<int16_t> directAudio;
    piper::SynthesisResult directResult;
    piper::textToAudio(config, voice, "Hola mundo", directAudio, directResult,
                       nullptr, nullptr);

    ASSERT_FALSE(directAudio.empty()) << "direct textToAudio produced nothing; "
                                        "the fixture itself is broken";
    EXPECT_EQ(ssmlAudio.size(), directAudio.size())
        << "SSML segment audio length diverged from the direct call";
}

// A <break> on a segment must add exactly its silence and nothing else. Both
// documents hold ONE segment with the same text, so the only difference is
// the break: no extra sentence boundary is introduced, which keeps this an
// exact assertion.
TEST_F(SsmlSynthTest, BreakAddsExactlyItsSilence) {
    std::vector<int16_t> withoutBreak;
    piper::SynthesisResult r1;
    synthesizeSsml("<speak>Hola</speak>", withoutBreak, r1);

    std::vector<int16_t> withBreak;
    piper::SynthesisResult r2;
    synthesizeSsml("<speak>Hola<break time=\"200ms\"/></speak>", withBreak, r2);

    ASSERT_GT(withoutBreak.size(), 0u);
    const std::size_t expectedSilence =
        static_cast<std::size_t>(0.2 * static_cast<double>(sampleRate()));
    ASSERT_GE(withBreak.size(), withoutBreak.size());
    EXPECT_EQ(withBreak.size() - withoutBreak.size(), expectedSilence);

    // The added tail must be the silence itself.
    for (std::size_t i = withoutBreak.size(); i < withBreak.size(); ++i) {
        ASSERT_EQ(withBreak[i], 0) << "break silence sample " << i
                                   << " is not zero";
    }
}

// Two text segments separated by a break must both be present. RED on dev:
// the result was 4410 samples = the break alone.
TEST_F(SsmlSynthTest, BothSidesOfABreakAreSynthesized) {
    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    const std::size_t samples = synthesizeSsml(
        "<speak>Hola<break time=\"200ms\"/>mundo</speak>", audio, result);

    const std::size_t breakSamples =
        static_cast<std::size_t>(0.2 * static_cast<double>(sampleRate()));
    ASSERT_GT(samples, breakSamples)
        << "output is not longer than the break silence, so at least one "
           "segment emitted nothing";
    EXPECT_TRUE(hasNonZeroSample(audio));

    // Speech must exist on BOTH sides of the silence run, not just one.
    const auto firstVoiced =
        std::find_if(audio.begin(), audio.end(),
                     [](int16_t s) { return s != 0; });
    const auto lastVoiced =
        std::find_if(audio.rbegin(), audio.rend(),
                     [](int16_t s) { return s != 0; });
    ASSERT_NE(firstVoiced, audio.end());
    const std::size_t firstIdx =
        static_cast<std::size_t>(std::distance(audio.begin(), firstVoiced));
    const std::size_t lastIdx =
        samples - 1 -
        static_cast<std::size_t>(std::distance(audio.rbegin(), lastVoiced));
    EXPECT_GT(lastIdx, firstIdx + breakSamples)
        << "voiced samples do not span a gap at least as wide as the break, "
           "so the two segments were not both synthesized";
}

// The reported audioSeconds must describe what the caller actually received.
// Before the fix it was accumulated from segResult.audioSeconds while the
// buffer stayed empty, so the CLI logged `audio=0.476 sec` for a 0-frame WAV.
TEST_F(SsmlSynthTest, ReportedAudioSecondsMatchesEmittedSamples) {
    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    const std::size_t samples = synthesizeSsml(
        "<speak>Hola<break time=\"200ms\"/>mundo</speak>", audio, result);

    ASSERT_GT(samples, 0u);
    const double emittedSeconds =
        static_cast<double>(samples) / static_cast<double>(sampleRate());
    EXPECT_NEAR(result.audioSeconds, emittedSeconds,
                1.0 / static_cast<double>(sampleRate()));
}

// lengthScale must be restored even though each segment multiplies it by its
// <prosody rate>, otherwise the rate of one document leaks into the next.
TEST_F(SsmlSynthTest, LengthScaleIsRestoredAfterSynthesis) {
    const float before = voice.synthesisConfig.lengthScale;

    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    synthesizeSsml("<speak><prosody rate=\"1.5\">Hola</prosody></speak>", audio,
                   result);

    EXPECT_FLOAT_EQ(voice.synthesisConfig.lengthScale, before);
}
