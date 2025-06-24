#include "openjtalk_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define access _access
#define F_OK 0
#else
#include <unistd.h>
#endif

#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

// Include OpenJTalk headers - these should be installed by the build process
#include "text2mecab.h"
#include "mecab.h"
#include "njd.h"
#include "jpcommon.h"
#include "njd_set_pronunciation.h"
#include "njd_set_digit.h"
#include "njd_set_accent_phrase.h"
#include "njd_set_accent_type.h"
#include "njd_set_unvoiced_vowel.h"
#include "njd_set_long_vowel.h"
#include "mecab2njd.h"
#include "njd2jpcommon.h"

// Structures to hold OpenJTalk state
struct _OpenJTalk {
    Mecab mecab;
    NJD njd;
    JPCommon jpcommon;
    char* dic_dir;
};

struct _OJ_Label {
    char** labels;
    size_t size;
};

OpenJTalk* openjtalk_initialize() {
    
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    // Initialize structures properly
    Mecab_initialize(&oj->mecab);
    NJD_initialize(&oj->njd);
    JPCommon_initialize(&oj->jpcommon);
    
    // Get dictionary directory from environment, CMake definition, or use default
    const char* dic_dir = getenv("OPENJTALK_DICTIONARY_DIR");
    if (!dic_dir) {
#ifdef OPENJTALK_DICT_DIR
        // Use CMake-defined dictionary path (for build/test)
        dic_dir = OPENJTALK_DICT_DIR;
        fprintf(stderr, "OpenJTalk: Using CMake dictionary dir: %s\n", dic_dir);
#else
        // Try to find dictionary relative to executable for installed version
        static char dict_path[PATH_MAX];
        char exe_path[PATH_MAX];
        exe_path[0] = '\0';
        
#ifdef _WIN32
        DWORD size = GetModuleFileNameA(NULL, exe_path, sizeof(exe_path));
        if (size > 0 && size < sizeof(exe_path)) {
            // Success
        }
#elif defined(__APPLE__)
        uint32_t size = sizeof(exe_path);
        if (_NSGetExecutablePath(exe_path, &size) == 0) {
            // Success
        }
#elif defined(__linux__)
        ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
        if (len > 0) {
            exe_path[len] = '\0';
        }
#endif
        
        if (exe_path[0] != '\0') {
            // Remove executable name to get directory
#ifdef _WIN32
            char* last_slash = strrchr(exe_path, '\\');
            if (!last_slash) last_slash = strrchr(exe_path, '/');
#else
            char* last_slash = strrchr(exe_path, '/');
#endif
            if (last_slash) {
                *last_slash = '\0';
                // Try ../share/piper/openjtalk-dict (installed location)
#ifdef _WIN32
                snprintf(dict_path, sizeof(dict_path), "%s\\..\\share\\piper\\openjtalk-dict", exe_path);
#else
                snprintf(dict_path, sizeof(dict_path), "%s/../share/piper/openjtalk-dict", exe_path);
#endif
                if (access(dict_path, F_OK) == 0) {
                    dic_dir = dict_path;
                } else {
                    // Try share/piper/openjtalk-dict (in same directory as executable)
#ifdef _WIN32
                    snprintf(dict_path, sizeof(dict_path), "%s\\share\\piper\\openjtalk-dict", exe_path);
#else
                    snprintf(dict_path, sizeof(dict_path), "%s/share/piper/openjtalk-dict", exe_path);
#endif
                    if (access(dict_path, F_OK) == 0) {
                        dic_dir = dict_path;
                    } else {
                        // Try build/naist-jdic (build directory)
#ifdef _WIN32
                        snprintf(dict_path, sizeof(dict_path), "%s\\..\\build\\naist-jdic", exe_path);
#else
                        snprintf(dict_path, sizeof(dict_path), "%s/../build/naist-jdic", exe_path);
#endif
                        if (access(dict_path, F_OK) == 0) {
                            dic_dir = dict_path;
                        } else {
                            // Fallback to current directory
                            dic_dir = "naist-jdic";
                        }
                    }
                }
            }
        } else {
            // Fallback if we can't determine exe path
            dic_dir = "naist-jdic";
        }
#endif
    }
    
    oj->dic_dir = strdup(dic_dir);
    
    // Initialize MeCab with dictionary
    if (Mecab_load(&oj->mecab, dic_dir) != TRUE) {
        fprintf(stderr, "OpenJTalk: Failed to initialize MeCab with dictionary: %s\n", dic_dir);
        openjtalk_finalize(oj);
        return NULL;
    }
    
    fprintf(stderr, "OpenJTalk: Initialized with dictionary: %s\n", dic_dir);
    
    // Debug: Check if dictionary files actually exist
    char dict_file[1024];
    snprintf(dict_file, sizeof(dict_file), "%s/sys.dic", dic_dir);
    if (access(dict_file, F_OK) != 0) {
        fprintf(stderr, "OpenJTalk: WARNING - Dictionary file not found: %s\n", dict_file);
    }
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    // Clear structures
    Mecab_clear(&oj->mecab);
    NJD_clear(&oj->njd);
    JPCommon_clear(&oj->jpcommon);
    
    if (oj->dic_dir) {
        free(oj->dic_dir);
    }
    
    free(oj);
}

