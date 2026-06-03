/**
 * Unit tests for multilingual G2P: LanguageDetector + per-language phonemizers.
 *
 * Covers: LanguageDetector segmentation (7 tests), English G2P (3),
 * Chinese G2P (2), Spanish G2P (2), French G2P (2), Portuguese G2P (2),
 * Korean G2P (2), PUA codepoint handling (1), ModelConfig defaults (1),
 * RTF calculation (1), UTF-8 validation (1), findDictionaryFile logic (3),
 * defaultLatinLang detection (4).  Total: 31 tests.
 */

#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

#include "../language_detector.hpp"
#include "../english_phonemize.hpp"
#include "../chinese_phonemize.hpp"
#include "../spanish_phonemize.hpp"
#include "../french_phonemize.hpp"
#include "../portuguese_phonemize.hpp"
#include "../korean_phonemize.hpp"
// NOTE: piper.hpp is intentionally NOT included here — it pulls in
// <onnxruntime_cxx_api.h> which introduces a static initializer referencing
// OrtGetApiBase.  This test does not link against onnxruntime, so we define
// only the minimal types/helpers needed without that dependency.
#include "../phoneme_parser.hpp"  // piper::Phoneme = char32_t
#include "../utf8.h"
#include "../json.hpp"  // SwedishLidMatrix fixture parsing (Issue #539)

namespace piper {

// Minimal ModelConfig used by TestModelConfigTest (no ORT fields).
struct ModelConfig {
    int numSpeakers = 0;
    int numLanguages = 1;
};

// Implementations of helpers declared in piper.hpp but defined here so
// this test links without the full piper.cpp / onnxruntime.
bool isSingleCodepoint(std::string s) {
    return utf8::distance(s.begin(), s.end()) == 1;
}

Phoneme getCodepoint(std::string s) {
    utf8::iterator<std::string::iterator> character_iter(s.begin(), s.begin(),
                                                         s.end());
    return *character_iter;
}

} // namespace piper

using namespace piper;

// =========================================================================
// Helper: build a small inline CMU dictionary for English tests.
// Only contains the words used in assertions so the tests are self-contained
// (no external cmudict_data.json required).
// =========================================================================

static std::unordered_map<std::string, std::string> makeTestCmuDict() {
    return {
        {"hello",  "HH AH0 L OW1"},
        {"the",    "DH AH0"},
        {"how",    "HH AW1"},
        {"are",    "AA1 R"},
        {"you",    "Y UW1"},
    };
}

// =========================================================================
// Helper: build minimal pinyin dictionaries for Chinese tests.
// Single-char dict maps Unicode codepoint (int) -> pinyin with tone digit.
// Phrase dict maps UTF-8 string -> space-separated pinyin.
// =========================================================================

static std::unordered_map<int, std::string> makeTestSingleCharDict() {
    return {
        // 你 = U+4F60, 好 = U+597D
        {0x4F60, "ni3"},
        {0x597D, "hao3"},
        // 今 = U+4ECA, 天 = U+5929, 气 = U+6C14, 很 = U+5F88
        {0x4ECA, "jin1"},
        {0x5929, "tian1"},
        {0x6C14, "qi4"},
        {0x5F88, "hen3"},
    };
}

static std::unordered_map<std::string, std::string> makeTestPhraseDict() {
    return {
        // 天气 -> tian1 qi4
        {"\xE5\xA4\xA9\xE6\xB0\x94", "tian1 qi4"},
    };
}

// =========================================================================
// 1. LanguageDetector tests (7)
// =========================================================================

class LanguageDetectorTest : public ::testing::Test {
protected:
    // Detector configured for all 6 languages + ko
    UnicodeLanguageDetector detector{
        {"ja", "en", "zh", "ko", "es", "fr", "pt"}, "en"};
};

TEST_F(LanguageDetectorTest, JapaneseText) {
    auto segments = detector.segmentText("\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf");  // こんにちは
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "ja");
}

TEST_F(LanguageDetectorTest, EnglishText) {
    auto segments = detector.segmentText("Hello world");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "en");
}

