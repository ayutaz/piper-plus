/**
 * OpenJTalk WebAssembly Core Implementation
 * 
 * Japanese text processing and phoneme generation for TTS
 * Based on OpenJTalk 1.11
 */

#include <emscripten.h>
#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <string>
#include <vector>
#include <memory>
#include <iostream>
#include <sstream>
#include <algorithm>
#include <unordered_map>
#include <cstring>
#include "error_handler.h"

using namespace emscripten;

namespace openjtalk {

// Phoneme mapping for Japanese
struct PhonemeMapping {
    std::string text;
    std::string phoneme;
    std::string pua_code;  // Private Use Area code for compatibility
};

// Feature extraction from MeCab output
struct MorphFeature {
    std::string surface;
    std::string pos;        // Part of speech
    std::string pos_detail1;
    std::string pos_detail2;
    std::string pos_detail3;
    std::string inflection_type;
    std::string inflection_form;
    std::string base_form;
    std::string reading;
    std::string pronunciation;
};

// NJD (New Japanese Dictionary) node
struct NJDNode {
    std::string string;
    std::string pos;
    std::string pos_group1;
    std::string pos_group2;
    std::string pos_group3;
    std::string ctype;
    std::string cform;
    std::string orig;
    std::string read;
    std::string pron;
    int acc;
    int mora_size;
    std::string chain_rule;
    int chain_flag;
};

// Text analyzer class
class TextAnalyzer {
private:
    // Accent rules
    std::unordered_map<std::string, int> accent_dict;
    
    // Parse MeCab feature string
    MorphFeature parseFeature(const std::string& surface, const std::string& features) {
        MorphFeature morph;
        morph.surface = surface;
        
        std::vector<std::string> parts;
        std::stringstream ss(features);
        std::string part;
        
        while (std::getline(ss, part, ',')) {
            parts.push_back(part);
        }
        
        // Standard MeCab feature format
        if (parts.size() >= 9) {
            morph.pos = parts[0];
            morph.pos_detail1 = parts[1];
            morph.pos_detail2 = parts[2];
            morph.pos_detail3 = parts[3];
            morph.inflection_type = parts[4];
            morph.inflection_form = parts[5];
            morph.base_form = parts[6];
            morph.reading = parts[7];
            morph.pronunciation = parts[8];
        }
        
        return morph;
    }
    
public:
    TextAnalyzer() {
        // Initialize basic accent dictionary
        initializeAccentDict();
    }
    
    void initializeAccentDict() {
        // Basic accent patterns for common words
        accent_dict["コンニチハ"] = 0;
        accent_dict["アリガトウ"] = 2;
        accent_dict["サヨウナラ"] = 2;
        accent_dict["オハヨウ"] = 0;
        // Add more entries as needed
    }
    
    // Convert MeCab output to NJD nodes
    std::vector<NJDNode> mecabToNJD(const std::string& mecab_output) {
        std::vector<NJDNode> nodes;
        std::stringstream ss(mecab_output);
        std::string line;
        
        while (std::getline(ss, line)) {
            if (line == "EOS" || line.empty()) {
                continue;
            }
            
            // Split surface and features
            size_t tab_pos = line.find('\t');
            if (tab_pos == std::string::npos) {
                continue;
            }
            
            std::string surface = line.substr(0, tab_pos);
            std::string features = line.substr(tab_pos + 1);
            
            MorphFeature morph = parseFeature(surface, features);
            
            // Create NJD node
            NJDNode node;
            node.string = morph.surface;
            node.pos = morph.pos;
            node.pos_group1 = morph.pos_detail1;
            node.pos_group2 = morph.pos_detail2;
            node.pos_group3 = morph.pos_detail3;
            node.ctype = morph.inflection_type;
            node.cform = morph.inflection_form;
            node.orig = morph.base_form;
            node.read = morph.reading;
            node.pron = morph.pronunciation.empty() ? morph.reading : morph.pronunciation;
            
            // Set accent from dictionary
            auto it = accent_dict.find(node.pron);
            if (it != accent_dict.end()) {
                node.acc = it->second;
            } else {
                node.acc = 0;  // Default accent
            }
            
            // Calculate mora size (simplified)
            node.mora_size = countMora(node.pron);
            
            nodes.push_back(node);
        }
        
        return nodes;
    }
    
