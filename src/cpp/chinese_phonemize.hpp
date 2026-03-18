#ifndef CHINESE_PHONEMIZE_HPP
#define CHINESE_PHONEMIZE_HPP

#include <string>
#include <vector>
#include <unordered_map>

#include "phoneme_parser.hpp" // Phoneme = char32_t

namespace piper {

// Load pypinyin dictionaries from JSON files.
// singleCharPath: path to pinyin_single.json (codepoint -> pinyin)
// phrasePath:     path to pinyin_phrases.json (char sequence -> pinyin)
bool loadPinyinDicts(const std::string& singleCharPath,
                     const std::string& phrasePath,
                     std::unordered_map<int, std::string>& singleCharDict,
                     std::unordered_map<std::string, std::string>& phraseDict);

// Phonemize Chinese text using pypinyin dictionaries + pinyin-to-IPA conversion.
// Implements the full pipeline from chinese.py:
//   1. Text -> pinyin (dictionary lookup with phrase matching)
//   2. Pinyin normalization (y/w stripping, v->u-umlaut)
//   3. Tone sandhi (T3+T3, yi, bu rules)
//   4. Pinyin -> IPA conversion (initial/final split, compound finals)
//   5. Erhua handling
//   6. Multi-char IPA -> PUA codepoint mapping
//
// Output is a vector of sentences, each sentence a vector of Phoneme (char32_t).
// Non-CJK characters (punctuation, Latin, digits) are passed through as-is.
void phonemize_chinese(const std::string& text,
                       std::vector<std::vector<Phoneme>>& phonemes,
                       const std::unordered_map<int, std::string>& singleCharDict,
                       const std::unordered_map<std::string, std::string>& phraseDict);

} // namespace piper

#endif // CHINESE_PHONEMIZE_HPP
