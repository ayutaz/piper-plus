#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/cpp/openjtalk_api.h"

int main(int argc, char *argv[]) {
    const char *text = "こんにちは";
    if (argc > 1) {
        text = argv[1];
    }
    
    printf("Testing OpenJTalk with text: %s\n", text);
    
    // Initialize OpenJTalk
    OpenJTalk *oj = openjtalk_initialize();
    if (!oj) {
        fprintf(stderr, "Failed to initialize OpenJTalk\n");
        return 1;
    }
    
    printf("OpenJTalk initialized successfully\n");
    
    // Extract labels
    OJ_Label *labels = openjtalk_extract_fullcontext(oj, text);
    if (!labels) {
        fprintf(stderr, "Failed to extract labels\n");
        openjtalk_finalize(oj);
        return 1;
    }
    
    // Print labels
    size_t num_labels = OJ_Label_get_size(labels);
    printf("Number of labels: %zu\n", num_labels);
    
    for (size_t i = 0; i < num_labels; i++) {
        const char *label = OJ_Label_get_string(labels, i);
        if (label) {
            printf("Label[%zu]: %s\n", i, label);
        }
    }
    
    // Cleanup
    OJ_Label_clear(labels);
    openjtalk_finalize(oj);
    
    return 0;
}