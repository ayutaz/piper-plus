#ifndef OPENJTALK_PHONEMIZE_UTILS_H
#define OPENJTALK_PHONEMIZE_UTILS_H

#include <string>
#include <vector>
#include <unordered_map>

namespace piper {

// PUA mapping from multi-character phoneme tokens to Unicode Private Use Area
// This MUST match the Python implementation in jp_id_map.py exactly
extern const std::unordered_map<std::string, char32_t> phonemeToPua;

// Determine question type from the text ending (matches Python _get_question_type)
std::string getQuestionType(const std::string& text);

// Check if a token is a special/prosody token (should be skipped for N-variant lookahead)
bool isSpecialToken(const std::string& token);

// Apply context-dependent N phoneme rules (matches Python _apply_n_phoneme_rules)
void applyNPhonemeRules(std::vector<std::string>& tokens);

} // namespace piper

#endif // OPENJTALK_PHONEMIZE_UTILS_H
