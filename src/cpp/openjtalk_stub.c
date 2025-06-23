#include "openjtalk_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Stub implementation of OpenJTalk that provides fallback behavior
// This allows the build to succeed while we work on proper OpenJTalk integration

struct _OpenJTalk {
    int initialized;
};

struct _HTS_Label {
    char** labels;
    size_t size;
};

OpenJTalk* openjtalk_initialize() {
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    oj->initialized = 0;
    
    // Log that we're using stub implementation
    fprintf(stderr, "OpenJTalk: Using stub implementation - Japanese text will fallback to codepoints\n");
    
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    free(oj);
}

HTS_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text) return NULL;
    
    // Stub implementation: just return empty label set
    HTS_Label* label = (HTS_Label*)malloc(sizeof(HTS_Label));
    if (!label) return NULL;
    
    label->labels = NULL;
    label->size = 0;
    
    return label;
}

size_t HTS_Label_get_size(HTS_Label* label) {
    if (!label) return 0;
    return label->size;
}

const char* HTS_Label_get_string(HTS_Label* label, size_t index) {
    if (!label || !label->labels || index >= label->size) return NULL;
    return label->labels[index];
}

void HTS_Label_clear(HTS_Label* label) {
    if (!label) return;
    
    if (label->labels) {
        for (size_t i = 0; i < label->size; i++) {
            if (label->labels[i]) free(label->labels[i]);
        }
        free(label->labels);
    }
    
    free(label);
}