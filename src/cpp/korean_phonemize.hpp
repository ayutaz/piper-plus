#ifndef KOREAN_PHONEMIZE_HPP
#define KOREAN_PHONEMIZE_HPP

#include <string>
#include <vector>

#include "phoneme_parser.hpp" // Phoneme = char32_t

namespace piper {

// Phonemize Korean text using Hangul decomposition + IPA mapping.
// Output is a vector of sentences, each sentence a vector of Phoneme (char32_t)
// codepoints.  Multi-codepoint IPA symbols are mapped to PUA codepoints so that
// every phoneme is a single char32_t.
//
// Without g2pk2 (C++ has no access to the Python G2P engine), this performs
// pure Hangul decomposition with basic liaison as the only phonological rule.
void phonemize_korean(const std::string &text,
                      std::vector<std::vector<Phoneme>> &phonemes);

} // namespace piper

#endif // KOREAN_PHONEMIZE_HPP
