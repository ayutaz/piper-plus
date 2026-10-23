// English text normalization -- C++ port of g2p_en's preprocessing (#821).
//
// Python's English G2P is g2p_en (src/python/g2p/piper_plus_g2p/_vendor/
// g2p_en). Before its dictionary lookup, G2p.__call__ rewrites the text:
//
//   1. normalize_numbers (expand.py) spells numbers out with inflect;
//   2. NFD decomposition, combining marks removed, lowercased;
//   3. every character other than `a-z ' . , ? ! -` and space is removed;
//   4. "i.e." / "e.g." become "that is" / "for example";
//   5. nltk's TweetTokenizer splits the result into words.
//
// This header ports those steps, following
// docs/design/english-g2p-normalization-cpp-rust-2026-10-23.md section 3.
// Two deliberate differences from Python:
//   - case is kept (Python lowercases in step 2): the out-of-vocabulary
//     ladder in english_phonemize.cpp splits CamelCase words on the original
//     capitals, and looks words up lowercased;
//   - inflect's scale words are ported up to "quintillion"; a longer digit run
//     is read digit by digit (Python goes to "decillion", then raises).
//
// The regular expressions are replaced by hand-written scans; each scan notes
// the expression it implements. Only ASCII digits, the pound sign and the
// characters that survive step 3 matter, so the scans work on UTF-8 bytes.
//
// tests/fixtures/g2p/english_normalize_cases.json, generated from the Python
// code by scripts/build_english_normalize_fixture.py, pins the behaviour
// (src/cpp/tests/test_english_normalize.cpp). Header-only so that test links
// nothing but gtest.

#ifndef PIPER_PLUS_ENGLISH_NORMALIZE_HPP
#define PIPER_PLUS_ENGLISH_NORMALIZE_HPP

#include "utf8.h"

#include <algorithm>
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

