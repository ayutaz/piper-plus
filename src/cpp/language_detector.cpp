#include "language_detector.hpp"
#include "utf8.h"

#include <algorithm>
#include <cstdint>
#include <map>

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
      hasKo_(languages_.count("ko") > 0) {
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

    return segments;
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
