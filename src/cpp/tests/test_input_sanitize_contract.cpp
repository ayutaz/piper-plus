/**
 * Test: the C++ library and the C API strip control characters before they
 * read a text.
 *
 * Contract: docs/spec/input-sanitize-contract.toml (runtime "cpp").
 * Cases: tests/fixtures/g2p/input_sanitize_cases.json, read here directly.
 *
 * Regression focus: #934 (2026-11) stripped control characters in the
 * Python G2P only. Here a control character inside "hola" split the word, a
 * custom dictionary missed a word with one inside it, a NUL inside "Python"
 * between Chinese text spelled it out letter by letter, and a control
 * character after "." hid the sentence boundary from synth_start.
 *
 * A C string cannot hold a NUL, so the C API cases put DEL (removed by the
 * same rule) where a case has a NUL. stripControlChars itself takes the NUL.
 *
 * Japanese is skipped (the OpenJTalk dictionary is not staged for this
 * executable), and so is pt-PT, which the engine-less G2P does not map.
 */

#include <gtest/gtest.h>

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "../json.hpp"
#include "../piper.hpp"
#include "../text_sanitize.hpp"
#include "piper_plus.h"

#ifndef PIPER_PLUS_SOURCE_DIR
#error "PIPER_PLUS_SOURCE_DIR must point at the repository root"
#endif

namespace {

using nlohmann::json;

const std::string kRoot = PIPER_PLUS_SOURCE_DIR;

json loadCases() {
    std::ifstream in(kRoot + "/tests/fixtures/g2p/input_sanitize_cases.json", std::ios::binary);
    if (!in) throw std::runtime_error("cannot open input_sanitize_cases.json");
    std::stringstream buf;
    buf << in.rdbuf();
    return json::parse(buf.str());
}

struct TextCase {
    std::string label;
    std::string language;  // "" = detect
    std::string clean;
    std::string dirty;  // NUL replaced by DEL
};

std::string asCString(std::string s) {
    for (auto& c : s) {
        if (c == '\0') c = '\x7f';
    }
    return s;
}

// The word cases the engine-less G2P can read, and every pipeline case.
std::vector<TextCase> textCases() {
    static const std::set<std::string> skipped = {"ja", "pt-PT"};
    const json doc = loadCases();
    std::vector<TextCase> out;
    for (const auto& c : doc["word_cases"]) {
        std::string lang = c["language"];
        if (skipped.count(lang)) continue;
        out.push_back({lang + " " + c["control"].get<std::string>() + " '" +
                           c["clean"].get<std::string>() + "'",
                       lang == "multilingual" ? "" : lang, c["clean"], asCString(c["dirty"])});
    }
    for (const auto& c : doc["pipeline_cases"]) {
        out.push_back(
            {c["name"].get<std::string>(), c["language"], c["clean"], asCString(c["dirty"])});
    }
    return out;
}

// Points PIPER_PLUS_DICTIONARIES_PATH at the canonical CMU / pinyin files
// (as test_c_api_g2p_golden.cpp does) and restores it afterwards.
class ScopedDictionaries {
   public:
    ScopedDictionaries() {
        const char* old = std::getenv("PIPER_PLUS_DICTIONARIES_PATH");
        if (old) previous_ = old;
        set(kRoot + "/src/rust/piper-plus-g2p/data");
    }
    ~ScopedDictionaries() { set(previous_); }

   private:
    static void set(const std::string& value) {
#ifdef _WIN32
        _putenv_s("PIPER_PLUS_DICTIONARIES_PATH", value.c_str());
#else
        if (value.empty()) {
            unsetenv("PIPER_PLUS_DICTIONARIES_PATH");
        } else {
            setenv("PIPER_PLUS_DICTIONARIES_PATH", value.c_str(), 1);
        }
#endif
    }
    std::string previous_;
};

std::string g2p(PiperPlusG2pHandle* h, const std::string& text, const std::string& lang) {
    PiperPlusPhonemeResult r{};
    const PiperPlusStatus rc = piper_plus_g2p_phonemize(h, text.c_str(), lang.c_str(), &r);
    if (rc != PIPER_PLUS_OK) return "<error " + std::to_string(rc) + ">";
    return r.phonemes ? r.phonemes : "";
}

// A custom dictionary that reads "hola" as "pero".
std::string writeHolaDict() {
    std::string path = testing::TempDir() + "input-sanitize-dict.json";
    std::ofstream out(path, std::ios::binary);
    out << R"({"version":"2.0","entries":{"hola":{"pronunciation":"pero","priority":9}}})";
    return path;
}

}  // namespace

