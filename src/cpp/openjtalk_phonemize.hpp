#ifndef OPENJTALK_PHONEMIZE_H
#define OPENJTALK_PHONEMIZE_H

#include <string>
#include <vector>
#include <unordered_map>
#include "piper.hpp"

extern "C" {
    // OpenJTalk C wrapper functions
    bool openjtalk_is_available();
    bool openjtalk_ensure_dictionary();
    char* openjtalk_text_to_phonemes(const char* text);
    void openjtalk_free_phonemes(char* phonemes);
}

namespace piper {

// Phonemize Japanese text using OpenJTalk
void phonemize_openjtalk(const std::string &text, 
                        std::vector<std::vector<Phoneme>> &phonemes);

} // namespace piper

#endif // OPENJTALK_PHONEMIZE_H