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
#include <limits>
#include <queue>

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

// Character type definition
struct CharInfo {
    uint32_t type;      // Character type bitmap
    uint32_t default_type;
    uint32_t length;    // Character length in bytes
    uint32_t group;     // Character group for unknown word processing
    bool invoke;        // Can invoke unknown word processing
};

// Lattice node for Viterbi algorithm
struct Node {
    size_t start_pos;   // Start position in bytes
    size_t end_pos;     // End position in bytes
    size_t length;      // Length in bytes
    std::string surface;
    std::vector<std::string> features;
    int16_t wcost;      // Word cost
    uint16_t left_id;   // Left context ID
    uint16_t right_id;  // Right context ID
    int32_t cost;       // Total cost up to this node
    Node* prev;         // Best previous node
    
    Node() : start_pos(0), end_pos(0), length(0), wcost(0), 
             left_id(0), right_id(0), cost(std::numeric_limits<int32_t>::max()), 
             prev(nullptr) {}
};

// DARTS (Double Array Trie) node structure
struct DartsNode {
    int32_t base;
    int32_t check;
};

class MeCabViterbi {
private:
    bool dictLoaded;
    DictionaryHeader sysHeader;
    std::vector<Token> tokens;
    std::vector<std::string> features;
    std::vector<DartsNode> darts;
    std::vector<int16_t> matrix;
    std::vector<CharInfo> charInfos;
    std::map<char32_t, CharInfo> charTypeMap;
    uint16_t matrixLSize;
    uint16_t matrixRSize;
    
    // Character types
    enum CharType {
        CHAR_DEFAULT    = 0,
        CHAR_SPACE      = 1,
        CHAR_KANJI      = 2,
        CHAR_SYMBOL     = 4,
        CHAR_NUMERIC    = 8,
        CHAR_ALPHA      = 16,
        CHAR_HIRAGANA   = 32,
        CHAR_KATAKANA   = 64,
        CHAR_KANJINUMERIC = 128,
        CHAR_GREEK      = 256,
        CHAR_CYRILLIC   = 512
    };
    
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
        darts.resize(sysHeader.dsize / sizeof(DartsNode));
        file.read(reinterpret_cast<char*>(darts.data()), sysHeader.dsize);
        
        // Read tokens
        tokens.resize(sysHeader.lexsize);
        file.read(reinterpret_cast<char*>(tokens.data()), sysHeader.lexsize * sizeof(Token));
        
        // Read features
        std::vector<uint8_t> featureData(sysHeader.fsize);
        file.read(reinterpret_cast<char*>(featureData.data()), sysHeader.fsize);
        features = parseFeatures(featureData.data(), sysHeader.fsize);
        
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
    
    // Load character type definitions
    bool loadCharDef(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            std::cerr << "Cannot open char.bin: " << path << std::endl;
            // Use default character types
            initDefaultCharTypes();
            return true;
        }
        
        // Read character definitions
        // Format: category_name invoke group length
        // TODO: Implement actual char.bin parsing
        
