#ifndef SWEDISH_PHONEMIZE_HPP
#define SWEDISH_PHONEMIZE_HPP

#include <string>
#include <vector>

#include "phoneme_parser.hpp" // Phoneme = char32_t

namespace piper {

// Phonemize Swedish text using rule-based G2P.
// Output is a vector of sentences, each sentence a vector of Phoneme (char32_t)
// codepoints.  Multi-codepoint IPA symbols are mapped to PUA codepoints so that
// every phoneme is a single char32_t.
void phonemize_swedish(const std::string &text,
                       std::vector<std::vector<Phoneme>> &phonemes);

} // namespace piper

#endif // SWEDISH_PHONEMIZE_HPP
