/* Minimal HTS Engine stub for phonemizer-only build */

#include <stdio.h>
#include <stdlib.h>
#include "HTS_engine.h"

/* Stub structures - need complete definitions for linking */
struct _HTS_Engine {
    void *dummy;
};

typedef struct _HTS_ModelSet {
    void *dummy;
} HTS_ModelSet;

typedef struct _HTS_Global {
    void *dummy;
} HTS_Global;

typedef struct _HTS_Audio {
    void *dummy;
} HTS_Audio;

/* Stub functions that should never be called */
void HTS_Engine_initialize(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_initialize called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_clear(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_clear called in phonemizer-only mode\n");
    exit(1);
}

int HTS_Engine_load(HTS_Engine *engine, char **voices, int num_voices) {
    fprintf(stderr, "ERROR: HTS_Engine_load called in phonemizer-only mode\n");
    exit(1);
}

int HTS_Engine_synthesize_from_strings(HTS_Engine *engine, char **lines, int num_lines) {
    fprintf(stderr, "ERROR: HTS_Engine_synthesize_from_strings called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_refresh(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_refresh called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_save_information(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_information called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_save_label(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_label called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_save_generated_speech(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_generated_speech called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_save_generated_parameter(HTS_Engine *engine, int stream_index, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_generated_parameter called in phonemizer-only mode\n");
    exit(1);
}

void HTS_Engine_save_riff(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_riff called in phonemizer-only mode\n");
    exit(1);
}

double HTS_Engine_get_generated_speech_size(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_get_generated_speech_size called in phonemizer-only mode\n");
    exit(1);
}

short *HTS_Engine_get_generated_speech(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_get_generated_speech called in phonemizer-only mode\n");
    exit(1);
}

/* Constants */
const char *HTS_COPYRIGHT = "HTS Engine stub - not for synthesis";