/**
 * Compressed Dictionary Loader for WebAssembly
 * 
 * Loads and decompresses dictionary data for MeCab/OpenJTalk
 */

#ifndef COMPRESSED_DICT_LOADER_H
#define COMPRESSED_DICT_LOADER_H

#include <vector>
#include <string>
#include <memory>
#include <cstdint>
#include <emscripten/fetch.h>
#include <zlib.h>

namespace piper {

// Dictionary entry for runtime use
struct RuntimeDictEntry {
    const char* surface;      // Pointer into string pool
    const char* reading;      // Pointer into string pool
    const char* pronunciation; // Pointer into string pool (may be same as reading)
    uint16_t left_id;
    uint16_t right_id;
    uint16_t cost;
    uint16_t pos_id;
    uint8_t accent;
};

class CompressedDictLoader {
private:
    // Header structure
    struct DictHeader {
        uint32_t magic;
        uint32_t version;
        uint32_t num_entries;
        uint32_t surface_offset;
        uint32_t reading_offset;
        uint32_t entry_offset;
    };
    
    // Memory buffers
    std::vector<uint8_t> dict_data;
    std::vector<RuntimeDictEntry> entries;
    std::vector<uint8_t> decompressed_entries;
    
    // String pools (points into dict_data)
    const char* surface_pool = nullptr;
    const char* reading_pool = nullptr;
    
    bool loaded = false;
    
    // Decompress data
    bool decompressData(const uint8_t* compressed, size_t compressed_size, 
                       uint8_t* output, size_t output_size) {
        uLongf dest_len = output_size;
        int result = uncompress(output, &dest_len, compressed, compressed_size);
        return result == Z_OK && dest_len == output_size;
    }
    
public:
    // Load from memory
    bool loadFromMemory(const uint8_t* data, size_t size) {
        if (size < sizeof(DictHeader)) {
            return false;
        }
        
        // Copy data
        dict_data.assign(data, data + size);
        
        // Read header
        const DictHeader* header = reinterpret_cast<const DictHeader*>(dict_data.data());
        
        // Validate magic number
        if (header->magic != 0x4D434142) {  // 'MCAB'
            return false;
        }
        
        // Set string pool pointers
        surface_pool = reinterpret_cast<const char*>(dict_data.data() + header->surface_offset);
        reading_pool = reinterpret_cast<const char*>(dict_data.data() + header->reading_offset);
        
        // Read compressed size
        const uint8_t* entry_data = dict_data.data() + header->entry_offset;
        uint32_t compressed_size = *reinterpret_cast<const uint32_t*>(entry_data);
        entry_data += sizeof(uint32_t);
        
        // Decompress entries
        size_t entry_size = 16;  // Fixed size per entry
        size_t total_size = header->num_entries * entry_size;
        decompressed_entries.resize(total_size);
        
        if (!decompressData(entry_data, compressed_size, 
                           decompressed_entries.data(), total_size)) {
            return false;
        }
        
        // Build runtime entries
        entries.resize(header->num_entries);
        const uint8_t* entry_ptr = decompressed_entries.data();
        
        for (uint32_t i = 0; i < header->num_entries; i++) {
            RuntimeDictEntry& entry = entries[i];
            
            // Read surface_id
            uint32_t surface_id = entry_ptr[0] | 
                                 (entry_ptr[1] << 8) | 
                                 (entry_ptr[2] << 16) | 
                                 (entry_ptr[3] << 24);
            entry.surface = surface_pool + surface_id;
            
            // Read other fields
            entry.left_id = entry_ptr[4] | (entry_ptr[5] << 8);
            entry.right_id = entry_ptr[6] | (entry_ptr[7] << 8);
            entry.cost = entry_ptr[8] | (entry_ptr[9] << 8);
            entry.pos_id = entry_ptr[10] | (entry_ptr[11] << 8);
            
            // Read reading offset
            uint16_t reading_offset = entry_ptr[12] | (entry_ptr[13] << 8);
            const char* reading_str = reading_pool + reading_offset;
            entry.reading = reading_str;
            
            // Check for separate pronunciation
            const char* pipe = strchr(reading_str, '|');
            if (pipe) {
                entry.pronunciation = pipe + 1;
            } else {
                entry.pronunciation = reading_str;
            }
            
            entry.accent = entry_ptr[14];
            
            entry_ptr += 16;
        }
        
        loaded = true;
        return true;
    }
    
    // Async load from URL
    void loadFromURL(const std::string& url, 
                    std::function<void(bool)> callback) {
        emscripten_fetch_attr_t attr;
        emscripten_fetch_attr_init(&attr);
        strcpy(attr.requestMethod, "GET");
        attr.attributes = EMSCRIPTEN_FETCH_LOAD_TO_MEMORY;
        
        // Store callback in userData
        struct CallbackData {
            CompressedDictLoader* loader;
            std::function<void(bool)> callback;
        };
        
        CallbackData* cb_data = new CallbackData{this, callback};
        attr.userData = cb_data;
        
        attr.onsuccess = [](emscripten_fetch_t* fetch) {
            CallbackData* cb_data = static_cast<CallbackData*>(fetch->userData);
            
            bool success = cb_data->loader->loadFromMemory(
                reinterpret_cast<const uint8_t*>(fetch->data), 
                fetch->numBytes
            );
            
            cb_data->callback(success);
            delete cb_data;
            emscripten_fetch_close(fetch);
        };
        
        attr.onerror = [](emscripten_fetch_t* fetch) {
            CallbackData* cb_data = static_cast<CallbackData*>(fetch->userData);
            cb_data->callback(false);
            delete cb_data;
            emscripten_fetch_close(fetch);
        };
        
        emscripten_fetch(&attr, url.c_str());
    }
    
    // Get entries
    const std::vector<RuntimeDictEntry>& getEntries() const {
        return entries;
    }
    
    // Lookup by surface form (binary search)
    const RuntimeDictEntry* lookup(const std::string& surface) const {
        if (!loaded) return nullptr;
        
        // Binary search (assumes entries are sorted by surface)
        auto it = std::lower_bound(entries.begin(), entries.end(), surface,
            [](const RuntimeDictEntry& entry, const std::string& key) {
                return strcmp(entry.surface, key.c_str()) < 0;
            });
        
        if (it != entries.end() && strcmp(it->surface, surface.c_str()) == 0) {
            return &(*it);
        }
        
        return nullptr;
    }
    
    // Get memory usage
    size_t getMemoryUsage() const {
        return dict_data.size() + 
               entries.size() * sizeof(RuntimeDictEntry) +
               decompressed_entries.size();
    }
    
    bool isLoaded() const {
        return loaded;
    }
};

} // namespace piper

#endif // COMPRESSED_DICT_LOADER_H