    // Count mora in katakana string
    int countMora(const std::string& kana) {
        int count = 0;
        size_t i = 0;
        
        while (i < kana.length()) {
            unsigned char c = kana[i];
            
            // Skip small kana (ャュョァィゥェォ)
            if (c == 0xE3 && i + 2 < kana.length()) {
                unsigned char c2 = kana[i + 1];
                unsigned char c3 = kana[i + 2];
                if ((c2 == 0x83 && (c3 == 0xA3 || c3 == 0xA5 || c3 == 0xA7)) ||  // ャュョ
                    (c2 == 0x82 && (c3 >= 0xA1 && c3 <= 0xAB))) {  // ァィゥェォ
                    i += 3;
                    continue;
                }
            }
            
            // Count as one mora
            count++;
            
            // Skip to next character (UTF-8)
            if (c < 0x80) {
                i += 1;
            } else if (c < 0xE0) {
                i += 2;
            } else if (c < 0xF0) {
                i += 3;
            } else {
                i += 4;
            }
        }
        
        return count;
    }
};

// Phoneme converter class
class PhonemeConverter {
private:
    // Phoneme mapping table
    std::vector<PhonemeMapping> phoneme_map;
    
    // Initialize phoneme mappings
    void initializePhonemeMap() {
        // Complete Japanese phoneme mapping
        // Using Private Use Area (E000-F8FF) for compatibility
        phoneme_map = {
            // Vowels
            {"ア", "a", "\uE000"},
            {"イ", "i", "\uE001"},
            {"ウ", "u", "\uE002"},
            {"エ", "e", "\uE003"},
            {"オ", "o", "\uE004"},
            
            // K-group
            {"カ", "k a", "\uE005"},
            {"キ", "k i", "\uE006"},
            {"ク", "k u", "\uE007"},
            {"ケ", "k e", "\uE008"},
            {"コ", "k o", "\uE009"},
            {"キャ", "ky a", "\uE00A"},
            {"キュ", "ky u", "\uE00B"},
            {"キョ", "ky o", "\uE00C"},
            
            // G-group
            {"ガ", "g a", "\uE010"},
            {"ギ", "g i", "\uE011"},
            {"グ", "g u", "\uE012"},
            {"ゲ", "g e", "\uE013"},
            {"ゴ", "g o", "\uE014"},
            {"ギャ", "gy a", "\uE015"},
            {"ギュ", "gy u", "\uE016"},
            {"ギョ", "gy o", "\uE017"},
            
            // S-group
            {"サ", "s a", "\uE020"},
            {"シ", "sh i", "\uE021"},
            {"ス", "s u", "\uE022"},
            {"セ", "s e", "\uE023"},
            {"ソ", "s o", "\uE024"},
            {"シャ", "sh a", "\uE025"},
            {"シュ", "sh u", "\uE026"},
            {"ショ", "sh o", "\uE027"},
            
            // Z-group
            {"ザ", "z a", "\uE030"},
            {"ジ", "j i", "\uE031"},
            {"ズ", "z u", "\uE032"},
            {"ゼ", "z e", "\uE033"},
            {"ゾ", "z o", "\uE034"},
            {"ジャ", "j a", "\uE035"},
            {"ジュ", "j u", "\uE036"},
            {"ジョ", "j o", "\uE037"},
            
            // T-group
            {"タ", "t a", "\uE040"},
            {"チ", "ch i", "\uE041"},
            {"ツ", "ts u", "\uE042"},
            {"テ", "t e", "\uE043"},
            {"ト", "t o", "\uE044"},
            {"チャ", "ch a", "\uE045"},
            {"チュ", "ch u", "\uE046"},
            {"チョ", "ch o", "\uE047"},
            
            // D-group
            {"ダ", "d a", "\uE050"},
            {"ヂ", "j i", "\uE051"},
            {"ヅ", "z u", "\uE052"},
            {"デ", "d e", "\uE053"},
            {"ド", "d o", "\uE054"},
            
            // N-group
            {"ナ", "n a", "\uE060"},
            {"ニ", "n i", "\uE061"},
            {"ヌ", "n u", "\uE062"},
            {"ネ", "n e", "\uE063"},
            {"ノ", "n o", "\uE064"},
            {"ニャ", "ny a", "\uE065"},
            {"ニュ", "ny u", "\uE066"},
            {"ニョ", "ny o", "\uE067"},
            
            // H-group
            {"ハ", "h a", "\uE070"},
            {"ヒ", "h i", "\uE071"},
            {"フ", "f u", "\uE072"},
            {"ヘ", "h e", "\uE073"},
            {"ホ", "h o", "\uE074"},
            {"ヒャ", "hy a", "\uE075"},
            {"ヒュ", "hy u", "\uE076"},
            {"ヒョ", "hy o", "\uE077"},
            
            // B-group
            {"バ", "b a", "\uE080"},
            {"ビ", "b i", "\uE081"},
            {"ブ", "b u", "\uE082"},
            {"ベ", "b e", "\uE083"},
            {"ボ", "b o", "\uE084"},
            {"ビャ", "by a", "\uE085"},
            {"ビュ", "by u", "\uE086"},
            {"ビョ", "by o", "\uE087"},
            
            // P-group
            {"パ", "p a", "\uE090"},
            {"ピ", "p i", "\uE091"},
            {"プ", "p u", "\uE092"},
            {"ペ", "p e", "\uE093"},
            {"ポ", "p o", "\uE094"},
            {"ピャ", "py a", "\uE095"},
            {"ピュ", "py u", "\uE096"},
            {"ピョ", "py o", "\uE097"},
            
            // M-group
            {"マ", "m a", "\uE0A0"},
            {"ミ", "m i", "\uE0A1"},
            {"ム", "m u", "\uE0A2"},
            {"メ", "m e", "\uE0A3"},
            {"モ", "m o", "\uE0A4"},
            {"ミャ", "my a", "\uE0A5"},
            {"ミュ", "my u", "\uE0A6"},
            {"ミョ", "my o", "\uE0A7"},
            
            // Y-group
            {"ヤ", "y a", "\uE0B0"},
            {"ユ", "y u", "\uE0B2"},
            {"ヨ", "y o", "\uE0B4"},
            
            // R-group
            {"ラ", "r a", "\uE0C0"},
            {"リ", "r i", "\uE0C1"},
            {"ル", "r u", "\uE0C2"},
            {"レ", "r e", "\uE0C3"},
            {"ロ", "r o", "\uE0C4"},
            {"リャ", "ry a", "\uE0C5"},
            {"リュ", "ry u", "\uE0C6"},
            {"リョ", "ry o", "\uE0C7"},
            
            // W-group
            {"ワ", "w a", "\uE0D0"},
            {"ヲ", "w o", "\uE0D1"},
            
            // Special sounds
            {"ン", "N", "\uE0E0"},
            {"ッ", "cl", "\uE0E1"},
            {"ー", ":", "\uE0E2"},
            
            // Small kana
            {"ァ", "a", "\uE0F0"},
            {"ィ", "i", "\uE0F1"},
            {"ゥ", "u", "\uE0F2"},
            {"ェ", "e", "\uE0F3"},
            {"ォ", "o", "\uE0F4"},
            
            // Special combinations
            {"ヴ", "v u", "\uE100"},
            {"ヴァ", "v a", "\uE101"},
            {"ヴィ", "v i", "\uE102"},
            {"ヴェ", "v e", "\uE103"},
            {"ヴォ", "v o", "\uE104"},
        };
    }
    
public:
    PhonemeConverter() {
        initializePhonemeMap();
    }
    