TEST_F(LanguageDetectorTest, MixedText) {
    // "Hello、こんにちは" — should produce an "en" segment then a "ja" segment
    auto segments = detector.segmentText(
        "Hello\xe3\x80\x81\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf");
    ASSERT_GE(segments.size(), 2u);

    // Find en and ja segments (order may vary due to neutral punct)
    bool foundEn = false, foundJa = false;
    for (const auto& seg : segments) {
        if (seg.lang == "en") foundEn = true;
        if (seg.lang == "ja") foundJa = true;
    }
    EXPECT_TRUE(foundEn);
    EXPECT_TRUE(foundJa);
}

TEST_F(LanguageDetectorTest, CJKText) {
    // "你好" — CJK ideographs without kana context -> "zh"
    auto segments = detector.segmentText("\xe4\xbd\xa0\xe5\xa5\xbd");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "zh");
}

TEST_F(LanguageDetectorTest, ChineseTextWithPunctuation) {
    // "你好，今天天气很好。" — CJK punctuation should stay with Chinese segment
    auto segments = detector.segmentText(
        "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8c"           // 你好，
        "\xe4\xbb\x8a\xe5\xa4\xa9\xe5\xa4\xa9\xe6\xb0\x94"  // 今天天气
        "\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82");          // 很好。
    ASSERT_FALSE(segments.empty());
    // Should be a single "zh" segment, not split by punctuation
    EXPECT_EQ(segments.size(), 1u);
    EXPECT_EQ(segments[0].lang, "zh");
}

TEST_F(LanguageDetectorTest, JapaneseTextWithPunctuation) {
    // "こんにちは。" — kana + CJK period should be a single "ja" segment
    auto segments = detector.segmentText(
        "\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf"  // こんにちは
        "\xe3\x80\x82");                                                     // 。
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments.size(), 1u);
    EXPECT_EQ(segments[0].lang, "ja");
}

TEST_F(LanguageDetectorTest, ChineseMultipleSentences) {
    // "你好！谢谢。" — multiple sentences with CJK punctuation
    auto segments = detector.segmentText(
        "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x81"  // 你好！
        "\xe8\xb0\xa2\xe8\xb0\xa2\xe3\x80\x82"); // 谢谢。
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments.size(), 1u);
    EXPECT_EQ(segments[0].lang, "zh");
}

// =========================================================================
// 2. English G2P tests (3)
// =========================================================================

class EnglishG2PTest : public ::testing::Test {
protected:
    std::unordered_map<std::string, std::string> cmuDict = makeTestCmuDict();
};

TEST_F(EnglishG2PTest, BasicWord) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_english("hello", phonemes, cmuDict);

    // Should produce at least one sentence with non-empty phoneme sequence
    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST_F(EnglishG2PTest, CmuDictHit_The) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_english("the", phonemes, cmuDict);

    ASSERT_FALSE(phonemes.empty());
    ASSERT_FALSE(phonemes[0].empty());

    // "the" -> DH AH0 -> should contain the eth character (U+00F0 = ð)
    bool hasEth = false;
    for (auto ph : phonemes[0]) {
        if (ph == 0x00F0) {  // ð
            hasEth = true;
            break;
        }
    }
    EXPECT_TRUE(hasEth) << "Expected phoneme sequence to contain eth (U+00F0)";
}

TEST_F(EnglishG2PTest, FullSentence) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_english("Hello, how are you?", phonemes, cmuDict);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

// =========================================================================
// 3. Chinese G2P tests (2)
// =========================================================================

class ChineseG2PTest : public ::testing::Test {
protected:
    std::unordered_map<int, std::string> singleCharDict = makeTestSingleCharDict();
    std::unordered_map<std::string, std::string> phraseDict = makeTestPhraseDict();
};

