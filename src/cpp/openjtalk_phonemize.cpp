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
// This MUST match the Python implementation in jp_id_map.py exactly
static const std::unordered_map<std::string, char32_t> phonemeToPua = {
    // Long vowels (matches Python order)
    {"a:", 0xE000}, {"i:", 0xE001}, {"u:", 0xE002}, {"e:", 0xE003}, {"o:", 0xE004},
    // Special consonants
    {"cl", 0xE005}, // 促音/終止閉鎖
    // Palatalized consonants - matches Python order exactly
    {"ky", 0xE006}, {"kw", 0xE007}, {"gy", 0xE008}, {"gw", 0xE009},
    {"ty", 0xE00A}, {"dy", 0xE00B}, {"py", 0xE00C}, {"by", 0xE00D}, 
    {"ch", 0xE00E}, {"ts", 0xE00F}, {"sh", 0xE010}, 
    {"zy", 0xE011}, {"hy", 0xE012}, {"ny", 0xE013}, 
    {"my", 0xE014}, {"ry", 0xE015}
    // Note: N, q, j are single characters and don't need PUA mapping
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
    
    // Parse phoneme string - phonemes are space-separated, sil marks sentence boundaries
    std::vector<Phoneme> sentencePhonemes;
    std::stringstream phonemeStream(phoneme_string);
    std::string phoneme;
    
    while (phonemeStream >> phoneme) {
        if (phoneme == "sil") {
            // Sentence boundary
            if (!sentencePhonemes.empty()) {
                phonemes.push_back(sentencePhonemes);
                sentencePhonemes.clear();
            }
        } else if (phoneme == "pau") {
            // Short pause within sentence - add a special pause marker
            sentencePhonemes.push_back(static_cast<Phoneme>('_'));
        } else {
            // Regular phoneme
            spdlog::debug("Processing phoneme: '{}' (length: {})", phoneme, phoneme.length());
            
            // Check if this is a multi-character phoneme that needs PUA
            auto it = phonemeToPua.find(phoneme);
            if (it != phonemeToPua.end()) {
                spdlog::debug("Found PUA mapping for '{}': U+{:04X}", phoneme, static_cast<uint32_t>(it->second));
                sentencePhonemes.push_back(it->second);
            } else if (phoneme.length() == 1) {
                // Single character phoneme
                spdlog::debug("Single character phoneme '{}': U+{:04X}", phoneme, static_cast<uint32_t>(phoneme[0]));
                sentencePhonemes.push_back(static_cast<Phoneme>(phoneme[0]));
            } else {
                // Unknown multi-character phoneme, skip
                spdlog::warn("Unknown multi-character phoneme: '{}' (length: {})", phoneme, phoneme.length());
            }
        }
    }
    
    // Add any remaining phonemes as final sentence
    if (!sentencePhonemes.empty()) {
        phonemes.push_back(sentencePhonemes);
    }

    spdlog::debug("OpenJTalk phonemization complete: {} sentences", phonemes.size());
}

void phonemize_openjtalk_with_prosody(
    const std::string &text,
    std::vector<std::vector<Phoneme>> &phonemes,
    std::vector<std::vector<ProsodyFeature>> &prosodyFeatures) {

    spdlog::debug("OpenJTalk phonemizer with prosody called with text: {}", text);

    // Clear any existing data
    phonemes.clear();
    prosodyFeatures.clear();

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

    // Get phonemes with prosody from OpenJTalk
    OpenJTalkProsodyResult* result = openjtalk_text_to_phonemes_with_prosody(text.c_str());
    if (!result) {
        spdlog::error("OpenJTalk failed to convert text to phonemes with prosody");
        return;
    }

    std::string phoneme_string(result->phonemes);
    spdlog::debug("OpenJTalk returned {} phonemes with prosody", result->count);

    // Parse phoneme string - phonemes are space-separated, sil marks sentence boundaries
    std::vector<Phoneme> sentencePhonemes;
    std::vector<ProsodyFeature> sentenceProsody;
    std::stringstream phonemeStream(phoneme_string);
    std::string phoneme;
    int phonemeIdx = 0;

    while (phonemeStream >> phoneme && phonemeIdx < result->count) {
        // Get prosody values for current phoneme
        ProsodyFeature pf;
        pf.a1 = result->prosody_a1[phonemeIdx];
        pf.a2 = result->prosody_a2[phonemeIdx];
        pf.a3 = result->prosody_a3[phonemeIdx];

        if (phoneme == "sil") {
            // Sentence boundary
            if (!sentencePhonemes.empty()) {
                phonemes.push_back(sentencePhonemes);
                prosodyFeatures.push_back(sentenceProsody);
                sentencePhonemes.clear();
                sentenceProsody.clear();
            }
        } else if (phoneme == "pau") {
            // Short pause within sentence - add a special pause marker with zero prosody
            sentencePhonemes.push_back(static_cast<Phoneme>('_'));
            sentenceProsody.push_back({0, 0, 0});
        } else {
            // Regular phoneme
            auto it = phonemeToPua.find(phoneme);
            if (it != phonemeToPua.end()) {
                sentencePhonemes.push_back(it->second);
                sentenceProsody.push_back(pf);
            } else if (phoneme.length() == 1) {
                sentencePhonemes.push_back(static_cast<Phoneme>(phoneme[0]));
                sentenceProsody.push_back(pf);
            } else {
                spdlog::warn("Unknown multi-character phoneme: '{}' (length: {})", phoneme, phoneme.length());
            }
        }
        phonemeIdx++;
    }

    // Add any remaining phonemes as final sentence
    if (!sentencePhonemes.empty()) {
        phonemes.push_back(sentencePhonemes);
        prosodyFeatures.push_back(sentenceProsody);
    }

    // Clean up
    openjtalk_free_prosody_result(result);

    spdlog::debug("OpenJTalk phonemization with prosody complete: {} sentences", phonemes.size());
}

} // namespace piper