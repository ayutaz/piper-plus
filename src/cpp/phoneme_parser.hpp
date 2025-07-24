#ifndef PHONEME_PARSER_H_
#define PHONEME_PARSER_H_

#include <string>
#include <vector>
#include <regex>
#include <cstdint>

namespace piper {

// Forward declarations to avoid including piper.hpp
typedef char32_t Phoneme;
enum PhonemeType { 
  eSpeakPhonemes, 
  TextPhonemes,
  OpenJTalkPhonemes
};

// Structure to hold either text or phonemes
struct TextOrPhonemes {
    bool isPhonemes;
    std::string text;
    std::vector<Phoneme> phonemes;
};

// Parse text containing [[ phonemes ]] notation
// Returns a vector of TextOrPhonemes segments
std::vector<TextOrPhonemes> parsePhonemeNotation(const std::string& input);

// Convert phoneme string to vector of Phoneme objects
// Handles both single-character and multi-character phonemes
std::vector<Phoneme> parsePhonemeString(const std::string& phonemeStr, PhonemeType phonemeType);

} // namespace piper

#endif // PHONEME_PARSER_H_