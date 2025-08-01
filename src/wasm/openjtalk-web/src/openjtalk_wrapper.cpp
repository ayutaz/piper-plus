#include <emscripten.h>
#include <string>
#include <cstring>
#include <cstdlib>
#include <vector>

// OpenJTalk headers - minimal includes to reduce conflicts
extern "C" {

// Forward declarations to avoid header conflicts
typedef struct _Mecab {
    void *feature;
    int size;
    void *model;
    void *lattice;
    void *mecab;
} Mecab;

typedef struct _NJD {
    void *head;
    void *tail;
} NJD;

typedef struct _JPCommon {
    void *label;
    int label_size;
} JPCommon;

typedef struct _HTS_Engine {
    void *internal;
} HTS_Engine;

// Function declarations - these should match the actual OpenJTalk functions
int Mecab_initialize(Mecab *m);
int Mecab_load(Mecab *m, const char *dicdir);
int Mecab_analysis(Mecab *m, const char *str);
int Mecab_get_size(Mecab *m);
char** Mecab_get_feature(Mecab *m);
int Mecab_refresh(Mecab *m);
int Mecab_clear(Mecab *m);

void NJD_initialize(NJD *njd);
void NJD_refresh(NJD *njd);
void NJD_clear(NJD *njd);

void JPCommon_initialize(JPCommon *jpcommon);
void JPCommon_refresh(JPCommon *jpcommon);
void JPCommon_clear(JPCommon *jpcommon);
int JPCommon_get_label_size(JPCommon *jpcommon);
char* JPCommon_get_label_feature(JPCommon *jpcommon, int i);

void HTS_Engine_initialize(HTS_Engine *engine);
int HTS_Engine_load(HTS_Engine *engine, char **voices, int num_voices);
void HTS_Engine_refresh(HTS_Engine *engine);
void HTS_Engine_clear(HTS_Engine *engine);

// Text processing functions
void text2mecab(char *output, const char *input);
void mecab2njd(NJD *njd, char **features, int size);
void njd_set_pronunciation(NJD *njd);
void njd_set_digit(NJD *njd);
void njd_set_accent_phrase(NJD *njd);
void njd_set_accent_type(NJD *njd);
void njd_set_unvoiced_vowel(NJD *njd);
void njd_set_long_vowel(NJD *njd);
void njd2jpcommon(JPCommon *jpcommon, NJD *njd);

// Global instances
static Mecab mecab;
static NJD njd;
static JPCommon jpcommon;
static HTS_Engine engine;
static bool initialized = false;

EMSCRIPTEN_KEEPALIVE
int openjtalk_initialize(const char* dic_dir, const char* voice_path) {
    if (initialized) {
        return 0;
    }
    
    // Initialize MeCab
    Mecab_initialize(&mecab);
    if (!Mecab_load(&mecab, dic_dir)) {
        Mecab_clear(&mecab);
        return -1;
    }
    
    // Initialize NJD
    NJD_initialize(&njd);
    
    // Initialize JPCommon
    JPCommon_initialize(&jpcommon);
    
    // Initialize HTS Engine
    HTS_Engine_initialize(&engine);
    
    // Load voice
    char *voices[1];
    voices[0] = const_cast<char*>(voice_path);
    if (!HTS_Engine_load(&engine, voices, 1)) {
        HTS_Engine_clear(&engine);
        JPCommon_clear(&jpcommon);
        NJD_clear(&njd);
        Mecab_clear(&mecab);
        return -2;
    }
    
    initialized = true;
    return 0;
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_clear() {
    if (!initialized) {
        return;
    }
    
    HTS_Engine_clear(&engine);
    JPCommon_clear(&jpcommon);
    NJD_clear(&njd);
    Mecab_clear(&mecab);
    
    initialized = false;
}

EMSCRIPTEN_KEEPALIVE
char* openjtalk_synthesis_labels(const char* text) {
    if (!initialized) {
        return strdup("ERROR: Not initialized");
    }
    
    char buff[8192];
    text2mecab(buff, text);
    
    Mecab_analysis(&mecab, buff);
    mecab2njd(&njd, Mecab_get_feature(&mecab), Mecab_get_size(&mecab));
    
    njd_set_pronunciation(&njd);
    njd_set_digit(&njd);
    njd_set_accent_phrase(&njd);
    njd_set_accent_type(&njd);
    njd_set_unvoiced_vowel(&njd);
    njd_set_long_vowel(&njd);
    
    njd2jpcommon(&jpcommon, &njd);
    
    // Get labels
    int label_size = JPCommon_get_label_size(&jpcommon);
    std::string result;
    
    for (int i = 0; i < label_size; i++) {
        char* label = JPCommon_get_label_feature(&jpcommon, i);
        if (label) {
            result += label;
            result += "\n";
        }
    }
    
    // Clear for next use
    JPCommon_refresh(&jpcommon);
    NJD_refresh(&njd);
    Mecab_refresh(&mecab);
    
    return strdup(result.c_str());
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_free_string(char* str) {
    if (str) {
        free(str);
    }
}

} // extern "C"