OJ_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text) {
        fprintf(stderr, "OpenJTalk: Invalid parameters - oj=%p, text=%p\n", 
                (void*)oj, (void*)text);
        return NULL;
    }
    
    fprintf(stderr, "OpenJTalk: Processing text: %s\n", text);
    
    // Clear previous data
    NJD_refresh(&oj->njd);
    JPCommon_refresh(&oj->jpcommon);
    
    // Convert text to MeCab format
    char buff[8192];
    text2mecab(buff, text);
    fprintf(stderr, "OpenJTalk: MeCab format: %s\n", buff);
    
    // Analyze text with MeCab  
    if (Mecab_analysis(&oj->mecab, buff) != TRUE) {
        fprintf(stderr, "OpenJTalk: MeCab analysis failed\n");
        return NULL;
    }
    
    // Process through NJD pipeline
    fprintf(stderr, "OpenJTalk: Processing NJD pipeline...\n");
    
    // Convert MeCab result to NJD
    mecab2njd(&oj->njd, Mecab_get_feature(&oj->mecab), 
              Mecab_get_size(&oj->mecab));
    fprintf(stderr, "OpenJTalk: mecab2njd done\n");
    
    // Apply NJD processing
    njd_set_pronunciation(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_pronunciation done\n");
    njd_set_digit(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_digit done\n");
    njd_set_accent_phrase(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_accent_phrase done\n");
    njd_set_accent_type(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_accent_type done\n");
    njd_set_unvoiced_vowel(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_unvoiced_vowel done\n");
    njd_set_long_vowel(&oj->njd);
    fprintf(stderr, "OpenJTalk: njd_set_long_vowel done\n");
    
    // Convert to JPCommon
    njd2jpcommon(&oj->jpcommon, &oj->njd);
    fprintf(stderr, "OpenJTalk: njd2jpcommon done\n");
    
    // Generate labels
    JPCommon_make_label(&oj->jpcommon);
    fprintf(stderr, "OpenJTalk: JPCommon_make_label done\n");
    
    // Get labels
    int label_size = JPCommon_get_label_size(&oj->jpcommon);
    char** label_features = JPCommon_get_label_feature(&oj->jpcommon);
    
    fprintf(stderr, "OpenJTalk: Generated %d labels\n", label_size);
    
    if (label_size <= 0 || !label_features) {
        fprintf(stderr, "OpenJTalk: No labels generated (size=%d, features=%p)\n", 
                label_size, (void*)label_features);
        return NULL;
    }
    
    // Debug: Print first few labels
    for (int i = 0; i < label_size && i < 5; i++) {
        if (label_features[i]) {
            fprintf(stderr, "OpenJTalk: Label[%d]: %s\n", i, label_features[i]);
        }
    }
    
    // Create OJ_Label structure
    OJ_Label* label = (OJ_Label*)malloc(sizeof(OJ_Label));
    if (!label) return NULL;
    
    label->size = label_size;
    label->labels = (char**)malloc(sizeof(char*) * label_size);
    if (!label->labels) {
        free(label);
        return NULL;
    }
    
    // Copy labels
    for (int i = 0; i < label_size; i++) {
        if (label_features[i]) {
            label->labels[i] = strdup(label_features[i]);
        } else {
            label->labels[i] = NULL;
        }
    }
    
    return label;
}

size_t OJ_Label_get_size(OJ_Label* label) {
    if (!label) return 0;
    return label->size;
}

const char* OJ_Label_get_string(OJ_Label* label, size_t index) {
    if (!label || !label->labels || index >= label->size) return NULL;
    return label->labels[index];
}

void OJ_Label_clear(OJ_Label* label) {
    if (!label) return;
    
    if (label->labels) {
        for (size_t i = 0; i < label->size; i++) {
            if (label->labels[i]) free(label->labels[i]);
        }
        free(label->labels);
    }
    
    free(label);
}