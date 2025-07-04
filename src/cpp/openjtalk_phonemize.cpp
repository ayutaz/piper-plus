#include "openjtalk_phonemize.hpp"
#include <spdlog/spdlog.h>
#include <filesystem>
#include <cstdlib>
#include <sstream>
#include <memory>
#include <cstring>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace piper {

// Convert OpenJTalk phonemes to PUA characters for multi-phoneme support
static const std::unordered_map<std::string, char32_t> phonemeToPua = {
    {"a:", 0xE000}, {"i:", 0xE001}, {"u:", 0xE002}, {"e:", 0xE003}, {"o:", 0xE004},
    {"cl", 0xE005}, {"ky", 0xE006}, {"kw", 0xE007}, {"gy", 0xE008}, {"gw", 0xE009},
    {"ty", 0xE00A}, {"dy", 0xE00B}, {"py", 0xE00C}, {"by", 0xE00D}, {"ch", 0xE00E},
    {"ts", 0xE00F}, {"sh", 0xE010}, {"zy", 0xE011}, {"hy", 0xE012}, {"ny", 0xE013},
    {"my", 0xE014}, {"ry", 0xE015}
};

void phonemize_openjtalk(const std::string &text, std::vector<std::vector<Phoneme>> &phonemes) {
    spdlog::debug("OpenJTalk phonemizer called with text: {}", text);
    
    // Clear any existing phonemes
    phonemes.clear();
    
    // Check if OpenJTalk is available
    if (!openjtalk_is_available()) {
        spdlog::warn("OpenJTalk is not available on this system");
        return;
    }
    
    // Ensure dictionary is available
    if (!openjtalk_ensure_dictionary()) {
        spdlog::error("Failed to ensure OpenJTalk dictionary is available");
        return;
    }
    
    // Get phonemes from OpenJTalk
    char* phoneme_str = openjtalk_text_to_phonemes(text.c_str());
    if (!phoneme_str) {
        spdlog::error("OpenJTalk failed to convert text to phonemes");
        return;
    }
    
    // Parse phoneme string
    std::string phoneme_string(phoneme_str);
    openjtalk_free_phonemes(phoneme_str);
    
    spdlog::debug("OpenJTalk returned phonemes: {}", phoneme_string);
    
    // Split into sentences (OpenJTalk separates sentences with a period)
    std::vector<std::string> sentences;
    std::stringstream ss(phoneme_string);
    std::string sentence;
    
    while (std::getline(ss, sentence, '.')) {
        if (!sentence.empty()) {
            sentences.push_back(sentence);
        }
    }
    
    // Convert each sentence's phonemes
    for (const auto& sent : sentences) {
        std::vector<Phoneme> sentencePhonemes;
        std::stringstream phonemeStream(sent);
        std::string phoneme;
        
        while (phonemeStream >> phoneme) {
            // Check if this is a multi-character phoneme that needs PUA
            auto it = phonemeToPua.find(phoneme);
            if (it != phonemeToPua.end()) {
                sentencePhonemes.push_back(it->second);
            } else if (phoneme.length() == 1) {
                // Single character phoneme
                sentencePhonemes.push_back(static_cast<Phoneme>(phoneme[0]));
            } else {
                // Unknown multi-character phoneme, skip
                spdlog::warn("Unknown multi-character phoneme: {}", phoneme);
            }
        }
        
        if (!sentencePhonemes.empty()) {
            phonemes.push_back(sentencePhonemes);
        }
    }
    
    spdlog::debug("OpenJTalk phonemization complete: {} sentences", phonemes.size());
}

} // namespace piper