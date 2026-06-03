#include "language_detector.hpp"
#include "utf8.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_set>

#include "json.hpp"
#ifndef PIPER_PLUS_EMBEDDED_SV_FUNCTION_WORDS
#include "library_path.h"
#endif

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

// CONSERVATIVE Swedish strong-char test (Issue #539): true only for codepoints
// in the JSON-loaded ``strong_chars`` set (canonically å U+00E5 / Å U+00C5).
// ä/ö are deliberately NOT in that set -- they are shared with German /
// Finnish / loanwords, so a bare ä/ö is NOT sufficient to classify a word as
// Swedish (e.g. German "schön" / "Mädchen" must stay non-Swedish). The set
// comes entirely from ``sv_function_words.json`` (no hardcoded fallback), so
// this matches Python/Rust/Go -- including on the degradation path: when the
// JSON is absent/malformed the set is empty and the whole post-pass no-ops.
bool UnicodeLanguageDetector::isSwedishStrongChar(char32_t cp) {
    return swedishStrongChars().count(cp) > 0;
}

namespace {

// -------------------------------------------------------------------------
// Lowercasing helpers (ASCII + the three Swedish diacritics). Shared by the
// function-word loader below and refineLatinSegmentsForSwedish further down.
// -------------------------------------------------------------------------

// Lowercased UTF-8 codepoint (ASCII + Swedish letters only).
char32_t toLowerCP(char32_t cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    if (cp == 0x00C4) return 0x00E4; // Ä -> ä
    if (cp == 0x00D6) return 0x00F6; // Ö -> ö
    if (cp == 0x00C5) return 0x00E5; // Å -> å
    return cp;
}

// Convert a UTF-8 string to lowercase (ASCII + Swedish diacritics).
std::string toLowerUTF8(const std::string& s) {
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

// -------------------------------------------------------------------------
// Swedish LID data loader (Issue #539).
//
// Mirrors the ZH-EN loanword loader (chinese_loanword.cpp): the JSON is
// either compile-time embedded (Apple-embedded / Android, via the CMake
// `piper_embed_json_as_header()` -generated header) or loaded at runtime from
// `<exe-dir>/data/sv_function_words.json` on desktop. Both the
// `function_words` set and the `strong_chars` set are parsed here and cached
// behind a single `std::call_once`.
//
// Forward-compatible: unknown top-level keys (a future `schema_version` bump
// or added sections) are ignored. Missing / malformed data degrades gracefully
// to EMPTY sets for BOTH function_words and strong_chars -- so the entire
// per-word post-pass no-ops (å is not detected either). This matches the
// Python/Rust/Go loaders, which likewise carry no hardcoded fallback.
// -------------------------------------------------------------------------
#ifdef PIPER_PLUS_EMBEDDED_SV_FUNCTION_WORDS
#include "sv_function_words_data.h"  // CMake-generated by piper_embed_json_as_header()
inline std::string loadEmbeddedSvFunctionWordsJson() {
    return std::string(reinterpret_cast<const char*>(sv_function_words_json),
                       sv_function_words_json_len);
}
#else
std::string getSvFunctionWordsPath() {
    // Beside the executable, in the conventional dict_dir layout used by the
    // desktop installer (`<exe-dir>/data/sv_function_words.json`), mirroring
    // the loanword loader.
    std::array<char, 4096> buf{};
    if (piper_plus_get_exe_dir(buf.data(), static_cast<int>(buf.size())) == 0) {
        std::string dir(buf.data());
        return dir + "/data/sv_function_words.json";
    }
    return "data/sv_function_words.json";  // CWD-relative fallback
}
#endif

std::unordered_set<std::string> g_svFunctionWords;
std::unordered_set<char32_t> g_svStrongChars;
std::once_flag g_svDataInitFlag;

void initSvData() {
    std::string json;
#ifdef PIPER_PLUS_EMBEDDED_SV_FUNCTION_WORDS
    json = loadEmbeddedSvFunctionWordsJson();
#else
    const std::string path = getSvFunctionWordsPath();
    std::ifstream ifs(path);
    if (!ifs) {
        // Missing bundle -> both sets stay empty -> whole post-pass no-ops.
        return;
    }
    std::ostringstream buf;
    buf << ifs.rdbuf();
    json = buf.str();
#endif

    try {
        nlohmann::json root = nlohmann::json::parse(json);
        if (!root.is_object()) {
            return;  // malformed -> graceful no-op (both sets empty)
        }
        // function_words: list[str], lowercased on load. Any other (future)
        // keys are ignored for forward-compat.
        auto fwIt = root.find("function_words");
        if (fwIt != root.end() && fwIt->is_array()) {
            for (const auto& elem : *fwIt) {
                if (elem.is_string()) {
                    std::string w = elem.get<std::string>();
                    if (!w.empty()) {
                        g_svFunctionWords.insert(toLowerUTF8(w));
                    }
                }
            }
        }
        // strong_chars: list[str], each a single-codepoint UTF-8 string
        // (canonically "å"/"Å"). Decode each to its codepoint -- same as the
        // matching Python/Rust/Go loaders. A multi-codepoint string would only
        // contribute its first codepoint; the JSON is single-codepoint by
        // contract (enforced by the CI sync gate).
        auto scIt = root.find("strong_chars");
        if (scIt != root.end() && scIt->is_array()) {
            for (const auto& elem : *scIt) {
                if (elem.is_string()) {
                    std::string s = elem.get<std::string>();
                    if (!s.empty()) {
                        auto sit = s.begin();
                        uint32_t cp = utf8::unchecked::next(sit);
                        g_svStrongChars.insert(static_cast<char32_t>(cp));
                    }
                }
            }
        }
    } catch (const std::exception&) {
        // Corrupt / truncated JSON -> graceful no-op: clear BOTH sets so a
        // partial parse never leaves an inconsistent state (mirrors Python).
        g_svFunctionWords.clear();
        g_svStrongChars.clear();
    }
}

}  // namespace

const std::unordered_set<std::string>&
UnicodeLanguageDetector::swedishFunctionWords() {
    std::call_once(g_svDataInitFlag, initSvData);
    return g_svFunctionWords;
}

const std::unordered_set<char32_t>&
UnicodeLanguageDetector::swedishStrongChars() {
    std::call_once(g_svDataInitFlag, initSvData);
    return g_svStrongChars;
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
//
// toLowerCP / toLowerUTF8 are defined in the anonymous namespace above (shared
// with the function-word loader); stripPunct is local to this post-pass.
// ---------------------------------------------------------------------------

// Helper: strip leading/trailing punctuation (.,;:!?) from a UTF-8 word.
// The 5-mark strip set (. , ; : ! ?) is PINNED across all runtimes
// (Python/Rust/Go/C++) for byte-identical tokenization -- do not broaden it.
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

            // CONSERVATIVE strong-char check (Issue #539): only å/Å count as a
            // strong Swedish indicator. ä/ö are NOT strong (shared with German
            // etc.), so e.g. "schön" / "Mädchen" / "wörter" do NOT match here.
            bool hasSvStrongChar = false;
            {
                auto wit = wordLower.begin();
                auto wend = wordLower.end();
                while (wit != wend) {
                    uint32_t cp = utf8::unchecked::next(wit);
                    if (isSwedishStrongChar(static_cast<char32_t>(cp))) {
                        hasSvStrongChar = true;
                        break;
                    }
                }
            }

            if (hasSvStrongChar) {
                svScore++;
            } else if (swedishFunctionWords().count(wordLower) > 0) {
                // Swedish function words (only checked when no strong char was
                // found, matching Python's elif logic). 46-word list loaded
                // from sv_function_words.json (incl. "är").
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