        initDefaultCharTypes();
        return true;
    }
    
    // Initialize default character types
    void initDefaultCharTypes() {
        // Space
        for (char32_t c = 0x0009; c <= 0x0020; c++) {
            charTypeMap[c] = {CHAR_SPACE, CHAR_SPACE, 1, 0, true};
        }
        charTypeMap[0x3000] = {CHAR_SPACE, CHAR_SPACE, 3, 0, true}; // Full-width space
        
        // Numbers
        for (char32_t c = '0'; c <= '9'; c++) {
            charTypeMap[c] = {CHAR_NUMERIC, CHAR_NUMERIC, 1, 0, true};
        }
        for (char32_t c = 0xFF10; c <= 0xFF19; c++) { // Full-width
            charTypeMap[c] = {CHAR_NUMERIC, CHAR_NUMERIC, 3, 0, true};
        }
        
        // Latin alphabet
        for (char32_t c = 'A'; c <= 'Z'; c++) {
            charTypeMap[c] = {CHAR_ALPHA, CHAR_ALPHA, 1, 0, true};
        }
        for (char32_t c = 'a'; c <= 'z'; c++) {
            charTypeMap[c] = {CHAR_ALPHA, CHAR_ALPHA, 1, 0, true};
        }
        
        // Hiragana
        for (char32_t c = 0x3040; c <= 0x309F; c++) {
            charTypeMap[c] = {CHAR_HIRAGANA, CHAR_HIRAGANA, 3, 0, true};
        }
        
        // Katakana
        for (char32_t c = 0x30A0; c <= 0x30FF; c++) {
            charTypeMap[c] = {CHAR_KATAKANA, CHAR_KATAKANA, 3, 0, true};
        }
        
        // Kanji (CJK Unified Ideographs)
        for (char32_t c = 0x4E00; c <= 0x9FFF; c++) {
            charTypeMap[c] = {CHAR_KANJI, CHAR_KANJI, 3, 0, true};
        }
    }
    
    // Get character type
    CharInfo getCharType(char32_t codepoint) {
        auto it = charTypeMap.find(codepoint);
        if (it != charTypeMap.end()) {
            return it->second;
        }
        // Default: symbol
        return {CHAR_SYMBOL, CHAR_SYMBOL, 1, 0, true};
    }
    
    // Get UTF-8 character length
    size_t getUTF8CharLength(const char* str) {
        unsigned char c = *str;
        if ((c & 0x80) == 0) return 1;
        if ((c & 0xE0) == 0xC0) return 2;
        if ((c & 0xF0) == 0xE0) return 3;
        if ((c & 0xF8) == 0xF0) return 4;
        return 1; // Invalid UTF-8
    }
    
    // Convert UTF-8 to codepoint
    char32_t utf8ToCodepoint(const char* str, size_t& len) {
        unsigned char c = *str;
        char32_t codepoint = 0;
        
        if ((c & 0x80) == 0) {
            len = 1;
            return c;
        } else if ((c & 0xE0) == 0xC0) {
            len = 2;
            codepoint = (c & 0x1F) << 6;
            codepoint |= (str[1] & 0x3F);
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
            codepoint = (c & 0x0F) << 12;
            codepoint |= (str[1] & 0x3F) << 6;
            codepoint |= (str[2] & 0x3F);
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
            codepoint = (c & 0x07) << 18;
            codepoint |= (str[1] & 0x3F) << 12;
            codepoint |= (str[2] & 0x3F) << 6;
            codepoint |= (str[3] & 0x3F);
        } else {
            len = 1;
            return c; // Invalid UTF-8
        }
        
        return codepoint;
    }
    
    // Get connection cost
    int16_t getConnectionCost(uint16_t leftId, uint16_t rightId) {
        if (leftId >= matrixLSize || rightId >= matrixRSize) {
            return 0;
        }
        return matrix[leftId * matrixRSize + rightId];
    }
    
    // DARTS lookup - find all matching tokens
    std::vector<std::pair<size_t, size_t>> dartsLookup(const char* text, size_t pos, size_t len) {
        std::vector<std::pair<size_t, size_t>> results;
        
        if (darts.empty()) {
            return results;
        }
        
        size_t node_pos = 0;
        size_t key_pos = pos;
        
        while (key_pos < len) {
            size_t char_len;
            char32_t ch = utf8ToCodepoint(text + key_pos, char_len);
            
            // Check DARTS transition
            size_t next_pos = darts[node_pos].base + ch;
            if (next_pos >= darts.size() || darts[next_pos].check != node_pos) {
                break;
            }
            
            node_pos = next_pos;
            key_pos += char_len;
            
            // Check if this is a terminal node
            size_t terminal = darts[node_pos].base;
            if (terminal < tokens.size()) {
                results.push_back({terminal, key_pos - pos});
            }
        }
        
        return results;
    }
    
    // Create unknown word nodes
    std::vector<Node*> createUnknownNodes(const char* text, size_t pos, size_t len) {
        std::vector<Node*> nodes;
        
        // Get character type at position
        size_t char_len;
        char32_t ch = utf8ToCodepoint(text + pos, char_len);
        CharInfo charInfo = getCharType(ch);
        
        // Group consecutive characters of the same type
        size_t end = pos + char_len;
        uint32_t current_type = charInfo.type;
        
        while (end < len) {
            size_t next_len;
            char32_t next_ch = utf8ToCodepoint(text + end, next_len);
            CharInfo next_info = getCharType(next_ch);
            
            // Check if same character type
            if ((next_info.type & current_type) == 0) {
                break;
            }
            
            end += next_len;
        }
        
        // Create unknown word node
        Node* node = new Node();
        node->start_pos = pos;
        node->end_pos = end;
        node->length = end - pos;
        node->surface = std::string(text + pos, end - pos);
        
        // Set features based on character type
        if (charInfo.type & CHAR_KANJI) {
            node->features = {"名詞", "一般", "*", "*", "*", "*", node->surface, "*", "*"};
            node->left_id = 1285;  // Default left ID for 名詞,一般
            node->right_id = 1285;
        } else if (charInfo.type & CHAR_KATAKANA) {
            node->features = {"名詞", "一般", "*", "*", "*", "*", node->surface, node->surface, node->surface};
            node->left_id = 1285;
            node->right_id = 1285;
        } else if (charInfo.type & CHAR_ALPHA) {
            node->features = {"名詞", "一般", "*", "*", "*", "*", node->surface, node->surface, node->surface};
            node->left_id = 1285;
            node->right_id = 1285;
        } else if (charInfo.type & CHAR_NUMERIC) {
            node->features = {"名詞", "数", "*", "*", "*", "*", node->surface, node->surface, node->surface};
            node->left_id = 1295;
            node->right_id = 1295;
        } else {
            node->features = {"記号", "一般", "*", "*", "*", "*", node->surface, node->surface, node->surface};
            node->left_id = 1292;
            node->right_id = 1292;
        }
        
        node->wcost = 5000; // High cost for unknown words
        nodes.push_back(node);
        
        return nodes;
    }
    
    // Create lattice for Viterbi
    std::vector<std::vector<Node*>> createLattice(const std::string& text) {
        std::vector<std::vector<Node*>> lattice(text.length() + 1);
        const char* ctext = text.c_str();
        size_t len = text.length();
        
        // BOS (Beginning of Sentence) node
        Node* bos = new Node();
        bos->start_pos = 0;
        bos->end_pos = 0;
        bos->surface = "BOS";
        bos->features = {"BOS/EOS", "*", "*", "*", "*", "*", "*", "*", "*"};
        bos->wcost = 0;
        bos->cost = 0;
        bos->left_id = 0;
        bos->right_id = 0;
        lattice[0].push_back(bos);
        
        // Build lattice
        for (size_t pos = 0; pos < len; ) {
            size_t char_len = getUTF8CharLength(ctext + pos);
            
            // Dictionary lookup
            auto matches = dartsLookup(ctext, pos, len);
            
            if (!matches.empty()) {
                // Found in dictionary
                for (const auto& match : matches) {
                    size_t token_id = match.first;
                    size_t match_len = match.second;
                    
                    if (token_id < tokens.size()) {
                        const Token& token = tokens[token_id];
                        
                        Node* node = new Node();
                        node->start_pos = pos;
                        node->end_pos = pos + match_len;
                        node->length = match_len;
                        node->surface = std::string(ctext + pos, match_len);
                        
                        if (token.feature < features.size()) {
                            node->features = splitFeature(features[token.feature]);
                        }
                        
                        node->wcost = token.wcost;
                        node->left_id = token.lcAttr;
                        node->right_id = token.rcAttr;
                        
                        lattice[node->end_pos].push_back(node);
                    }
                }
            }
            
            // Always add unknown word candidates
            auto unknown_nodes = createUnknownNodes(ctext, pos, len);
            for (auto* node : unknown_nodes) {
                lattice[node->end_pos].push_back(node);
            }
            
            pos += char_len;
        }
        
        // EOS (End of Sentence) node
        Node* eos = new Node();
        eos->start_pos = len;
        eos->end_pos = len;
        eos->surface = "EOS";
        eos->features = {"BOS/EOS", "*", "*", "*", "*", "*", "*", "*", "*"};
        eos->wcost = 0;
        eos->left_id = 0;
        eos->right_id = 0;
        lattice[len].push_back(eos);
        
        return lattice;
    }
    
    // Viterbi algorithm
    std::vector<Node*> viterbi(const std::string& text) {
        auto lattice = createLattice(text);
        
        // Forward pass
        for (size_t pos = 1; pos <= text.length(); pos++) {
            for (auto* node : lattice[pos]) {
                int32_t best_cost = std::numeric_limits<int32_t>::max();
                Node* best_prev = nullptr;
                
                // Check all possible previous nodes
                for (size_t prev_pos = 0; prev_pos < pos; prev_pos++) {
                    for (auto* prev : lattice[prev_pos]) {
                        if (prev->end_pos != node->start_pos) continue;
                        
                        // Calculate cost
                        int32_t cost = prev->cost + node->wcost;
                        
                        // Add connection cost
                        if (prev->surface != "BOS" && node->surface != "EOS") {
                            cost += getConnectionCost(prev->right_id, node->left_id);
                        }
                        
                        if (cost < best_cost) {
                            best_cost = cost;
                            best_prev = prev;
                        }
                    }
                }
                
                node->cost = best_cost;
                node->prev = best_prev;
            }
        }
        
        // Find best path (backtrack from EOS)
        std::vector<Node*> path;
        Node* current = nullptr;
        
        // Find EOS node with minimum cost
        for (auto* node : lattice[text.length()]) {
            if (node->surface == "EOS" && node->prev != nullptr) {
                current = node->prev; // Skip EOS itself
                break;
            }
        }
        
        // Backtrack
        while (current != nullptr && current->surface != "BOS") {
            path.push_back(current);
            current = current->prev;
        }
        
        std::reverse(path.begin(), path.end());
        
        // Clean up non-path nodes
        for (const auto& nodes : lattice) {
            for (auto* node : nodes) {
                if (std::find(path.begin(), path.end(), node) == path.end()) {
                    delete node;
                }
            }
        }
        
        return path;
    }
    
