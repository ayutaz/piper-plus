#include "openjtalk_wrapper.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <libgen.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#ifdef __linux__
#include <unistd.h>
#endif

// Include the individual OpenJTalk component headers
#ifdef OPENJTALK_DICTIONARY_DIR
#include "text2mecab.h"
#include "mecab.h"
#include "njd.h"  
#include "jpcommon.h"
#include "mecab2njd.h"
#include "njd2jpcommon.h"
#include "njd_set_pronunciation.h"
#include "njd_set_digit.h"
#include "njd_set_accent_phrase.h"
#include "njd_set_accent_type.h"
#include "njd_set_long_vowel.h"
#include "njd_set_unvoiced_vowel.h"
#endif

// Internal OpenJTalk structure with actual components
#ifdef OPENJTALK_DICTIONARY_DIR
typedef struct {
    Mecab mecab;
    NJD njd;
    JPCommon jpcommon;
    int initialized;
} OpenJTalk_Internal;
#endif

// Internal HTS Label structure
typedef struct {
    JPCommon* jpcommon;
    int size;
} HTS_Label_Internal;

OpenJTalk* openjtalk_initialize() {
#ifdef OPENJTALK_DICTIONARY_DIR
    OpenJTalk_Internal* oj = (OpenJTalk_Internal*)malloc(sizeof(OpenJTalk_Internal));
    if (!oj) return NULL;
    
    oj->initialized = 0;
    
    // Initialize MeCab
    Mecab_initialize(&oj->mecab);
    
    // Try to load MeCab dictionary from multiple locations
    const char* dic_dir = getenv("OPENJTALK_DICTIONARY_DIR");
    int loaded = 0;
    
    // Try environment variable first
    if (dic_dir) {
        if (Mecab_load(&oj->mecab, dic_dir)) {
            loaded = 1;
        }
    }
    
    // Try relative to the binary (../share/naist-jdic)
    if (!loaded) {
        char path[PATH_MAX];
        #ifdef __linux__
            ssize_t len = readlink("/proc/self/exe", path, sizeof(path) - 1);
            if (len != -1) {
                path[len] = '\0';
                char* path_copy = strdup(path);
                char* dir = dirname(path_copy);
                snprintf(path, sizeof(path), "%s/../share/naist-jdic", dir);
                if (Mecab_load(&oj->mecab, path)) {
                    loaded = 1;
                }
                free(path_copy);
            }
        #elif defined(__APPLE__)
            uint32_t size = sizeof(path);
            if (_NSGetExecutablePath(path, &size) == 0) {
                char* path_copy = strdup(path);
                char* dir = dirname(path_copy);
                snprintf(path, sizeof(path), "%s/../share/naist-jdic", dir);
                if (Mecab_load(&oj->mecab, path)) {
                    loaded = 1;
                }
                free(path_copy);
            }
        #endif
    }
    
    // Try compile-time default
    if (!loaded) {
        if (Mecab_load(&oj->mecab, OPENJTALK_DICTIONARY_DIR)) {
            loaded = 1;
        }
    }
    
    if (!loaded) {
        fprintf(stderr, "Failed to load MeCab dictionary from any known location\n");
        if (dic_dir) fprintf(stderr, "  Tried: %s\n", dic_dir);
        fprintf(stderr, "  Tried: ../share/naist-jdic (relative to binary)\n");
        fprintf(stderr, "  Tried: %s\n", OPENJTALK_DICTIONARY_DIR);
        free(oj);
        return NULL;
    }
    
    // Initialize NJD
    NJD_initialize(&oj->njd);
    
    // Initialize JPCommon
    JPCommon_initialize(&oj->jpcommon);
    
    oj->initialized = 1;
    return (OpenJTalk*)oj;
#else
    // Stub implementation when OpenJTalk is not available
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    oj->initialized = 0;
    return oj;
#endif
}

void openjtalk_finalize(OpenJTalk* oj_public) {
    if (!oj_public) return;
    
#ifdef OPENJTALK_DICTIONARY_DIR
    OpenJTalk_Internal* oj = (OpenJTalk_Internal*)oj_public;
    
    if (oj->initialized) {
        JPCommon_clear(&oj->jpcommon);
        NJD_clear(&oj->njd);
        Mecab_clear(&oj->mecab);
    }
#endif
    
    free(oj_public);
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj_public, const char* text) {
    if (!oj_public || !text) return NULL;
    
#ifdef OPENJTALK_DICTIONARY_DIR
    OpenJTalk_Internal* oj = (OpenJTalk_Internal*)oj_public;
    if (!oj->initialized) return NULL;
    
    // Allocate buffer for MeCab output (estimate size)
    size_t text_len = strlen(text);
    size_t buffer_size = text_len * 10; // Generous estimate for MeCab output
    char* mecab_output = (char*)malloc(buffer_size);
    if (!mecab_output) return NULL;
    
    // Convert text to MeCab format
    text2mecab(mecab_output, text);
    
    // Clear previous analysis
    NJD_clear(&oj->njd);
    NJD_initialize(&oj->njd);
    
    // Analyze with MeCab
    Mecab_analysis(&oj->mecab, mecab_output);
    
    // Convert MeCab output to NJD
    mecab2njd(&oj->njd, Mecab_get_feature(&oj->mecab), Mecab_get_size(&oj->mecab));
    
    // Process through NJD stages
    njd_set_pronunciation(&oj->njd);
    njd_set_digit(&oj->njd);
    njd_set_accent_phrase(&oj->njd);
    njd_set_accent_type(&oj->njd);
    njd_set_unvoiced_vowel(&oj->njd);
    njd_set_long_vowel(&oj->njd);
    
    // Clear previous JPCommon analysis
    JPCommon_refresh(&oj->jpcommon);
    
    // Convert to JPCommon
    njd2jpcommon(&oj->jpcommon, &oj->njd);
    
    // Make full-context labels
    JPCommon_make_label(&oj->jpcommon);
    
    // Create HTS_Label wrapper
    HTS_Label_Internal* label = (HTS_Label_Internal*)malloc(sizeof(HTS_Label_Internal));
    if (!label) {
        free(mecab_output);
        return NULL;
    }
    
    label->jpcommon = &oj->jpcommon;
    label->size = JPCommon_get_label_size(&oj->jpcommon);
    
    free(mecab_output);
    return (HTS_Label_Wrapper*)label;
#else
    // Return NULL to trigger fallback to codepoints
    return NULL;
#endif
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label_public) {
    if (!label_public) return 0;
#ifdef OPENJTALK_DICTIONARY_DIR
    HTS_Label_Internal* label = (HTS_Label_Internal*)label_public;
    return label->size;
#else
    return 0;
#endif
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label_public, size_t index) {
    if (!label_public) return NULL;
#ifdef OPENJTALK_DICTIONARY_DIR
    HTS_Label_Internal* label = (HTS_Label_Internal*)label_public;
    
    if (!label->jpcommon || index >= label->size) return NULL;
    
    char** features = JPCommon_get_label_feature(label->jpcommon);
    if (!features) return NULL;
    
    return features[index];
#else
    return NULL;
#endif
}

void HTS_Label_clear(HTS_Label_Wrapper* label_public) {
    if (!label_public) return;
    // JPCommon cleanup is handled by openjtalk_finalize
    // Don't free the JPCommon here as it's owned by OpenJTalk
    free(label_public);
}