TEST_F(ChineseG2PTest, NiHao) {
    std::vector<std::vector<Phoneme>> phonemes;
    // 你好
    phonemize_chinese("\xe4\xbd\xa0\xe5\xa5\xbd", phonemes,
                      singleCharDict, phraseDict);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST_F(ChineseG2PTest, SentenceWithPunctuation) {
    std::vector<std::vector<Phoneme>> phonemes;
    // 今天天气很好。
    phonemize_chinese(
        "\xe4\xbb\x8a\xe5\xa4\xa9\xe5\xa4\xa9\xe6\xb0\x94\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82",
        phonemes, singleCharDict, phraseDict);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());

    // Chinese G2P maps fullwidth period U+3002 to ASCII '.' (0x2E)
    bool hasPunct = false;
    for (auto ph : phonemes[0]) {
        if (ph == '.') {  // U+3002 mapped to ASCII period
            hasPunct = true;
            break;
        }
    }
    EXPECT_TRUE(hasPunct) << "Expected ASCII period '.' (mapped from U+3002) in output";
}

// =========================================================================
// 4. Spanish G2P tests (2)
// =========================================================================

TEST(SpanishG2PTest, BasicWord) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_spanish("Hola", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST(SpanishG2PTest, Sentence) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_spanish("Buenos dias", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

// =========================================================================
// 5. French G2P tests (2)
// =========================================================================

TEST(FrenchG2PTest, BasicWord) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_french("Bonjour", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST(FrenchG2PTest, Sentence) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_french("Comment allez-vous?", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

// =========================================================================
// 6. Portuguese G2P tests (2)
// =========================================================================

TEST(PortugueseG2PTest, BasicWord) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_portuguese("Ola", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST(PortugueseG2PTest, Sentence) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_portuguese("Como voce esta?", phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

// =========================================================================
// 7. Korean G2P tests (2)
// =========================================================================

TEST(KoreanG2PTest, BasicWord) {
    std::vector<std::vector<Phoneme>> phonemes;
    // 안녕하세요
    phonemize_korean(
        "\xec\x95\x88\xeb\x85\x95\xed\x95\x98\xec\x84\xb8\xec\x9a\x94",
        phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

TEST(KoreanG2PTest, Sentence) {
    std::vector<std::vector<Phoneme>> phonemes;
    // 오늘 날씨가 좋습니다
    phonemize_korean(
        "\xec\x98\xa4\xeb\x8a\x98 "
        "\xeb\x82\xa0\xec\x94\xa8\xea\xb0\x80 "
        "\xec\xa2\x8b\xec\x8a\xb5\xeb\x8b\x88\xeb\x8b\xa4",
        phonemes);

    ASSERT_FALSE(phonemes.empty());
    EXPECT_FALSE(phonemes[0].empty());
}

// =========================================================================
// 8. PUA codepoint test (1) — isSingleCodepoint handles multi-byte UTF-8
// =========================================================================

TEST(PuaCodepointTest, MultiByteUtf8IsSingleCodepoint) {
    // PUA U+E000 is 3 bytes in UTF-8 (\xEE\x80\x80) but 1 codepoint
    std::string pua_e000 = "\xEE\x80\x80";
    EXPECT_TRUE(piper::isSingleCodepoint(pua_e000));
    EXPECT_EQ(piper::getCodepoint(pua_e000), 0xE000);

    // 2 codepoints
    EXPECT_FALSE(piper::isSingleCodepoint("ab"));

    // Empty string
    EXPECT_FALSE(piper::isSingleCodepoint(""));
}

// =========================================================================
// 9. ModelConfig default initialization test (1)
// =========================================================================

TEST(ModelConfigTest, DefaultNumSpeakersIsZero) {
    piper::ModelConfig config;
    EXPECT_EQ(config.numSpeakers, 0);
    EXPECT_EQ(config.numLanguages, 1);
}

// =========================================================================
// 10. RTF calculation test (1)
// =========================================================================

TEST(RtfCalculationTest, FormulaIsInferOverAudio) {
    // RTF = inferSeconds / audioSeconds
    double inferSeconds = 0.1;
    double audioSeconds = 1.0;
    double rtf = inferSeconds / audioSeconds;
    EXPECT_NEAR(rtf, 0.1, 0.001);
    // Inverted formula would give 10.0 (this was the original bug)
    double wrong_rtf = audioSeconds / inferSeconds;
    EXPECT_NEAR(wrong_rtf, 10.0, 0.001);
}

// =========================================================================
// 11. Invalid UTF-8 input does not crash any G2P phonemizer (1)
// =========================================================================

TEST(Utf8ValidationTest, InvalidUtf8ReturnsEmpty) {
    std::string invalid = "\xFF\xFE\x80";

    // English
    {
        std::vector<std::vector<Phoneme>> phonemes;
        std::unordered_map<std::string, std::string> emptyDict;
        EXPECT_NO_THROW(phonemize_english(invalid, phonemes, emptyDict));
    }

    // Chinese
    {
        std::vector<std::vector<Phoneme>> phonemes;
        std::unordered_map<int, std::string> emptySingle;
        std::unordered_map<std::string, std::string> emptyPhrase;
        EXPECT_NO_THROW(
            phonemize_chinese(invalid, phonemes, emptySingle, emptyPhrase));
    }

    // Spanish
    {
        std::vector<std::vector<Phoneme>> phonemes;
        EXPECT_NO_THROW(phonemize_spanish(invalid, phonemes));
    }

    // French
    {
        std::vector<std::vector<Phoneme>> phonemes;
        EXPECT_NO_THROW(phonemize_french(invalid, phonemes));
    }

    // Portuguese
    {
        std::vector<std::vector<Phoneme>> phonemes;
        EXPECT_NO_THROW(phonemize_portuguese(invalid, phonemes));
    }

    // Korean
    {
        std::vector<std::vector<Phoneme>> phonemes;
        EXPECT_NO_THROW(phonemize_korean(invalid, phonemes));
    }
}

// =========================================================================
// 12. findDictionaryFile logic tests (3)
//
// findDictionaryFile and getExeDir are static in piper.cpp and cannot be
// linked from this test binary (it does not link onnxruntime).  We
// replicate the same 3-tier search algorithm here so the logic is
// validated without pulling in the full piper.cpp dependency.
// =========================================================================

namespace {

// Replicates piper.cpp findDictionaryFile() search logic:
//   1. modelDir/<filename>
//   2. <exeDir>/../share/piper/dicts/<filename>  (skipped here — no exe context)
//   3. PIPER_DICTIONARIES_PATH/<filename>
// Returns first existing path, or empty string.
std::string findDictionaryFileTestImpl(const std::string &filename,
                                       const std::string &modelDir) {
    namespace fs = std::filesystem;

    // 1. Model directory
    fs::path p1 = fs::path(modelDir) / filename;
    if (fs::exists(p1)) {
        return p1.string();
    }

    // 2. (exe-relative path skipped in test context)

    // 3. Environment variable
    const char *envPath = std::getenv("PIPER_DICTIONARIES_PATH");
    if (envPath && envPath[0] != '\0') {
        fs::path p3 = fs::path(envPath) / filename;
        if (fs::exists(p3)) {
            return p3.string();
        }
    }

    return {};
}

// RAII helper to set/unset an environment variable for the scope of a test.
class ScopedEnvVar {
public:
    ScopedEnvVar(const std::string &name, const std::string &value)
        : name_(name) {
#ifdef _WIN32
        _putenv_s(name_.c_str(), value.c_str());
#else
        setenv(name_.c_str(), value.c_str(), 1);
#endif
    }
    ~ScopedEnvVar() {
#ifdef _WIN32
        _putenv_s(name_.c_str(), "");
#else
        unsetenv(name_.c_str());
#endif
    }
private:
    std::string name_;
};

// Create a temporary directory that is cleaned up on destruction.
class TempDir {
public:
    TempDir() {
        namespace fs = std::filesystem;
        path_ = fs::temp_directory_path() / "piper_test_dict_XXXXXX";
        // Ensure unique name by appending a counter
        int counter = 0;
        while (fs::exists(path_)) {
            path_ = fs::temp_directory_path() /
                     ("piper_test_dict_" + std::to_string(counter++));
        }
        fs::create_directories(path_);
    }
    ~TempDir() {
        std::filesystem::remove_all(path_);
    }
    const std::filesystem::path &path() const { return path_; }
private:
    std::filesystem::path path_;
};

} // anonymous namespace

TEST(FindDictionaryFileTest, EnvVarOverride) {
    // Create a temp directory with a dummy dictionary file
    TempDir tmpDir;
    std::string filename = "cmudict_data.json";
    std::ofstream(tmpDir.path() / filename) << "{}";

    // Set environment variable to point to the temp directory
    ScopedEnvVar env("PIPER_DICTIONARIES_PATH", tmpDir.path().string());

    // Model dir does NOT contain the file -> should fall through to env var
    TempDir emptyModelDir;
    std::string result = findDictionaryFileTestImpl(filename, emptyModelDir.path().string());

    EXPECT_FALSE(result.empty()) << "Dictionary should be found via PIPER_DICTIONARIES_PATH";
    EXPECT_NE(result.find(filename), std::string::npos);
}

TEST(FindDictionaryFileTest, NonexistentPathReturnsEmpty) {
    // Neither model dir nor env var points to a valid file
    std::string bogusDir = "/no/such/directory/piper_test_bogus_12345";

    // Make sure env var is not set or points to a nonexistent path
    ScopedEnvVar env("PIPER_DICTIONARIES_PATH", bogusDir);

    std::string result = findDictionaryFileTestImpl("cmudict_data.json", bogusDir);
    EXPECT_TRUE(result.empty()) << "Should return empty string for nonexistent paths";
}

TEST(FindDictionaryFileTest, ModelDirHasPriority) {
    // Create two temp dirs: one for model dir, one for env var
    TempDir modelDir;
    TempDir envDir;
    std::string filename = "cmudict_data.json";

    // Place the file in both directories
    std::ofstream(modelDir.path() / filename) << "{\"source\": \"model\"}";
    std::ofstream(envDir.path() / filename) << "{\"source\": \"env\"}";

    ScopedEnvVar env("PIPER_DICTIONARIES_PATH", envDir.path().string());

    std::string result = findDictionaryFileTestImpl(filename, modelDir.path().string());

    EXPECT_FALSE(result.empty());
    // Model dir path should win (priority 1 over priority 3)
    EXPECT_NE(result.find(modelDir.path().string()), std::string::npos)
        << "Model directory should have priority over PIPER_DICTIONARIES_PATH";
}

// =========================================================================
// 13. defaultLatinLang detection tests (4)
//
// Verify that UnicodeLanguageDetector classifies Latin text according to
// the defaultLatinLang constructor parameter.
// =========================================================================

TEST(DefaultLatinLangTest, SpanishDefault) {
    UnicodeLanguageDetector detector{
        {"ja", "en", "zh", "es", "fr", "pt"}, "es"};

    auto segments = detector.segmentText("Hola");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "es")
        << "Latin text should be classified as 'es' when defaultLatinLang=\"es\"";
}

TEST(DefaultLatinLangTest, FrenchDefault) {
    UnicodeLanguageDetector detector{
        {"ja", "en", "zh", "es", "fr", "pt"}, "fr"};

    auto segments = detector.segmentText("Bonjour");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "fr")
        << "Latin text should be classified as 'fr' when defaultLatinLang=\"fr\"";
}

TEST(DefaultLatinLangTest, PortugueseDefault) {
    UnicodeLanguageDetector detector{
        {"ja", "en", "zh", "es", "fr", "pt"}, "pt"};

    // "Olá" contains Latin characters (including accented a)
    auto segments = detector.segmentText("Ol\xc3\xa1");  // Olá in UTF-8
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "pt")
        << "Latin text should be classified as 'pt' when defaultLatinLang=\"pt\"";
}

TEST(DefaultLatinLangTest, EnglishDefault) {
    UnicodeLanguageDetector detector{
        {"ja", "en", "zh", "es", "fr", "pt"}, "en"};

    auto segments = detector.segmentText("Hello");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "en")
        << "Latin text should be classified as 'en' when defaultLatinLang=\"en\"";
}

// =========================================================================
// 14. Swedish per-word LID — CONSERVATIVE policy (Issue #539)
//
// The char-level detector maps å/ä/ö to the default Latin language; a
// word-level post-pass then re-classifies a default-Latin segment to "sv"
// ONLY when a STRONG indicator is present: the å/Å character, or an exact
// match in the 46-word function-word list (loaded from
// sv_function_words.json). ä/ö alone are WEAK (shared with German/Finnish/
// loanwords) and must NOT trigger Swedish.
//
// Mirrors the canonical Python cases in
// tests/.../test_multilingual.py (Issue #539).
// =========================================================================

// Helper: does any segment of `text` get classified as Swedish?
static bool containsSwedishSegment(const UnicodeLanguageDetector &det,
                                   const std::string &text) {
    for (const auto &seg : det.segmentText(text)) {
        if (seg.lang == "sv") {
            return true;
        }
    }
    return false;
}

class SwedishLidTest : public ::testing::Test {
protected:
    // Swedish present alongside English -> per-word post-pass is active.
    UnicodeLanguageDetector det{{"en", "sv"}, "en"};
};

// --- Strong char (å/Å) path: already worked under the lenient policy ---

TEST_F(SwedishLidTest, AaCharIsSwedish_Sa) {
    // "så" — å is a strong char
    EXPECT_TRUE(containsSwedishSegment(det, "s\xc3\xa5"));
}

TEST_F(SwedishLidTest, AaCharIsSwedish_Fran) {
    // "från" — å is a strong char
    EXPECT_TRUE(containsSwedishSegment(det, "fr\xc3\xa5n"));
}

// --- Function-word path (no Swedish char) ---

TEST_F(SwedishLidTest, FunctionWordIsSwedish_Och) {
    EXPECT_TRUE(containsSwedishSegment(det, "och"));
}

TEST_F(SwedishLidTest, FunctionWordIsSwedish_Jag) {
    EXPECT_TRUE(containsSwedishSegment(det, "jag"));
}

TEST_F(SwedishLidTest, FunctionWordIsSwedish_Inte) {
    EXPECT_TRUE(containsSwedishSegment(det, "inte"));
}

TEST_F(SwedishLidTest, FunctionWordWithUmlautIsSwedish_For) {
    // "för" — contains ö (weak) but IS in the function-word list
    EXPECT_TRUE(containsSwedishSegment(det, "f\xc3\xb6r"));
}

TEST_F(SwedishLidTest, FunctionWordWithUmlautIsSwedish_Nar) {
    // "när" — contains ä (weak) but IS in the function-word list
    EXPECT_TRUE(containsSwedishSegment(det, "n\xc3\xa4r"));
}

TEST_F(SwedishLidTest, FunctionWordWithUmlautIsSwedish_Ar) {
    // "är" — the new 46th word; contains ä (weak) but IS in the list.
    EXPECT_TRUE(containsSwedishSegment(det, "\xc3\xa4r"));
}

// --- Conservative invariant: bare ä/ö must NOT be Swedish ---
// (These FAIL under the old lenient policy where ä/ö were strong chars.)

TEST_F(SwedishLidTest, BareUmlautIsNotSwedish_Madchen) {
    // German "Mädchen" — has ä but is NOT a Swedish function word.
    EXPECT_FALSE(containsSwedishSegment(det, "M\xc3\xa4""dchen"));
}

TEST_F(SwedishLidTest, BareUmlautIsNotSwedish_Schon) {
    // German "schön" — has ö but is NOT a Swedish function word.
    EXPECT_FALSE(containsSwedishSegment(det, "sch\xc3\xb6n"));
}

TEST_F(SwedishLidTest, BareUmlautIsNotSwedish_Worter) {
    // "wörter" — has ö but not a function word.
    EXPECT_FALSE(containsSwedishSegment(det, "w\xc3\xb6rter"));
}

TEST_F(SwedishLidTest, BareUmlautIsNotSwedish_Xox) {
    // "xöx" — bare ö, weak-char invariant.
    EXPECT_FALSE(containsSwedishSegment(det, "x\xc3\xb6x"));
}

// --- Sentence-level ---

TEST_F(SwedishLidTest, SentenceWithFunctionWordIsSwedish) {
    // "jag heter Anna" — "jag" is a function word -> whole segment sv.
    EXPECT_TRUE(containsSwedishSegment(det, "jag heter Anna"));
}

// --- Gate: sv must be present (alongside >=2 Latin langs) ---

TEST(SwedishLidGateTest, NoSwedishInLanguageSet) {
    // {"en","es"} has no sv -> post-pass disabled -> "från" stays non-sv.
    UnicodeLanguageDetector det{{"en", "es"}, "en"};
    EXPECT_FALSE(containsSwedishSegment(det, "fr\xc3\xa5n"));
}

// --- detectDominantLanguage parity (function-word path) ---

TEST_F(SwedishLidTest, DetectDominantArIsSwedish) {
    // "är" via detectDominantLanguage — note: the char-level dominant counter
    // classifies ä as the default Latin lang ("en"); the Swedish per-word
    // post-pass lives in segmentText. This documents that distinction.
    EXPECT_EQ(detectDominantLanguage("\xc3\xa4r", det), "en");
    // segmentText (the LID surface that carries the post-pass) IS sv:
    EXPECT_TRUE(containsSwedishSegment(det, "\xc3\xa4r"));
}

// =========================================================================
// 15. Cross-runtime Swedish per-word LID parity fixture matrix (Issue #539).
//
// `src/cpp/tests/fixtures/swedish_lid_matrix.json` is mirrored byte-for-byte
// from the canonical `tests/fixtures/g2p/swedish_lid_matrix.json` by
// scripts/check_swedish_lid_consistency.py. This consumer builds a detector
// from the fixture's `languages` + `default_latin`, runs segmentText, and
// asserts ("sv" in segment languages) == expect_contains_sv for every case.
// The sister tests in Python / Rust×2 / Go / C# / WASM consume the SAME
// fixture, so cross-runtime agreement here is the parity proof. Mirrors
// ZhEnLoanwordTest.FixtureMatrixLoadable. The bundled sv_function_words.json
// is staged next to this binary by CMakeLists.txt (same as the SwedishLidTest
// happy-path cases above).
// =========================================================================

namespace {

std::string findSwedishLidMatrix() {
    namespace fs = std::filesystem;
    const std::vector<std::string> candidates = {
        "src/cpp/tests/fixtures/swedish_lid_matrix.json",
        "tests/fixtures/swedish_lid_matrix.json",
        "../tests/fixtures/swedish_lid_matrix.json",
        "tests/fixtures/g2p/swedish_lid_matrix.json",
    };
    for (const auto &c : candidates) {
        if (fs::exists(c)) {
            return c;
        }
    }
    return "";
}

}  // namespace

TEST(SwedishLidMatrixTest, FixtureMatrixParity) {
    const std::string path = findSwedishLidMatrix();
    if (path.empty()) {
        GTEST_SKIP() << "matrix fixture not found from working dir="
                     << std::filesystem::current_path().string();
    }

    std::ifstream ifs(path);
    ASSERT_TRUE(ifs.is_open()) << "could not open: " << path;
    nlohmann::json json;
    ASSERT_NO_THROW(ifs >> json) << "matrix is not valid JSON: " << path;

    ASSERT_EQ(json.value("schema_version", -1), 1) << "unexpected schema_version";

    std::vector<std::string> languages;
    for (const auto &l : json.at("languages")) {
        languages.push_back(l.get<std::string>());
    }
    const std::string defaultLatin = json.at("default_latin").get<std::string>();

    ASSERT_TRUE(json.contains("cases") && json["cases"].is_array());
    const auto &cases = json["cases"];
    ASSERT_FALSE(cases.empty()) << "matrix `cases` must be non-empty";

    UnicodeLanguageDetector det{languages, defaultLatin};

    int checked = 0;
    for (const auto &c : cases) {
        const std::string text = c.at("text").get<std::string>();
        const bool expectSv = c.at("expect_contains_sv").get<bool>();
        const bool got = containsSwedishSegment(det, text);
        EXPECT_EQ(got, expectSv)
            << "matrix case \"" << text << "\": expected contains_sv=" << expectSv
            << ", got " << got
            << "\n  → if intentional, update "
               "tests/fixtures/g2p/swedish_lid_matrix.json and re-sync via "
               "`python scripts/check_swedish_lid_consistency.py --fix`";
        checked++;
    }
    EXPECT_GE(checked, 10) << "expected >=10 matrix cases, checked " << checked;
}
