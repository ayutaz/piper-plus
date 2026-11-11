// Strips control characters from a text before it is read, by the rule every
// runtime shares (docs/spec/input-sanitize-contract.toml).
//
// Header-only: piper.cpp, chinese_phonemize.cpp, the C API and main.cpp call
// it, and several test executables compile those sources directly.

#ifndef PIPER_TEXT_SANITIZE_HPP
#define PIPER_TEXT_SANITIZE_HPP

#include <string>

namespace piper {

// Returns utf8 cleaned by the input-sanitize rule: '\n', '\t' and '\r' stay
// (sentence splitting and SSML use them); VT, FF and NEL (U+000B, U+000C,
// U+0085) separate words, so they become a space; every other control
// character (Unicode category Cc: U+0000-001F, U+007F, U+0080-009F) is
// removed. Format characters (U+200D, U+FEFF), separators (U+2028) and NBSP
// stay.
//
// Works on bytes: C0 and DEL are single bytes, and C1 is the two-byte
// sequence 0xC2 0x80-0x9F. Bytes that are not valid UTF-8 are kept as they
// are, so the phonemizers see the same invalid input as before.
inline std::string stripControlChars(const std::string &utf8) {
  std::string out;
  out.reserve(utf8.size());
  const std::size_t n = utf8.size();
  for (std::size_t i = 0; i < n; ++i) {
    const auto b = static_cast<unsigned char>(utf8[i]);
    if (b < 0x20) {
      if (b == '\n' || b == '\t' || b == '\r') {
        out.push_back(static_cast<char>(b));
      } else if (b == 0x0B || b == 0x0C) {
        out.push_back(' ');
      }
      continue;
    }
    if (b == 0x7F) {
      continue;
    }
    if (b == 0xC2 && i + 1 < n) {
      const auto next = static_cast<unsigned char>(utf8[i + 1]);
      if (next >= 0x80 && next <= 0x9F) {
        if (next == 0x85) {
          out.push_back(' ');
        }
        ++i;
        continue;
      }
    }
    out.push_back(static_cast<char>(b));
  }
  return out;
}

}  // namespace piper

#endif  // PIPER_TEXT_SANITIZE_HPP
