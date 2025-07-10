#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// OpenJTalk wrapper functions
extern char* openjtalk_text_to_phonemes(const char* text);
extern void openjtalk_free_phonemes(char* phonemes);
extern int openjtalk_ensure_dictionary();

int main(int argc, char* argv[]) {
    const char* test_text = "こんにちは";
    
    if (argc > 1) {
        test_text = argv[1];
    }
    
    printf("Testing OpenJTalk phonemization...\n");
    printf("Input text: %s\n", test_text);
    
    // Ensure dictionary
    if (!openjtalk_ensure_dictionary()) {
        fprintf(stderr, "Failed to ensure dictionary\n");
        return 1;
    }
    
    // Get phonemes
    char* phonemes = openjtalk_text_to_phonemes(test_text);
    if (phonemes) {
        printf("Phonemes: %s\n", phonemes);
        
        // Print each phoneme
        char* copy = strdup(phonemes);
        char* token = strtok(copy, " ");
        int i = 0;
        while (token != NULL) {
            printf("  [%d] '%s' (length: %zu)\n", i++, token, strlen(token));
            token = strtok(NULL, " ");
        }
        free(copy);
        
        openjtalk_free_phonemes(phonemes);
    } else {
        fprintf(stderr, "Failed to get phonemes\n");
        return 1;
    }
    
    return 0;
}