namespace piper {
namespace english_normalize_detail {

inline bool isDigit(char c) { return c >= '0' && c <= '9'; }

inline bool isLetter(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }

inline bool isUpper(char c) { return c >= 'A' && c <= 'Z'; }

inline char toLower(char c) { return isUpper(c) ? static_cast<char>(c - 'A' + 'a') : c; }

inline const char *unitWord(int digit) {
    static const char *const units[] = {"",     "one", "two",   "three", "four",
                                        "five", "six", "seven", "eight", "nine"};
    return units[digit];
}

// The digits of `s` with leading zeros removed; "0" when nothing is left
// (Python's int(), applied to a run of digits).
inline std::string canonicalDigits(const std::string &s) {
    std::string digits;
    for (char c : s) {
        if (isDigit(c) && !(digits.empty() && c == '0')) digits += c;
    }
    return digits.empty() ? "0" : digits;
}

// inflect tenfn: 0..99 in words ("" for 0).
inline std::string tensWords(int tens, int units) {
    static const char *const teens[] = {"ten",     "eleven",  "twelve",    "thirteen", "fourteen",
                                        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"};
    static const char *const decades[] = {"",      "",      "twenty",  "thirty", "forty",
                                          "fifty", "sixty", "seventy", "eighty", "ninety"};
    if (tens == 1) return teens[units];
    if (tens == 0) return unitWord(units);
    std::string out = decades[tens];
    if (units) {
        out += '-';
        out += unitWord(units);
    }
    return out;
}

// inflect number_to_words(n, andword=...) for a run of digits (group=0).
//
// The digits are split into groups of three from the right. Each non-zero
// group reads "<h> hundred<and><tens> <scale>", where <and> is " and " for
// useAnd and " " otherwise. Groups are joined with ", ", except that a last
// group of 1..99 under a higher group is joined with <and> (inflect's
// COMMA_WORD rule: "one million one", "five thousand and fifth").
inline std::string numberToWords(const std::string &run, bool useAnd) {
    static const char *const scales[] = {"",          " thousand",    " million",    " billion",
                                         " trillion", " quadrillion", " quintillion"};
    constexpr size_t kMaxGroups = sizeof(scales) / sizeof(scales[0]);

    const std::string digits = canonicalDigits(run);
    if (digits == "0") return "zero";
    if (digits.size() > 3 * kMaxGroups) {
        // Beyond the scale words: read each digit.
        std::string out;
        for (char c : digits) {
            if (!out.empty()) out += ' ';
            out += c == '0' ? "zero" : unitWord(c - '0');
        }
        return out;
    }

    const char *andWord = useAnd ? " and " : " ";
    std::string out;
    size_t groups = (digits.size() + 2) / 3;
    for (size_t g = groups; g-- > 0;) {
        const size_t end = digits.size() - 3 * g;
        const size_t begin = end >= 3 ? end - 3 : 0;
        int value = 0;
        for (size_t i = begin; i < end; ++i) value = value * 10 + (digits[i] - '0');
        if (value == 0) continue;

        const int hundreds = value / 100;
        const int tens = (value / 10) % 10;
        const int units = value % 10;
        std::string words;
        if (hundreds) {
            words = std::string(unitWord(hundreds)) + " hundred";
            if (tens || units) words += andWord + tensWords(tens, units);
        } else {
            words = tensWords(tens, units);
        }
        words += scales[g];

        if (!out.empty()) out += (g == 0 && hundreds == 0) ? andWord : ", ";
        out += words;
    }
    return out;
}

// inflect's ordinal of the last word: "one" -> "first", "twenty" ->
// "twentieth", otherwise "-th".
inline std::string ordinalize(const std::string &words) {
    static const std::pair<const char *, const char *> suffixes[] = {
        {"ty", "tieth"},    {"one", "first"},  {"two", "second"}, {"three", "third"},
        {"five", "fifth"},  {"eight", "eighth"}, {"nine", "ninth"}, {"twelve", "twelfth"},
    };
    for (const auto &[from, to] : suffixes) {
        const std::string suffix = from;
        if (words.size() >= suffix.size() &&
            words.compare(words.size() - suffix.size(), suffix.size(), suffix) == 0) {
            return words.substr(0, words.size() - suffix.size()) + to;
        }
    }
    return words + "th";
}

// expand.py _expand_number: years between 1000 and 3000 (exclusive) are read
// in pairs ("nineteen eighty-four", "ten oh one", "twenty-one hundred").
inline std::string expandCardinal(const std::string &run) {
    const std::string digits = canonicalDigits(run);
    if (digits.size() == 4) {
        const int n = std::stoi(digits);
        if (n > 1000 && n < 3000) {
            if (n == 2000) return "two thousand";
            if (n > 2000 && n < 2010) return "two thousand " + numberToWords(digits.substr(3), true);
            if (n % 100 == 0) return numberToWords(std::to_string(n / 100), true) + " hundred";
            const int high = n / 100;
            const int low = n % 100;
            std::string out = tensWords(high / 10, high % 10) + " ";
            if (low >= 10) {
                out += tensWords(low / 10, low % 10);
            } else {
                out += "oh ";
                out += unitWord(low);
            }
            return out;
        }
    }
    return numberToWords(digits, false);
}

// expand.py _expand_dollars, given the text after '$'.
inline std::string expandDollars(const std::string &amount) {
    std::vector<std::string> parts(1);
    for (char c : amount) {
        if (c == '.') {
            parts.emplace_back();
        } else {
            parts.back() += c;
        }
    }
    if (parts.size() > 2) return amount + " dollars";  // unexpected format

    const std::string dollars = canonicalDigits(parts[0]);
    const std::string cents = parts.size() > 1 ? canonicalDigits(parts[1]) : "0";
    const std::string dollarUnit = dollars == "1" ? "dollar" : "dollars";
    const std::string centUnit = cents == "1" ? "cent" : "cents";
    if (dollars != "0" && cents != "0") {
        return dollars + " " + dollarUnit + ", " + cents + " " + centUnit;
    }
    if (dollars != "0") return dollars + " " + dollarUnit;
    if (cents != "0") return cents + " " + centUnit;
    return "zero dollars";
}

// End of the run of characters in `allowed` (plus digits) starting at
// `begin`, trimmed back to just after its last digit; `begin` when the run
// has no digit. Implements `[0-9<allowed>]*[0-9]+` with backtracking.
inline size_t digitRunEnd(const std::string &s, size_t begin, const char *allowed) {
    auto isAllowed = [allowed](char c) {
        for (const char *a = allowed; *a; ++a) {
            if (*a == c) return true;
        }
        return false;
    };
    size_t end = begin;
    while (end < s.size() && (isDigit(s[end]) || isAllowed(s[end]))) ++end;
    while (end > begin && !isDigit(s[end - 1])) --end;
    return end;
}

inline size_t digitsEnd(const std::string &s, size_t begin) {
    while (begin < s.size() && isDigit(s[begin])) ++begin;
    return begin;
}

// NFD base letter of a precomposed Latin letter, or 0. Covers U+00C0..U+024F
// and U+1E00..U+1EFF (Latin Extended Additional), plus the Kelvin and
// Angstrom signs whose canonical decomposition is a Latin letter. Letters
// without a canonical decomposition to an ASCII letter (ae, eth, sharp s,
// o with stroke, dotless i, ...) map to 0 and are removed, as in Python.
// The tables were generated with Python's unicodedata ('-' = none) and are
// the same as LATIN_BASE_00C0 / LATIN_BASE_1E00 in the Rust port.
inline char latinBaseLetter(char32_t cp) {
    static const char kTable00C0[] =
        "AAAAAA-CEEEEIIII-NOOOOO--UUUUY--aaaaaa-ceeeeiiii-nooooo--uuuuy-y"  // U+00C0
        "AaAaAaCcCcCcCcDd--EeEeEeEeEeGgGgGgGgHh--IiIiIiIiI---JjKk-LlLlLl-"  // U+0100
        "---NnNnNn---OoOoOo--RrRrRrSsSsSsSsTtTt--UuUuUuUuUuUuWwYyYZzZzZz-"  // U+0140
        "--------------------------------Oo-------------Uu---------------"  // U+0180
        "-------------AaIiOoUuUuUuUuUu-AaAa----GgKkOoOo--j---Gg--NnAa----"  // U+01C0
        "AaAaEeEeIiIiOoOoRrRrUuUuSsTt--Hh------AaEeOoOoOoOoYy------------"  // U+0200
        "----------------";  // U+0240
    static const char kTable1E00[] =
        "AaBbBbBbCcDdDdDdDdDdEeEeEeEeEeFfGgHhHhHhHhHhIiIiKkKkKkLlLlLlLlMm"  // U+1E00
        "MmMmNnNnNnNnOoOoOoOoPpPpRrRrRrRrSsSsSsSsSsTtTtTtTtUuUuUuUuUuVvVv"  // U+1E40
        "WwWwWwWwWwXxXxYyZzZzZzhtwy------AaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEe"  // U+1E80
        "EeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy------";  // U+1EC0
    char base = 0;
    if (cp >= 0xC0 && cp <= 0x24F) {
        base = kTable00C0[cp - 0xC0];
    } else if (cp >= 0x1E00 && cp <= 0x1EFF) {
        base = kTable1E00[cp - 0x1E00];
    } else if (cp == 0x212A) {
        base = 'K';  // KELVIN SIGN
    } else if (cp == 0x212B) {
        base = 'A';  // ANGSTROM SIGN
    }
    return base == '-' ? 0 : base;
}

// Replaces every case-insensitive occurrence of `from` (lowercase ASCII).
inline std::string replaceIgnoringCase(const std::string &s, const std::string &from,
                                       const std::string &to) {
    std::string out;
    size_t i = 0;
    while (i < s.size()) {
        bool match = i + from.size() <= s.size();
        for (size_t k = 0; match && k < from.size(); ++k) {
            match = toLower(s[i + k]) == from[k];
        }
        if (match) {
            out += to;
            i += from.size();
        } else {
            out += s[i++];
        }
    }
    return out;
}

// End of the TweetTokenizer "naked domain" form starting at a letter, or
// `begin` when there is none:
//   [a-z0-9]+(?:[.\-][a-z0-9]+){0,126}[.](?:[a-z]{2,13})\b
// The text holds letters and `' . , ? ! -` only, so each label is a maximal
// letter run and \b means "not followed by a letter". With backtracking the
// regex takes the most labels for which the next separator is '.' and the
// label after it has 2..13 letters.
inline size_t domainEnd(const std::string &s, size_t begin) {
    // labelEnds[k] = end of label k; label k > 0 starts after a separator.
    std::vector<size_t> labelEnds;
    size_t i = begin;
    while (true) {
        size_t start = i;
        while (i < s.size() && isLetter(s[i])) ++i;
        if (i == start) break;
        labelEnds.push_back(i);
        if (i + 1 < s.size() && (s[i] == '.' || s[i] == '-') && isLetter(s[i + 1])) {
            ++i;
        } else {
            break;
        }
    }
    // m repetitions consume labels 1..m; the domain ends with label m + 1.
    const size_t labels = labelEnds.size();
    if (labels < 2) return begin;
    for (size_t m = std::min<size_t>(labels - 2, 126) + 1; m-- > 0;) {
        const size_t sep = labelEnds[m];
        const size_t tldLength = labelEnds[m + 1] - (sep + 1);
        if (s[sep] == '.' && tldLength >= 2 && tldLength <= 13) return labelEnds[m + 1];
    }
    return begin;
}

}  // namespace english_normalize_detail

// g2p_en expand.normalize_numbers: the six substitutions of expand.py, in
// order, over the whole string.
inline std::string normalizeEnglishNumbers(const std::string &text) {
    using namespace english_normalize_detail;
    std::string s = text;

    // 1. ([0-9][0-9,]+[0-9]) -> the same without commas.
    {
        std::string out;
        size_t i = 0;
        while (i < s.size()) {
            if (!isDigit(s[i])) {
                out += s[i++];
                continue;
            }
            const size_t end = digitRunEnd(s, i, ",");
            if (end - i >= 3) {
                for (size_t k = i; k < end; ++k) {
                    if (s[k] != ',') out += s[k];
                }
            } else {
                out.append(s, i, end - i);
            }
            i = end;
        }
        s = std::move(out);
    }

    // 2. £([0-9,]*[0-9]+) -> "\1 pounds".
    // 3. \$([0-9.,]*[0-9]+) -> _expand_dollars.
    for (const bool pounds : {true, false}) {
        const std::string sign = pounds ? "\xC2\xA3" : "$";
        std::string out;
        size_t i = 0;
        while (i < s.size()) {
            if (s.compare(i, sign.size(), sign) == 0) {
                const size_t begin = i + sign.size();
                const size_t end = digitRunEnd(s, begin, pounds ? "," : ".,");
                if (end > begin) {
                    const std::string amount = s.substr(begin, end - begin);
                    out += pounds ? amount + " pounds" : expandDollars(amount);
                    i = end;
                    continue;
                }
            }
            out += s[i++];
        }
        s = std::move(out);
    }

    // 4. ([0-9]+\.[0-9]+) -> the '.' becomes " point ".
    {
        std::string out;
        size_t i = 0;
        while (i < s.size()) {
            if (!isDigit(s[i])) {
                out += s[i++];
                continue;
            }
            const size_t end = digitsEnd(s, i);
            if (end + 1 < s.size() && s[end] == '.' && isDigit(s[end + 1])) {
                const size_t fractionEnd = digitsEnd(s, end + 1);
                out.append(s, i, end - i);
                out += " point ";
                out.append(s, end + 1, fractionEnd - end - 1);
                i = fractionEnd;
            } else {
                out.append(s, i, end - i);
                i = end;
            }
        }
        s = std::move(out);
    }

    // 5. [0-9]+(st|nd|rd|th) -> ordinal (inflect, andword "and").
    // 6. [0-9]+ -> cardinal.
    for (const bool ordinals : {true, false}) {
        std::string out;
        size_t i = 0;
        while (i < s.size()) {
            if (!isDigit(s[i])) {
                out += s[i++];
                continue;
            }
            const size_t end = digitsEnd(s, i);
            const std::string run = s.substr(i, end - i);
            if (!ordinals) {
                out += expandCardinal(run);
                i = end;
                continue;
            }
            bool suffix = false;
            for (const char *ord : {"st", "nd", "rd", "th"}) {
                if (s.compare(end, 2, ord) == 0) suffix = true;
            }
            if (suffix) {
                out += ordinalize(numberToWords(run, true));
                i = end + 2;
            } else {
                out += run;
                i = end;
            }
        }
        s = std::move(out);
    }
    return s;
}

// Steps 1-4 of G2p.__call__: numbers, accent stripping, the character filter
// and the i.e. / e.g. replacement. Case is kept (see the file comment).
// Returns "" for invalid UTF-8.
inline std::string normalizeEnglishText(const std::string &text) {
    using namespace english_normalize_detail;
    const std::string numbers = normalizeEnglishNumbers(text);
    if (!utf8::is_valid(numbers.begin(), numbers.end())) return {};

    // NFD + combining marks removed + `[^ a-zA-Z'.,?!\-]` removed. Combining
    // marks (U+0300..U+036F) and everything else outside ASCII are removed by
    // the filter; a precomposed letter keeps its base letter. Tabs and
    // newlines are removed too, so the words around them join.
    std::string filtered;
    auto it = numbers.begin();
    while (it != numbers.end()) {
        const char32_t cp = utf8::unchecked::next(it);
        char c = 0;
        if (cp < 0x80) {
            c = static_cast<char>(cp);
            if (!(isLetter(c) || c == ' ' || c == '\'' || c == '.' || c == ',' || c == '?' ||
                  c == '!' || c == '-')) {
                c = 0;
            }
        } else {
            c = latinBaseLetter(cp);
        }
        if (c) filtered += c;
    }

    // Python replaces in its lowercased text; this port matches either case.
    return replaceIgnoringCase(replaceIgnoringCase(filtered, "i.e.", "that is"), "e.g.",
                               "for example");
}

// The part of nltk's TweetTokenizer reachable from normalizeEnglishText's
// output (letters, space and `' . , ? ! -`). Case is kept.
//
// First, a run of 4+ identical characters other than letters and digits is
// cut to 3 (HANG_RE). Then, at each position, the first of these that matches
// is one word (the first match, not the longest):
//   1. the naked-domain form (`hello.world`, `uh-huh.ok`);
//   2. [a-z]([a-z]|['-])+[a-z]  (`don't`, `uh-huh`, `a---b`);
//   3. [a-z]+;
//   4. \.( *\.)+  (`...`, `. . .`);
//   5. any single character other than a space.
inline std::vector<std::string> tokenizeEnglish(const std::string &text) {
    using namespace english_normalize_detail;

    std::string s;
    for (size_t i = 0; i < text.size();) {
        size_t run = i + 1;
        while (run < text.size() && text[run] == text[i]) ++run;
        const bool hang = !isLetter(text[i]) && !isDigit(text[i]) && run - i >= 4;
        s.append(hang ? 3 : run - i, text[i]);
        i = run;
    }

    std::vector<std::string> words;
    size_t i = 0;
    while (i < s.size()) {
        if (s[i] == ' ') {
            ++i;
            continue;
        }
        size_t end = i + 1;
        if (isLetter(s[i])) {
            end = domainEnd(s, i);
            if (end == i) {
                // [a-z]([a-z]|['-])+[a-z], backtracked to end on a letter.
                size_t run = i + 1;
                while (run < s.size() && (isLetter(s[run]) || s[run] == '\'' || s[run] == '-')) {
                    ++run;
                }
                while (run > i && !isLetter(s[run - 1])) --run;
                if (run - i >= 3) {
                    end = run;
                } else {
                    end = i + 1;
                    while (end < s.size() && isLetter(s[end])) ++end;
                }
            }
        } else if (s[i] == '.') {
            // \.(\s*\.)+, backtracked to end on a dot.
            size_t k = i + 1;
            while (k < s.size()) {
                size_t next = k;
                while (next < s.size() && s[next] == ' ') ++next;
                if (next < s.size() && s[next] == '.') {
                    end = next + 1;
                    k = next + 1;
                } else {
                    break;
                }
            }
        }
        words.push_back(s.substr(i, end - i));
        i = end;
    }
    return words;
}

// `[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+` over an ASCII word:
// "ChatGPT" -> Chat, GPT; "iPhone" -> i, Phone; "XMLHttp" -> XML, Http.
// Characters that are not letters are skipped.
inline std::vector<std::string> splitEnglishCamelCase(const std::string &word) {
    using english_normalize_detail::isLetter;
    using english_normalize_detail::isUpper;
    auto isLower = [](char c) { return c >= 'a' && c <= 'z'; };

    std::vector<std::string> parts;
    size_t i = 0;
    while (i < word.size()) {
        if (!isLetter(word[i])) {
            ++i;
            continue;
        }
        size_t end;
        if (isUpper(word[i])) {
            size_t upperEnd = i;
            while (upperEnd < word.size() && isUpper(word[upperEnd])) ++upperEnd;
            if (upperEnd < word.size() && isLower(word[upperEnd])) {
                // An uppercase run before a capitalized word keeps all but
                // its last capital; a single capital starts the word.
                if (upperEnd - i >= 2) {
                    end = upperEnd - 1;
                } else {
                    end = upperEnd;
                    while (end < word.size() && isLower(word[end])) ++end;
                }
            } else {
                end = upperEnd;
            }
        } else {
            end = i;
            while (end < word.size() && isLower(word[end])) ++end;
        }
        parts.push_back(word.substr(i, end - i));
        i = end;
    }
    return parts;
}

// ARPAbet of a letter's name (design doc 3.5), or nullptr for a non-letter.
inline const char *englishLetterArpabet(char letter) {
    static const char *const names[] = {
        "EY1",   "B IY1", "S IY1",   "D IY1", "IY1",   "EH1 F", "JH IY1",
        "EY1 CH", "AY1",  "JH EY1",  "K EY1", "EH1 L", "EH1 M", "EH1 N",
        "OW1",   "P IY1", "K Y UW1", "AA1 R", "EH1 S", "T IY1", "Y UW1",
        "V IY1", "D AH1 B AH0 L Y UW0", "EH1 K S", "W AY1", "Z IY1",
    };
    if (!english_normalize_detail::isLetter(letter)) return nullptr;
    return names[english_normalize_detail::toLower(letter) - 'a'];
}

// english.py _get_source_words: re.findall(r"[a-zA-Z']+", text.lower()) over
// the text BEFORE number expansion. phonemize_english matches these to the
// words that are not punctuation, in order, to find function words.
inline std::vector<std::string> englishSourceWords(const std::string &text) {
    using english_normalize_detail::isLetter;
    using english_normalize_detail::toLower;
    std::vector<std::string> words;
    size_t i = 0;
    while (i < text.size()) {
        if (!isLetter(text[i]) && text[i] != '\'') {
            ++i;
            continue;
        }
        std::string word;
        while (i < text.size() && (isLetter(text[i]) || text[i] == '\'')) {
            word += toLower(text[i++]);
        }
        words.push_back(std::move(word));
    }
    return words;
}

}  // namespace piper

#endif  // PIPER_PLUS_ENGLISH_NORMALIZE_HPP
