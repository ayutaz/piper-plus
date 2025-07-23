#include <emscripten/bind.h>
#include <emscripten/emscripten.h>
#include <emscripten/val.h>
#include <string>
#include <fstream>
#include <sstream>
#include <vector>
#include <memory>
#include <cstring>
#include <algorithm>
#include <iostream>
#include <map>
#include <cstdint>

using namespace emscripten;

// Dictionary structures based on MeCab format
struct DictionaryHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t type;
    uint32_t lexsize;
    uint32_t lsize;
    uint32_t rsize;
    uint32_t dsize;
    uint32_t tsize;
    uint32_t fsize;
    uint32_t reserved[10];
    char charset[32];
};

struct Token {
    uint16_t lcAttr;
    uint16_t rcAttr;
    uint16_t posid;
    int16_t wcost;
    uint32_t feature;
    uint32_t compound;
};

// Dictionary entry for easier access
struct DictionaryEntry {
    std::string surface;
    std::string reading;
    std::string pos;
    std::string pos1;
    std::string pos2;
    std::string pos3;
    std::string pos4;
    std::string pos5;
    std::string inflection;
    std::string base;
    int16_t cost;
    uint16_t left_id;
    uint16_t right_id;
};

class MeCabFull {
private:
    bool dictLoaded;
    DictionaryHeader sysHeader;
    std::vector<Token> tokens;
    std::vector<std::string> features;
    std::vector<int32_t> darts;
    std::vector<int16_t> matrix;
    uint16_t matrixLSize;
    uint16_t matrixRSize;
    std::map<std::string, std::vector<DictionaryEntry>> surfaceMap;
    
    // Parse features from null-terminated string data
    std::vector<std::string> parseFeatures(const uint8_t* data, size_t size) {
        std::vector<std::string> result;
        size_t start = 0;
        
        for (size_t i = 0; i < size; i++) {
            if (data[i] == 0) {
                result.push_back(std::string(reinterpret_cast<const char*>(data + start)));
                start = i + 1;
            }
        }
        
        return result;
    }
    
    // Split CSV feature string
    std::vector<std::string> splitFeature(const std::string& feature) {
        std::vector<std::string> parts;
        std::stringstream ss(feature);
        std::string part;
        
        while (std::getline(ss, part, ',')) {
            parts.push_back(part);
        }
        
        // Ensure we have at least 9 parts
        while (parts.size() < 9) {
            parts.push_back("*");
        }
        
        return parts;
    }
    
    // Load system dictionary
    bool loadSysDic(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            std::cerr << "Cannot open sys.dic: " << path << std::endl;
            return false;
        }
        
        // Read header
        file.read(reinterpret_cast<char*>(&sysHeader), sizeof(DictionaryHeader));
        
        // Validate magic number
        const uint32_t MECAB_DIC_MAGIC = 0xE954A1B6;
        if (sysHeader.magic != MECAB_DIC_MAGIC) {
            std::cerr << "Invalid dictionary magic: 0x" << std::hex << sysHeader.magic << std::endl;
            return false;
        }
        
        std::cout << "sys.dic: version=" << sysHeader.version 
                  << ", lexsize=" << sysHeader.lexsize 
                  << ", charset=" << sysHeader.charset << std::endl;
        
        // Read DARTS double array
        darts.resize(sysHeader.dsize / sizeof(int32_t));
        file.read(reinterpret_cast<char*>(darts.data()), sysHeader.dsize);
        
        // Read tokens
        tokens.resize(sysHeader.lexsize);
        file.read(reinterpret_cast<char*>(tokens.data()), sysHeader.lexsize * sizeof(Token));
        
        // Read features
        std::vector<uint8_t> featureData(sysHeader.fsize);
        file.read(reinterpret_cast<char*>(featureData.data()), sysHeader.fsize);
        features = parseFeatures(featureData.data(), sysHeader.fsize);
        
        // Build surface map for quick lookup
        buildSurfaceMap();
        