public:
    MeCabViterbi() : dictLoaded(false), matrixLSize(0), matrixRSize(0) {}
    
    ~MeCabViterbi() {
        // Vectors handle their own cleanup
    }
    
    bool initialize(const std::string& dictPath) {
        try {
            std::cout << "Initializing MeCabViterbi with dictionary path: " << dictPath << std::endl;
            
            // Load dictionary files
            if (!loadSysDic(dictPath + "/sys.dic")) {
                std::cerr << "Failed to load sys.dic" << std::endl;
                return false;
            }
            
            if (!loadMatrix(dictPath + "/matrix.bin")) {
                std::cerr << "Failed to load matrix.bin" << std::endl;
                // Continue without matrix - will use default costs
            }
            
            if (!loadCharDef(dictPath + "/char.bin")) {
                std::cerr << "Failed to load char.bin, using defaults" << std::endl;
            }
            
            dictLoaded = true;
            std::cout << "MeCabViterbi initialized successfully" << std::endl;
            return true;
            
        } catch (const std::exception& e) {
            std::cerr << "MeCabViterbi initialization error: " << e.what() << std::endl;
            return false;
        }
    }
    
    std::string parse(const std::string& text) {
        if (!dictLoaded) {
            return text + "\t名詞,一般,*,*,*,*," + text + "," + text + "," + text + "\nEOS\n";
        }
        
        if (text.empty()) {
            return "EOS\n";
        }
        
        // Run Viterbi algorithm
        auto path = viterbi(text);
        
        // Format output
        std::stringstream result;
        for (auto* node : path) {
            result << node->surface << "\t";
            for (size_t i = 0; i < node->features.size(); i++) {
                if (i > 0) result << ",";
                result << node->features[i];
            }
            result << "\n";
        }
        result << "EOS\n";
        
        // Clean up path nodes
        for (auto* node : path) {
            delete node;
        }
        
        return result.str();
    }
    
    std::string wakati(const std::string& text) {
        if (!dictLoaded || text.empty()) {
            return text;
        }
        
        // Run Viterbi algorithm
        auto path = viterbi(text);
        
        // Format output
        std::stringstream result;
        for (size_t i = 0; i < path.size(); i++) {
            if (i > 0) result << " ";
            result << path[i]->surface;
        }
        
        // Clean up path nodes
        for (auto* node : path) {
            delete node;
        }
        
        return result.str();
    }
    
    std::string parseDetailed(const std::string& text) {
        return parse(text);
    }
    
    std::string getVersion() {
        return "0.996-viterbi";
    }
    
    // Get dictionary statistics
    val getDictStats() {
        val stats = val::object();
        stats.set("loaded", dictLoaded);
        stats.set("tokenCount", tokens.size());
        stats.set("featureCount", features.size());
        stats.set("dartsSize", darts.size());
        stats.set("matrixSize", val::array());
        stats["matrixSize"].set(0, matrixLSize);
        stats["matrixSize"].set(1, matrixRSize);
        stats.set("charTypes", charTypeMap.size());
        return stats;
    }
};

EMSCRIPTEN_BINDINGS(mecab_viterbi_module) {
    class_<MeCabViterbi>("MeCab")
        .constructor<>()
        .function("initialize", &MeCabViterbi::initialize)
        .function("parse", &MeCabViterbi::parse)
        .function("wakati", &MeCabViterbi::wakati)
        .function("parseDetailed", &MeCabViterbi::parseDetailed)
        .function("getVersion", &MeCabViterbi::getVersion)
        .function("getDictStats", &MeCabViterbi::getDictStats);
}