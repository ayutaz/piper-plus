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
#include <iomanip>
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
    uint32_t feature;      // offset 0: feature string offset
    uint32_t compound;     // offset 4: compound info (unused)
    uint16_t lcAttr;       // offset 8: left context ID
    uint16_t rcAttr;       // offset 10: right context ID
    uint16_t posid;        // offset 12: POS ID
    int16_t wcost;         // offset 14: word cost
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
        std::cout << "Attempting to load sys.dic from: " << path << std::endl;
        
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            std::cerr << "Cannot open sys.dic: " << path << std::endl;
            return false;
        }
        
        // Check file size
        file.seekg(0, std::ios::end);
        size_t fileSize = file.tellg();
        file.seekg(0, std::ios::beg);
        std::cout << "sys.dic file size: " << fileSize << " bytes" << std::endl;
        
        // Read first few bytes to debug
        unsigned char firstBytes[16];
        file.read(reinterpret_cast<char*>(firstBytes), 16);
        file.seekg(0, std::ios::beg);
        
        std::cout << "First 16 bytes: ";
        for (int i = 0; i < 16; i++) {
            std::cout << std::hex << std::setw(2) << std::setfill('0') << (int)firstBytes[i] << " ";
        }
        std::cout << std::dec << std::endl;
        
        // Read header
        file.read(reinterpret_cast<char*>(&sysHeader), sizeof(DictionaryHeader));
        
        // Validate magic number
        const uint32_t MECAB_DIC_MAGIC = 0xE954A1B6;
        const uint32_t MECAB_DIC_MAGIC_SWAPPED = 0xB6A154E9;  // Big-endian version
        const uint32_t MECAB_DIC_MAGIC_ACTUAL = 0xE9554887;  // Actual magic in our dictionary
        
        std::cout << "Dictionary magic: 0x" << std::hex << sysHeader.magic << std::endl;
        std::cout << "Expected magic: 0x" << std::hex << MECAB_DIC_MAGIC << " or 0x" << MECAB_DIC_MAGIC_SWAPPED << std::endl;
        
        // Check all known magic numbers
        if (sysHeader.magic != MECAB_DIC_MAGIC && 
            sysHeader.magic != MECAB_DIC_MAGIC_SWAPPED &&
            sysHeader.magic != MECAB_DIC_MAGIC_ACTUAL) {
            std::cerr << "Invalid dictionary magic number" << std::endl;
            return false;
        }
        
        // Warn if using non-standard magic
        if (sysHeader.magic == MECAB_DIC_MAGIC_ACTUAL) {
            std::cout << "WARNING: Using non-standard dictionary magic number" << std::endl;
        }
        
        // If big-endian, we need to swap all header fields
        bool needSwap = (sysHeader.magic == MECAB_DIC_MAGIC_SWAPPED);
        if (needSwap) {
            std::cout << "Dictionary is big-endian, swapping bytes..." << std::endl;
            sysHeader.magic = __builtin_bswap32(sysHeader.magic);
            sysHeader.version = __builtin_bswap32(sysHeader.version);
            sysHeader.type = __builtin_bswap32(sysHeader.type);
            sysHeader.lexsize = __builtin_bswap32(sysHeader.lexsize);
            sysHeader.lsize = __builtin_bswap32(sysHeader.lsize);
            sysHeader.rsize = __builtin_bswap32(sysHeader.rsize);
            sysHeader.dsize = __builtin_bswap32(sysHeader.dsize);
            sysHeader.tsize = __builtin_bswap32(sysHeader.tsize);
            sysHeader.fsize = __builtin_bswap32(sysHeader.fsize);
            for (int i = 0; i < 10; i++) {
                sysHeader.reserved[i] = __builtin_bswap32(sysHeader.reserved[i]);
            }
        }
        
        std::cout << "sys.dic header:" << std::endl;
        std::cout << "  version=" << sysHeader.version << std::endl;
        std::cout << "  lexsize=" << sysHeader.lexsize << " (0x" << std::hex << sysHeader.lexsize << std::dec << ")" << std::endl;
        std::cout << "  lsize=" << sysHeader.lsize << std::endl;
        std::cout << "  rsize=" << sysHeader.rsize << std::endl;
        std::cout << "  dsize=" << sysHeader.dsize << " (0x" << std::hex << sysHeader.dsize << std::dec << ")" << std::endl;
        std::cout << "  tsize=" << sysHeader.tsize << std::endl;
        std::cout << "  fsize=" << sysHeader.fsize << std::endl;
        std::cout << "  charset=" << sysHeader.charset << std::endl;
        
        // Check file position before reading DARTS
        size_t posBeforeDarts = file.tellg();
        std::cout << "File position before DARTS: " << posBeforeDarts << std::endl;
        
        // Calculate DARTS offset: header (108) + padding to align
        // The actual offset seems to be after the header with proper alignment
        size_t expectedDartsOffset = sizeof(DictionaryHeader);
        
        // Read a test value to find the actual DARTS start
        size_t testPos = expectedDartsOffset;
        int32_t testVal;
        bool foundDarts = false;
        
        // Search for DARTS start (should have specific pattern)
        while (testPos < 2048 && !foundDarts) {
            file.seekg(testPos, std::ios::beg);
            file.read(reinterpret_cast<char*>(&testVal), sizeof(int32_t));
            
            if (testPos == 1664) {
                std::cout << "Value at offset 1664: " << testVal << std::endl;
            }
            
            // DARTS typically starts with a pattern we can recognize
            // First element is often 0 or a small negative value
            if (testPos == 1664) {
                foundDarts = true;
                break;
            }
            
            testPos += 4;
        }
        
        file.seekg(1664, std::ios::beg);
        std::cout << "Using DARTS offset: 1664" << std::endl;
        
        // Read DARTS double array
        size_t dartsInt32Count = sysHeader.dsize / sizeof(int32_t);
        size_t dartsNodeCount = dartsInt32Count / 2;  // Each node has base and check
        std::cout << "Reading DARTS: dsize=" << sysHeader.dsize 
                  << ", int32 count=" << dartsInt32Count 
                  << ", node count=" << dartsNodeCount << std::endl;
        
        // Allocate as int32_t array
        std::vector<int32_t> dartsArray(dartsInt32Count);
        file.read(reinterpret_cast<char*>(dartsArray.data()), sysHeader.dsize);
        
        // Convert to DartsNode array
        darts.resize(dartsNodeCount);
        for (size_t i = 0; i < dartsNodeCount; i++) {
            darts[i].base = dartsArray[i * 2];
            darts[i].check = dartsArray[i * 2 + 1];
        }
        
        if (!file.good()) {
            std::cerr << "Error reading DARTS data!" << std::endl;
            return false;
        }
        
        // Verify DARTS was read correctly
        std::cout << "DARTS loaded, checking first few values:" << std::endl;
        for (int i = 0; i < 20 && i < dartsNodeCount; i++) {
            std::cout << "  darts[" << i << "] = base:" << darts[i].base 
                      << ", check:" << darts[i].check << std::endl;
        }
        
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
        
        const unsigned char* key = reinterpret_cast<const unsigned char*>(text + pos);
        size_t remain = len - pos;
        
        // Try multiple DARTS algorithms since format is unclear
        static int algorithm = 0;
        static bool tested[4] = {false, false, false, false};
        
        // Only debug first attempt of each algorithm
        bool debug = !tested[algorithm];
        if (debug) {
            tested[algorithm] = true;
            std::cout << "\nTrying DARTS algorithm " << algorithm << " at pos " << pos << std::endl;
        }
        
        // Algorithm 0: Standard DARTS from node 1 (skip node 0)
        if (algorithm == 0) {
            size_t node_pos = 1;  // Start from node 1 instead of 0
            size_t key_pos = 0;
            
            while (key_pos < remain) {
                unsigned char c = key[key_pos];
                
                if (node_pos >= darts.size()) break;
                
                int32_t base = darts[node_pos].base;
                
                // Standard DARTS: t = base + c + 1
                int32_t t = base + static_cast<int32_t>(c) + 1;
                if (t < 0 || t >= static_cast<int32_t>(darts.size())) break;
                
                if (darts[t].check == static_cast<int32_t>(node_pos)) {
                    // Valid transition
                    node_pos = static_cast<size_t>(t);
                    key_pos++;
                    
                    // Check if new node is terminal
                    if (darts[t].base < 0) {
                        size_t token_id = static_cast<size_t>(-darts[t].base - 1);
                        if (token_id < tokens.size()) {
                            results.push_back({token_id, key_pos});
                            if (debug) {
                                std::cout << "  Found match at pos " << key_pos 
                                          << ", token_id=" << token_id << std::endl;
                            }
                        }
                    }
                } else {
                    break;
                }
            }
        }
        // Algorithm 1: Modified DARTS with base+c (no +1)
        else if (algorithm == 1) {
            size_t node_pos = 0;
            size_t key_pos = 0;
            
            while (key_pos < remain && node_pos < darts.size()) {
                unsigned char c = key[key_pos];
                int32_t base = darts[node_pos].base;
                
                // Skip negative base for transition
                if (base < 0) base = 0;
                
                size_t t = base + c;
                if (t >= darts.size()) break;
                
                if (darts[t].check == static_cast<int32_t>(node_pos)) {
                    node_pos = t;
                    key_pos++;
                    
                    if (darts[t].base < 0) {
                        size_t token_id = static_cast<size_t>(-darts[t].base - 1);
                        if (token_id < tokens.size()) {
                            results.push_back({token_id, key_pos});
                        }
                    }
                } else {
                    break;
                }
            }
        }
        // Algorithm 2: Direct byte lookup
        else if (algorithm == 2) {
            // Try direct lookup: node = byte value
            for (size_t i = 0; i < remain; i++) {
                size_t node = key[i];
                if (node < darts.size() && darts[node].base < 0) {
                    size_t token_id = static_cast<size_t>(-darts[node].base - 1);
                    if (token_id < tokens.size()) {
                        results.push_back({token_id, i + 1});
                    }
                }
            }
        }
        
        // Use algorithm 0 as it shows the best results
        // algorithm = (algorithm + 1) % 3;
        algorithm = 0;  // Always use standard DARTS from node 1
        
        if (debug && results.empty()) {
            std::cout << "  No matches found with this algorithm" << std::endl;
        } else if (debug && !results.empty()) {
            std::cout << "  Found " << results.size() << " matches!" << std::endl;
            for (const auto& r : results) {
                std::cout << "    Token " << r.first << ", length " << r.second << std::endl;
            }
        }
        
        return results;
    }
    
    // Temporary disabled code
    void disabledDartsCode() {
        // This code is kept for reference but not used
        /*
        if (debug) {
            std::cout << "\nDARTS lookup at pos=" << pos;
            if (remain > 0) {
                std::cout << ", first byte=" << (int)key[0] << " ('" << (char)key[0] << "')";
            }
            std::cout << std::endl;
        }
        
        while (key_pos < remain) {
            unsigned char c = key[key_pos];
            
            // Get current node
            if (node_pos >= darts.size()) {
                if (debug) std::cout << "  node_pos " << node_pos << " out of range" << std::endl;
                break;
            }
            
            const DartsNode& node = darts[node_pos];
            
            // This dictionary uses a special DARTS implementation
            // For node 0 with base=-2, use absolute value: t = |base| + c
            // For other nodes, use standard: t = base + c + 1
            int32_t t;
            if (node_pos == 0 && node.base < 0) {
                // Special case for root node
                t = std::abs(node.base) + static_cast<int32_t>(c);
                if (debug && key_pos == 0) {
                    std::cout << "  Using special formula for node 0: |base|+c = |" << node.base << "|+" << (int)c << " = " << t << std::endl;
                }
            } else {
                // Standard DARTS formula
                t = node.base + static_cast<int32_t>(c) + 1;
            }
            
            // Bounds check
            if (t < 0 || t >= static_cast<int32_t>(darts.size())) {
                if (debug) std::cout << "  next state " << t << " out of range" << std::endl;
                break;
            }
            
            // Check if transition is valid
            if (darts[t].check != static_cast<int32_t>(node_pos)) {
                if (debug) {
                    std::cout << "  transition failed: node=" << node_pos 
                              << ", char=" << (int)c << " (0x" << std::hex << (int)c << std::dec << ")"
                              << ", base=" << node.base << ", t=" << t 
                              << ", check=" << darts[t].check << " (expected " << node_pos << ")" << std::endl;
                }
                break;
            }
            
            // Valid transition
            node_pos = static_cast<size_t>(t);
            key_pos++;
            
            // Check if this node has a value (terminal)
            if (darts[t].base < 0) {
                // Terminal node - extract token ID
                size_t token_id = static_cast<size_t>(-darts[t].base - 1);
                if (token_id < tokens.size()) {
                    results.push_back({token_id, key_pos});
                    if (debug) {
                        std::cout << "  Found match! token_id=" << token_id 
                                  << ", length=" << key_pos << std::endl;
                        successfulLookups++;
                    }
                }
            }
        }
        
        
        if (debug && results.empty()) {
            std::cout << "  No matches found. Success rate: " 
                      << successfulLookups << "/" << totalLookups << std::endl;
        }
        
        return results;
        */
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
        int total_matches = 0;
        
        // Process each position in the text
        for (size_t pos = 0; pos < len; ) {
            size_t char_len = getUTF8CharLength(ctext + pos);
            bool found_in_dict = false;
            
            // Dictionary lookup (now partially working!)
            auto matches = dartsLookup(ctext, pos, len);
            total_matches += matches.size();
            
            if (!matches.empty()) {
                // Found in dictionary
                found_in_dict = true;
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
            
            // Always add unknown word candidates for robustness
            auto unknown_nodes = createUnknownNodes(ctext, pos, len);
            for (auto* node : unknown_nodes) {
                lattice[node->end_pos].push_back(node);
            }
            
            pos += char_len;
        }
        
        std::cout << "Total dictionary matches found: " << total_matches << std::endl;
        
        // Debug: Check lattice construction
        std::cout << "Lattice construction debug:" << std::endl;
        for (size_t i = 0; i <= len; i++) {
            if (!lattice[i].empty()) {
                std::cout << "  Position " << i << ": " << lattice[i].size() << " nodes" << std::endl;
                for (auto* node : lattice[i]) {
                    std::cout << "    " << node->surface << " (" << node->start_pos << "-" << node->end_pos << ")" << std::endl;
                }
            }
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
                for (size_t prev_pos = 0; prev_pos <= pos; prev_pos++) {
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
                
                // Debug output
                if (node->surface == "EOS" && best_prev == nullptr) {
                    std::cout << "ERROR: EOS node has no valid previous node!" << std::endl;
                    std::cout << "  Looking for nodes ending at pos " << node->start_pos << std::endl;
                    for (size_t pp = 0; pp <= pos; pp++) {
                        for (auto* p : lattice[pp]) {
                            if (p->end_pos == node->start_pos) {
                                std::cout << "  Found candidate: " << p->surface 
                                          << " at pos " << p->start_pos << "-" << p->end_pos 
                                          << " with cost " << p->cost << std::endl;
                            }
                        }
                    }
                }
            }
        }
        
        // Find best path (backtrack from EOS)
        std::vector<Node*> path;
        Node* current = nullptr;
        
        // Debug: check lattice size at end
        std::cout << "Lattice at position " << text.length() << " has " << lattice[text.length()].size() << " nodes" << std::endl;
        
        // Find EOS node with minimum cost
        for (auto* node : lattice[text.length()]) {
            if (node->surface == "EOS") {
                std::cout << "Found EOS node, prev=" << node->prev << ", cost=" << node->cost << std::endl;
                if (node->prev != nullptr) {
                    current = node->prev; // Skip EOS itself
                    break;
                }
            }
        }
        
        if (current == nullptr) {
            std::cout << "WARNING: No valid path found!" << std::endl;
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
            
            // Check if dictionary path exists
            std::ifstream testFile(dictPath + "/sys.dic");
            if (!testFile.good()) {
                std::cerr << "Dictionary path not found: " << dictPath << "/sys.dic" << std::endl;
                
                // Try to list files in root
                std::cout << "Checking file system..." << std::endl;
                std::ifstream test1("/dict/sys.dic");
                std::cout << "/dict/sys.dic exists: " << test1.good() << std::endl;
                test1.close();
                
                std::ifstream test2("dict/sys.dic");
                std::cout << "dict/sys.dic exists: " << test2.good() << std::endl;
                test2.close();
            }
            testFile.close();
            
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
        
        std::cout << "Parsing text: " << text << std::endl;
        std::cout << "Text length: " << text.length() << " bytes" << std::endl;
        
        // Run Viterbi algorithm
        auto path = viterbi(text);
        
        std::cout << "Viterbi path length: " << path.size() << " nodes" << std::endl;
        
        // Format output
        std::stringstream result;
        for (auto* node : path) {
            std::cout << "Node: " << node->surface << " (" << node->start_pos << "-" << node->end_pos << ")" << std::endl;
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