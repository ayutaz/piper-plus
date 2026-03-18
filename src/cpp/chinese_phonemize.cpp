// Chinese (Mandarin) phonemizer for Piper TTS — C++ port of chinese.py.
//
// Converts Chinese text to IPA phonemes via pinyin intermediate representation.
// Uses pypinyin-format JSON dictionaries for character-to-pinyin conversion,
// then applies normalization, tone sandhi, and IPA mapping identical to the
// Python pipeline.
//
// No runtime Python dependency — dictionaries are loaded from JSON at startup.

#include "chinese_phonemize.hpp"
#include "json.hpp"
#include "utf8.h"
#include "utf8_utils.hpp"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using json = nlohmann::json;

namespace piper {
namespace {

// =========================================================================
// PUA codepoints for multi-character IPA tokens
// Must match token_mapper.py dynamic allocation order from zh_id_map.py.
// =========================================================================

// --- Initials ---
constexpr Phoneme PUA_PH     = 0xE020; // p aspirated
constexpr Phoneme PUA_TH     = 0xE021; // t aspirated
constexpr Phoneme PUA_KH     = 0xE022; // k aspirated
constexpr Phoneme PUA_TC     = 0xE023; // alveolo-palatal affricate
constexpr Phoneme PUA_TCH    = 0xE024; // alveolo-palatal affricate aspirated
constexpr Phoneme PUA_TRS    = 0xE025; // retroflex affricate
constexpr Phoneme PUA_TRSH   = 0xE026; // retroflex affricate aspirated
constexpr Phoneme PUA_TSH    = 0xE027; // alveolar affricate aspirated

// --- Diphthongs ---
constexpr Phoneme PUA_AI     = 0xE028; // ai
constexpr Phoneme PUA_EI     = 0xE029; // ei
constexpr Phoneme PUA_AU     = 0xE02A; // ao
constexpr Phoneme PUA_OU     = 0xE02B; // ou

// --- Nasal finals ---
constexpr Phoneme PUA_AN     = 0xE02C; // an
constexpr Phoneme PUA_EN     = 0xE02D; // en (schwa+n)
constexpr Phoneme PUA_ANG    = 0xE02E; // ang
constexpr Phoneme PUA_ENG    = 0xE02F; // eng (schwa+ng)
constexpr Phoneme PUA_UNG    = 0xE030; // ong (u+ng)

// --- i-compound finals ---
constexpr Phoneme PUA_IA     = 0xE031; // ia
constexpr Phoneme PUA_IE     = 0xE032; // ie (i + open-e)
constexpr Phoneme PUA_IOU    = 0xE033; // iu/you
constexpr Phoneme PUA_IAU    = 0xE034; // iao
constexpr Phoneme PUA_IEN    = 0xE035; // ian (i + open-e + n)
constexpr Phoneme PUA_IN     = 0xE036; // in
constexpr Phoneme PUA_IANG   = 0xE037; // iang
constexpr Phoneme PUA_ING    = 0xE038; // ing
constexpr Phoneme PUA_IUNG   = 0xE039; // iong (i + u + ng)

// --- u-compound finals ---
constexpr Phoneme PUA_UA     = 0xE03A; // ua
constexpr Phoneme PUA_UO     = 0xE03B; // uo
constexpr Phoneme PUA_UAI    = 0xE03C; // uai
constexpr Phoneme PUA_UEI    = 0xE03D; // ui/wei
constexpr Phoneme PUA_UAN    = 0xE03E; // uan
constexpr Phoneme PUA_UEN    = 0xE03F; // un/wen (u + schwa + n)
constexpr Phoneme PUA_UANG   = 0xE040; // uang
constexpr Phoneme PUA_UENG   = 0xE041; // ueng (u + schwa + ng)

// --- u-umlaut compound finals ---
constexpr Phoneme PUA_YE     = 0xE042; // yue (y_vowel + open-e)
constexpr Phoneme PUA_YEN    = 0xE043; // yuan
constexpr Phoneme PUA_YN     = 0xE044; // yun

// --- Syllabic consonants ---
constexpr Phoneme PUA_RETRO  = 0xE045; // syllabic retroflex (zhi/chi/shi/ri)

// --- Tone markers ---
constexpr Phoneme PUA_TONE1  = 0xE046;
constexpr Phoneme PUA_TONE2  = 0xE047;
constexpr Phoneme PUA_TONE3  = 0xE048;
constexpr Phoneme PUA_TONE4  = 0xE049;
constexpr Phoneme PUA_TONE5  = 0xE04A;

// --- Single-codepoint IPA symbols (output directly, no PUA needed) ---
constexpr Phoneme IPA_ALVPAL_FRIC = 0x0255; // voiceless alveolo-palatal fricative
constexpr Phoneme IPA_RETRO_FRIC  = 0x0282; // voiceless retroflex fricative
constexpr Phoneme IPA_RETRO_APPR  = 0x027B; // retroflex approximant
constexpr Phoneme IPA_RSCHWA      = 0x025A; // rhotacized schwa (er, erhua)
constexpr Phoneme IPA_CLOSE_BACK  = 0x0264; // close-mid back unrounded (pinyin e)
constexpr Phoneme IPA_BARRED_I    = 0x0268; // close central unrounded (zi/ci/si)
constexpr Phoneme PUA_Y_VOWEL     = 0xE01E; // close front rounded [y] (pinyin u-umlaut)

// =========================================================================
// Chinese punctuation mapping (fullwidth -> ASCII equivalent)
// =========================================================================

static Phoneme mapZhPunct(char32_t cp) {
    switch (cp) {
        case 0x3002: return '.';   // fullwidth period
        case 0xFF0C: return ',';   // fullwidth comma
        case 0xFF01: return '!';   // fullwidth exclamation
        case 0xFF1F: return '?';   // fullwidth question
        case 0x3001: return ',';   // ideographic comma
        case 0xFF1B: return ';';   // fullwidth semicolon
        case 0xFF1A: return ':';   // fullwidth colon
        case 0x2026: return '.';   // ellipsis (…)
        case 0x2014: return ',';   // em-dash (—) -> pause
        case 0x201C: return '"';   // left double curly quote (")
        case 0x201D: return '"';   // right double curly quote (")
        case 0x2018: return '\'';  // left single curly quote (')
        case 0x2019: return '\'';  // right single curly quote (')
        default:     return 0;
    }
}

static bool isZhPunctuation(char32_t cp) {
    return cp == ',' || cp == '.' || cp == ';' || cp == ':' ||
           cp == '!' || cp == '?' ||
           cp == 0x3002 || cp == 0xFF0C || cp == 0xFF01 || cp == 0xFF1F ||
           cp == 0x3001 || cp == 0xFF1B || cp == 0xFF1A ||
           cp == 0x201C || cp == 0x201D || cp == 0x2018 || cp == 0x2019 ||
           cp == 0x2026 || cp == 0x2014;
}

// =========================================================================
// CJK detection (U+4E00-9FFF main block, U+3400-4DBF extension A)
// =========================================================================

static bool isCJK(char32_t cp) {
    return (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0x3400 && cp <= 0x4DBF);
}

// =========================================================================
// UTF-8 helpers — delegated to utf8_utils.hpp
// =========================================================================

using utf8_util::toCodepoints;
using utf8_util::cpToUtf8;
using utf8_util::cpsToUtf8;

// =========================================================================
// Pinyin initial consonants (ordered: two-char first for prefix matching)
// =========================================================================

struct InitialEntry {
    const char* pinyin;
    int len;
};

static const InitialEntry INITIALS_ORDER[] = {
    {"zh", 2}, {"ch", 2}, {"sh", 2},
    {"b",  1}, {"p",  1}, {"m",  1}, {"f",  1},
    {"d",  1}, {"t",  1}, {"n",  1}, {"l",  1},
    {"g",  1}, {"k",  1}, {"h",  1},
    {"j",  1}, {"q",  1}, {"x",  1},
    {"r",  1}, {"z",  1}, {"c",  1}, {"s",  1},
};
static const int NUM_INITIALS = sizeof(INITIALS_ORDER) / sizeof(INITIALS_ORDER[0]);

static const std::unordered_set<std::string> RETROFLEX_INITIALS = {
    "zh", "ch", "sh", "r"
};
static const std::unordered_set<std::string> ALVEOLAR_INITIALS = {
    "z", "c", "s"
};

// =========================================================================
// Initial -> IPA PUA mapping
// =========================================================================

static Phoneme initialToIPA(const std::string& init) {
    if (init == "b")  return 'p';
    if (init == "p")  return PUA_PH;
    if (init == "m")  return 'm';
    if (init == "f")  return 'f';
    if (init == "d")  return 't';
    if (init == "t")  return PUA_TH;
    if (init == "n")  return 'n';
    if (init == "l")  return 'l';
    if (init == "g")  return 'k';
    if (init == "k")  return PUA_KH;
    if (init == "h")  return 'x';
    if (init == "j")  return PUA_TC;
    if (init == "q")  return PUA_TCH;
    if (init == "x")  return IPA_ALVPAL_FRIC;
    if (init == "zh") return PUA_TRS;
    if (init == "ch") return PUA_TRSH;
    if (init == "sh") return IPA_RETRO_FRIC;
    if (init == "r")  return IPA_RETRO_APPR;
    if (init == "z")  return 0xE00F; // PUA_TS (shared with JA "ts")
    if (init == "c")  return PUA_TSH;
    if (init == "s")  return 's';
    return 0;
}

// =========================================================================
// Final -> IPA PUA mapping
// =========================================================================

// Internal key for syllabic consonant detection
static const std::string KEY_RETRO = "-i_retroflex";
static const std::string KEY_ALVE  = "-i_alveolar";

static Phoneme finalToIPA(const std::string& fin) {
    // Simple vowels
    if (fin == "a") return 'a';
    if (fin == "o") return 'o';
    if (fin == "e") return IPA_CLOSE_BACK;     // pinyin e -> close-mid back
    if (fin == "i") return 'i';
    if (fin == "u") return 'u';
    if (fin == "\xc3\xbc" || fin == "v") return PUA_Y_VOWEL;  // u-umlaut

    // Diphthongs
    if (fin == "ai")  return PUA_AI;
    if (fin == "ei")  return PUA_EI;
    if (fin == "ao")  return PUA_AU;
    if (fin == "ou")  return PUA_OU;

    // Nasal finals
    if (fin == "an")  return PUA_AN;
    if (fin == "en")  return PUA_EN;
    if (fin == "ang") return PUA_ANG;
    if (fin == "eng") return PUA_ENG;
    if (fin == "ong") return PUA_UNG;

    // Retroflex final
    if (fin == "er")  return IPA_RSCHWA;

    // i-compound finals
    if (fin == "ia")   return PUA_IA;
    if (fin == "ie")   return PUA_IE;
    if (fin == "iao")  return PUA_IAU;
    if (fin == "iu" || fin == "iou") return PUA_IOU;
    if (fin == "ian")  return PUA_IEN;
    if (fin == "in")   return PUA_IN;
    if (fin == "iang") return PUA_IANG;
    if (fin == "ing")  return PUA_ING;
    if (fin == "iong") return PUA_IUNG;

    // u-compound finals
    if (fin == "ua")   return PUA_UA;
    if (fin == "uo")   return PUA_UO;
    if (fin == "uai")  return PUA_UAI;
    if (fin == "ui" || fin == "uei") return PUA_UEI;
    if (fin == "uan")  return PUA_UAN;
    if (fin == "un" || fin == "uen") return PUA_UEN;
    if (fin == "uang") return PUA_UANG;
    if (fin == "ueng") return PUA_UENG;

    // u-umlaut compound finals (UTF-8 u-umlaut = \xc3\xbc)
    if (fin == "\xc3\xbc" "e" || fin == "ve") return PUA_YE;
    if (fin == "\xc3\xbc" "an" || fin == "van") return PUA_YEN;
    if (fin == "\xc3\xbc" "n"  || fin == "vn")  return PUA_YN;

    // Syllabic consonants (internal keys from splitPinyin)
    if (fin == KEY_RETRO) return PUA_RETRO;
    if (fin == KEY_ALVE)  return IPA_BARRED_I;

    return 0; // unknown
}

// =========================================================================
// Tone number -> PUA
// =========================================================================

static Phoneme toneToPUA(int tone) {
    switch (tone) {
        case 1: return PUA_TONE1;
        case 2: return PUA_TONE2;
        case 3: return PUA_TONE3;
        case 4: return PUA_TONE4;
        case 5: return PUA_TONE5;
        default: return 0;
    }
}

// =========================================================================
// Pinyin normalization (matches chinese.py _normalize_pinyin)
// =========================================================================

// Check if string starts with a prefix
static bool startsWith(const std::string& s, const std::string& prefix) {
    return s.size() >= prefix.size() &&
           s.compare(0, prefix.size(), prefix) == 0;
}

static std::string normalizePinyin(const std::string& py) {
    // v -> u-umlaut (UTF-8: \xc3\xbc)
    std::string s = py;
    {
        size_t pos = 0;
        while ((pos = s.find('v', pos)) != std::string::npos) {
            s.replace(pos, 1, "\xc3\xbc");
            pos += 2; // u-umlaut is 2 bytes in UTF-8
        }
    }

    // y- initial
    if (startsWith(s, "yu")) {
        // yu -> u-umlaut + remainder
        return std::string("\xc3\xbc") + s.substr(2);
    }
    if (s.size() > 0 && s[0] == 'y') {
        std::string remainder = s.substr(1);
        if (startsWith(remainder, "i")) {
            return remainder;  // yi->i, yin->in, ying->ing
        }
        return "i" + remainder;  // ya->ia, ye->ie, yan->ian
    }

    // w- initial
    if (s.size() > 0 && s[0] == 'w') {
        std::string remainder = s.substr(1);
        if (startsWith(remainder, "u")) {
            return remainder;  // wu->u
        }
        return "u" + remainder;  // wa->ua, wo->uo, wai->uai
    }

    return s;
}

// =========================================================================
// Split normalized pinyin into (initial, final)
// Matches chinese.py _split_pinyin
// =========================================================================

struct PinyinSplit {
    std::string initial;
    std::string final_;
};

static PinyinSplit splitPinyin(const std::string& pinyin) {
    for (int i = 0; i < NUM_INITIALS; ++i) {
        const auto& entry = INITIALS_ORDER[i];
        if (pinyin.size() >= static_cast<size_t>(entry.len) &&
            pinyin.compare(0, entry.len, entry.pinyin) == 0) {

            std::string init(entry.pinyin, entry.len);
            std::string fin = pinyin.substr(entry.len);

            // Syllabic consonant: bare "i" after retroflex or alveolar initials
            if (fin == "i") {
                if (RETROFLEX_INITIALS.count(init)) {
                    return {init, KEY_RETRO};
                }
                if (ALVEOLAR_INITIALS.count(init)) {
                    return {init, KEY_ALVE};
                }
            }

            // After j/q/x, u represents u-umlaut
            if ((init == "j" || init == "q" || init == "x") &&
                fin.size() > 0 && fin[0] == 'u') {
                fin = std::string("\xc3\xbc") + fin.substr(1);
            }

            return {init, fin};
        }
    }

    // No consonant initial
    return {"", pinyin};
}

// =========================================================================
// Pinyin -> IPA conversion (single syllable)
// Matches chinese.py _pinyin_to_ipa
// =========================================================================

static std::vector<Phoneme> pinyinToIPA(const std::string& syllable, int tone) {
    auto split = splitPinyin(syllable);
    std::vector<Phoneme> tokens;

    // Initial consonant
    if (!split.initial.empty()) {
        Phoneme ipa = initialToIPA(split.initial);
        if (ipa != 0) {
            tokens.push_back(ipa);
        }
    }

    // Final vowel(s) as a single compound token
    if (!split.final_.empty()) {
        Phoneme ipa = finalToIPA(split.final_);
        if (ipa != 0) {
            tokens.push_back(ipa);
        } else {
            // Fallback: decompose unknown finals character by character
            for (char ch : split.final_) {
                if (ch >= 'a' && ch <= 'z') {
                    std::string single(1, ch);
                    Phoneme f = finalToIPA(single);
                    if (f != 0) {
                        tokens.push_back(f);
                    } else {
                        tokens.push_back(static_cast<Phoneme>(ch));
                    }
                }
            }
        }
    }

    // Tone marker
    Phoneme t = toneToPUA(tone);
    if (t != 0) {
        tokens.push_back(t);
    }

    return tokens;
}

// =========================================================================
// Tone sandhi (matches chinese.py _apply_tone_sandhi)
// =========================================================================

struct SyllableTone {
    std::string syllable;  // normalized pinyin without tone number
    int tone;
};

static void applyToneSandhi(std::vector<SyllableTone>& st) {
    int n = static_cast<int>(st.size());
    for (int i = 0; i < n - 1; ++i) {
        const auto& syl = st[i].syllable;
        int tone_i = st[i].tone;
        int tone_next = st[i + 1].tone;

        // Rule 1: T3 + T3 -> T2 + T3
        if (tone_i == 3 && tone_next == 3) {
            st[i].tone = 2;
            continue;
        }

        // Rule 2 & 3: yi (normalized to "i") tone sandhi
        if (syl == "i" && tone_i == 1) {
            if (tone_next == 4) {
                st[i].tone = 2;   // T1 -> T2 before T4
            } else if (tone_next >= 1 && tone_next <= 3) {
                st[i].tone = 4;   // T1 -> T4 before T1/T2/T3
            }
            continue;
        }

        // Rule 4: bu (T4) + T4 -> T2 + T4
        if (syl == "bu" && tone_i == 4 && tone_next == 4) {
            st[i].tone = 2;
        }
    }
}

// =========================================================================
// Text -> Pinyin conversion using dictionaries
// =========================================================================

// Extract a tone digit from the end of a pinyin syllable string.
// Returns the tone (1-5) and sets base to the syllable without the digit.
// If no digit, returns 5 (neutral tone).
static int extractTone(const std::string& syllable, std::string& base) {
    if (!syllable.empty() && syllable.back() >= '1' && syllable.back() <= '5') {
        base = syllable.substr(0, syllable.size() - 1);
        return syllable.back() - '0';
    }
    base = syllable;
    return 5;
}

// Split a space-separated pinyin string into individual syllable strings.
static std::vector<std::string> splitPinyinString(const std::string& s) {
    std::vector<std::string> result;
    size_t start = 0;
    while (start < s.size()) {
        // Skip whitespace
        while (start < s.size() && (s[start] == ' ' || s[start] == '\t')) {
            ++start;
        }
        if (start >= s.size()) break;
        size_t end = s.find_first_of(" \t", start);
        if (end == std::string::npos) end = s.size();
        result.push_back(s.substr(start, end - start));
        start = end;
    }
    return result;
}

// For a single-char dict entry that may have comma-separated alternatives,
// return the first alternative.
static std::string firstAlternative(const std::string& s) {
    size_t comma = s.find(',');
    if (comma != std::string::npos) {
        return s.substr(0, comma);
    }
    return s;
}

// Attempt longest-prefix phrase match starting at position `pos` in codepoints.
// Returns the number of codepoints matched (0 if no match found), and sets
// `pinyinOut` to the matched phrase's pinyin string.
static size_t phraseMatch(const std::vector<char32_t>& cps, size_t pos,
                          const std::unordered_map<std::string, std::string>& phraseDict,
                          std::string& pinyinOut) {
    // Try decreasing lengths (max phrase length typically <= 8 chars)
    size_t maxLen = std::min(cps.size() - pos, static_cast<size_t>(8));
    for (size_t len = maxLen; len >= 2; --len) {
        std::string key = cpsToUtf8(cps, pos, len);
        auto it = phraseDict.find(key);
        if (it != phraseDict.end()) {
            pinyinOut = it->second;
            return len;
        }
    }
    return 0;
}

// Represents a character in the text with its pinyin and tone info.
struct CharPinyin {
    char32_t codepoint;
    bool isChinese;
    std::string normalized;   // normalized pinyin (no tone digit)
    int tone;                 // 1-5
};

// Convert text to a list of CharPinyin entries using the dictionaries.
static std::vector<CharPinyin> textToPinyin(
    const std::vector<char32_t>& cps,
    const std::unordered_map<int, std::string>& singleCharDict,
    const std::unordered_map<std::string, std::string>& phraseDict) {

    std::vector<CharPinyin> result;
    size_t n = cps.size();
    size_t i = 0;

    while (i < n) {
        char32_t cp = cps[i];

        if (!isCJK(cp)) {
            // Non-CJK: pass through
            result.push_back({cp, false, "", 0});
            ++i;
            continue;
        }

        // Try phrase match first
        std::string phrasePy;
        size_t matchLen = phraseMatch(cps, i, phraseDict, phrasePy);
        if (matchLen > 0) {
            // Split the phrase pinyin and assign to each character
            auto syllables = splitPinyinString(phrasePy);
            for (size_t j = 0; j < matchLen; ++j) {
                std::string base;
                int tone = 5;
                if (j < syllables.size()) {
                    tone = extractTone(syllables[j], base);
                }
                std::string normalized = normalizePinyin(base);
                result.push_back({cps[i + j], true, normalized, tone});
            }
            i += matchLen;
            continue;
        }

        // Single character lookup
        int cpInt = static_cast<int>(cp);
        auto it = singleCharDict.find(cpInt);
        if (it != singleCharDict.end()) {
            std::string raw = firstAlternative(it->second);
            std::string base;
            int tone = extractTone(raw, base);
            std::string normalized = normalizePinyin(base);
            result.push_back({cp, true, normalized, tone});
        } else {
            // Unknown CJK character: skip silently
            result.push_back({cp, false, "", 0});
        }
        ++i;
    }

    return result;
}

// =========================================================================
// Group consecutive Chinese characters for tone sandhi
// =========================================================================

static void applyToneSandhiToChars(std::vector<CharPinyin>& chars) {
    int n = static_cast<int>(chars.size());
    int i = 0;

    while (i < n) {
        if (!chars[i].isChinese) {
            ++i;
            continue;
        }

        // Find the end of this consecutive Chinese character group
        int groupStart = i;
        while (i < n && chars[i].isChinese) {
            ++i;
        }
        int groupEnd = i;

        if (groupEnd - groupStart < 2) continue;

        // Build SyllableTone vector for this group
        std::vector<SyllableTone> st;
        st.reserve(groupEnd - groupStart);
        for (int j = groupStart; j < groupEnd; ++j) {
            st.push_back({chars[j].normalized, chars[j].tone});
        }

        applyToneSandhi(st);

        // Write back
        for (int j = groupStart; j < groupEnd; ++j) {
            chars[j].tone = st[j - groupStart].tone;
        }
    }
}

} // anonymous namespace

// =========================================================================
// Public API: loadPinyinDicts
// =========================================================================

bool loadPinyinDicts(const std::string& singleCharPath,
                     const std::string& phrasePath,
                     std::unordered_map<int, std::string>& singleCharDict,
                     std::unordered_map<std::string, std::string>& phraseDict) {

    // Load single-char dictionary
    {
        std::ifstream f(singleCharPath);
        if (!f.is_open()) {
            return false;
        }
        json j;
        try {
            f >> j;
        } catch (...) {
            return false;
        }

        // Keys are codepoint values as strings (e.g., "19968" for U+4E00)
        // Values are pinyin strings (may have comma-separated alternatives)
        for (auto& [key, val] : j.items()) {
            try {
                int codepoint = std::stoi(key);
                if (val.is_string()) {
                    singleCharDict[codepoint] = val.get<std::string>();
                } else if (val.is_array() && !val.empty()) {
                    // If the value is an array, take the first element
                    singleCharDict[codepoint] = val[0].get<std::string>();
                }
            } catch (...) {
                // Skip malformed entries
                continue;
            }
        }
    }

    // Load phrase dictionary
    {
        std::ifstream f(phrasePath);
        if (!f.is_open()) {
            return false;
        }
        json j;
        try {
            f >> j;
        } catch (...) {
            return false;
        }

        // Keys are Chinese character sequences (UTF-8 strings)
        // Values may be:
        //   - a string: "yi2 ge4"
        //   - an array of arrays: [["yi2"], ["ge4"]]  (pypinyin format)
        //   - an array of strings: ["yi2", "ge4"]
        for (auto& [key, val] : j.items()) {
            if (val.is_string()) {
                phraseDict[key] = val.get<std::string>();
            } else if (val.is_array() && !val.empty()) {
                std::string pyStr;
                for (size_t idx = 0; idx < val.size(); ++idx) {
                    if (idx > 0) pyStr += " ";
                    if (val[idx].is_array() && !val[idx].empty()) {
                        pyStr += val[idx][0].get<std::string>();
                    } else if (val[idx].is_string()) {
                        pyStr += val[idx].get<std::string>();
                    }
                }
                if (!pyStr.empty()) {
                    phraseDict[key] = pyStr;
                }
            }
        }
    }

    return true;
}

// =========================================================================
// Public API: phonemize_chinese
// =========================================================================

void phonemize_chinese(const std::string& text,
                       std::vector<std::vector<Phoneme>>& phonemes,
                       const std::unordered_map<int, std::string>& singleCharDict,
                       const std::unordered_map<std::string, std::string>& phraseDict) {
    phonemes.clear();

    if (!utf8::is_valid(text.begin(), text.end())) {
        return;
    }

    // Decode UTF-8 to codepoints
    auto cps = toCodepoints(text);
    if (cps.empty()) return;

    // Step 1: Text -> pinyin (dictionary lookup with phrase matching)
    auto charPinyins = textToPinyin(cps, singleCharDict, phraseDict);

    // Step 2: Tone sandhi on consecutive Chinese character groups
    applyToneSandhiToChars(charPinyins);

    // Step 3: Generate phonemes
    std::vector<Phoneme> sentence;

    for (const auto& cp : charPinyins) {
        // Non-Chinese character passthrough
        if (!cp.isChinese) {
            char32_t ch = cp.codepoint;

            // Map fullwidth Chinese punctuation to ASCII equivalent
            Phoneme mapped = mapZhPunct(ch);
            if (mapped != 0) {
                sentence.push_back(mapped);
                continue;
            }

            // Other punctuation: pass through directly
            if (isZhPunctuation(ch)) {
                sentence.push_back(ch);
                continue;
            }

            // Whitespace: emit space
            if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r') {
                sentence.push_back(static_cast<Phoneme>(' '));
                continue;
            }

            // Digits: pass through
            if (ch >= '0' && ch <= '9') {
                sentence.push_back(ch);
                continue;
            }

            // Latin letters: pass through
            if ((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z')) {
                sentence.push_back(ch);
                continue;
            }

            // Other characters: skip
            continue;
        }

        // Chinese character: convert pinyin to IPA
        std::string normalized = cp.normalized;
        int tone = cp.tone;

        // Erhua handling: trailing 'r' that is not standalone "er"
        bool hasErhua = false;
        if (normalized.size() > 1 && normalized != "er" &&
            normalized.back() == 'r') {
            hasErhua = true;
            normalized = normalized.substr(0, normalized.size() - 1);
        }

        // Convert to IPA tokens
        auto ipaTokens = pinyinToIPA(normalized, tone);

        // Insert erhua token before tone marker
        if (hasErhua && !ipaTokens.empty()) {
            // Check if last token is a tone marker
            Phoneme lastToken = ipaTokens.back();
            bool lastIsTone = (lastToken >= PUA_TONE1 && lastToken <= PUA_TONE5);

            if (lastIsTone) {
                // Insert erhua before tone
                ipaTokens.insert(ipaTokens.end() - 1, IPA_RSCHWA);
            } else {
                ipaTokens.push_back(IPA_RSCHWA);
            }
        }

        // Append all tokens to sentence
        for (Phoneme ph : ipaTokens) {
            sentence.push_back(ph);
        }
    }

    if (!sentence.empty()) {
        phonemes.push_back(std::move(sentence));
    }
}

} // namespace piper
