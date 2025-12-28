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

    // Prosody result structure for phonemes with A1/A2/A3 values
    typedef struct {
        char* phonemes;         // Space-separated phonemes
        int* prosody_a1;        // A1 values for each phoneme
        int* prosody_a2;        // A2 values for each phoneme
        int* prosody_a3;        // A3 values for each phoneme
        int count;              // Number of phonemes
    } OpenJTalkProsodyResult;

    // Get phonemes with prosody features from text
    OpenJTalkProsodyResult* openjtalk_text_to_phonemes_with_prosody(const char* text);
    void openjtalk_free_prosody_result(OpenJTalkProsodyResult* result);
}

namespace piper {

// Prosody info for a phoneme (A1/A2/A3 values from OpenJTalk)
struct ProsodyFeature {
    int a1;  // Relative position from accent nucleus
    int a2;  // Position in accent phrase (1-based)
    int a3;  // Total morae in accent phrase
};

// Phonemize Japanese text using OpenJTalk
void phonemize_openjtalk(const std::string &text,
                        std::vector<std::vector<Phoneme>> &phonemes);

// Phonemize Japanese text with prosody features
void phonemize_openjtalk_with_prosody(
    const std::string &text,
    std::vector<std::vector<Phoneme>> &phonemes,
    std::vector<std::vector<ProsodyFeature>> &prosodyFeatures);

} // namespace piper

#endif // OPENJTALK_PHONEMIZE_H