        return true;
    }
    
    // Load connection matrix
    bool loadMatrix(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            std::cerr << "Cannot open matrix.bin: " << path << std::endl;
            return false;
        }
        
        // Read dimensions
        file.read(reinterpret_cast<char*>(&matrixLSize), sizeof(uint16_t));
        file.read(reinterpret_cast<char*>(&matrixRSize), sizeof(uint16_t));
        
        // Read matrix data
        matrix.resize(matrixLSize * matrixRSize);
        file.read(reinterpret_cast<char*>(matrix.data()), matrix.size() * sizeof(int16_t));
        
        std::cout << "Matrix: " << matrixLSize << "x" << matrixRSize << std::endl;
        return true;
    }
    
    // Build surface form to token mapping
    void buildSurfaceMap() {
        surfaceMap.clear();
        
        // This is a simplified version - in real MeCab, DARTS is used for efficient lookup
        for (size_t i = 0; i < tokens.size() && i < features.size(); i++) {
            const Token& token = tokens[i];
            if (token.feature < features.size()) {
                const std::string& feature = features[token.feature];
                auto parts = splitFeature(feature);
                
                if (parts.size() >= 7) {
                    std::string surface = parts[6];
                    if (surface != "*" && !surface.empty()) {
                        DictionaryEntry entry;
                        entry.surface = surface;
                        entry.pos = parts[0];
                        entry.pos1 = parts[1];
                        entry.pos2 = parts[2];
                        entry.pos3 = parts[3];
                        entry.pos4 = parts[4];
                        entry.pos5 = parts[5];
                        entry.inflection = parts[6];
                        entry.reading = (parts.size() > 7) ? parts[7] : surface;
                        entry.base = (parts.size() > 8) ? parts[8] : surface;
                        entry.cost = token.wcost;
                        entry.left_id = token.lcAttr;
                        entry.right_id = token.rcAttr;
                        
                        surfaceMap[surface].push_back(entry);
                    }
                }
            }
        }
        
        std::cout << "Built surface map with " << surfaceMap.size() << " unique surfaces" << std::endl;
    }
    
    // Get connection cost
    int16_t getConnectionCost(uint16_t leftId, uint16_t rightId) {
        if (leftId >= matrixLSize || rightId >= matrixRSize) {
            return 0;
        }
        return matrix[leftId * matrixRSize + rightId];
    }
    
    // Simple tokenizer fallback when exact match not found
    std::vector<std::string> simpleTokenize(const std::string& text) {
        std::vector<std::string> tokens;
        std::string current;
        
        for (size_t i = 0; i < text.length(); ) {
            // Get UTF-8 character
            unsigned char c = text[i];
            size_t char_len = 1;
            
            if ((c & 0x80) == 0) {
                char_len = 1;
            } else if ((c & 0xE0) == 0xC0) {
                char_len = 2;
            } else if ((c & 0xF0) == 0xE0) {
                char_len = 3;
            } else if ((c & 0xF8) == 0xF0) {
                char_len = 4;
            }
            
            // Check if it's ASCII punctuation or space
            if (char_len == 1 && (std::isspace(c) || std::ispunct(c))) {
                if (!current.empty()) {
                    tokens.push_back(current);
                    current.clear();
                }
                if (!std::isspace(c)) {
                    tokens.push_back(text.substr(i, 1));
                }
            } else {
                current += text.substr(i, char_len);
            }
            
            i += char_len;
        }
        
        if (!current.empty()) {
            tokens.push_back(current);
        }
        
        return tokens;
    }
    
    // Convert hiragana to katakana for reading
    std::string hiraganaToKatakana(const std::string& text) {
        std::string result;
        for (size_t i = 0; i < text.length(); ) {
            unsigned char c = text[i];
            if ((c == 0xe3) && i + 2 < text.length()) {
                unsigned char c1 = text[i + 1];
                unsigned char c2 = text[i + 2];
                // Hiragana range: U+3040 to U+309F (E3 81 80 to E3 82 9F)
                if (c1 == 0x81 || c1 == 0x82) {
                    // Convert to katakana by adding 0x60
                    result += (char)0xe3;
                    if (c1 == 0x81) {
                        result += (char)0x82;
                        result += (char)(c2 + 0x20);
                    } else {
                        result += (char)0x83;
                        result += (char)(c2 - 0x60);
                    }
                    i += 3;
                    continue;
                }
            }
            result += text[i];
            i++;
        }
        return result;
    }
    
