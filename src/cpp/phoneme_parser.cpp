#include "phoneme_parser.hpp"
#include <sstream>
#include <algorithm>
#include <spdlog/spdlog.h>

namespace piper {

// Japanese multi-character phoneme mappings (PUA)
static const std::map<std::string, char32_t> japanesePhonemePUA = {
    {"ky", 0xE000}, {"gy", 0xE001}, {"sy", 0xE002}, {"sh", 0xE002},
    {"zy", 0xE003}, {"jy", 0xE003}, {"ty", 0xE004}, {"ch", 0xE004},
    {"dy", 0xE005}, {"ny", 0xE006}, {"hy", 0xE007}, {"by", 0xE008},
    {"py", 0xE009}, {"my", 0xE00A}, {"ry", 0xE00B}, {"ts", 0xE00C},
    {"dz", 0xE00D}, {"kw", 0xE00E}, {"f", 0xE00F}, {"gw", 0xE010},
    {"v", 0xE011}, {"dy", 0xE012}, {"mh", 0xE013}, {"nh", 0xE014},
    {"nw", 0xE015}
};

std::vector<TextOrPhonemes> parsePhonemeNotation(const std::string& input) {
    std::vector<TextOrPhonemes> result;
    std::regex phonemeRegex(R"(\[\[\s*([^\]]+)\s*\]\])");
    
    size_t lastPos = 0;
    auto begin = std::sregex_iterator(input.begin(), input.end(), phonemeRegex);
    auto end = std::sregex_iterator();
    
    for (std::sregex_iterator i = begin; i != end; ++i) {
        std::smatch match = *i;
        
        // Add text before the phoneme notation
        if (match.position() > lastPos) {
            TextOrPhonemes textSegment;
            textSegment.isPhonemes = false;
            textSegment.text = input.substr(lastPos, match.position() - lastPos);
            result.push_back(textSegment);
        }
        
        // Add the phonemes
        TextOrPhonemes phonemeSegment;
        phonemeSegment.isPhonemes = true;
        phonemeSegment.text = match[1].str(); // Store original phoneme string
        // Phonemes will be parsed later based on the phoneme type
        result.push_back(phonemeSegment);
        
        lastPos = match.position() + match.length();
    }
    
    // Add any remaining text
    if (lastPos < input.length()) {
        TextOrPhonemes textSegment;
        textSegment.isPhonemes = false;
        textSegment.text = input.substr(lastPos);
        result.push_back(textSegment);
    }
    
    return result;
}

std::vector<Phoneme> parsePhonemeString(const std::string& phonemeStr, PhonemeType phonemeType) {
    std::vector<Phoneme> phonemes;
    std::istringstream iss(phonemeStr);
    std::string token;
    
    // Split by whitespace
    while (iss >> token) {
        if (token.empty()) continue;
        
        if (phonemeType == OpenJTalkPhonemes) {
            // For Japanese, check if it's a multi-character phoneme
            auto it = japanesePhonemePUA.find(token);
            if (it != japanesePhonemePUA.end()) {
                // Use the PUA codepoint directly
                phonemes.push_back(it->second);
            } else if (token.length() == 1) {
                // Single character phoneme
                phonemes.push_back(static_cast<Phoneme>(token[0]));
            } else {
                // Unknown multi-character phoneme, add each character separately
                for (char c : token) {
                    phonemes.push_back(static_cast<Phoneme>(c));
                }
            }
        } else {
            // For espeak-ng and text phonemes
            if (token == "pau" || token == "_") {
                // Pause marker
                phonemes.push_back(static_cast<Phoneme>('_'));
            } else if (token.length() == 1) {
                // Single character
                phonemes.push_back(static_cast<Phoneme>(token[0]));
            } else {
                // Multi-character phoneme for espeak - convert from UTF-8
                // For now, just use the first character as a simple implementation
                // In a full implementation, we'd need proper UTF-8 decoding
                const char* str = token.c_str();
                size_t len = token.length();
                size_t i = 0;
                
                while (i < len) {
                    char32_t codepoint = 0;
                    unsigned char c = str[i];
                    
                    if ((c & 0x80) == 0) {
                        // ASCII character
                        codepoint = c;
                        i++;
                    } else if ((c & 0xE0) == 0xC0) {
                        // 2-byte UTF-8
                        if (i + 1 < len) {
                            codepoint = ((c & 0x1F) << 6) | (str[i+1] & 0x3F);
                            i += 2;
                        } else {
                            i++;
                        }
                    } else if ((c & 0xF0) == 0xE0) {
                        // 3-byte UTF-8
                        if (i + 2 < len) {
                            codepoint = ((c & 0x0F) << 12) | ((str[i+1] & 0x3F) << 6) | (str[i+2] & 0x3F);
                            i += 3;
                        } else {
                            i++;
                        }
                    } else if ((c & 0xF8) == 0xF0) {
                        // 4-byte UTF-8
                        if (i + 3 < len) {
                            codepoint = ((c & 0x07) << 18) | ((str[i+1] & 0x3F) << 12) | 
                                       ((str[i+2] & 0x3F) << 6) | (str[i+3] & 0x3F);
                            i += 4;
                        } else {
                            i++;
                        }
                    } else {
                        // Invalid UTF-8, skip
                        i++;
                        continue;
                    }
                    
                    if (codepoint > 0) {
                        phonemes.push_back(codepoint);
                    }
                }
            }
        }
    }
    
    spdlog::debug("Parsed {} phonemes from string: {}", phonemes.size(), phonemeStr);
    return phonemes;
}

} // namespace piper