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
};

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

// The offset rule itself. Inline `[[ ]]` notation is the only way to force
// three synthesize() units out of one call: plain multi-sentence text is
// flattened into a single unit by the multilingual phonemizer.
TEST_F(TimingTextPathTest, MultiUnitOffsetsMatchEmittedSampleCounts) {
    const std::string combinedText = "Hola. [[ m u n d o ]] Adios.";

    std::vector<int16_t> combinedAudio;
    piper::SynthesisResult combined;
    piper::textToAudio(config, voice, combinedText, combinedAudio, combined,
                       nullptr);

    ASSERT_TRUE(combined.hasTimingInfo);
    // Pinned measurement: 5 + 5 + 7 entries across the three units.
    ASSERT_EQ(combined.phonemeTimings.size(), 17u);
    expectMonotonic(combined.phonemeTimings);

    // Re-synthesize each unit alone with the trailing sentence silence turned
    // off, so each run's audioBuffer.size() is exactly that unit's length.
    // Durations are deterministic for a given id sequence, so the isolated
    // entries are the combined run's entries minus the offset.
    const float sentenceSilenceSeconds =
        voice.synthesisConfig.sentenceSilenceSeconds;
    voice.synthesisConfig.sentenceSilenceSeconds = 0.0f;

    const std::vector<std::string> segments = {"Hola.", "[[ m u n d o ]]",
                                               "Adios."};
    std::vector<std::size_t> unitSamples;
    std::vector<std::vector<piper::PhonemeInfo>> unitTimings;
    for (const auto &segment : segments) {
        std::vector<int16_t> segmentAudio;
        piper::SynthesisResult segmentResult;
        piper::textToAudio(config, voice, segment, segmentAudio, segmentResult,
                           nullptr);
        ASSERT_TRUE(segmentResult.hasTimingInfo) << segment;
        ASSERT_FALSE(segmentResult.phonemeTimings.empty()) << segment;
        unitSamples.push_back(segmentAudio.size());
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

        const double offsetSeconds = static_cast<double>(offsetSamples) /
                                     (static_cast<double>(sampleRate()) *
                                      channels());
        const int offsetFrames = static_cast<int>(
            offsetSamples /
            (static_cast<std::size_t>(hopSize()) * channels()));

        for (std::size_t i = 0; i < unitTimings[unit].size(); ++i) {
            const piper::PhonemeInfo &expected = unitTimings[unit][i];
            const piper::PhonemeInfo &actual =
                combined.phonemeTimings[entryIdx + i];
            const std::string at = where + " entry " + std::to_string(i);

            EXPECT_EQ(actual.phoneme, expected.phoneme) << at;
            // Exact inter-unit delta, tolerance one sample. Forwarding only
            // unit 0 never reaches this loop; concatenating with no offset,
            // using the per-unit audioSeconds (#654) or a raw duration sum
            // (#653) are all off by 72-140 ms here.
            EXPECT_NEAR(static_cast<double>(actual.start_time),
                        static_cast<double>(expected.start_time) + offsetSeconds,
                        oneSample())
                << at;
            EXPECT_NEAR(static_cast<double>(actual.end_time),
                        static_cast<double>(expected.end_time) + offsetSeconds,
                        oneSample())
                << at;
            EXPECT_EQ(actual.start_frame, expected.start_frame + offsetFrames)
                << at;
            EXPECT_EQ(actual.end_frame, expected.end_frame + offsetFrames) << at;
        }

        entryIdx += unitTimings[unit].size();
        offsetSamples += unitSamples[unit] + sentenceSilenceSamples;
    }

    EXPECT_EQ(entryIdx, combined.phonemeTimings.size())
        << "every combined entry must belong to one of the three units";
    // Sum(unit audio) + Sum(sentence silence) reconstructs the emitted stream
    // to the sample; this is what makes the offsets positions in the caller's
    // WAV rather than approximations.
    EXPECT_EQ(combinedAudio.size(), offsetSamples);
}

// Intra-sentence phrase tier: `phonemeSilenceSeconds` splits one sentence into
// several synthesize() units, which the partial forward this fix replaces
// dropped silently. Unreachable from the C API.
TEST_F(TimingTextPathTest, PhraseSilenceSplitOffsetsAreExact) {
    const piper::Phoneme splitPhoneme = U'l';
    if (voice.phonemizeConfig.phonemeIdMap.count(splitPhoneme) == 0) {
        GTEST_SKIP() << "phoneme 'l' is absent from this model's "
                        "phoneme_id_map, so the phrase split cannot happen";
    }

    const std::string text = "Hola mundo.";

    auto runWithPhraseSilence = [&](float seconds, std::vector<int16_t> &audio,
                                    piper::SynthesisResult &result) {
        voice.synthesisConfig.phonemeSilenceSeconds =
            std::map<piper::Phoneme, float>{{splitPhoneme, seconds}};
        piper::textToAudio(config, voice, text, audio, result, nullptr);
        voice.synthesisConfig.phonemeSilenceSeconds.reset();
    };

    std::vector<int16_t> audioA;
    std::vector<int16_t> audioB;
    piper::SynthesisResult resultA;
    piper::SynthesisResult resultB;
    runWithPhraseSilence(0.3f, audioA, resultA);
    runWithPhraseSilence(0.6f, audioB, resultB);

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
    EXPECT_EQ(audioB.size() - audioA.size(), silenceB - silenceA)
        << "the phrase silence must be the only audio difference";

    // The phrase boundary is the first entry whose start_time moved; phrase 1
    // carries offset 0 in both runs, so it must be bit-identical.
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
        << "no phrase split happened; the phrase tier is untested";
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

    const double expectedShift = static_cast<double>(silenceB - silenceA) /
                                 (static_cast<double>(sampleRate()) * channels());
    const int expectedFrameShift =
        static_cast<int>(silenceB / (static_cast<std::size_t>(hopSize()) * channels())) -
        static_cast<int>(silenceA / (static_cast<std::size_t>(hopSize()) * channels()));
    for (std::size_t i = boundary; i < resultA.phonemeTimings.size(); ++i) {
        const std::string at = "phrase 2 entry " + std::to_string(i);
        EXPECT_NEAR(static_cast<double>(resultB.phonemeTimings[i].start_time) -
                        static_cast<double>(resultA.phonemeTimings[i].start_time),
                    expectedShift, oneSample())
            << at;
        EXPECT_NEAR(static_cast<double>(resultB.phonemeTimings[i].end_time) -
                        static_cast<double>(resultA.phonemeTimings[i].end_time),
                    expectedShift, oneSample())
            << at;
        EXPECT_EQ(resultB.phonemeTimings[i].start_frame -
                      resultA.phonemeTimings[i].start_frame,
                  expectedFrameShift)
            << at;
    }
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
