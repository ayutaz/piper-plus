#ifndef DICTIONARY_READER_H
#define DICTIONARY_READER_H

#include <string>
#include <vector>
#include <memory>
#include <cstdint>

#define DIC_MAGIC_ID 0xE954A1B6

// MeCab dictionary format structures
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
    uint16_t wcost;
    uint32_t feature;
    uint32_t compound;
};

struct DartsNode {
    int32_t base;
    uint32_t check;
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
};

class DictionaryReader {
private:
    bool loaded;
    DictionaryHeader header;
    std::vector<DartsNode> darts;
    std::vector<Token> tokens;
    std::vector<char> features;
    std::vector<std::string> posNames;
    
    // Cached entries for quick lookup
    std::vector<DictionaryEntry> entries;
    
    bool loadPosFile(const std::string& path);
    bool parseDictionary(const uint8_t* data, size_t size);
    std::vector<std::string> parseFeature(const char* feature);
    
public:
    DictionaryReader();
    ~DictionaryReader();
    
    bool loadFromFile(const std::string& dictPath);
    bool loadFromMemory(const uint8_t* data, size_t size);
    
    std::vector<DictionaryEntry> lookup(const std::string& text);
    std::vector<DictionaryEntry> getAllEntries() { return entries; }
    
    bool isLoaded() const { return loaded; }
    size_t getEntryCount() const { return entries.size(); }
};

#endif // DICTIONARY_READER_H