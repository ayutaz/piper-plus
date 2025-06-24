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

// OpenJTalk implementation using static linking
// This avoids the need for internal headers at compile time

// For static linking, declare the external functions
extern void text2mecab(char*, const char*);
extern void* mecab_new2(const char*, const char*);
extern const char* mecab_sparse_tostr(void*, const char*);
extern void mecab_destroy(void*);
extern void mecab2njd(void*, const char*, int);
extern void njd_set_pronunciation(void*);
extern void njd_set_digit(void*);
extern void njd_set_accent_phrase(void*);
extern void njd_set_accent_type(void*);
extern void njd_set_unvoiced_vowel(void*);
extern void njd_set_long_vowel(void*);
extern void njd2jpcommon(void*, void*);
extern void JPCommon_make_label(void*);
extern int JPCommon_get_label_size(void*);
extern char** JPCommon_get_label_feature(void*);
extern void NJD_initialize(void*);
extern void NJD_clear(void*);
extern void JPCommon_initialize(void*);
extern void JPCommon_clear(void*);
extern void JPCommon_refresh(void*);
extern void NJD_refresh(void*);

// Structures to hold OpenJTalk state
struct _OpenJTalk {
    void* mecab;
    void* njd;
    void* jpcommon;
    char* dic_dir;
};

struct _OJ_Label {
    char** labels;
    size_t size;
};


// Helper to allocate structures with proper size
// We allocate larger buffers to accommodate the actual struct sizes
static void* alloc_njd() {
    // NJD structure is relatively large, allocate enough space
    return calloc(1, 4096);
}

static void* alloc_jpcommon() {
    // JPCommon structure, allocate enough space
    return calloc(1, 2048);
}

OpenJTalk* openjtalk_initialize() {
    
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    // Initialize NJD and JPCommon structures
    oj->njd = alloc_njd();
    oj->jpcommon = alloc_jpcommon();
    
    if (!oj->njd || !oj->jpcommon) {
        if (oj->njd) free(oj->njd);
        if (oj->jpcommon) free(oj->jpcommon);
        free(oj);
        return NULL;
    }
    
    // Initialize structures
    NJD_initialize(oj->njd);
    JPCommon_initialize(oj->jpcommon);
    
    // Get dictionary directory from environment, CMake definition, or use default
    const char* dic_dir = getenv("OPENJTALK_DICTIONARY_DIR");
    if (!dic_dir) {
#ifdef OPENJTALK_DICT_DIR
        // Use CMake-defined dictionary path (for build/test)
        dic_dir = OPENJTALK_DICT_DIR;
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
    char mecab_options[1024];
    snprintf(mecab_options, sizeof(mecab_options), "-d %s", dic_dir);
    
    oj->mecab = mecab_new2(mecab_options, "");
    
    if (!oj->mecab) {
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
    
    if (oj->mecab) {
        mecab_destroy(oj->mecab);
    }
    
    if (oj->njd) {
        NJD_clear(oj->njd);
        free(oj->njd);
    }
    
    if (oj->jpcommon) {
        JPCommon_clear(oj->jpcommon);
        free(oj->jpcommon);
    }
    
    if (oj->dic_dir) {
        free(oj->dic_dir);
    }
    
    free(oj);
}

OJ_Label* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text || !oj->mecab) return NULL;
    
    // Clear previous data
    NJD_refresh(oj->njd);
    JPCommon_refresh(oj->jpcommon);
    
    // Convert text to MeCab format
    char buff[8192];
    text2mecab(buff, text);
    
    // Parse with MeCab
    const char* mecab_output = mecab_sparse_tostr(oj->mecab, buff);
    
    if (!mecab_output) {
        fprintf(stderr, "OpenJTalk: MeCab parsing failed\n");
        return NULL;
    }
    
    // Process through NJD pipeline
    mecab2njd(oj->njd, mecab_output, strlen(mecab_output));
    njd_set_pronunciation(oj->njd);
    njd_set_digit(oj->njd);
    njd_set_accent_phrase(oj->njd);
    njd_set_accent_type(oj->njd);
    njd_set_unvoiced_vowel(oj->njd);
    njd_set_long_vowel(oj->njd);
    njd2jpcommon(oj->jpcommon, oj->njd);
    JPCommon_make_label(oj->jpcommon);
    
    // Get labels
    int label_size = JPCommon_get_label_size(oj->jpcommon);
    char** label_features = JPCommon_get_label_feature(oj->jpcommon);
    
    if (label_size <= 0 || !label_features) {
        fprintf(stderr, "OpenJTalk: No labels generated\n");
        return NULL;
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