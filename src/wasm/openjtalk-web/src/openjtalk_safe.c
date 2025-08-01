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

// Global instances - properly allocated
static Mecab *mecab = NULL;
static NJD *njd = NULL;
static JPCommon *jpcommon = NULL;
static HTS_Engine *engine = NULL;
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
    
    // Allocate structures
    mecab = (Mecab*)malloc(sizeof(Mecab));
    njd = (NJD*)malloc(sizeof(NJD));
    jpcommon = (JPCommon*)malloc(sizeof(JPCommon));
    engine = (HTS_Engine*)malloc(sizeof(HTS_Engine));
    
    if (!mecab || !njd || !jpcommon || !engine) {
        EM_ASM({ console.error('Failed to allocate memory for structures'); });
        return -3;
    }
    
    // Initialize Mecab
    EM_ASM({ console.log('Initializing Mecab...'); });
    Mecab_initialize(mecab);
    
    EM_ASM({ console.log('Loading Mecab dictionary...'); });
    if (Mecab_load(mecab, dic_dir) != TRUE) {
        EM_ASM({ console.error('Failed to load Mecab dictionary'); });
        return -1;
    }
    EM_ASM({ console.log('Mecab initialized successfully'); });
    
    // Initialize NJD
    NJD_initialize(njd);
    
    // Initialize JPCommon
    JPCommon_initialize(jpcommon);
    
    // Initialize HTS Engine
    EM_ASM({ console.log('Initializing HTS Engine...'); });
    HTS_Engine_initialize(engine);
    
    // Load voice
    EM_ASM({ console.log('Loading voice file...'); });
    char *voices[1] = {(char*)voice_path};
    if (HTS_Engine_load(engine, voices, 1) != TRUE) {
        EM_ASM({ console.error('Failed to load HTS voice'); });
        // Clean up
        Mecab_clear(mecab);
        free(mecab);
        free(njd);
        free(jpcommon);
        free(engine);
        return -2;
    }
    EM_ASM({ console.log('HTS Engine initialized successfully'); });
    
    // Set some default parameters
    HTS_Engine_set_sampling_frequency(engine, 48000);
    HTS_Engine_set_speed(engine, 1.0);
    HTS_Engine_set_alpha(engine, 0.55);
    
    initialized = 1;
    EM_ASM({ console.log('OpenJTalk initialization complete!'); });
    return 0;
}

EMSCRIPTEN_KEEPALIVE
char* openjtalk_synthesis_labels(const char* text) {
    if (!initialized || !text) {
        return strdup("ERROR: Not initialized or null text");
    }
    
    // Debug output
    EM_ASM({ console.log('Synthesizing text:', UTF8ToString($0)); }, text);
    
    char buff[8192];
    text2mecab(buff, text);
    
    Mecab_analysis(mecab, buff);
    mecab2njd(njd, Mecab_get_feature(mecab), Mecab_get_size(mecab));
    
    njd_set_pronunciation(njd);
    njd_set_digit(njd);
    njd_set_accent_phrase(njd);
    njd_set_accent_type(njd);
    njd_set_unvoiced_vowel(njd);
    njd_set_long_vowel(njd);
    
    njd2jpcommon(jpcommon, njd);
    
    // Get labels
    int label_size = JPCommon_get_label_size(jpcommon);
    if (label_size <= 0) {
        return strdup("ERROR: No labels generated");
    }
    
    // Get all labels at once
    char **labels = JPCommon_get_label_feature(jpcommon);
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
    JPCommon_refresh(jpcommon);
    NJD_refresh(njd);
    Mecab_refresh(mecab);
    
    EM_ASM({ console.log('Generated', $0, 'labels'); }, label_size);
    
    return result;
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_clear() {
    if (!initialized) {
        return;
    }
    
    if (engine) {
        HTS_Engine_clear(engine);
        free(engine);
    }
    if (jpcommon) {
        JPCommon_clear(jpcommon);
        free(jpcommon);
    }
    if (njd) {
        NJD_clear(njd);
        free(njd);
    }
    if (mecab) {
        Mecab_clear(mecab);
        free(mecab);
    }
    
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