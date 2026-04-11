#ifndef OPENJTALK_DICTIONARY_MANAGER_H
#define OPENJTALK_DICTIONARY_MANAGER_H

#ifdef __cplusplus
extern "C" {
#endif

// Get the path to the OpenJTalk dictionary
const char* get_openjtalk_dictionary_path();

// Ensure the OpenJTalk dictionary is available (download if necessary)
int ensure_openjtalk_dictionary();

// Reset the cached dictionary path (for testing only)
void reset_openjtalk_dictionary_cache(void);

// Force the cached dictionary path to a specific value (for testing)
void force_openjtalk_dictionary_path(const char* path);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_DICTIONARY_MANAGER_H