// ---------------------------------------------------------------------------
// stripControlChars
// ---------------------------------------------------------------------------

TEST(InputSanitize, StripMatchesEveryStripCase) {
    const json doc = loadCases();
    int checked = 0;
    for (const auto& c : doc["strip_cases"]) {
        const std::string input = c["input"];
        EXPECT_EQ(piper::stripControlChars(input), c["expected"].get<std::string>())
            << c["name"].get<std::string>();
        ++checked;
    }
    EXPECT_GT(checked, 10);
}

TEST(InputSanitize, StripIsIdempotent) {
    const json doc = loadCases();
    for (const auto& c : doc["strip_cases"]) {
        const std::string once = piper::stripControlChars(c["input"].get<std::string>());
        EXPECT_EQ(piper::stripControlChars(once), once) << c["name"].get<std::string>();
    }
}

TEST(InputSanitize, StripKeepsInvalidUtf8Bytes) {
    // A lone 0xFF, a 0xC2 at the end and a 0xC2 before a non-C1 byte stay.
    EXPECT_EQ(piper::stripControlChars(std::string("a\xff\x00"
                                                   "b",
                                                   4)),
              "a\xff"
              "b");
    EXPECT_EQ(piper::stripControlChars("a\xc2"), "a\xc2");
    EXPECT_EQ(piper::stripControlChars("\xc2"
                                       "A"),
              "\xc2"
              "A");
    // U+00A0 (C2 A0) is NBSP, not C1.
    EXPECT_EQ(piper::stripControlChars("a\xc2\xa0"
                                       "b"),
              "a\xc2\xa0"
              "b");
}

// ---------------------------------------------------------------------------
// Engine-less G2P (piper_plus_g2p_phonemize -> phonemizeText)
// ---------------------------------------------------------------------------

// One handle per suite: creating one loads the CMU and pinyin dictionaries
// (about 5 s in a Debug build), and test_c_api has a 60 s timeout.
class InputSanitizeG2p : public ::testing::Test {
   protected:
    static void SetUpTestSuite() {
        dictionaries_ = new ScopedDictionaries();  // must outlive create()
        handle_ = piper_plus_g2p_create(nullptr);
    }
    static void TearDownTestSuite() {
        piper_plus_g2p_free(handle_);
        handle_ = nullptr;
        delete dictionaries_;
        dictionaries_ = nullptr;
    }
    void SetUp() override { ASSERT_NE(handle_, nullptr) << piper_plus_get_last_error(); }

    static inline ScopedDictionaries* dictionaries_ = nullptr;
    static inline PiperPlusG2pHandle* handle_ = nullptr;
};

// A suite of its own (and so a handle of its own): the dictionary it loads
// stays on the handle.
class InputSanitizeG2pDict : public InputSanitizeG2p {};

TEST_F(InputSanitizeG2p, ReadsDirtyLikeClean) {
    const auto cases = textCases();
    ASSERT_GT(cases.size(), 30u);
    for (const auto& c : cases) {
        const std::string clean = g2p(handle_, c.clean, c.language);
        ASSERT_EQ(clean.rfind("<error", 0), std::string::npos) << c.label << ": " << clean;
        EXPECT_EQ(g2p(handle_, c.dirty, c.language), clean) << c.label;
    }
}

