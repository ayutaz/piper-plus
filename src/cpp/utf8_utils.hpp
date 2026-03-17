// Shared UTF-8 utility functions for Piper TTS C++ phonemizers.
//
// Consolidates toCodepoints / utf8ToU32 / utf8Decode / cpToUtf8 / cpsToUtf8
// that were previously duplicated across every phonemizer .cpp file.
// All functions use utf8::unchecked internally; callers must validate input
// with utf8::is_valid() before calling these helpers.

#ifndef UTF8_UTILS_HPP
#define UTF8_UTILS_HPP

#include "utf8.h"

#include <cstdint>
#include <string>
#include <vector>

namespace piper {
namespace utf8_util {

// Decode a UTF-8 string to a vector of char32_t codepoints.
// Input MUST be valid UTF-8 (caller is responsible for validation).
inline std::vector<char32_t> toCodepoints(const std::string &s) {
    std::vector<char32_t> cps;
    auto it = s.begin();
    while (it != s.end()) {
        cps.push_back(utf8::unchecked::next(it));
    }
    return cps;
}

// Decode a UTF-8 string to a std::u32string.
// Input MUST be valid UTF-8 (caller is responsible for validation).
inline std::u32string utf8ToU32(const std::string &s) {
    std::u32string result;
    auto it = s.begin();
    while (it != s.end()) {
        result.push_back(utf8::unchecked::next(it));
    }
    return result;
}

// Encode a single codepoint to a UTF-8 string.
inline std::string cpToUtf8(char32_t cp) {
    std::string s;
    utf8::unchecked::append(cp, std::back_inserter(s));
    return s;
}

// Encode a vector of codepoints to a UTF-8 string.
inline std::string cpsToUtf8(const std::vector<char32_t> &cps) {
    std::string s;
    for (auto cp : cps) {
        utf8::unchecked::append(cp, std::back_inserter(s));
    }
    return s;
}

// Encode a sub-range of a codepoint vector to a UTF-8 string.
inline std::string cpsToUtf8(const std::vector<char32_t> &cps,
                              size_t start, size_t count) {
    std::string s;
    for (size_t i = start; i < start + count && i < cps.size(); ++i) {
        utf8::unchecked::append(cps[i], std::back_inserter(s));
    }
    return s;
}

} // namespace utf8_util
} // namespace piper

#endif // UTF8_UTILS_HPP
