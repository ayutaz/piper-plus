#include "phoneme_parser.hpp"
#include <sstream>
#include <algorithm>
#include <map>
#include <spdlog/spdlog.h>

namespace piper {

// Japanese multi-character phoneme mappings (PUA)
// Must match Python token_mapper.py FIXED_PUA_MAPPING
static const std::map<std::string, char32_t> japanesePhonemePUA = {
    // Long vowels
    {"a:", 0xE000},
    {"i:", 0xE001},
    {"u:", 0xE002},
    {"e:", 0xE003},
    {"o:", 0xE004},
    // Special consonants
    {"cl", 0xE005},
    // Palatalized consonants
    {"ky", 0xE006},
    {"kw", 0xE007},
    {"gy", 0xE008},
    {"gw", 0xE009},
    {"ty", 0xE00A},
    {"dy", 0xE00B},
    {"py", 0xE00C},
    {"by", 0xE00D},
    // Affricates and special sounds
    {"ch", 0xE00E},
    {"ts", 0xE00F},
    {"sh", 0xE010},
    {"zy", 0xE011},
    {"hy", 0xE012},
    // Palatalized nasals/liquids
    {"ny", 0xE013},
    {"my", 0xE014},
    {"ry", 0xE015},
    // Question type markers (Issue #204)
    {"?!", 0xE016},  // Emphatic question - 強調疑問
    {"?.", 0xE017},  // Neutral/rhetorical question - 平叙疑問
    {"?~", 0xE018},  // Tag question - 確認疑問
    // N phoneme variants (Issue #207)
    {"N_m", 0xE019},      // ん before m/b/p (bilabial)
    {"N_n", 0xE01A},      // ん before n/t/d/ts/ch (alveolar)
    {"N_ng", 0xE01B},     // ん before k/g (velar)
    {"N_uvular", 0xE01C}, // ん at end or before vowels
};

std::vector<TextOrPhonemes> parsePhonemeNotation(const std::string& input) {
    std::vector<TextOrPhonemes> result;
    std::regex phonemeRegex(R"(\[\[\s*([^\]]*)\s*\]\])");
    
    size_t lastPos = 0;
    auto begin = std::sregex_iterator(input.begin(), input.end(), phonemeRegex);
    auto end = std::sregex_iterator();
    
    for (std::sregex_iterator i = begin; i != end; ++i) {
        std::smatch match = *i;
        
        // Add text before the phoneme notation
        if (static_cast<size_t>(match.position()) > lastPos) {
            TextOrPhonemes textSegment;
            textSegment.isPhonemes = false;
            textSegment.text = input.substr(lastPos, match.position() - lastPos);
            result.push_back(textSegment);
        }
        
        // Add the phonemes
        TextOrPhonemes phonemeSegment;
        phonemeSegment.isPhonemes = true;
        std::string phonemeStr = match[1].str();
        // Trim trailing whitespace
        phonemeStr.erase(phonemeStr.find_last_not_of(" \t\n\r") + 1);
        phonemeSegment.text = phonemeStr; // Store trimmed phoneme string
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

std::vector<Phoneme> parsePhonemeString(const std::string& phonemeStr, PhonemeTypeInt phonemeType) {
    std::vector<Phoneme> phonemes;
    std::istringstream iss(phonemeStr);
    std::string token;
    
    // Split by whitespace
    while (iss >> token) {
        if (token.empty()) continue;
        
        if (phonemeType == PHONEME_TYPE_OPENJTALK) {
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