TEST_F(InputSanitizeG2p, OnlyControlsReadAsEmptyText) {
    const std::string empty = g2p(handle_, "", "es");
    ASSERT_EQ(empty.rfind("<error", 0), std::string::npos) << empty;
    EXPECT_EQ(g2p(handle_, "\x01\x7f\xc2\x9f", "es"), empty);
}

TEST_F(InputSanitizeG2pDict, CustomDictionaryFindsTheWord) {
    const std::string dict = writeHolaDict();
    ASSERT_EQ(piper_plus_g2p_load_custom_dict(handle_, dict.c_str()), PIPER_PLUS_OK)
        << piper_plus_get_last_error();
    const std::string expected = g2p(handle_, "pero", "es");
    EXPECT_EQ(g2p(handle_, "hola", "es"), expected);
    EXPECT_EQ(g2p(handle_, "ho\x7fla", "es"), expected);
    std::remove(dict.c_str());
}

// ---------------------------------------------------------------------------
// piper_plus_phonemize_embedded_english (-> piper::phonemizeEmbeddedEnglish)
// ---------------------------------------------------------------------------

TEST(InputSanitize, EmbeddedEnglishReadsDirtyLikeClean) {
    PiperPlusLoanwordHandle* h = piper_plus_loanword_load_default();
    ASSERT_NE(h, nullptr) << piper_plus_get_last_error();
    auto read = [h](const char* text) {
        PiperPlusPhonemeResult r{};
        EXPECT_EQ(piper_plus_phonemize_embedded_english(h, text, &r), PIPER_PLUS_OK);
        return std::string(r.phonemes ? r.phonemes : "");
    };
    const std::string clean = read("Python");
    ASSERT_FALSE(clean.empty());
    // A control character inside "Python" split it into two runs, which were
    // spelled out letter by letter.
    EXPECT_EQ(read("Py\x7fthon"), clean);
    EXPECT_EQ(read("\x07Python\x1b"), clean);
    EXPECT_EQ(read("Pyth\xc2\x9fon"), clean);
    piper_plus_loanword_free(h);
}

// ---------------------------------------------------------------------------
// Engine (piper_plus_phonemize / synthesize / synth_start)
// ---------------------------------------------------------------------------

// One engine per suite, for the same reason as InputSanitizeG2p.
class InputSanitizeEngine : public ::testing::Test {
   protected:
    static void SetUpTestSuite() {
        const std::string model = kRoot + "/test/models/multilingual-test-medium.onnx";
        PiperPlusConfig config = {};
        config.model_path = model.c_str();
        config.provider = "cpu";
        config.num_threads = 1;
        if (piper_plus_create(&config, &engine_) != PIPER_PLUS_OK) {
            engine_ = nullptr;
            return;
        }
        opts_ = piper_plus_default_options();
        opts_.noise_scale = 0.0f;
        opts_.noise_w = 0.0f;
        opts_.language_id = piper_plus_language_id(engine_, "es");
    }
    static void TearDownTestSuite() {
        piper_plus_free(engine_);
        engine_ = nullptr;
    }
    void SetUp() override {
        ASSERT_NE(engine_, nullptr) << piper_plus_get_last_error();
        ASSERT_GE(opts_.language_id, 0);
    }

    static std::string phonemize(const std::string& text) {
        PiperPlusPhonemeResult r{};
        const PiperPlusStatus rc = piper_plus_phonemize(engine_, text.c_str(), "es", &r);
        if (rc != PIPER_PLUS_OK) return "<error " + std::to_string(rc) + ">";
        return r.phonemes ? r.phonemes : "";
    }

