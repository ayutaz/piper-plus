#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include "../src/cpp/openjtalk_phonemize.hpp"
#include "../src/cpp/openjtalk_api.h"
#include "../src/cpp/utf8.h"

// Simple phoneme ID mapping for debugging
std::map<std::string, int> createPhonemeMap() {
    std::map<std::string, int> map;
    // Japanese phonemes
    map["^"] = 1;  // sentence start
    map["$"] = 2;  // sentence end
    map["_"] = 3;  // pause
    map["a"] = 10;
    map["i"] = 11;
    map["u"] = 12;
    map["e"] = 13;
    map["o"] = 14;
    map["k"] = 20;
    map["g"] = 21;
    map["s"] = 22;
    map["z"] = 23;
    map["t"] = 24;
    map["d"] = 25;
    map["n"] = 26;
    map["h"] = 27;
    map["b"] = 28;
    map["p"] = 29;
    map["m"] = 30;
    map["y"] = 31;
    map["r"] = 32;
    map["w"] = 33;
    map["N"] = 34; // ん
    map["cl"] = 35; // っ
    map["ts"] = 36;
    map["ch"] = 37;
    map["sh"] = 38;
    map["f"] = 39;
    map["j"] = 40;
    map["ky"] = 41;
    map["gy"] = 42;
    map["ny"] = 43;
    map["hy"] = 44;
    map["by"] = 45;
    map["py"] = 46;
    map["my"] = 47;
    map["ry"] = 48;
    return map;
}

// Convert phoneme to string for display
std::string phonemeToStr(piper::Phoneme p) {
    if (p < 128) {
        return std::string(1, static_cast<char>(p));
    }
    // Convert UTF-32 to UTF-8
    std::string result;
    utf8::append(p, std::back_inserter(result));
    return result;
}

void testOpenJTalkDirect(const std::string& text) {
    std::cout << "\n=== Direct OpenJTalk API Test ===" << std::endl;
    std::cout << "Input text: " << text << std::endl;
    
    // Initialize OpenJTalk
    OpenJTalk* oj = openjtalk_initialize();
    if (!oj) {
        std::cerr << "Failed to initialize OpenJTalk" << std::endl;
        return;
    }
    
    // Extract labels
    OJ_Label* labels = openjtalk_extract_fullcontext(oj, text.c_str());
    if (!labels) {
        std::cerr << "Failed to extract labels" << std::endl;
        openjtalk_finalize(oj);
        return;
    }
    
    size_t num_labels = OJ_Label_get_size(labels);
    std::cout << "Number of labels: " << num_labels << std::endl;
    
    // Process each label
    std::cout << "\nLabel details:" << std::endl;
    for (size_t i = 0; i < num_labels; ++i) {
        const char* label = OJ_Label_get_string(labels, i);
        if (!label) continue;
        
        std::string lab(label);
        std::cout << "Label[" << i << "]: " << lab << std::endl;
        
        // Parse phoneme from label
        auto pos1 = lab.find('-');
        auto pos2 = lab.find('+');
        if (pos1 != std::string::npos && pos2 != std::string::npos && pos2 > pos1) {
            std::string phoneme = lab.substr(pos1 + 1, pos2 - pos1 - 1);
            std::cout << "  -> Extracted phoneme: '" << phoneme << "'" << std::endl;
            
            // Handle special cases
            if (phoneme == "sil") {
                if (i == 0) {
                    std::cout << "  -> Mapped to: '^' (sentence start)" << std::endl;
                } else {
                    std::cout << "  -> Mapped to: '$' (sentence end)" << std::endl;
                }
            } else if (phoneme == "pau") {
                std::cout << "  -> Mapped to: '_' (pause)" << std::endl;
            } else {
                // Check if it's a devoiced vowel (uppercase)
                if (phoneme.size() == 1 && std::isupper(phoneme[0])) {
                    std::cout << "  -> Devoiced vowel, converting to: '" 
                              << static_cast<char>(std::tolower(phoneme[0])) << "'" << std::endl;
                }
            }
        }
    }
    
    // Cleanup
    OJ_Label_clear(labels);
    openjtalk_finalize(oj);
}

void testPhonemize(const std::string& text) {
    std::cout << "\n=== Phonemize Function Test ===" << std::endl;
    std::cout << "Input text: " << text << std::endl;
    
    std::vector<std::vector<piper::Phoneme>> sentences;
    piper::phonemize_openjtalk(text, sentences);
    
    std::cout << "Number of sentences: " << sentences.size() << std::endl;
    
    auto phonemeMap = createPhonemeMap();
    
    for (size_t i = 0; i < sentences.size(); ++i) {
        std::cout << "\nSentence " << i << ": " << sentences[i].size() << " phonemes" << std::endl;
        std::cout << "Phonemes: ";
        
        for (const auto& phoneme : sentences[i]) {
            std::string pStr = phonemeToStr(phoneme);
            std::cout << "'" << pStr << "' ";
            
            // Try to find in phoneme map
            auto it = phonemeMap.find(pStr);
            if (it != phonemeMap.end()) {
                std::cout << "(" << it->second << ") ";
            } else {
                std::cout << "(?) ";
            }
        }
        std::cout << std::endl;
        
        // Also show as raw values
        std::cout << "Raw values: ";
        for (const auto& phoneme : sentences[i]) {
            std::cout << static_cast<uint32_t>(phoneme) << " ";
        }
        std::cout << std::endl;
    }
}

int main(int argc, char* argv[]) {
    // Test texts
    std::vector<std::string> testTexts = {
        "こんにちは",
        "今日はいい天気ですね。",
        "OpenJTalkのテストです。",
        "Hello World"  // Test with English
    };
    
    if (argc > 1) {
        // Use command line argument as test text
        testTexts.clear();
        testTexts.push_back(argv[1]);
    }
    
    for (const auto& text : testTexts) {
        std::cout << "\n========================================" << std::endl;
        testOpenJTalkDirect(text);
        testPhonemize(text);
    }
    
    return 0;
}