    // Convert NJD nodes to phoneme sequence
    std::string njdToPhoneme(const std::vector<NJDNode>& nodes) {
        std::stringstream phonemes;
        
        for (const auto& node : nodes) {
            std::string pron = node.pron;
            
            // Convert each katakana to phoneme
            size_t i = 0;
            while (i < pron.length()) {
                bool found = false;
                
                // Try to match longest sequence first
                for (size_t len = std::min(pron.length() - i, size_t(9)); len > 0; --len) {
                    std::string substr = pron.substr(i, len);
                    
                    for (const auto& mapping : phoneme_map) {
                        if (mapping.text == substr) {
                            if (!phonemes.str().empty() && phonemes.str().back() != ' ') {
                                phonemes << " ";
                            }
                            phonemes << mapping.phoneme;
                            i += len;
                            found = true;
                            break;
                        }
                    }
                    
                    if (found) break;
                }
                
                // If no match found, skip character
                if (!found) {
                    unsigned char c = pron[i];
                    if (c < 0x80) {
                        i += 1;
                    } else if (c < 0xE0) {
                        i += 2;
                    } else if (c < 0xF0) {
                        i += 3;
                    } else {
                        i += 4;
                    }
                }
            }
            
            // Add pause for punctuation
            if (node.pos == "記号") {
                if (node.string == "。" || node.string == "、") {
                    if (!phonemes.str().empty() && phonemes.str().back() != ' ') {
                        phonemes << " ";
                    }
                    phonemes << "pau";
                }
            }
        }
        
        return phonemes.str();
    }
    
    // Convert to PUA encoded string
    std::string njdToPUA(const std::vector<NJDNode>& nodes) {
        std::stringstream pua_stream;
        
        for (const auto& node : nodes) {
            std::string pron = node.pron;
            
            size_t i = 0;
            while (i < pron.length()) {
                bool found = false;
                
                for (size_t len = std::min(pron.length() - i, size_t(9)); len > 0; --len) {
                    std::string substr = pron.substr(i, len);
                    
                    for (const auto& mapping : phoneme_map) {
                        if (mapping.text == substr) {
                            pua_stream << mapping.pua_code;
                            i += len;
                            found = true;
                            break;
                        }
                    }
                    
                    if (found) break;
                }
                
                if (!found) {
                    unsigned char c = pron[i];
                    if (c < 0x80) {
                        i += 1;
                    } else if (c < 0xE0) {
                        i += 2;
                    } else if (c < 0xF0) {
                        i += 3;
                    } else {
                        i += 4;
                    }
                }
            }
        }
        
        return pua_stream.str();
    }
};

// Main OpenJTalk class
class OpenJTalk {
private:
    std::unique_ptr<TextAnalyzer> text_analyzer;
    std::unique_ptr<PhonemeConverter> phoneme_converter;
    bool initialized;
    
public:
    OpenJTalk() : initialized(false) {}
    