    static int32_t synthesizedSamples(const std::string& text) {
        float* samples = nullptr;
        int32_t n = 0, rate = 0;
        EXPECT_EQ(piper_plus_synthesize(engine_, text.c_str(), &opts_, &samples, &n, &rate),
                  PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        piper_plus_free_audio(samples);
        return n;
    }

    // Number of chunks synth_next yields, and their total length.
    static std::pair<int, int64_t> streamed(const std::string& text) {
        EXPECT_EQ(piper_plus_synth_start(engine_, text.c_str(), &opts_), PIPER_PLUS_OK)
            << piper_plus_get_last_error();
        int chunks = 0;
        int64_t total = 0;
        PiperPlusAudioChunk chunk{};
        // The last chunk comes with PIPER_PLUS_DONE (an empty one when there
        // is no sentence).
        while (true) {
            const PiperPlusStatus rc = piper_plus_synth_next(engine_, &chunk);
            if (rc != PIPER_PLUS_OK && rc != PIPER_PLUS_DONE) {
                ADD_FAILURE() << "synth_next: " << piper_plus_get_last_error();
                break;
            }
            if (chunk.num_samples > 0) {
                ++chunks;
                total += chunk.num_samples;
            }
            if (rc == PIPER_PLUS_DONE) break;
        }
        return {chunks, total};
    }

    // The Spanish word cases, the pipeline cases, and one case for the
    // sentence splitting of synth_start: a control character between "3."
    // and "5" hid the decimal point.
    static std::vector<TextCase> spanishCases() {
        std::vector<TextCase> out;
        for (const auto& c : textCases()) {
            if (c.language == "es") out.push_back(c);
        }
        out.push_back({"del_in_decimal", "es", "3.5 metros.",
                       "3.\x7f"
                       "5 metros."});
        return out;
    }

    static inline PiperPlusEngine* engine_ = nullptr;
    static inline PiperPlusSynthOptions opts_{};
};

// A suite of its own: the dictionary it loads stays on the engine.
class InputSanitizeEngineDict : public InputSanitizeEngine {};

TEST_F(InputSanitizeEngine, PhonemizeReadsDirtyLikeClean) {
    const auto cases = spanishCases();
    ASSERT_GT(cases.size(), 5u);
    for (const auto& c : cases) {
        const std::string clean = phonemize(c.clean);
        ASSERT_EQ(clean.rfind("<error", 0), std::string::npos) << c.label << ": " << clean;
        EXPECT_EQ(phonemize(c.dirty), clean) << c.label;
    }
}

TEST_F(InputSanitizeEngine, SynthesizeReadsDirtyLikeClean) {
    for (const auto& c : spanishCases()) {
        EXPECT_EQ(synthesizedSamples(c.dirty), synthesizedSamples(c.clean)) << c.label;
    }
}

TEST_F(InputSanitizeEngine, SynthStartSplitsTheStrippedText) {
    for (const auto& c : spanishCases()) {
        const auto clean = streamed(c.clean);
        ASSERT_GT(clean.first, 0) << c.label;
        const auto dirty = streamed(c.dirty);
        EXPECT_EQ(dirty.first, clean.first) << c.label << ": chunks";
        EXPECT_EQ(dirty.second, clean.second) << c.label << ": samples";
    }
}

// synth_start rejects an empty text, so it rejects a text of only control
// characters too (it used to accept it and yield nothing).
TEST_F(InputSanitizeEngine, SynthStartRejectsOnlyControlsLikeAnEmptyText) {
    ASSERT_EQ(piper_plus_synth_start(engine_, "", &opts_), PIPER_PLUS_ERR_TEXT);
    EXPECT_EQ(piper_plus_synth_start(engine_, "\x01\x7f\xc2\x9f", &opts_), PIPER_PLUS_ERR_TEXT);
    PiperPlusAudioCallback ignore = [](const float*, int32_t, int32_t, void*) {};
    EXPECT_EQ(piper_plus_synthesize_streaming(engine_, "\x01\x7f", &opts_, ignore, nullptr),
              PIPER_PLUS_ERR_TEXT);
    // The engine is usable afterwards.
    EXPECT_GT(synthesizedSamples("hola"), 0);
    EXPECT_GT(streamed("hola").first, 0);
}

TEST_F(InputSanitizeEngineDict, CustomDictionaryFindsTheWord) {
    const std::string dict = writeHolaDict();
    ASSERT_EQ(piper_plus_load_custom_dict(engine_, dict.c_str()), PIPER_PLUS_OK)
        << piper_plus_get_last_error();
    const std::string expected = phonemize("pero");
    EXPECT_EQ(phonemize("ho\x7fla"), expected);
    EXPECT_EQ(synthesizedSamples("ho\x7fla"), synthesizedSamples("hola"));
    EXPECT_EQ(streamed("ho\x7fla"), streamed("hola"));
    std::remove(dict.c_str());
}

// ---------------------------------------------------------------------------
// C++ library (piper::phonemizeText / piper::textToAudioStreaming)
//
// The C API and the CLI strip before they call these, so only calling them
// directly shows that the library strips too. These take a std::string, so
// the cases keep their NUL.
// ---------------------------------------------------------------------------

// One voice per suite, for the same reason as InputSanitizeG2p.
class InputSanitizeLibrary : public ::testing::Test {
   protected:
    static void SetUpTestSuite() {
        const std::string model = kRoot + "/test/models/multilingual-test-medium.onnx";
        config_ = std::make_unique<piper::PiperConfig>();
        voice_ = std::make_unique<piper::Voice>();
        std::optional<piper::SpeakerId> speakerId;
        piper::loadVoice(*config_, model, model + ".json", *voice_, speakerId, "cpu");
        piper::initialize(*config_);
        voice_->synthesisConfig.noiseScale = 0.0f;
        voice_->synthesisConfig.noiseW = 0.0f;
        if (voice_->modelConfig.languageIdMap.has_value()) {
            voice_->synthesisConfig.languageId = voice_->modelConfig.languageIdMap->at("es");
        }
    }
    static void TearDownTestSuite() {
        piper::terminate(*config_);
        voice_.reset();
        config_.reset();
    }
    void SetUp() override { ASSERT_TRUE(voice_->modelConfig.languageIdMap.has_value()); }

