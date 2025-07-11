#ifndef OPENJTALK_OPTIMIZED_H
#define OPENJTALK_OPTIMIZED_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stddef.h>

// Cache configuration
typedef struct {
    size_t max_entries;        // Maximum number of cached entries
    size_t max_memory_bytes;   // Maximum memory usage for cache
    int ttl_seconds;          // Time-to-live for cache entries (0 = no expiration)
} OpenJTalkCacheConfig;

// Initialize the optimized OpenJTalk with optional cache
// Pass NULL for cache_config to disable caching
bool openjtalk_optimized_init(const OpenJTalkCacheConfig* cache_config);

// Cleanup resources
void openjtalk_optimized_cleanup(void);

// Convert text to phonemes using optimized pipe-based implementation
// Returns allocated string that must be freed with openjtalk_free_phonemes()
char* openjtalk_text_to_phonemes_optimized(const char* text);

// Clear the phoneme cache
void openjtalk_clear_cache(void);

// Get cache statistics
typedef struct {
    size_t total_requests;
    size_t cache_hits;
    size_t cache_misses;
    size_t current_entries;
    size_t current_memory_bytes;
} OpenJTalkCacheStats;

void openjtalk_get_cache_stats(OpenJTalkCacheStats* stats);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_OPTIMIZED_H