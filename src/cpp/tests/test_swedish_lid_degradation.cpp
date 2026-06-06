/**
 * Swedish per-word LID — DEGRADATION-PATH test (Issue #539).
 *
 * Companion to the happy-path SwedishLidTest cases in test_multilingual_g2p.cpp.
 * This binary is deliberately built WITHOUT staging sv_function_words.json next
 * to it (and it runs from the repo root, where no `data/sv_function_words.json`
 * exists), so the std::call_once loader in language_detector.cpp finds no data
 * and leaves BOTH the function-word set and the strong-char set EMPTY.
 *
 * The contract being pinned: with the JSON absent, C++ matches Python/Rust/Go
 * exactly — there is NO hardcoded fallback for the strong chars (å/Å), so the
 * entire per-word post-pass no-ops. "så" / "från" are NOT reclassified to "sv"
 * (they stay the default Latin language), and neither are function words like
 * "och". This is the regression guard that prevents anyone re-introducing a
 * hardcoded å/Å fallback (which would make C++ diverge from the other runtimes
 * on the degradation path).
 *
 * Self-contained: links only language_detector.cpp + library_path.c + gtest
 * (language_detector.cpp pulls in json.hpp / utf8.h header-only — no
 * spdlog/fmt/ORT/OpenJTalk dependency).
 */

#include <gtest/gtest.h>
#include <string>

#include "../language_detector.hpp"

using namespace piper;

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

class SwedishLidDegradationTest : public ::testing::Test {
protected:
    // sv present alongside en -> the per-word post-pass *would* run, but with
    // no JSON data loaded it has nothing to match on.
    UnicodeLanguageDetector det{{"en", "sv"}, "en"};
};

// --- Strong-char (å/Å) path: NO hardcoded fallback ---
// Under the OLD design (hardcoded å/Å), "så" would still become sv even with
// the JSON absent. The conservative + JSON-only design makes it stay default.

TEST_F(SwedishLidDegradationTest, AaChar_NotSwedish_WhenJsonAbsent_Sa) {
    // "så" — å is a strong char per the JSON, but the JSON is absent here, so
    // the strong-char set is empty and "så" is NOT reclassified to sv.
    EXPECT_FALSE(containsSwedishSegment(det, "s\xc3\xa5"));
}

TEST_F(SwedishLidDegradationTest, AaChar_NotSwedish_WhenJsonAbsent_Fran) {
    // "från" — same: å present but strong-char set is empty -> not sv.
    EXPECT_FALSE(containsSwedishSegment(det, "fr\xc3\xa5n"));
}

// --- Function-word path also no-ops ---

TEST_F(SwedishLidDegradationTest, FunctionWord_NotSwedish_WhenJsonAbsent_Och) {
    // "och" — a function word per the JSON, but the function-word set is empty
    // here -> not sv.
    EXPECT_FALSE(containsSwedishSegment(det, "och"));
}

TEST_F(SwedishLidDegradationTest, Sentence_NotSwedish_WhenJsonAbsent) {
    // "jag heter Anna" — no data loaded -> whole post-pass no-ops -> not sv.
    EXPECT_FALSE(containsSwedishSegment(det, "jag heter Anna"));
}

// --- Sanity: a plain English word is unaffected either way ---

TEST_F(SwedishLidDegradationTest, EnglishStaysEnglish_WhenJsonAbsent) {
    auto segments = det.segmentText("hello");
    ASSERT_FALSE(segments.empty());
    EXPECT_EQ(segments[0].lang, "en");
    EXPECT_FALSE(containsSwedishSegment(det, "hello"));
}
