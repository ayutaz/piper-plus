#include "language_detector.hpp"
#include "utf8.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <map>
#include <unordered_set>

namespace piper {

// ---------------------------------------------------------------------------
// Static Unicode range helpers
// ---------------------------------------------------------------------------

// Hiragana: U+3040-309F, Katakana: U+30A0-30FF, Katakana Phonetic Ext: U+31F0-31FF,
// Halfwidth Katakana: U+FF65-FF9F
bool UnicodeLanguageDetector::isKana(char32_t cp) {
    return (cp >= 0x3040 && cp <= 0x309F) ||
           (cp >= 0x30A0 && cp <= 0x30FF) ||
           (cp >= 0x31F0 && cp <= 0x31FF) ||
           (cp >= 0xFF65 && cp <= 0xFF9F);
}

// CJK Unified Ideographs: U+4E00-9FFF, Extension A: U+3400-4DBF,
// CJK Compatibility Ideographs: U+F900-FAFF
bool UnicodeLanguageDetector::isCJK(char32_t cp) {
    return (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0x3400 && cp <= 0x4DBF) ||
           (cp >= 0xF900 && cp <= 0xFAFF);
}

// Hangul Syllables: U+AC00-D7AF, Jamo: U+1100-11FF, Compat Jamo: U+3130-318F,
// Halfwidth Hangul: U+FFA0-FFDC
bool UnicodeLanguageDetector::isHangul(char32_t cp) {
    return (cp >= 0xAC00 && cp <= 0xD7AF) ||
           (cp >= 0x1100 && cp <= 0x11FF) ||
           (cp >= 0x3130 && cp <= 0x318F) ||
           (cp >= 0xFFA0 && cp <= 0xFFDC);
}

// Fullwidth Latin letters: U+FF21-FF3A (A-Z), U+FF41-FF5A (a-z)
bool UnicodeLanguageDetector::isFullwidthLatin(char32_t cp) {
    return (cp >= 0xFF21 && cp <= 0xFF3A) ||
           (cp >= 0xFF41 && cp <= 0xFF5A);
}

// CJK shared punctuation: CJK punctuation (U+3000-303F) + fullwidth
// forms, EXCLUDING fullwidth Latin letters (handled by isFullwidthLatin),
// halfwidth Katakana (FF65-FF9F, handled by isKana), and
// halfwidth Hangul (FFA0-FFDC, handled by isHangul).
bool UnicodeLanguageDetector::isCJKPunct(char32_t cp) {
    return (cp >= 0x3000 && cp <= 0x303F) ||
           (cp >= 0xFF00 && cp <= 0xFF20) ||  // Fullwidth digits & symbols
           (cp >= 0xFF3B && cp <= 0xFF40) ||  // Fullwidth brackets & symbols
           (cp >= 0xFF5B && cp <= 0xFF64) ||  // Fullwidth braces & misc symbols
           (cp >= 0xFFE0 && cp <= 0xFFEF);    // Fullwidth currency & misc
}

// Basic Latin + Latin Extended-A diacritics.
// Excludes U+00D7 (multiplication sign) and U+00F7 (division sign) which
// fall inside the A0-FF range but are not letters.
bool UnicodeLanguageDetector::isLatin(char32_t cp) {
    return (cp >= 'A' && cp <= 'Z') ||
           (cp >= 'a' && cp <= 'z') ||
           (cp >= 0x00C0 && cp <= 0x00D6) ||  // A-grave .. O-diaeresis
           (cp >= 0x00D8 && cp <= 0x00F6) ||  // O-stroke .. o-diaeresis
           (cp >= 0x00F8 && cp <= 0x00FF);    // o-stroke .. y-diaeresis
}

// Swedish-specific characters not used by EN/ES/PT/FR:
// ä (U+00E4), ö (U+00F6), å (U+00E5) and their uppercase variants.
// å is shared with DA/NO but neither is in piper-plus, so it's a safe indicator.
bool UnicodeLanguageDetector::isSwedishChar(char32_t cp) {
    return cp == 0x00E4 || cp == 0x00F6 || cp == 0x00E5 ||   // ä ö å
           cp == 0x00C4 || cp == 0x00D6 || cp == 0x00C5;     // Ä Ö Å
}

// Swedish function words -- highly distinctive, do not appear in EN/ES/PT/FR.
// Same 45 words as the Python implementation.
const std::unordered_set<std::string>
    UnicodeLanguageDetector::SWEDISH_FUNCTION_WORDS = {
        "och", "att", "jag", "det", "den", "inte", "som", "han", "hon",
        "var", "har", "kan", "ska", "med", "för", "sig", "sin", "min",
        "din", "vill", "från", "när", "här", "där", "också", "alla",
        "denna", "efter", "eller", "under", "utan", "mycket", "mellan",
        "genom", "bara", "sedan", "redan", "aldrig", "alltid", "igen",
        "något", "några", "varje", "vilken", "vilket",
};

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------

UnicodeLanguageDetector::UnicodeLanguageDetector(
    const std::vector<std::string>& languages,
    const std::string& defaultLatinLang)
    : languages_(languages.begin(), languages.end()),
      defaultLatinLang_(defaultLatinLang),
      hasJa_(languages_.count("ja") > 0),
      hasZh_(languages_.count("zh") > 0),
      hasKo_(languages_.count("ko") > 0),
      hasSv_(languages_.count("sv") > 0),
      detectSwedish_(false) {
    // Enable Swedish detection when sv is present alongside at least one
    // other Latin-script language (mirrors Python's _detect_swedish logic).
    static const std::set<std::string> latinLangs = {"en", "es", "pt", "fr", "sv"};
    if (hasSv_) {
        int latinCount = 0;
        for (const auto& lang : languages_) {
            if (latinLangs.count(lang) > 0) {
                latinCount++;
            }
        }
        detectSwedish_ = (latinCount >= 2);
    }
}

// ---------------------------------------------------------------------------
// detectChar -- priority order matches Python implementation exactly
// ---------------------------------------------------------------------------

std::string UnicodeLanguageDetector::detectChar(char32_t ch,
                                                bool contextHasKana) const {
    // 1. Kana -> always Japanese
    if (isKana(ch)) {
        return hasJa_ ? "ja" : "";
    }

    // 2. Hangul -> Korean
    if (isHangul(ch)) {
        return hasKo_ ? "ko" : "";
    }

    // 3. CJK ideographs -> JA or ZH depending on context
    if (isCJK(ch)) {
        if (hasJa_ && hasZh_) {
            return contextHasKana ? "ja" : "zh";
        }
        if (hasJa_) return "ja";
        if (hasZh_) return "zh";
        return "";
    }

    // 4. Fullwidth Latin letters (before JaPunct check!)
    if (isFullwidthLatin(ch)) {
        if (languages_.count(defaultLatinLang_) > 0) {
            return defaultLatinLang_;
        }
        return "";
    }

    // 5. CJK punctuation — treat as neutral so it joins the surrounding segment
    //    (same behavior as ASCII punctuation in step 7)
    if (isCJKPunct(ch)) {
        return "";
    }

    // 6. Latin characters
    if (isLatin(ch)) {
        if (languages_.count(defaultLatinLang_) > 0) {
            return defaultLatinLang_;
        }
        return "";
    }

    // 7. Neutral: whitespace, digits, ASCII punctuation, etc.
    return "";
}

// ---------------------------------------------------------------------------
// hasKana -- scan UTF-8 text for any kana codepoint
// ---------------------------------------------------------------------------

bool UnicodeLanguageDetector::hasKana(const std::string& utf8Text) const {
    if (!utf8::is_valid(utf8Text.begin(), utf8Text.end())) {
        return false;
    }

    auto it = utf8Text.begin();
    auto end = utf8Text.end();
    while (it != end) {
        uint32_t cp = utf8::unchecked::next(it);
        if (isKana(static_cast<char32_t>(cp))) {
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// segmentText -- state machine matching Python's _segment_text_multilingual
// ---------------------------------------------------------------------------

std::vector<LangSegment> UnicodeLanguageDetector::segmentText(
    const std::string& utf8Text) const {

    if (!utf8::is_valid(utf8Text.begin(), utf8Text.end())) {
        return {};
    }

    // Check if the text is empty or whitespace-only
    bool hasNonWhitespace = false;
    for (char c : utf8Text) {
        if (c != ' ' && c != '\t' && c != '\n' && c != '\r') {
            hasNonWhitespace = true;
            break;
        }
    }
    if (!hasNonWhitespace) {
        return {};
    }

    // Pre-scan for kana to help CJK disambiguation
    bool contextHasKana = hasKana(utf8Text);

    std::vector<LangSegment> segments;
    std::string currentLang;      // empty = no language assigned yet
    std::string currentChars;     // accumulated UTF-8 bytes

    auto it = utf8Text.begin();
    auto end = utf8Text.end();

    while (it != end) {
        // Remember the byte position before decoding the codepoint so we can
        // extract the raw UTF-8 bytes for this character.
        auto charStart = it;
        uint32_t cp = utf8::unchecked::next(it);  // advances 'it'

        std::string lang = detectChar(static_cast<char32_t>(cp), contextHasKana);

        // Flush on language change (only when both old and new are non-empty
        // and different).
        if (!lang.empty() && lang != currentLang && !currentLang.empty()) {
            segments.push_back({currentLang, currentChars});
            currentChars.clear();
        }

        // Update current language when we see a language-specific char
        if (!lang.empty()) {
            currentLang = lang;
        }

        // Append the raw UTF-8 bytes for this codepoint
        currentChars.append(charStart, it);
    }

    // Flush remaining
    if (!currentChars.empty() && !currentLang.empty()) {
        segments.push_back({currentLang, currentChars});
    }

    // Fallback: if no language-specific characters were detected (e.g. text
    // is only numbers/URLs/punctuation), use the default Latin language so
    // the text is processed rather than silently dropped.
    if (segments.empty() && hasNonWhitespace) {
        segments.push_back({defaultLatinLang_, utf8Text});
    }

    // Post-pass: word-level Swedish detection within Latin segments.
    // When sv is in the language set alongside other Latin languages,
    // re-examine default-Latin segments for Swedish function words / chars.
    if (detectSwedish_) {
        segments = refineLatinSegmentsForSwedish(std::move(segments));
    }

    return segments;
}

// ---------------------------------------------------------------------------
// refineLatinSegmentsForSwedish -- post-pass matching Python's
// _refine_latin_segments_for_swedish
// ---------------------------------------------------------------------------

// Helper: lowercased UTF-8 codepoint (ASCII + Swedish letters only)
static char32_t toLowerCP(char32_t cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    if (cp == 0x00C4) return 0x00E4; // Ä -> ä
    if (cp == 0x00D6) return 0x00F6; // Ö -> ö
    if (cp == 0x00C5) return 0x00E5; // Å -> å
    return cp;
}

// Helper: convert UTF-8 string to lowercase (ASCII + Swedish diacritics)
static std::string toLowerUTF8(const std::string& s) {
    std::string result;
    result.reserve(s.size());
    auto it = s.begin();
    auto end = s.end();
    while (it != end) {
        uint32_t cp = utf8::unchecked::next(it);
        char32_t lower = toLowerCP(static_cast<char32_t>(cp));
        utf8::unchecked::append(lower, std::back_inserter(result));
    }
    return result;
}

// Helper: strip leading/trailing punctuation (.,;:!?) from a UTF-8 word
static std::string stripPunct(const std::string& word) {
    static const std::string punct = ".,;:!?";
    auto begin = word.begin();
    auto end = word.end();
    // Strip leading
    while (begin != end) {
        auto next = begin;
        uint32_t cp = utf8::unchecked::peek_next(next);
        if (cp < 128 && punct.find(static_cast<char>(cp)) != std::string::npos) {
            utf8::unchecked::next(begin);
        } else {
            break;
        }
    }
    // Strip trailing -- work on the remaining substring
    std::string trimmed(begin, end);
    while (!trimmed.empty()) {
        // Find the last codepoint
        auto it = trimmed.begin();
        auto last = it;
        while (it != trimmed.end()) {
            last = it;
            utf8::unchecked::next(it);
        }
        uint32_t cp = utf8::unchecked::peek_next(last);
        if (cp < 128 && punct.find(static_cast<char>(cp)) != std::string::npos) {
            trimmed.erase(last, trimmed.end());
        } else {
            break;
        }
    }
    return trimmed;
}

std::vector<LangSegment> UnicodeLanguageDetector::refineLatinSegmentsForSwedish(
    std::vector<LangSegment> segments) const {
    // If Swedish IS the default Latin language, no refinement needed --
    // all Latin segments are already classified as "sv".
    if (defaultLatinLang_ == "sv") {
        return segments;
    }

    std::vector<LangSegment> result;
    result.reserve(segments.size());

    for (auto& seg : segments) {
        if (seg.lang != defaultLatinLang_) {
            result.push_back(std::move(seg));
            continue;
        }

        // Count Swedish indicators in this segment
        int svScore = 0;

        // Split on whitespace and check each word
        std::string remaining = seg.text;
        size_t pos = 0;
        while (pos < remaining.size()) {
            // Skip whitespace
            while (pos < remaining.size() && (remaining[pos] == ' ' ||
                   remaining[pos] == '\t' || remaining[pos] == '\n' ||
                   remaining[pos] == '\r')) {
                pos++;
            }
            if (pos >= remaining.size()) break;

            // Find word boundary
            size_t wordStart = pos;
            while (pos < remaining.size() && remaining[pos] != ' ' &&
                   remaining[pos] != '\t' && remaining[pos] != '\n' &&
                   remaining[pos] != '\r') {
                pos++;
            }

            std::string word = remaining.substr(wordStart, pos - wordStart);
            std::string wordLower = toLowerUTF8(stripPunct(word));
            if (wordLower.empty()) continue;

            // Check for Swedish-specific characters (ä/ö/å)
            bool hasSvChar = false;
            {
                auto wit = wordLower.begin();
                auto wend = wordLower.end();
                while (wit != wend) {
                    uint32_t cp = utf8::unchecked::next(wit);
                    if (isSwedishChar(static_cast<char32_t>(cp))) {
                        hasSvChar = true;
                        break;
                    }
                }
            }

            if (hasSvChar) {
                svScore++;
            } else if (SWEDISH_FUNCTION_WORDS.count(wordLower) > 0) {
                // Swedish function words (only checked when no Swedish char
                // was found, matching Python's elif logic)
                svScore++;
            }
        }

        if (svScore >= 1) {
            result.push_back({"sv", std::move(seg.text)});
        } else {
            result.push_back(std::move(seg));
        }
    }

    return result;
}

// ---------------------------------------------------------------------------
// detectDominantLanguage -- count characters per language, return the max
// ---------------------------------------------------------------------------

std::string detectDominantLanguage(
    const std::string& utf8Text,
    const UnicodeLanguageDetector& detector) {

    if (!utf8::is_valid(utf8Text.begin(), utf8Text.end())) {
        return detector.defaultLatinLanguage();
    }

    bool contextHasKana = detector.hasKana(utf8Text);

    std::map<std::string, int> counts;
    auto it = utf8Text.begin();
    auto end = utf8Text.end();

    while (it != end) {
        uint32_t cp = utf8::unchecked::next(it);
        std::string lang = detector.detectChar(static_cast<char32_t>(cp),
                                               contextHasKana);
        if (!lang.empty()) {
            counts[lang]++;
        }
    }

    if (counts.empty()) {
        return detector.defaultLatinLanguage();
    }

    // Find the language with the highest count
    auto best = std::max_element(
        counts.begin(), counts.end(),
        [](const std::pair<std::string, int>& a,
           const std::pair<std::string, int>& b) {
            return a.second < b.second;
        });

    return best->first;
}

} // namespace piper
