#include <emscripten.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Forward declarations for Open JTalk functions
typedef struct _Mecab Mecab;
typedef struct _NJD NJD;
typedef struct _JPCommon JPCommon;
typedef struct _HTS_Engine HTS_Engine;

// Function declarations
void Mecab_initialize(Mecab *m);
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
char* JPCommon_get_label_feature(JPCommon *jpcommon, int index);

void HTS_Engine_initialize(HTS_Engine *engine);
int HTS_Engine_load(HTS_Engine *engine, char **voices, int num_voices);
void HTS_Engine_refresh(HTS_Engine *engine);
void HTS_Engine_clear(HTS_Engine *engine);

void text2mecab(char *output, const char *input);
void mecab2njd(NJD *njd, char **features, int size);
void njd_set_pronunciation(NJD *njd);
void njd_set_digit(NJD *njd);
void njd_set_accent_phrase(NJD *njd);
void njd_set_accent_type(NJD *njd);
void njd_set_unvoiced_vowel(NJD *njd);
void njd_set_long_vowel(NJD *njd);
void njd2jpcommon(JPCommon *jpcommon, NJD *njd);

// Static instances (allocate proper size)
static char mecab_buf[8192];
static char njd_buf[8192];
static char jpcommon_buf[8192];
static char engine_buf[65536];
static int initialized = 0;

#define TRUE 1
#define FALSE 0

EMSCRIPTEN_KEEPALIVE
int openjtalk_initialize(const char* dic_dir, const char* voice_path) {
    if (initialized) {
        return 0;
    }
    
    Mecab *mecab = (Mecab*)mecab_buf;
    NJD *njd = (NJD*)njd_buf;
    JPCommon *jpcommon = (JPCommon*)jpcommon_buf;
    HTS_Engine *engine = (HTS_Engine*)engine_buf;
    
    // Initialize components
    Mecab_initialize(mecab);
    if (Mecab_load(mecab, dic_dir) != TRUE) {
        return -1;
    }
    
    NJD_initialize(njd);
    JPCommon_initialize(jpcommon);
    HTS_Engine_initialize(engine);
    
    char *voices[1] = {(char*)voice_path};
    if (HTS_Engine_load(engine, voices, 1) != TRUE) {
        return -2;
    }
    
    initialized = 1;
    return 0;
}

EMSCRIPTEN_KEEPALIVE
char* openjtalk_synthesis_labels(const char* text) {
    if (!initialized) {
        return strdup("ERROR: Not initialized");
    }
    
    Mecab *mecab = (Mecab*)mecab_buf;
    NJD *njd = (NJD*)njd_buf;
    JPCommon *jpcommon = (JPCommon*)jpcommon_buf;
    
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
    int total_len = 0;
    int i;
    
    // Calculate total length needed
    for (i = 0; i < label_size; i++) {
        char* label = JPCommon_get_label_feature(jpcommon, i);
        if (label) {
            total_len += strlen(label) + 1;
        }
    }
    
    // Allocate result buffer
    char* result = (char*)malloc(total_len + 1);
    result[0] = '\0';
    
    // Build result
    for (i = 0; i < label_size; i++) {
        char* label = JPCommon_get_label_feature(jpcommon, i);
        if (label) {
            strcat(result, label);
            strcat(result, "\n");
        }
    }
    
    // Clean up
    JPCommon_refresh(jpcommon);
    NJD_refresh(njd);
    Mecab_refresh(mecab);
    
    return result;
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_clear() {
    if (!initialized) {
        return;
    }
    
    HTS_Engine *engine = (HTS_Engine*)engine_buf;
    JPCommon *jpcommon = (JPCommon*)jpcommon_buf;
    NJD *njd = (NJD*)njd_buf;
    Mecab *mecab = (Mecab*)mecab_buf;
    
    HTS_Engine_clear(engine);
    JPCommon_clear(jpcommon);
    NJD_clear(njd);
    Mecab_clear(mecab);
    
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
    return "OpenJTalk WebAssembly 1.0.0";
}

EMSCRIPTEN_KEEPALIVE
int test_function(int a, int b) {
    return a + b;
}
