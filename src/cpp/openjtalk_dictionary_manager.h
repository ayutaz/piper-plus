#ifndef OPENJTALK_DICTIONARY_MANAGER_H
#define OPENJTALK_DICTIONARY_MANAGER_H

#ifdef __cplusplus
extern "C" {
#endif

// Get the path to the OpenJTalk dictionary
const char* get_openjtalk_dictionary_path();

// Get the path to the HTS voice file
const char* get_openjtalk_voice_path();

// Ensure the OpenJTalk dictionary is available (download if necessary)
int ensure_openjtalk_dictionary();

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_DICTIONARY_MANAGER_H