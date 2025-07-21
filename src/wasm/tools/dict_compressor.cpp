/**
 * Dictionary Compression Tool for MeCab/OpenJTalk
 * 
 * Compresses dictionary files for WebAssembly deployment
 * Target: 103MB -> 50MB reduction
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <memory>
#include <cstring>
#include <zlib.h>

// Dictionary entry structure
struct DictEntry {
    uint32_t surface_id;      // Surface form ID (for deduplication)
    uint16_t left_id;         // Left context ID
    uint16_t right_id;        // Right context ID
    uint16_t cost;            // Connection cost
    uint16_t pos_id;          // Part of speech ID
    std::string reading;      // Reading (katakana)
    std::string pronunciation; // Pronunciation
    uint8_t accent;           // Accent information
};

// Compressed dictionary format
struct CompressedDict {
    // Header
    uint32_t magic;           // Magic number: 'MCAB'
    uint32_t version;         // Format version
    uint32_t num_entries;     // Number of entries
    uint32_t surface_offset;  // Offset to surface strings
    uint32_t reading_offset;  // Offset to reading strings
    uint32_t entry_offset;    // Offset to entry data
    
    // String pools
    std::vector<char> surface_pool;
    std::vector<char> reading_pool;
    
    // Compressed entries
    std::vector<uint8_t> entries;
};

class DictCompressor {
private:
    std::map<std::string, uint32_t> surface_map;
    std::map<std::string, uint32_t> reading_map;
    std::vector<DictEntry> entries;
    
    // Add string to pool and return offset
    uint32_t addToPool(const std::string& str, 
                       std::vector<char>& pool, 
                       std::map<std::string, uint32_t>& map) {
        auto it = map.find(str);
        if (it != map.end()) {
            return it->second;
        }
        
        uint32_t offset = pool.size();
        pool.insert(pool.end(), str.begin(), str.end());
        pool.push_back('\0');
        map[str] = offset;
        return offset;
    }
    
    // Compress using zlib
    std::vector<uint8_t> compressData(const uint8_t* data, size_t size) {
        // Estimate compressed size
        uLongf compressed_size = compressBound(size);
        std::vector<uint8_t> compressed(compressed_size);
        
        int result = compress2(
            compressed.data(), &compressed_size,
            data, size,
            Z_BEST_COMPRESSION
        );
        
        if (result != Z_OK) {
            throw std::runtime_error("Compression failed");
        }
        
        compressed.resize(compressed_size);
        return compressed;
    }
    
public:
    // Load dictionary from MeCab format
    bool loadMeCabDict(const std::string& filename) {
        std::ifstream file(filename, std::ios::binary);
        if (!file) {
            std::cerr << "Failed to open: " << filename << std::endl;
            return false;
        }
        
        // Skip MeCab binary header (simplified)
        file.seekg(100);  // Actual header size varies
        
        // Read entries (simplified format)
        std::string line;
        while (std::getline(file, line)) {
            // Parse CSV format (simplified)
            // surface,left_id,right_id,cost,pos,pos_id,...,reading,pronunciation
            
            // This is a simplified parser - real implementation would be more robust
            DictEntry entry;
            // ... parse entry from line ...
            entries.push_back(entry);
        }
        
        return true;
    }
    
    // Load from text dictionary (for testing)
    bool loadTextDict(const std::string& filename) {
        std::ifstream file(filename);
        if (!file) {
            std::cerr << "Failed to open: " << filename << std::endl;
            return false;
        }
        
        std::string line;
        while (std::getline(file, line)) {
            if (line.empty() || line[0] == '#') continue;
            
            // Simple tab-separated format for testing
            // surface\tleft_id\tright_id\tcost\tpos_id\treading\tpronunciation\taccent
            std::vector<std::string> parts;
            size_t start = 0;
            size_t pos = 0;
            
            while ((pos = line.find('\t', start)) != std::string::npos) {
                parts.push_back(line.substr(start, pos - start));
                start = pos + 1;
            }
            parts.push_back(line.substr(start));
            
            if (parts.size() >= 8) {
                DictEntry entry;
                entry.surface_id = 0;  // Will be set during compression
                entry.left_id = std::stoi(parts[1]);
                entry.right_id = std::stoi(parts[2]);
                entry.cost = std::stoi(parts[3]);
                entry.pos_id = std::stoi(parts[4]);
                entry.reading = parts[5];
                entry.pronunciation = parts[6];
                entry.accent = std::stoi(parts[7]);
                
                entries.push_back(entry);
            }
        }
        
        std::cout << "Loaded " << entries.size() << " entries" << std::endl;
        return true;
    }
    
    // Compress dictionary
    CompressedDict compress() {
        CompressedDict dict;
        dict.magic = 0x4D434142;  // 'MCAB'
        dict.version = 1;
        dict.num_entries = entries.size();
        
        // Build string pools
        for (auto& entry : entries) {
            // Note: In real implementation, surface would come from a separate source
            std::string surface = "dummy";  // Placeholder
            entry.surface_id = addToPool(surface, dict.surface_pool, surface_map);
            
            // Combine reading and pronunciation to save space
            std::string reading_pron = entry.reading;
            if (entry.pronunciation != entry.reading) {
                reading_pron += "|" + entry.pronunciation;
            }
            uint32_t reading_offset = addToPool(reading_pron, dict.reading_pool, reading_map);
        }
        
        // Pack entries into binary format
        std::vector<uint8_t> packed_entries;
        for (const auto& entry : entries) {
            // Fixed-size entry: 16 bytes
            // 4 bytes: surface_id
            // 2 bytes: left_id
            // 2 bytes: right_id
            // 2 bytes: cost
            // 2 bytes: pos_id
            // 2 bytes: reading_offset (into reading pool)
            // 1 byte: accent
            // 1 byte: flags/reserved
            
            // Write surface_id
            packed_entries.push_back(entry.surface_id & 0xFF);
            packed_entries.push_back((entry.surface_id >> 8) & 0xFF);
            packed_entries.push_back((entry.surface_id >> 16) & 0xFF);
            packed_entries.push_back((entry.surface_id >> 24) & 0xFF);
            
            // Write other fields
            packed_entries.push_back(entry.left_id & 0xFF);
            packed_entries.push_back((entry.left_id >> 8) & 0xFF);
            packed_entries.push_back(entry.right_id & 0xFF);
            packed_entries.push_back((entry.right_id >> 8) & 0xFF);
            packed_entries.push_back(entry.cost & 0xFF);
            packed_entries.push_back((entry.cost >> 8) & 0xFF);
            packed_entries.push_back(entry.pos_id & 0xFF);
            packed_entries.push_back((entry.pos_id >> 8) & 0xFF);
            
            // Get reading offset
            auto reading_key = entry.reading;
            if (entry.pronunciation != entry.reading) {
                reading_key += "|" + entry.pronunciation;
            }
            uint32_t reading_offset = reading_map[reading_key];
            packed_entries.push_back(reading_offset & 0xFF);
            packed_entries.push_back((reading_offset >> 8) & 0xFF);
            
            packed_entries.push_back(entry.accent);
            packed_entries.push_back(0);  // Reserved
        }
        
        // Compress entry data
        dict.entries = compressData(packed_entries.data(), packed_entries.size());
        
        // Calculate offsets
        dict.surface_offset = sizeof(uint32_t) * 6;  // After header
        dict.reading_offset = dict.surface_offset + dict.surface_pool.size();
        dict.entry_offset = dict.reading_offset + dict.reading_pool.size();
        
        return dict;
    }
    
    // Save compressed dictionary
    bool save(const CompressedDict& dict, const std::string& filename) {
        std::ofstream file(filename, std::ios::binary);
        if (!file) {
            std::cerr << "Failed to create: " << filename << std::endl;
            return false;
        }
        
        // Write header
        file.write(reinterpret_cast<const char*>(&dict.magic), sizeof(dict.magic));
        file.write(reinterpret_cast<const char*>(&dict.version), sizeof(dict.version));
        file.write(reinterpret_cast<const char*>(&dict.num_entries), sizeof(dict.num_entries));
        file.write(reinterpret_cast<const char*>(&dict.surface_offset), sizeof(dict.surface_offset));
        file.write(reinterpret_cast<const char*>(&dict.reading_offset), sizeof(dict.reading_offset));
        file.write(reinterpret_cast<const char*>(&dict.entry_offset), sizeof(dict.entry_offset));
        
        // Write string pools
        file.write(dict.surface_pool.data(), dict.surface_pool.size());
        file.write(dict.reading_pool.data(), dict.reading_pool.size());
        
        // Write compressed entry size
        uint32_t compressed_size = dict.entries.size();
        file.write(reinterpret_cast<const char*>(&compressed_size), sizeof(compressed_size));
        
        // Write compressed entries
        file.write(reinterpret_cast<const char*>(dict.entries.data()), dict.entries.size());
        
        return true;
    }
    
    // Print statistics
    void printStats(const CompressedDict& dict) {
        size_t original_size = entries.size() * sizeof(DictEntry);
        size_t compressed_size = sizeof(uint32_t) * 6 + 
                                dict.surface_pool.size() + 
                                dict.reading_pool.size() + 
                                dict.entries.size() + 
                                sizeof(uint32_t);
        
        std::cout << "\n=== Dictionary Compression Stats ===" << std::endl;
        std::cout << "Entries: " << dict.num_entries << std::endl;
        std::cout << "Surface pool: " << dict.surface_pool.size() << " bytes" << std::endl;
        std::cout << "Reading pool: " << dict.reading_pool.size() << " bytes" << std::endl;
        std::cout << "Entry data (compressed): " << dict.entries.size() << " bytes" << std::endl;
        std::cout << "Total size: " << compressed_size << " bytes" << std::endl;
        std::cout << "Compression ratio: " << 
                     (100.0 * compressed_size / original_size) << "%" << std::endl;
    }
};

// Main program
int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <input_dict> <output_dict>" << std::endl;
        std::cerr << "Options:" << std::endl;
        std::cerr << "  -t    Input is text format (for testing)" << std::endl;
        return 1;
    }
    
    bool text_format = false;
    int input_arg = 1;
    
    if (argc > 3 && std::string(argv[1]) == "-t") {
        text_format = true;
        input_arg = 2;
    }
    
    std::string input_file = argv[input_arg];
    std::string output_file = argv[input_arg + 1];
    
    DictCompressor compressor;
    
    // Load dictionary
    bool loaded = text_format ? 
                  compressor.loadTextDict(input_file) :
                  compressor.loadMeCabDict(input_file);
    
    if (!loaded) {
        std::cerr << "Failed to load dictionary" << std::endl;
        return 1;
    }
    
    // Compress
    std::cout << "Compressing dictionary..." << std::endl;
    CompressedDict compressed = compressor.compress();
    
    // Save
    if (!compressor.save(compressed, output_file)) {
        std::cerr << "Failed to save compressed dictionary" << std::endl;
        return 1;
    }
    
    // Print statistics
    compressor.printStats(compressed);
    
    std::cout << "\nCompressed dictionary saved to: " << output_file << std::endl;
    
    return 0;
}