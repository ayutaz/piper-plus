#ifndef LANGUAGE_DETECTOR_HPP
#define LANGUAGE_DETECTOR_HPP

#include <string>
#include <vector>
#include <set>

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

    std::set<std::string> languages_;
    std::string defaultLatinLang_;
    bool hasJa_;
    bool hasZh_;
    bool hasKo_;
};

// Detect the dominant language in text (most non-neutral characters)
std::string detectDominantLanguage(
    const std::string& utf8Text,
    const UnicodeLanguageDetector& detector);

} // namespace piper

#endif // LANGUAGE_DETECTOR_HPP
