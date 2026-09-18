/**
 * test_phoneme_timing_text_path.cpp — phoneme timing propagation through the
 * aggregating text -> audio entry points (model required).
 *
 * Issue #652: `textToAudio` / `textToAudioFloat` accumulated only
 * `audioSeconds` / `inferSeconds` from their per-phrase results and never
 * forwarded `phraseResults[i].phonemeTimings` / `.hasTimingInfo`;
 * `phonemesToAudioFloat` forwarded only phrase 0; both streaming paths
 * discarded their per-unit results entirely. `hasTimingInfo` therefore stayed
 * false, so the CLI's `--output-timing` gate (main.cpp) wrote no file even
 * though the debug log reported `Extracted timing for N phonemes`, and the C
 * API's `piper_plus_get_phoneme_timing` returned an error.
 *
 * These tests pin the propagation AND the offset rule: a timing value is a
 * position in the WAV the caller receives, so each unit is shifted by the
 * interleaved PCM samples already emitted (unit audio + inter-phrase silence
 * + inter-sentence silence). The int16 `textToAudio` path is reachable only
 * from the CLI and `textToWavFile`, and the `phonemeSilenceSeconds` phrase
 * tier is unreachable from the C API, so both need a target that links
 * piper.cpp.
 *
 * The exact-offset checks are written once (`expectMultiUnitOffsetsExact`,
 * `expectPhraseSilenceOffsetsExact`) and run against EVERY aggregating entry
 * point via the `Aggregator` adapters, not just the int16 generator. Covering
 * only `textToAudio` left the two paths that production actually uses
 * unguarded: `textToAudioFloat` is what the C API and every FFI binding call,
 * and `phonemesToAudioFloat` is the Iterator body (`piper_plus_synth_next`).
 * Deleting the `emittedSamples` advance from either of them, or forwarding
 * only phrase 0 again, kept an int16-only suite green while every C API
 * caller received offsets that were 0.2 s per sentence short.
 *
 * Every timing-vs-audio bound here is ONE-SIDED (`end_time <= audio_length +
 * tol`): the ONNX `durations` tensor is exported pre-`ceil` (issue #653), so
 * the timing total runs short of the real audio by a model-dependent amount.
 * Every exact assertion is on an inter-unit DELTA, which is independent of
 * both #653 and the `audioSeconds` re-assignment of #654.
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
#include <functional>
#include <locale>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#include "../piper.hpp"

namespace fs = std::filesystem;

// Shared model state across all TimingTextPathTest instances
static std::string g_timing_model_path;
static std::string g_timing_config_path;
static bool g_timing_model_found = false;

namespace {

// Mirrors the hop-size resolution the aggregators use (configRoot
// ["audio"]["hop_size"], else the VITS default 256).
int hopSizeOf(const piper::Voice &voice) {
    if (voice.configRoot.contains("audio") &&
        voice.configRoot["audio"].contains("hop_size")) {
        return voice.configRoot["audio"]["hop_size"].get<int>();
    }
    return 256;
}

// Does the ONNX file declare a graph output named "durations"?
//
// Byte scan of the serialised protobuf, mirroring
// test_c_api_integration.cpp::modelDeclaresDurations so both suites gate on
// the same fact in the same way. Deliberately independent of the loaded
// session: it answers "is the fixture still a timing-capable export?" even if
// the runtime probe in loadVoice were to change.
bool modelDeclaresDurations(const std::string &path) {
    if (path.empty()) {
        return false;
    }
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return false;
    }

    const std::string needle = "durations";
    // Keep the trailing needle.size()-1 bytes of each block so a needle that
    // straddles a block boundary is still found.
    const std::size_t overlap = needle.size() - 1;
    std::vector<char> block(64 * 1024);
    std::string window;
    while (in.read(block.data(), static_cast<std::streamsize>(block.size())) ||
           in.gcount() > 0) {
        window.append(block.data(), static_cast<std::size_t>(in.gcount()));
        if (window.find(needle) != std::string::npos) {
            return true;
        }
        if (window.size() > overlap) {
            window.erase(0, window.size() - overlap);
        }
    }
    return false;
}

// Non-decreasing start_time and end_time >= start_time. Deliberately NOT
// contiguity: extractTimingsFromDurations drops the PAD/BOS/EOS ids from the
// entry list while still advancing its cursor, so intra-unit gaps are
// legitimate.
void expectMonotonic(const std::vector<piper::PhonemeInfo> &timings) {
    for (std::size_t i = 0; i < timings.size(); ++i) {
        EXPECT_GE(timings[i].end_time, timings[i].start_time) << "entry " << i;
        if (i > 0) {
            EXPECT_GE(timings[i].start_time, timings[i - 1].start_time)
                << "start_time regressed at entry " << i;
        }
    }
}

// One-sided: see the #653 note in the file header.
void expectWithinAudio(const std::vector<piper::PhonemeInfo> &timings,
                       std::size_t audioSamples, int sampleRate, int channels) {
    ASSERT_FALSE(timings.empty());
    const double audioSeconds =
        static_cast<double>(audioSamples) /
        (static_cast<double>(sampleRate) * static_cast<double>(channels));
    EXPECT_LE(static_cast<double>(timings.back().end_time), audioSeconds + 1e-3);
}

// One aggregating entry point under test, normalised to "text in ->
// interleaved PCM sample count + aggregated result out". `samples` is the
// number of interleaved samples the call emitted into the caller's buffer,
// which is the base the offset rule is defined against.
struct Aggregator {
    std::string name;
    std::function<void(const std::string &text, std::size_t &samples,
                       piper::SynthesisResult &result)>
        run;
};

} // namespace

class TimingTextPathTest : public ::testing::Test {
protected:
    piper::PiperConfig config;
    piper::Voice voice;

    static void SetUpTestSuite() {
        std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };
        for (const auto& path : searchPaths) {
            if (fs::exists(path)) {
                std::string configPath = path + ".json";
                if (fs::exists(configPath)) {
                    g_timing_model_path = path;
                    g_timing_config_path = configPath;
                    g_timing_model_found = true;
                }
                break;
            }
        }
    }

    void SetUp() override {
        if (!g_timing_model_found) {
            GTEST_SKIP() << "Test model not found; skipping phoneme timing text-path test";
        }

        std::optional<piper::SpeakerId> speakerId;
        loadVoice(config, g_timing_model_path, g_timing_config_path,
                  voice, speakerId, "cpu");
        piper::initialize(config);

        // Pin the Latin-script G2P the way the CLI's `--language es` does.
        // phonemizeText() derives its default Latin language from
        // synthesisConfig.languageId, so leaving it unset routes the Spanish
        // fixture text through the English CMU path and changes every phoneme
        // count these tests pin.
        if (!voice.modelConfig.languageIdMap ||
            voice.modelConfig.languageIdMap->count("es") == 0) {
            GTEST_SKIP() << "fixture model declares no 'es' language id; "
                            "skipping the Spanish-text timing assertions";
        }
        voice.synthesisConfig.languageId =
            voice.modelConfig.languageIdMap->at("es");
    }

    void TearDown() override {
        if (g_timing_model_found) {
            piper::terminate(config);
        }
    }

    int sampleRate() const { return voice.synthesisConfig.sampleRate; }
    int channels() const { return std::max(1, voice.synthesisConfig.channels); }
    int hopSize() const { return hopSizeOf(voice); }
    double oneSample() const {
        return 1.0 / (static_cast<double>(sampleRate()) * channels());
    }

    // ---- Aggregators under test -------------------------------------------

    // int16 generator. Reachable from the CLI and textToWavFile only.
    Aggregator int16TextAggregator() {
        Aggregator agg;
        agg.name = "piper::textToAudio";
        agg.run = [this](const std::string &text, std::size_t &samples,
                         piper::SynthesisResult &result) {
            std::vector<int16_t> audio;
            piper::textToAudio(config, voice, text, audio, result, nullptr);
            samples = audio.size();
        };
        return agg;
    }

    // float generator. This is the one the C API (piper_plus_synthesize,
    // piper_plus_synthesize_streaming) and every FFI binding call.
    Aggregator floatTextAggregator() {
        Aggregator agg;
        agg.name = "piper::textToAudioFloat";
        agg.run = [this](const std::string &text, std::size_t &samples,
                         piper::SynthesisResult &result) {
            std::vector<float> audio;
            piper::textToAudioFloat(config, voice, text, audio, result,
                                    nullptr);
            samples = audio.size();
        };
        return agg;
    }

    // Pre-phonemized float generator. This is the Iterator body: the only
    // production caller is piper_plus_synth_next, which feeds it the phonemes
    // synth_start pre-computed. Its multi-unit tier is the
    // phonemeSilenceSeconds phrase split, so only the phrase-silence check
    // applies to it.
    Aggregator floatPhonemeAggregator() {
        Aggregator agg;
        agg.name = "piper::phonemesToAudioFloat";
        agg.run = [this](const std::string &text, std::size_t &samples,
                         piper::SynthesisResult &result) {
            piper::PhonemizeResult phonResult;
            piper::phonemizeText(voice, text, phonResult);
            ASSERT_FALSE(phonResult.phonemes.empty()) << text;
            std::vector<float> audio;
            piper::phonemesToAudioFloat(config, voice,
                                        phonResult.phonemes.front(), nullptr,
                                        audio, result);
            samples = audio.size();
        };
        return agg;
    }

    // ---- Shared exact-offset checks ---------------------------------------

    // The offset rule across SENTENCE units. Inline `[[ ]]` notation is the
    // only way to force three synthesize() units out of one call: plain
    // multi-sentence text is flattened into a single unit by the multilingual
    // phonemizer. The units land in the per-sentence loop, so the gap between
    // them is the inter-sentence silence -- which is what pins the
    // `emittedSamples += sentenceSilenceSamples` step. Deleting that step
    // shifts every unit after the first by -0.2 s.
    void expectMultiUnitOffsetsExact(const Aggregator &agg) {
        SCOPED_TRACE(agg.name);
        const std::string combinedText = "Hola. [[ m u n d o ]] Adios.";

        std::size_t combinedSamples = 0;
        piper::SynthesisResult combined;
        ASSERT_NO_FATAL_FAILURE(
            agg.run(combinedText, combinedSamples, combined));

        ASSERT_TRUE(combined.hasTimingInfo);
        // Pinned measurement: 5 + 5 + 7 entries across the three units.
        ASSERT_EQ(combined.phonemeTimings.size(), 17u);
        expectMonotonic(combined.phonemeTimings);

        // Re-synthesize each unit alone with the trailing sentence silence
        // turned off, so each run's emitted sample count is exactly that
        // unit's length. Durations are deterministic for a given id sequence,
        // so the isolated entries are the combined run's entries minus the
        // offset.
        const float sentenceSilenceSeconds =
            voice.synthesisConfig.sentenceSilenceSeconds;
        voice.synthesisConfig.sentenceSilenceSeconds = 0.0f;

        const std::vector<std::string> segments = {"Hola.", "[[ m u n d o ]]",
                                                   "Adios."};
        std::vector<std::size_t> unitSamples;
        std::vector<std::vector<piper::PhonemeInfo>> unitTimings;
        for (const auto &segment : segments) {
            SCOPED_TRACE(segment);
            std::size_t segmentSamples = 0;
            piper::SynthesisResult segmentResult;
            ASSERT_NO_FATAL_FAILURE(
                agg.run(segment, segmentSamples, segmentResult));
            ASSERT_TRUE(segmentResult.hasTimingInfo);
            ASSERT_FALSE(segmentResult.phonemeTimings.empty());
            unitSamples.push_back(segmentSamples);
            unitTimings.push_back(segmentResult.phonemeTimings);
        }

        voice.synthesisConfig.sentenceSilenceSeconds = sentenceSilenceSeconds;

        // Pinned per-unit entry counts.
        ASSERT_EQ(unitTimings.size(), 3u);
        EXPECT_EQ(unitTimings[0].size(), 5u);
        EXPECT_EQ(unitTimings[1].size(), 5u);
        EXPECT_EQ(unitTimings[2].size(), 7u);
        ASSERT_GT(combined.phonemeTimings.size(), unitTimings[0].size())
            << "the 3-unit run must carry strictly more entries than one unit";

        // Same expression the aggregator uses (piper.cpp), so the sample count
        // matches bit-for-bit.
        const std::size_t sentenceSilenceSamples = static_cast<std::size_t>(
            sentenceSilenceSeconds * sampleRate() * channels());
        ASSERT_GT(sentenceSilenceSamples, 0u)
            << "this test needs a non-zero inter-sentence silence";

        std::size_t entryIdx = 0;
        std::size_t offsetSamples = 0;
        for (std::size_t unit = 0; unit < unitTimings.size(); ++unit) {
            const std::string where = "unit " + std::to_string(unit);
            ASSERT_LE(entryIdx + unitTimings[unit].size(),
                      combined.phonemeTimings.size())
                << where;

            const double offsetSeconds =
                static_cast<double>(offsetSamples) /
                (static_cast<double>(sampleRate()) * channels());
            const int offsetFrames = static_cast<int>(
                offsetSamples /
                (static_cast<std::size_t>(hopSize()) * channels()));

            for (std::size_t i = 0; i < unitTimings[unit].size(); ++i) {
                const piper::PhonemeInfo &expected = unitTimings[unit][i];
                const piper::PhonemeInfo &actual =
                    combined.phonemeTimings[entryIdx + i];
                const std::string at = where + " entry " + std::to_string(i);

                EXPECT_EQ(actual.phoneme, expected.phoneme) << at;
                // Exact inter-unit delta, tolerance one sample. Forwarding
                // only unit 0 never reaches this loop; concatenating with no
                // offset, using the per-unit audioSeconds (#654), dropping the
                // inter-sentence silence from the cursor or a raw duration sum
                // (#653) are all off by 72-200 ms here.
                EXPECT_NEAR(static_cast<double>(actual.start_time),
                            static_cast<double>(expected.start_time) +
                                offsetSeconds,
                            oneSample())
                    << at;
                EXPECT_NEAR(static_cast<double>(actual.end_time),
                            static_cast<double>(expected.end_time) +
                                offsetSeconds,
                            oneSample())
                    << at;
                EXPECT_EQ(actual.start_frame,
                          expected.start_frame + offsetFrames)
                    << at;
                EXPECT_EQ(actual.end_frame, expected.end_frame + offsetFrames)
                    << at;
            }

            entryIdx += unitTimings[unit].size();
            offsetSamples += unitSamples[unit] + sentenceSilenceSamples;
        }

        EXPECT_EQ(entryIdx, combined.phonemeTimings.size())
            << "every combined entry must belong to one of the three units";
        // Sum(unit audio) + Sum(sentence silence) reconstructs the emitted
        // stream to the sample; this is what makes the offsets positions in
        // the caller's WAV rather than approximations.
        EXPECT_EQ(combinedSamples, offsetSamples);
    }

    // The offset rule across PHRASE units inside one sentence.
    // `phonemeSilenceSeconds` splits one sentence into several synthesize()
    // units, which the partial forward this fix replaces dropped silently.
    // Unreachable from the C API, and the only tier `phonemesToAudioFloat`
    // has. Re-running with a larger silence isolates the cursor advance: with
    // it, phrase 2 moves by exactly the extra silence; without it, phrase 2
    // sits at offset 0 in both runs.
    void expectPhraseSilenceOffsetsExact(const Aggregator &agg) {
        SCOPED_TRACE(agg.name);
        const piper::Phoneme splitPhoneme = U'l';
        if (voice.phonemizeConfig.phonemeIdMap.count(splitPhoneme) == 0) {
            GTEST_SKIP() << "phoneme 'l' is absent from this model's "
                            "phoneme_id_map, so the phrase split cannot happen";
        }

        const std::string text = "Hola mundo.";

        auto runWithPhraseSilence = [&](float seconds, std::size_t &samples,
                                        piper::SynthesisResult &result) {
            voice.synthesisConfig.phonemeSilenceSeconds =
                std::map<piper::Phoneme, float>{{splitPhoneme, seconds}};
            agg.run(text, samples, result);
            voice.synthesisConfig.phonemeSilenceSeconds.reset();
        };

        std::size_t samplesA = 0;
        std::size_t samplesB = 0;
        piper::SynthesisResult resultA;
        piper::SynthesisResult resultB;
        ASSERT_NO_FATAL_FAILURE(runWithPhraseSilence(0.3f, samplesA, resultA));
        ASSERT_NO_FATAL_FAILURE(runWithPhraseSilence(0.6f, samplesB, resultB));

        ASSERT_TRUE(resultA.hasTimingInfo);
        ASSERT_TRUE(resultB.hasTimingInfo);
        ASSERT_FALSE(resultA.phonemeTimings.empty());
        ASSERT_EQ(resultA.phonemeTimings.size(), resultB.phonemeTimings.size());
        // Pinned measurement: 3 + 9 phonemes across the two phrases.
        EXPECT_EQ(resultA.phonemeTimings.size(), 12u);
        expectMonotonic(resultA.phonemeTimings);
        expectMonotonic(resultB.phonemeTimings);

        // Same expressions the phrase loop uses.
        const std::size_t silenceA =
            static_cast<std::size_t>(0.3f * sampleRate() * channels());
        const std::size_t silenceB =
            static_cast<std::size_t>(0.6f * sampleRate() * channels());
        ASSERT_GT(silenceB, silenceA);
        EXPECT_EQ(samplesB - samplesA, silenceB - silenceA)
            << "the phrase silence must be the only audio difference";

        // The phrase boundary is the first entry whose start_time moved;
        // phrase 1 carries offset 0 in both runs, so it must be bit-identical.
        std::size_t boundary = resultA.phonemeTimings.size();
        for (std::size_t i = 0; i < resultA.phonemeTimings.size(); ++i) {
            if (resultA.phonemeTimings[i].start_time !=
                resultB.phonemeTimings[i].start_time) {
                boundary = i;
                break;
            }
        }
        ASSERT_GT(boundary, 0u) << "phrase 1 must keep offset 0 in both runs";
        ASSERT_LT(boundary, resultA.phonemeTimings.size())
            << "no phrase split happened, or the phrase cursor never advances; "
               "the phrase tier is untested";
        EXPECT_EQ(boundary, 3u);  // Pinned: the split lands after 3 phonemes.

        for (std::size_t i = 0; i < boundary; ++i) {
            const std::string at = "phrase 1 entry " + std::to_string(i);
            EXPECT_EQ(resultB.phonemeTimings[i].start_time,
                      resultA.phonemeTimings[i].start_time)
                << at;
            EXPECT_EQ(resultB.phonemeTimings[i].end_time,
                      resultA.phonemeTimings[i].end_time)
                << at;
            EXPECT_EQ(resultB.phonemeTimings[i].start_frame,
                      resultA.phonemeTimings[i].start_frame)
                << at;
            EXPECT_EQ(resultB.phonemeTimings[i].end_frame,
                      resultA.phonemeTimings[i].end_frame)
                << at;
        }

        const double expectedShift =
            static_cast<double>(silenceB - silenceA) /
            (static_cast<double>(sampleRate()) * channels());
        const int expectedFrameShift =
            static_cast<int>(silenceB /
                             (static_cast<std::size_t>(hopSize()) * channels())) -
            static_cast<int>(silenceA /
                             (static_cast<std::size_t>(hopSize()) * channels()));
        for (std::size_t i = boundary; i < resultA.phonemeTimings.size(); ++i) {
            const std::string at = "phrase 2 entry " + std::to_string(i);
            EXPECT_NEAR(
                static_cast<double>(resultB.phonemeTimings[i].start_time) -
                    static_cast<double>(resultA.phonemeTimings[i].start_time),
                expectedShift, oneSample())
                << at;
            EXPECT_NEAR(
                static_cast<double>(resultB.phonemeTimings[i].end_time) -
                    static_cast<double>(resultA.phonemeTimings[i].end_time),
                expectedShift, oneSample())
                << at;
            EXPECT_EQ(resultB.phonemeTimings[i].start_frame -
                          resultA.phonemeTimings[i].start_frame,
                      expectedFrameShift)
                << at;
        }
    }
};

// Anti-vacuity gate. GREEN both before and after the #652 fix -- it is not a
// reproducer. Every exact assertion in this file is only meaningful while the
// fixture actually emits a `durations` tensor: swap in a durations-less export
// and `hasTimingInfo` stays false everywhere, which is exactly the state #652
// shipped in. Without this gate the whole suite would degrade to "the model
// does not support timing" and report PASSED. Mirrors
// test_c_api_integration.cpp::FixtureModelDeclaresDurationsOutput.
// The static half of the gate lives OUTSIDE the fixture on purpose. The
// fixture's SetUp() calls GTEST_SKIP() when the model is missing, and gtest
// applies a SetUp skip before the test body, so a gate written as TEST_F can
// never fail: with no model the suite reports `[ PASSED ] 0 tests` and exit
// code 0, which ctest calls a pass. Measured by running the binary from a
// directory where the relative model path does not resolve.
TEST(TimingTextPathGate, FixtureModelDeclaresDurationsOutput) {
    std::string model;
    for (const auto &path : {"test/models/multilingual-test-medium.onnx",
                             "../test/models/multilingual-test-medium.onnx",
                             "../../test/models/multilingual-test-medium.onnx"}) {
        if (fs::exists(path)) {
            model = path;
            break;
        }
    }
    ASSERT_FALSE(model.empty())
        << "test/models/multilingual-test-medium.onnx is missing, so every "
           "timing case in this file skips and the suite reports success";
    EXPECT_TRUE(modelDeclaresDurations(model.c_str()))
        << model
        << " declares no 'durations' graph output; every timing assertion in "
           "this file would pass vacuously";
}

// The runtime half needs a loaded voice, so it stays in the fixture: a model
// that declares the output but whose session does not expose it is just as
// vacuous. This one legitimately skips without a model -- the gate above is
// what reports that.
TEST_F(TimingTextPathTest, LoadedSessionExposesDurationOutput) {
    EXPECT_TRUE(voice.session.hasDurationOutput)
        << "the loaded session exposes no duration output";
}

// `hasTimingInfo` is literally the flag the CLI tests before writing
// --output-timing, so assert it on both generators.
TEST_F(TimingTextPathTest, TextPathPropagatesTiming) {
    const std::string text = "Hola mundo.";

    std::vector<int16_t> audioI16;
    piper::SynthesisResult resultA;
    piper::textToAudio(config, voice, text, audioI16, resultA, nullptr);

    ASSERT_TRUE(resultA.hasTimingInfo) << "textToAudio dropped its phrase timings";
    ASSERT_FALSE(resultA.phonemeTimings.empty());
    expectMonotonic(resultA.phonemeTimings);
    expectWithinAudio(resultA.phonemeTimings, audioI16.size(), sampleRate(),
                      channels());

    std::vector<float> audioF32;
    piper::SynthesisResult resultB;
    piper::textToAudioFloat(config, voice, text, audioF32, resultB, nullptr);

    ASSERT_TRUE(resultB.hasTimingInfo) << "textToAudioFloat dropped its phrase timings";
    ASSERT_FALSE(resultB.phonemeTimings.empty());
    expectMonotonic(resultB.phonemeTimings);
    expectWithinAudio(resultB.phonemeTimings, audioF32.size(), sampleRate(),
                      channels());

    EXPECT_EQ(resultB.phonemeTimings.size(), resultA.phonemeTimings.size())
        << "the int16 and float generators must report the same entries";
}

// The sentence-unit offset rule, once per generator. `textToAudio` is the CLI
// path; `textToAudioFloat` is the one the C API and every FFI binding use, and
// it was unguarded until this pair existed.
TEST_F(TimingTextPathTest, MultiUnitOffsetsMatchEmittedSampleCounts) {
    ASSERT_NO_FATAL_FAILURE(
        expectMultiUnitOffsetsExact(int16TextAggregator()));
}

TEST_F(TimingTextPathTest, MultiUnitOffsetsMatchEmittedSampleCountsFloat) {
    ASSERT_NO_FATAL_FAILURE(
        expectMultiUnitOffsetsExact(floatTextAggregator()));
}

// Intra-sentence phrase tier, once per aggregator that has one. The
// phonemesToAudioFloat variant is the only exact coverage the Iterator body
// gets: its cursor advance is unreachable from the C API because
// phonemeSilenceSeconds is not exposed there.
TEST_F(TimingTextPathTest, PhraseSilenceSplitOffsetsAreExact) {
    ASSERT_NO_FATAL_FAILURE(
        expectPhraseSilenceOffsetsExact(int16TextAggregator()));
}

TEST_F(TimingTextPathTest, PhraseSilenceSplitOffsetsAreExactFloat) {
    ASSERT_NO_FATAL_FAILURE(
        expectPhraseSilenceOffsetsExact(floatTextAggregator()));
}

TEST_F(TimingTextPathTest, PhraseSilenceSplitOffsetsAreExactPhonemesFloat) {
    ASSERT_NO_FATAL_FAILURE(
        expectPhraseSilenceOffsetsExact(floatPhonemeAggregator()));
}

// The gate for the one new bug an append-based fix can introduce: the CLI
// declares a single SynthesisResult and reuses it for every stdin line while
// rewriting the timing file per line, so a missing entry reset would emit
// line1 + line2 + ... on the last line.
TEST_F(TimingTextPathTest, ReusedResultDoesNotAccumulateTimings) {
    const std::string text = "Hola mundo.";

    piper::PhonemizeResult phonResult;
    piper::phonemizeText(voice, text, phonResult);
    ASSERT_FALSE(phonResult.phonemes.empty());
    const std::vector<piper::Phoneme> &phonemes = phonResult.phonemes.front();
    auto noopChunk = [](const std::vector<int16_t> &) {};

    {
        piper::SynthesisResult result;
        std::vector<int16_t> first;
        std::vector<int16_t> second;
        piper::textToAudio(config, voice, text, first, result, nullptr);
        ASSERT_FALSE(result.phonemeTimings.empty());
        const std::size_t afterFirst = result.phonemeTimings.size();
        piper::textToAudio(config, voice, text, second, result, nullptr);
        EXPECT_EQ(result.phonemeTimings.size(), afterFirst)
            << "textToAudio accumulated timings across calls";
    }

    {
        piper::SynthesisResult result;
        std::vector<float> first;
        std::vector<float> second;
        piper::textToAudioFloat(config, voice, text, first, result, nullptr);
        ASSERT_FALSE(result.phonemeTimings.empty());
        const std::size_t afterFirst = result.phonemeTimings.size();
        piper::textToAudioFloat(config, voice, text, second, result, nullptr);
        EXPECT_EQ(result.phonemeTimings.size(), afterFirst)
            << "textToAudioFloat accumulated timings across calls";
    }

    {
        piper::SynthesisResult result;
        std::vector<float> first;
        std::vector<float> second;
        piper::phonemesToAudioFloat(config, voice, phonemes, nullptr, first,
                                    result);
        ASSERT_FALSE(result.phonemeTimings.empty());
        const std::size_t afterFirst = result.phonemeTimings.size();
        piper::phonemesToAudioFloat(config, voice, phonemes, nullptr, second,
                                    result);
        EXPECT_EQ(result.phonemeTimings.size(), afterFirst)
            << "phonemesToAudioFloat accumulated timings across calls";
    }

    {
        piper::SynthesisResult result;
        std::vector<int16_t> first;
        std::vector<int16_t> second;
        piper::textToAudioStreaming(config, voice, text, first, result,
                                    noopChunk);
        ASSERT_FALSE(result.phonemeTimings.empty());
        const std::size_t afterFirst = result.phonemeTimings.size();
        piper::textToAudioStreaming(config, voice, text, second, result,
                                    noopChunk);
        EXPECT_EQ(result.phonemeTimings.size(), afterFirst)
            << "textToAudioStreaming accumulated timings across calls";
    }

    {
        piper::SynthesisResult result;
        std::vector<int16_t> first;
        std::vector<int16_t> second;
        piper::phonemesToAudioStreaming(config, voice, phonemes, first, result,
                                        noopChunk);
        ASSERT_FALSE(result.phonemeTimings.empty());
        const std::size_t afterFirst = result.phonemeTimings.size();
        piper::phonemesToAudioStreaming(config, voice, phonemes, second, result,
                                        noopChunk);
        EXPECT_EQ(result.phonemeTimings.size(), afterFirst)
            << "phonemesToAudioStreaming accumulated timings across calls";
    }

    // A result carrying stale timings must come back empty, not "still true",
    // from a call that produces nothing.
    {
        piper::SynthesisResult result;
        std::vector<int16_t> textAudio;
        piper::textToAudio(config, voice, text, textAudio, result, nullptr);
        ASSERT_TRUE(result.hasTimingInfo);
        std::vector<int16_t> streamingAudio;
        piper::textToAudioStreaming(config, voice, "", streamingAudio, result,
                                    noopChunk);
        EXPECT_FALSE(result.hasTimingInfo);
        EXPECT_TRUE(result.phonemeTimings.empty());
    }

    // Nothing above asserts on audioSeconds / inferSeconds: their cross-call
    // accumulation is existing behaviour the CLI's per-line RTF log relies on.
}

// `--output_raw --streaming` routes through these two functions and then hits
// the same --output-timing gate, so they are a #652 symptom too. Both clear
// their output buffer at entry and grow only by insert, which makes the
// absolute buffer size the correct offset base.
TEST_F(TimingTextPathTest, StreamingPathsPropagateTiming) {
    auto noopChunk = [](const std::vector<int16_t> &) {};

    {
        std::vector<int16_t> audio;
        piper::SynthesisResult result;
        piper::textToAudioStreaming(config, voice, "Hola. Adios.", audio,
                                    result, noopChunk);
        ASSERT_TRUE(result.hasTimingInfo)
            << "textToAudioStreaming dropped its sentence timings";
        ASSERT_FALSE(result.phonemeTimings.empty());
        expectMonotonic(result.phonemeTimings);
        expectWithinAudio(result.phonemeTimings, audio.size(), sampleRate(),
                          channels());
    }

    {
        piper::PhonemizeResult phonResult;
        piper::phonemizeText(voice, "Hola mundo.", phonResult);
        ASSERT_FALSE(phonResult.phonemes.empty());

        std::vector<int16_t> audio;
        piper::SynthesisResult result;
        // A small chunk size forces several inference units.
        piper::phonemesToAudioStreaming(config, voice,
                                        phonResult.phonemes.front(), audio,
                                        result, noopChunk, 4);
        ASSERT_TRUE(result.hasTimingInfo)
            << "phonemesToAudioStreaming dropped its chunk timings";
        ASSERT_FALSE(result.phonemeTimings.empty());
        expectMonotonic(result.phonemeTimings);
        expectWithinAudio(result.phonemeTimings, audio.size(), sampleRate(),
                          channels());
    }
}

// Route the propagated timings through the PRODUCTION writers, so drift
// between the in-test mirrors of test_phoneme_timing.cpp and the real
// functions cannot hide a broken CLI output path.
TEST_F(TimingTextPathTest, CliWriterEmitsTimingForTextPath) {
    const std::string text = "Hola mundo.";

    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    piper::textToAudio(config, voice, text, audio, result, nullptr);
    ASSERT_TRUE(result.hasTimingInfo);
    ASSERT_FALSE(result.phonemeTimings.empty());

    std::ostringstream jsonOut;
    piper::outputTimingsAsJSON(result.phonemeTimings, jsonOut, text,
                               sampleRate(), hopSize());
    const nlohmann::json parsed = nlohmann::json::parse(jsonOut.str());
    ASSERT_TRUE(parsed.contains("phonemes"));
    ASSERT_TRUE(parsed["phonemes"].is_array());
    ASSERT_FALSE(parsed["phonemes"].empty());
    EXPECT_EQ(parsed["phonemes"].size(), result.phonemeTimings.size());

    std::ostringstream tsvOut;
    piper::outputTimingsAsTSV(result.phonemeTimings, tsvOut);
    std::istringstream tsvIn(tsvOut.str());
    std::size_t lineCount = 0;
    std::string line;
    while (std::getline(tsvIn, line)) {
        ++lineCount;
    }
    // Header row + one row per entry.
    EXPECT_EQ(lineCount, result.phonemeTimings.size() + 1);
}

// No-regression pin, green before and after the fix: phonemesToAudio runs a
// single inference straight into the caller's result, so it aggregates
// nothing and its entries must stay 0-based. This is the one CLI path
// (--raw-phonemes) that already emitted timing before the fix.
TEST_F(TimingTextPathTest, PhonemesToAudioTimingUnchanged) {
    piper::PhonemizeResult phonResult;
    piper::phonemizeText(voice, "Hola mundo.", phonResult);
    ASSERT_FALSE(phonResult.phonemes.empty());

    std::vector<int16_t> audio;
    piper::SynthesisResult result;
    piper::phonemesToAudio(config, voice, phonResult.phonemes.front(), audio,
                           result);

    ASSERT_TRUE(result.hasTimingInfo);
    ASSERT_FALSE(result.phonemeTimings.empty());
    EXPECT_EQ(result.phonemeTimings.front().start_time, 0.0f);
    EXPECT_EQ(result.phonemeTimings.front().start_frame, 0);
    expectMonotonic(result.phonemeTimings);
    expectWithinAudio(result.phonemeTimings, audio.size(), sampleRate(),
                      channels());
}

// ---------------------------------------------------------------------------
// Locale independence of the production TSV writer. Model-free: it drives
// piper::outputTimingsAsTSV over a hand-built timing vector, so it runs even
// where the fixture model is absent.
//
// The CLI installs a global "en_US.UTF-8" locale (main.cpp) before any
// synthesis happens, so the ofstream behind --output-timing inherits its
// numpunct, which groups thousands. Every entry past 1 second was written as
// `1,011.541`: not a number to any TSV consumer, and not the format the spec
// pins in [output_formats.tsv] (float_precision = 3). It reproduced only on
// runtimes where that locale is installable -- main.cpp falls back to the
// classic locale otherwise -- and the writer's own tests never saw it because
// their fixture data stays under one second.
//
// A hand-rolled numpunct is used rather than a named locale so the grouping is
// reproduced identically on every runner, with no dependency on which locales
// happen to be installed.
// ---------------------------------------------------------------------------
namespace {

class CommaGroupingNumpunct : public std::numpunct<char> {
protected:
    char do_thousands_sep() const override { return ','; }
    std::string do_grouping() const override { return "\3"; }
};

std::vector<std::string> splitTabs(const std::string &line) {
    std::vector<std::string> columns;
    std::string current;
    for (const char c : line) {
        if (c == '\t') {
            columns.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    columns.push_back(current);
    return columns;
}

} // namespace

TEST(TimingTsvWriterLocaleTest, NumericColumnsHaveNoThousandsSeparator) {
    // Both entries end past the 1000 ms grouping boundary, which is where the
    // separator appears. A fixture that stays under a second cannot see this.
    const std::vector<piper::PhonemeInfo> timings = {
        {"a", 0.900f, 1.011541f, 77, 87},
        {"b", 1.011541f, 2.103099f, 87, 181},
    };

    std::ostringstream out;
    out.imbue(std::locale(std::locale::classic(), new CommaGroupingNumpunct));
    piper::outputTimingsAsTSV(timings, out);

    const std::string text = out.str();
    ASSERT_FALSE(text.empty());

    std::istringstream lines(text);
    std::string header;
    ASSERT_TRUE(static_cast<bool>(std::getline(lines, header)));

    std::size_t rows = 0;
    std::string line;
    while (std::getline(lines, line)) {
        const std::vector<std::string> columns = splitTabs(line);
        ASSERT_EQ(columns.size(), 8u) << "row='" << line << "'";
        // Columns 1..5 are floating point; 6..7 are integers. None of them may
        // carry a digit-group separator, and each must round-trip through
        // std::stod consuming the whole field.
        for (std::size_t i = 1; i < columns.size(); ++i) {
            EXPECT_EQ(columns[i].find(','), std::string::npos)
                << "column " << i << " of row '" << line
                << "' contains a thousands separator, so the TSV is not "
                   "numerically parseable";
            std::size_t consumed = 0;
            const double value = std::stod(columns[i], &consumed);
            EXPECT_EQ(consumed, columns[i].size())
                << "column " << i << " ('" << columns[i]
                << "') did not parse as a single number";
            EXPECT_GE(value, 0.0);
        }
        ++rows;
    }
    EXPECT_EQ(rows, timings.size());

    // The caller's locale must be left as it was found.
    EXPECT_EQ(out.getloc().name(), std::locale(std::locale::classic(),
                                               new CommaGroupingNumpunct)
                                       .name());
}

// ---------------------------------------------------------------------------
// SRT millisecond rounding (issue #681). Model-free: drives the production
// piper::outputTimingsAsSRT over a hand-built timing vector.
//
// The rule is half-away-from-zero, per
// docs/spec/phoneme-timing-contract.toml [output_formats.srt].rounding. Python
// and C# used their language default (round-half-to-EVEN) and emitted a
// timestamp 1 ms earlier than this runtime on every .5 boundary; these cases
// pin C++ on the correct side so a future "cleanup" to std::round or
// std::lround (both half-away-from-zero, but easy to replace with a
// banker's-rounding helper) cannot drift silently.
//
// The contract's rounding_cases are expressed in MILLISECONDS, but PhonemeInfo
// stores SECONDS as float, and no float multiplied by 1000 lands exactly on
// 1234.5 ms. The values below are the ms equivalents that ARE exactly
// representable (k/2000 with k a multiple of 125) and whose integer part is
// even -- the only combination that both round-trips through float and
// distinguishes the two rounding rules.
// ---------------------------------------------------------------------------
TEST(TimingSrtWriterRoundingTest, RoundsHalfAwayFromZero) {
    struct Case {
        float seconds;
        double expectedMs;  // documentation: what seconds * 1000 must equal
        const char *timestamp;
    };
    // 0.0625 s = 62.5 ms (62 even), 0.3125 s = 312.5 ms (312 even).
    const Case cases[] = {
        {0.0625f, 62.5, "00:00:00,063"},
        {0.3125f, 312.5, "00:00:00,313"},
        {0.5625f, 562.5, "00:00:00,563"},
    };

    for (const Case &c : cases) {
        ASSERT_DOUBLE_EQ(static_cast<double>(c.seconds) * 1000.0, c.expectedMs)
            << "fixture value " << c.seconds
            << " does not land exactly on the .5 ms boundary, so this case "
               "cannot distinguish the two rounding rules";

        const std::vector<piper::PhonemeInfo> timings = {
            {"a", c.seconds, c.seconds, 0, 0},
        };
        std::ostringstream out;
        piper::outputTimingsAsSRT(timings, out, 22050.0, 256);

        const std::string expectedCue =
            std::string(c.timestamp) + " --> " + c.timestamp;
        EXPECT_NE(out.str().find(expectedCue), std::string::npos)
            << "expected cue '" << expectedCue << "' in:\n" << out.str();
    }
}

// ---------------------------------------------------------------------------
// The SRT cue index must not inherit a grouping numpunct (issue #684).
//
// outputTimingsAsSRT writes the 1-based index with `output << (i + 1)`. The CLI
// installs a global "en_US.UTF-8" locale (main.cpp), so the ofstream behind
// --output-timing inherits its numpunct and every index from 1000 on is written
// as "1,000" -- not an integer to any SRT parser. outputTimingsAsTSV pins the
// classic locale for exactly this reason; the SRT writer did not, and the bug
// was unreachable from the CLI until --timing-format srt was exposed (#657).
//
// 1000 entries is the smallest count that crosses the grouping boundary.
// Model-free: it drives the production writer over a synthetic timing vector.
// ---------------------------------------------------------------------------
TEST(TimingSrtWriterLocaleTest, CueIndexHasNoThousandsSeparator) {
    std::vector<piper::PhonemeInfo> timings;
    timings.reserve(1000);
    for (int i = 0; i < 1000; ++i) {
        const float start = static_cast<float>(i) * 0.01f;
        timings.push_back({"a", start, start + 0.01f, i, i + 1});
    }

    std::ostringstream out;
    out.imbue(std::locale(std::locale::classic(), new CommaGroupingNumpunct));
    piper::outputTimingsAsSRT(timings, out, 22050.0, 256);

    const std::string text = out.str();
    ASSERT_FALSE(text.empty());

    // Every cue's first line must parse as a bare integer.
    std::istringstream lines(text);
    std::string line;
    std::size_t expectedIndex = 0;
    while (std::getline(lines, line)) {
        if (line.empty()) {
            continue;
        }
        // Cue blocks are index / timestamps / phoneme; only the index line is
        // a bare number, and the timestamp line always contains " --> ".
        if (line.find(" --> ") != std::string::npos || line == "a") {
            continue;
        }
        ++expectedIndex;
        EXPECT_EQ(line.find(','), std::string::npos)
            << "cue index line '" << line
            << "' contains a thousands separator, so the SRT index is not an "
               "integer";
        EXPECT_EQ(line, std::to_string(expectedIndex))
            << "cue index line '" << line << "' is not the bare integer "
            << expectedIndex;
    }
    EXPECT_EQ(expectedIndex, timings.size());
}
