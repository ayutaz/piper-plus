#ifndef ENGLISH_PHONEMIZE_HPP
#define ENGLISH_PHONEMIZE_HPP

#include <string>
#include <unordered_map>
#include <vector>

#include "phoneme_parser.hpp" // Phoneme = char32_t

namespace piper {

// Load CMU dictionary from a JSON file.
// The JSON must be an object mapping lowercase words to ARPAbet strings,
// e.g. {"hello": "HH AH0 L OW1", "world": "W ER1 L D"}.
// Returns true if the file was loaded successfully.
bool loadCmuDict(const std::string &jsonPath,
                 std::unordered_map<std::string, std::string> &dict);

// Phonemize English text using CMU dictionary + ARPAbet-to-IPA conversion.
//
// Pipeline (matches Python piper_train/phonemize/english.py):
//   1. Tokenize text into words and punctuation
//   2. Look up each word in the CMU dictionary
//   3. Convert ARPAbet to IPA with context-dependent rules
//      (AA+R -> merged, stressed ER -> open variant, etc.)
//   4. Apply function-word destressing
//   5. Insert stress markers before stressed vowels
//   6. Each IPA character is a separate Phoneme (char32_t)
//
// Words not found in the dictionary are handled by morphological fallback
// (stripping common suffixes and retrying the lookup).  Truly OOV words
// produce no phonemes for that word.
//
// Output is a vector of sentences (typically one), each sentence a vector
// of Phoneme codepoints.
void phonemize_english(const std::string &text,
                       std::vector<std::vector<Phoneme>> &phonemes,
                       const std::unordered_map<std::string, std::string> &cmuDict);

} // namespace piper

#endif // ENGLISH_PHONEMIZE_HPP