    static std::vector<std::pair<std::string, std::pair<std::string, std::string>>> cases() {
        std::vector<std::pair<std::string, std::pair<std::string, std::string>>> out;
        const json doc = loadCases();
        for (const auto& c : doc["word_cases"]) {
            if (c["language"] == "es") {
                out.push_back({"es " + c["control"].get<std::string>(),
                               {c["clean"].get<std::string>(), c["dirty"].get<std::string>()}});
            }
        }
        for (const auto& c : doc["pipeline_cases"]) {
            out.push_back({c["name"].get<std::string>(),
                           {c["clean"].get<std::string>(), c["dirty"].get<std::string>()}});
        }
        out.push_back({"nul_in_decimal",
                       {"3.5 metros.", std::string("3.\0"
                                                   "5 metros.",
                                                   12)}});
        return out;
    }

    static std::vector<std::vector<piper::Phoneme>> phonemes(const std::string& text) {
        piper::PhonemizeResult r;
        piper::phonemizeText(*voice_, text, r, nullptr);
        return r.phonemes;
    }

    static std::pair<int, size_t> streamed(const std::string& text) {
        std::vector<int16_t> audio;
        piper::SynthesisResult result;
        int chunks = 0;
        piper::textToAudioStreaming(*config_, *voice_, text, audio, result,
                                    [&chunks](const std::vector<int16_t>&) { ++chunks; });
        return {chunks, audio.size()};
    }

    static inline std::unique_ptr<piper::PiperConfig> config_;
    static inline std::unique_ptr<piper::Voice> voice_;
};

TEST_F(InputSanitizeLibrary, PhonemizeTextReadsDirtyLikeClean) {
    const auto all = cases();
    ASSERT_GT(all.size(), 5u);
    for (const auto& [label, c] : all) {
        EXPECT_EQ(phonemes(c.second), phonemes(c.first)) << label;
    }
}

TEST_F(InputSanitizeLibrary, TextToAudioStreamingSplitsTheStrippedText) {
    for (const auto& [label, c] : cases()) {
        const auto clean = streamed(c.first);
        ASSERT_GT(clean.first, 0) << label;
        EXPECT_EQ(streamed(c.second), clean) << label;
    }
}
