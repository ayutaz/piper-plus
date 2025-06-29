// Minimal phonemize implementation for Windows
// This provides a basic phonemization interface without full piper-phonemize dependencies

#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <cctype>

#ifdef _WIN32
#define PHONEMIZE_API __declspec(dllexport)
#else
#define PHONEMIZE_API
#endif

namespace piper {

// Simple phoneme mapping for basic English
static const std::map<std::string, std::string> BASIC_PHONEME_MAP = {
    {"a", "æ"}, {"e", "ɛ"}, {"i", "ɪ"}, {"o", "ɒ"}, {"u", "ʌ"},
    {"th", "θ"}, {"sh", "ʃ"}, {"ch", "tʃ"}, {"ng", "ŋ"},
    {"ee", "iː"}, {"oo", "uː"}, {"ar", "ɑː"}, {"er", "ɜː"}, {"or", "ɔː"}
};

// Minimal phonemize function
PHONEMIZE_API std::string phonemize_text(const std::string& text, const std::string& language = "en") {
    std::string result;
    std::string lower_text = text;
    
    // Convert to lowercase
    for (char& c : lower_text) {
        c = std::tolower(c);
    }
    
    // Simple word boundary detection
    std::istringstream iss(lower_text);
    std::string word;
    bool first_word = true;
    
    while (iss >> word) {
        if (!first_word) {
            result += " ";
        }
        first_word = false;
        
        // Process each word
        size_t i = 0;
        while (i < word.length()) {
            bool found = false;
            
            // Try two-character combinations first
            if (i + 1 < word.length()) {
                std::string two_char = word.substr(i, 2);
                auto it = BASIC_PHONEME_MAP.find(two_char);
                if (it != BASIC_PHONEME_MAP.end()) {
                    result += it->second;
                    i += 2;
                    found = true;
                }
            }
            
            // Single character
            if (!found) {
                if (std::isalpha(word[i])) {
                    std::string single_char(1, word[i]);
                    auto it = BASIC_PHONEME_MAP.find(single_char);
                    if (it != BASIC_PHONEME_MAP.end()) {
                        result += it->second;
                    } else {
                        result += word[i];
                    }
                } else {
                    result += word[i];
                }
                i++;
            }
        }
    }
    
    return result;
}

// Minimal espeak compatibility layer
class MinimalEspeak {
public:
    static MinimalEspeak& getInstance() {
        static MinimalEspeak instance;
        return instance;
    }
    
    std::vector<std::string> textToPhonemes(const std::string& text, const std::string& voice = "en") {
        std::vector<std::string> phonemes;
        std::string phoneme_text = phonemize_text(text, voice);
        
        // Split into individual phonemes
        std::istringstream iss(phoneme_text);
        std::string phoneme;
        while (iss >> phoneme) {
            phonemes.push_back(phoneme);
        }
        
        return phonemes;
    }
    
private:
    MinimalEspeak() = default;
};

} // namespace piper

// C interface for compatibility
extern "C" {
    PHONEMIZE_API const char* piper_phonemize(const char* text, const char* language) {
        static std::string result;
        result = piper::phonemize_text(text, language ? language : "en");
        return result.c_str();
    }
    
    PHONEMIZE_API void piper_phonemize_free(const char* /*phonemes*/) {
        // No-op for this implementation
    }
}