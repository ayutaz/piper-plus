#include <emscripten.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Include actual OpenJTalk headers
#include "mecab.h"
#include "njd.h"
#include "jpcommon.h"
#include "HTS_engine.h"
#include "text2mecab.h"
#include "mecab2njd.h"
#include "njd_set_pronunciation.h"
#include "njd_set_digit.h"
#include "njd_set_accent_phrase.h"
#include "njd_set_accent_type.h"
#include "njd_set_unvoiced_vowel.h"
#include "njd_set_long_vowel.h"
#include "njd2jpcommon.h"

// Use Open_JTalk structure like the reference implementation
typedef struct _Open_JTalk {
   Mecab mecab;
   NJD njd;
   JPCommon jpcommon;
   HTS_Engine engine;
} Open_JTalk;

// Global instance - properly allocated
static Open_JTalk *open_jtalk = NULL;
static int initialized = 0;

#define TRUE 1
#define FALSE 0

EMSCRIPTEN_KEEPALIVE
int openjtalk_initialize(const char* dic_dir, const char* voice_path) {
    if (initialized) {
        return 0;
    }
    
    // Debug output
    EM_ASM({ console.log('Initializing OpenJTalk with dict:', UTF8ToString($0), 'voice:', UTF8ToString($1)); }, dic_dir, voice_path);
    
    // Allocate Open_JTalk structure
    open_jtalk = (Open_JTalk*)malloc(sizeof(Open_JTalk));
    if (!open_jtalk) {
        EM_ASM({ console.error('Failed to allocate memory for Open_JTalk'); });
        return -3;
    }
    
    // Initialize components in the same order as reference
    EM_ASM({ console.log('Initializing Mecab...'); });
    Mecab_initialize(&open_jtalk->mecab);
    
    EM_ASM({ console.log('Initializing NJD...'); });
    NJD_initialize(&open_jtalk->njd);
    
    EM_ASM({ console.log('Initializing JPCommon...'); });
    JPCommon_initialize(&open_jtalk->jpcommon);
    
    EM_ASM({ console.log('Initializing HTS Engine...'); });
    HTS_Engine_initialize(&open_jtalk->engine);
    
    // Load dictionary
    EM_ASM({ console.log('Loading Mecab dictionary...'); });
    if (Mecab_load(&open_jtalk->mecab, dic_dir) != TRUE) {
        EM_ASM({ console.error('Failed to load Mecab dictionary'); });
        free(open_jtalk);
        return -1;
    }
    EM_ASM({ console.log('Mecab dictionary loaded successfully'); });
    
    // Load voice
    EM_ASM({ console.log('Loading voice file...'); });
    char *voices[1] = {(char*)voice_path};
    if (HTS_Engine_load(&open_jtalk->engine, voices, 1) != TRUE) {
        EM_ASM({ console.error('Failed to load HTS voice'); });
        Mecab_clear(&open_jtalk->mecab);
        free(open_jtalk);
        return -2;
    }
    EM_ASM({ console.log('HTS Engine loaded successfully'); });
    
    // Set default parameters
    HTS_Engine_set_sampling_frequency(&open_jtalk->engine, 48000);
    HTS_Engine_set_speed(&open_jtalk->engine, 1.0);
    HTS_Engine_set_alpha(&open_jtalk->engine, 0.55);
    
    initialized = 1;
    EM_ASM({ console.log('OpenJTalk initialization complete!'); });
    return 0;
}

EMSCRIPTEN_KEEPALIVE
char* openjtalk_synthesis_labels(const char* text) {
    if (!initialized || !text || !open_jtalk) {
        return strdup("ERROR: Not initialized or null text");
    }
    
    // Debug output
    EM_ASM({ console.log('Synthesizing text:', UTF8ToString($0)); }, text);
    
    char buff[8192];
    text2mecab(buff, text);
    EM_ASM({ console.log('After text2mecab:', UTF8ToString($0)); }, buff);
    
    int mecab_result = Mecab_analysis(&open_jtalk->mecab, buff);
    EM_ASM({ console.log('Mecab_analysis result:', $0); }, mecab_result);
    
    int mecab_size = Mecab_get_size(&open_jtalk->mecab);
    EM_ASM({ console.log('Mecab_get_size:', $0); }, mecab_size);
    
    if (mecab_size > 0) {
        char** features = Mecab_get_feature(&open_jtalk->mecab);
        if (features && features[0]) {
            EM_ASM({ console.log('First feature:', UTF8ToString($0)); }, features[0]);
        }
    }
    
    mecab2njd(&open_jtalk->njd, Mecab_get_feature(&open_jtalk->mecab), Mecab_get_size(&open_jtalk->mecab));
    
    njd_set_pronunciation(&open_jtalk->njd);
    njd_set_digit(&open_jtalk->njd);
    njd_set_accent_phrase(&open_jtalk->njd);
    njd_set_accent_type(&open_jtalk->njd);
    njd_set_unvoiced_vowel(&open_jtalk->njd);
    njd_set_long_vowel(&open_jtalk->njd);
    
    njd2jpcommon(&open_jtalk->jpcommon, &open_jtalk->njd);
    
    // Make label first
    JPCommon_make_label(&open_jtalk->jpcommon);
    
    // Get labels
    int label_size = JPCommon_get_label_size(&open_jtalk->jpcommon);
    EM_ASM({ console.log('Label size after make_label:', $0); }, label_size);
    
    if (label_size <= 0) {
        return strdup("ERROR: No labels generated");
    }
    
    // Get all labels at once
    char **labels = JPCommon_get_label_feature(&open_jtalk->jpcommon);
    if (!labels) {
        return strdup("ERROR: Failed to get labels");
    }
    
    // Calculate total size needed
    int total_len = 0;
    int i;
    for (i = 0; i < label_size; i++) {
        if (labels[i]) {
            total_len += strlen(labels[i]) + 1; // +1 for newline
        }
    }
    
    // Allocate result
    char* result = (char*)malloc(total_len + 1);
    if (!result) {
        return strdup("ERROR: Memory allocation failed");
    }
    result[0] = '\0';
    
    // Build result
    for (i = 0; i < label_size; i++) {
        if (labels[i]) {
            strcat(result, labels[i]);
            strcat(result, "\n");
        }
    }
    
    // Clean up for next synthesis
    JPCommon_refresh(&open_jtalk->jpcommon);
    NJD_refresh(&open_jtalk->njd);
    Mecab_refresh(&open_jtalk->mecab);
    
    EM_ASM({ console.log('Generated', $0, 'labels'); }, label_size);
    
    return result;
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_clear() {
    if (!initialized || !open_jtalk) {
        return;
    }
    
    HTS_Engine_clear(&open_jtalk->engine);
    JPCommon_clear(&open_jtalk->jpcommon);
    NJD_clear(&open_jtalk->njd);
    Mecab_clear(&open_jtalk->mecab);
    
    free(open_jtalk);
    open_jtalk = NULL;
    initialized = 0;
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_free_string(char* str) {
    if (str) {
        free(str);
    }
}

// Test functions
EMSCRIPTEN_KEEPALIVE
const char* get_version() {
    return "OpenJTalk WebAssembly 1.0.1 (Safe)";
}

EMSCRIPTEN_KEEPALIVE
int test_function(int a, int b) {
    return a + b;
}