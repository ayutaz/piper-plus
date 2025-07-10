#ifndef OPENJTALK_WRAPPER_FUNCTIONS_H_
#define OPENJTALK_WRAPPER_FUNCTIONS_H_

#ifdef __cplusplus
extern "C" {
#endif

// Check if OpenJTalk binary is available
int openjtalk_is_available();

// Ensure OpenJTalk dictionary is available
int openjtalk_ensure_dictionary();

// Convert text to phonemes using OpenJTalk (external binary)
char* openjtalk_text_to_phonemes(const char* text);

// Convert text to phonemes using OpenJTalk internal API (more efficient)
// TEMPORARILY DISABLED - requires OpenJTalk static libs
// char* openjtalk_text_to_phonemes_api(const char* text);

// Free phoneme string
void openjtalk_free_phonemes(char* phonemes);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_WRAPPER_FUNCTIONS_H_