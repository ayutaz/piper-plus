#include "openjtalk_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Include the individual OpenJTalk component headers
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

#include <unistd.h>
#include <limits.h>
#ifdef _WIN32
#include <windows.h>
#endif

// Get dictionary path from compile definition
#ifndef OPENJTALK_DICT_DIR
#define OPENJTALK_DICT_DIR "openjtalk-dict"
#endif

// MeCab functions
extern int Mecab_load(Mecab *m, const char *dic_dir);

// Helper function to find dictionary
static char* find_openjtalk_dict() {
    static char dict_path[PATH_MAX];
    char exe_path[PATH_MAX];
    char test_path[PATH_MAX];
    
    // Try environment variable first
    const char* env_dict = getenv("OPENJTALK_DICT_DIR");
    if (env_dict && access(env_dict, R_OK) == 0) {
        strncpy(dict_path, env_dict, PATH_MAX - 1);
        return dict_path;
    }
    
    // Get executable directory
#ifdef _WIN32
    GetModuleFileNameA(NULL, exe_path, PATH_MAX);
    char* last_slash = strrchr(exe_path, '\\');
    if (last_slash) *last_slash = '\0';
#else
    ssize_t len = readlink("/proc/self/exe", exe_path, PATH_MAX - 1);
    if (len > 0) {
        exe_path[len] = '\0';
        char* last_slash = strrchr(exe_path, '/');
        if (last_slash) *last_slash = '\0';
    } else {
        exe_path[0] = '\0';
    }
#endif
    
    // Try relative paths from executable
    const char* relative_paths[] = {
        "/../share/piper/openjtalk-dict",
        "/../share/openjtalk-dict",
        "/../../share/piper/openjtalk-dict",
        "/../" OPENJTALK_DICT_DIR,
        "/" OPENJTALK_DICT_DIR,
        NULL
    };
    
    for (const char** rel_path = relative_paths; *rel_path; rel_path++) {
        snprintf(test_path, PATH_MAX, "%s%s", exe_path, *rel_path);
        if (access(test_path, R_OK) == 0) {
            strncpy(dict_path, test_path, PATH_MAX - 1);
            return dict_path;
        }
    }
    
    // Try system paths
    const char* system_paths[] = {
        "/usr/share/piper/openjtalk-dict",
        "/usr/local/share/piper/openjtalk-dict",
        "/usr/share/openjtalk/dic/utf-8",
        OPENJTALK_DICT_DIR,  // Compile-time fallback
        NULL
    };
    
    for (const char** sys_path = system_paths; *sys_path; sys_path++) {
        if (access(*sys_path, R_OK) == 0) {
            strncpy(dict_path, *sys_path, PATH_MAX - 1);
            return dict_path;
        }
    }
    
    // Return compile-time default as last resort
    strncpy(dict_path, OPENJTALK_DICT_DIR, PATH_MAX - 1);
    return dict_path;
}

// OpenJTalk wrapper structure
struct _OpenJTalk {
    Mecab mecab;
    NJD njd;
    JPCommon jpcommon;
    int initialized;
};

// HTS Label wrapper structure that holds JPCommon labels
struct _HTS_Label {
    JPCommon* jpcommon;
    int size;
};

OpenJTalk* openjtalk_initialize() {
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    oj->initialized = 0;
    
    // Initialize MeCab
    Mecab_initialize(&oj->mecab);
    
    // Find and load MeCab dictionary
    char* dict_path = find_openjtalk_dict();
    if (!Mecab_load(&oj->mecab, dict_path)) {
        fprintf(stderr, "Failed to load MeCab dictionary from: %s\n", dict_path);
        fprintf(stderr, "Searched paths:\n");
        fprintf(stderr, "  - $OPENJTALK_DICT_DIR (env var)\n");
        fprintf(stderr, "  - Relative to executable\n");
        fprintf(stderr, "  - System directories\n");
        fprintf(stderr, "To fix: Set OPENJTALK_DICT_DIR environment variable or install dictionary\n");
        // Clean up and return NULL
        Mecab_clear(&oj->mecab);
        free(oj);
        return NULL;
    }
    fprintf(stderr, "Loaded OpenJTalk dictionary from: %s\n", dict_path);
    
    // Initialize NJD
    NJD_initialize(&oj->njd);
    
    // Initialize JPCommon
    JPCommon_initialize(&oj->jpcommon);
    
    oj->initialized = 1;
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    if (oj->initialized) {
        JPCommon_clear(&oj->jpcommon);
        NJD_clear(&oj->njd);
        Mecab_clear(&oj->mecab);
    }
    
    free(oj);
}

HTS_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !oj->initialized || !text) return NULL;
    
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
    HTS_Label* label = (HTS_Label*)malloc(sizeof(HTS_Label));
    if (!label) {
        free(mecab_output);
        return NULL;
    }
    
    label->jpcommon = &oj->jpcommon;
    label->size = JPCommon_get_label_size(&oj->jpcommon);
    
    free(mecab_output);
    return label;
}

size_t HTS_Label_get_size(HTS_Label* label) {
    if (!label) return 0;
    return label->size;
}

const char* HTS_Label_get_string(HTS_Label* label, size_t index) {
    if (!label || !label->jpcommon || index >= label->size) return NULL;
    
    char** features = JPCommon_get_label_feature(label->jpcommon);
    if (!features) return NULL;
    
    return features[index];
}

void HTS_Label_clear(HTS_Label* label) {
    if (!label) return;
    // JPCommon cleanup is handled by openjtalk_finalize
    // Don't free the JPCommon here as it's owned by OpenJTalk
    free(label);
}