    bool initialize() {
        try {
            text_analyzer = std::make_unique<TextAnalyzer>();
            phoneme_converter = std::make_unique<PhonemeConverter>();
            initialized = true;
            
            ErrorHandler::logInfo("OpenJTalk initialized successfully");
            return true;
        } catch (const std::exception& e) {
            ErrorHandler::logError("OpenJTalk initialization failed: " + std::string(e.what()));
            return false;
        }
    }
    
    // Process MeCab output to phonemes
    std::string processText(const std::string& mecab_output) {
        if (!initialized) {
            ErrorHandler::logError("OpenJTalk not initialized");
            return "";
        }
        
        try {
            // Convert MeCab output to NJD
            auto njd_nodes = text_analyzer->mecabToNJD(mecab_output);
            
            // Convert NJD to phonemes
            return phoneme_converter->njdToPhoneme(njd_nodes);
            
        } catch (const std::exception& e) {
            ErrorHandler::logError("Text processing failed: " + std::string(e.what()));
            return "";
        }
    }
    
    // Process to PUA encoded string
    std::string processToPUA(const std::string& mecab_output) {
        if (!initialized) {
            return "";
        }
        
        try {
            auto njd_nodes = text_analyzer->mecabToNJD(mecab_output);
            return phoneme_converter->njdToPUA(njd_nodes);
        } catch (const std::exception& e) {
            ErrorHandler::logError("PUA conversion failed: " + std::string(e.what()));
            return "";
        }
    }
    
    // Get NJD nodes (for debugging)
    std::vector<NJDNode> getNJDNodes(const std::string& mecab_output) {
        if (!initialized) {
            return {};
        }
        
        return text_analyzer->mecabToNJD(mecab_output);
    }
    
    bool isInitialized() const {
        return initialized;
    }
};

} // namespace openjtalk

// Global instance
std::unique_ptr<openjtalk::OpenJTalk> globalOpenJTalk;

// C-style interface
extern "C" {
    EMSCRIPTEN_KEEPALIVE
    int openjtalk_initialize() {
        globalOpenJTalk = std::make_unique<openjtalk::OpenJTalk>();
        return globalOpenJTalk->initialize() ? 1 : 0;
    }
    
    EMSCRIPTEN_KEEPALIVE
    const char* openjtalk_process(const char* mecab_output) {
        if (!globalOpenJTalk) {
            return "";
        }
        static std::string result;
        result = globalOpenJTalk->processText(mecab_output);
        return result.c_str();
    }
    
    EMSCRIPTEN_KEEPALIVE
    const char* openjtalk_process_pua(const char* mecab_output) {
        if (!globalOpenJTalk) {
            return "";
        }
        static std::string result;
        result = globalOpenJTalk->processToPUA(mecab_output);
        return result.c_str();
    }
    
    EMSCRIPTEN_KEEPALIVE
    void openjtalk_destroy() {
        globalOpenJTalk.reset();
    }
}

// Embind interface
EMSCRIPTEN_BINDINGS(openjtalk_module) {
    // NJDNode class
    class_<openjtalk::NJDNode>("NJDNode")
        .property("string", &openjtalk::NJDNode::string)
        .property("pos", &openjtalk::NJDNode::pos)
        .property("pos_group1", &openjtalk::NJDNode::pos_group1)
        .property("pos_group2", &openjtalk::NJDNode::pos_group2)
        .property("pos_group3", &openjtalk::NJDNode::pos_group3)
        .property("read", &openjtalk::NJDNode::read)
        .property("pron", &openjtalk::NJDNode::pron)
        .property("acc", &openjtalk::NJDNode::acc)
        .property("mora_size", &openjtalk::NJDNode::mora_size);
    
    // OpenJTalk class
    class_<openjtalk::OpenJTalk>("OpenJTalk")
        .constructor<>()
        .function("initialize", &openjtalk::OpenJTalk::initialize)
        .function("processText", &openjtalk::OpenJTalk::processText)
        .function("processToPUA", &openjtalk::OpenJTalk::processToPUA)
        .function("getNJDNodes", &openjtalk::OpenJTalk::getNJDNodes)
        .function("isInitialized", &openjtalk::OpenJTalk::isInitialized);
    
    // Register vector<NJDNode>
    register_vector<openjtalk::NJDNode>("VectorNJDNode");
    
    // Utility functions
    function("setDebugMode", &openjtalk::ErrorHandler::setDebugMode);
}