public:
    MeCabFull() : dictLoaded(false), matrixLSize(0), matrixRSize(0) {}
    
    bool initialize(const std::string& dictPath) {
        try {
            std::cout << "Initializing MeCabFull with dictionary path: " << dictPath << std::endl;
            
            // Load dictionary files
            if (!loadSysDic(dictPath + "/sys.dic")) {
                std::cerr << "Failed to load sys.dic" << std::endl;
                return false;
            }
            
            if (!loadMatrix(dictPath + "/matrix.bin")) {
                std::cerr << "Failed to load matrix.bin" << std::endl;
                // Continue without matrix - will use default costs
            }
            
            dictLoaded = true;
            std::cout << "MeCabFull initialized successfully" << std::endl;
            return true;
            
        } catch (const std::exception& e) {
            std::cerr << "MeCabFull initialization error: " << e.what() << std::endl;
            return false;
        }
    }
    
    std::string parse(const std::string& text) {
        if (!dictLoaded) {
            return text + "\t名詞,一般,*,*,*,*," + text + "," + text + "," + text + "\nEOS\n";
        }
        
        std::stringstream result;
        std::vector<std::string> segments = simpleTokenize(text);
        
        for (const auto& segment : segments) {
            auto it = surfaceMap.find(segment);
            
            if (it != surfaceMap.end() && !it->second.empty()) {
                // Found in dictionary - use first match (should use Viterbi for best)
                const DictionaryEntry& entry = it->second[0];
                result << entry.surface << "\t"
                       << entry.pos << ","
                       << entry.pos1 << ","
                       << entry.pos2 << ","
                       << entry.pos3 << ","
                       << entry.pos4 << ","
                       << entry.pos5 << ","
                       << entry.inflection << ","
                       << entry.reading << ","
                       << entry.base << "\n";
            } else {
                // Not found - make educated guess
                std::string reading = segment;
                std::string pos = "名詞";
                std::string pos1 = "一般";
                
                // Simple heuristics
                if (segment.length() >= 3) {
                    unsigned char c0 = segment[0];
                    unsigned char c1 = segment[1];
                    unsigned char c2 = segment[2];
                    
                    // Check if hiragana
                    if (c0 == 0xe3 && (c1 == 0x81 || c1 == 0x82)) {
                        reading = hiraganaToKatakana(segment);
                        // Could be particle
                        if (segment.length() == 3) {
                            pos = "助詞";
                            pos1 = "格助詞";
                        }
                    }
                    // Check if katakana
                    else if (c0 == 0xe3 && (c1 == 0x82 || c1 == 0x83)) {
                        reading = segment;
                        pos = "名詞";
                        pos1 = "一般";
                    }
                    // ASCII number
                    else if (std::isdigit(c0)) {
                        pos = "名詞";
                        pos1 = "数";
                        reading = segment;
                    }
                    // Punctuation
                    else if (segment == "。" || segment == "、") {
                        pos = "記号";
                        pos1 = (segment == "。") ? "句点" : "読点";
                        reading = segment;
                    }
                }
                
                result << segment << "\t"
                       << pos << ","
                       << pos1 << ",*,*,*,*,"
                       << segment << ","
                       << reading << ","
                       << segment << "\n";
            }
        }
        
        result << "EOS\n";
        return result.str();
    }
    
    std::string wakati(const std::string& text) {
        if (!dictLoaded) {
            return text;
        }
        
        std::vector<std::string> segments = simpleTokenize(text);
        std::string result;
        
        for (size_t i = 0; i < segments.size(); i++) {
            if (i > 0 && segments[i] != "。" && segments[i] != "、") {
                result += " ";
            }
            result += segments[i];
        }
        
        return result;
    }
    
    std::string parseDetailed(const std::string& text) {
        return parse(text);
    }
    
    std::string getVersion() {
        return "0.996-emscripten-full";
    }
    
    // Get dictionary statistics
    val getDictStats() {
        val stats = val::object();
        stats.set("loaded", dictLoaded);
        stats.set("tokenCount", tokens.size());
        stats.set("featureCount", features.size());
        stats.set("surfaceCount", surfaceMap.size());
        stats.set("matrixSize", val::array());
        stats["matrixSize"].set(0, matrixLSize);
        stats["matrixSize"].set(1, matrixRSize);
        return stats;
    }
};

EMSCRIPTEN_BINDINGS(mecab_full_module) {
    class_<MeCabFull>("MeCab")
        .constructor<>()
        .function("initialize", &MeCabFull::initialize)
        .function("parse", &MeCabFull::parse)
        .function("wakati", &MeCabFull::wakati)
        .function("parseDetailed", &MeCabFull::parseDetailed)
        .function("getVersion", &MeCabFull::getVersion)
        .function("getDictStats", &MeCabFull::getDictStats);
}