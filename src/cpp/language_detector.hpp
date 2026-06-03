#ifndef LANGUAGE_DETECTOR_HPP
#define LANGUAGE_DETECTOR_HPP

#include <string>
#include <vector>
#include <set>
#include <unordered_set>

namespace piper {

struct LangSegment {
    std::string lang;  // "ja", "en", "zh", "ko", etc.
    std::string text;  // UTF-8 text for this segment
};

class UnicodeLanguageDetector {
public:
    UnicodeLanguageDetector(const std::vector<std::string>& languages,
                            const std::string& defaultLatinLang = "en");

    // Detect language for a single Unicode codepoint
    // Returns empty string for neutral characters
    std::string detectChar(char32_t ch, bool contextHasKana) const;

    // Check if UTF-8 text contains any kana characters
    bool hasKana(const std::string& utf8Text) const;

    // Segment UTF-8 text into language/text pairs
    std::vector<LangSegment> segmentText(const std::string& utf8Text) const;

    const std::string& defaultLatinLanguage() const { return defaultLatinLang_; }

private:
    static bool isKana(char32_t cp);
    static bool isHangul(char32_t cp);
    static bool isCJK(char32_t cp);
    static bool isFullwidthLatin(char32_t cp);
    static bool isCJKPunct(char32_t cp);
    static bool isLatin(char32_t cp);

    // CONSERVATIVE Swedish strong-char test (Issue #539): true only for
    // codepoints in the JSON-loaded ``strong_chars`` set (canonically å/Å).
    // ä/ö are deliberately NOT in that set — they are shared with
    // German/Finnish/loanwords, so a bare ä/ö is NOT a sufficient Swedish
    // indicator. The set is loaded from ``sv_function_words.json`` (no
    // hardcoded fallback), so this matches Python/Rust/Go exactly, including
    // on the degradation path (empty set when the JSON is absent/malformed).
    static bool isSwedishStrongChar(char32_t cp);

    // Post-pass: re-classify Latin segments as Swedish based on indicators
    std::vector<LangSegment> refineLatinSegmentsForSwedish(
        std::vector<LangSegment> segments) const;

    // Swedish function words loaded from ``sv_function_words.json`` (the
    // LID-discriminative 46-word list — distinct from the prosody/stress list
    // in swedish_phonemize.cpp). Highly distinctive, not shared with
    // EN/ES/PT/FR. Loaded once (process-wide, ``std::call_once``) and shared.
    static const std::unordered_set<std::string>& swedishFunctionWords();

    // Swedish strong characters loaded from ``sv_function_words.json``
    // (``strong_chars``, canonically å/Å), decoded to codepoints. Loaded by
    // the same ``std::call_once`` initializer as swedishFunctionWords(); both
    // degrade to an empty set on JSON load failure (mirrors Python/Rust/Go).
    static const std::unordered_set<char32_t>& swedishStrongChars();

    std::set<std::string> languages_;
    std::string defaultLatinLang_;
    bool hasJa_;
    bool hasZh_;
    bool hasKo_;
    bool hasSv_;
    bool detectSwedish_;  // sv present alongside other Latin languages
};

// Detect the dominant language in text (most non-neutral characters)
std::string detectDominantLanguage(
    const std::string& utf8Text,
    const UnicodeLanguageDetector& detector);

} // namespace piper

#endif // LANGUAGE_DETECTOR_HPP
