/* Minimal HTS Engine stub for phonemizer-only build */

#include <stdio.h>
#include "HTS_engine.h"

/* Stub structures are already defined in HTS_engine.h */

/* Stub functions that should never be called */
void HTS_Engine_initialize(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_initialize called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_clear(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_clear called in phonemizer-only mode\n");
    return;
}

int HTS_Engine_load(HTS_Engine *engine, char **voices, int num_voices) {
    fprintf(stderr, "ERROR: HTS_Engine_load called in phonemizer-only mode\n");
    return 0;
}

int HTS_Engine_synthesize_from_strings(HTS_Engine *engine, char **lines, int num_lines) {
    fprintf(stderr, "ERROR: HTS_Engine_synthesize_from_strings called in phonemizer-only mode\n");
    return 0;
}

void HTS_Engine_refresh(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_refresh called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_save_information(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_information called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_save_label(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_label called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_save_generated_speech(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_generated_speech called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_save_generated_parameter(HTS_Engine *engine, int stream_index, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_generated_parameter called in phonemizer-only mode\n");
    return;
}

void HTS_Engine_save_riff(HTS_Engine *engine, FILE *fp) {
    fprintf(stderr, "ERROR: HTS_Engine_save_riff called in phonemizer-only mode\n");
    return;
}

double HTS_Engine_get_generated_speech_size(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_get_generated_speech_size called in phonemizer-only mode\n");
    return 0.0;
}

short *HTS_Engine_get_generated_speech(HTS_Engine *engine) {
    fprintf(stderr, "ERROR: HTS_Engine_get_generated_speech called in phonemizer-only mode\n");
    return NULL;
}

/* Additional functions required by OpenJTalk */
const char *HTS_Engine_get_fullcontext_label_format(HTS_Engine *engine) {
    (void)engine;
    return "HTS_TTS_JPN";
}

void HTS_Engine_set_gv_weight(HTS_Engine *engine, int stream_index, double weight) {
    (void)engine;
    (void)stream_index;
    (void)weight;
}

void HTS_Engine_set_sampling_frequency(HTS_Engine *engine, int sampling_frequency) {
    (void)engine;
    (void)sampling_frequency;
}

void HTS_Engine_set_fperiod(HTS_Engine *engine, int fperiod) {
    (void)engine;
    (void)fperiod;
}

void HTS_Engine_set_gv_interpolation_weight(HTS_Engine *engine, int stream_index, int stage, double weight) {
    (void)engine;
    (void)stream_index;
    (void)stage;
    (void)weight;
}

void HTS_Engine_set_alpha(HTS_Engine *engine, double alpha) {
    (void)engine;
    (void)alpha;
}

void HTS_Engine_set_beta(HTS_Engine *engine, double beta) {
    (void)engine;
    (void)beta;
}

void HTS_Engine_set_speed(HTS_Engine *engine, double speed) {
    (void)engine;
    (void)speed;
}

void HTS_Engine_add_half_tone(HTS_Engine *engine, double half_tone) {
    (void)engine;
    (void)half_tone;
}

void HTS_Engine_set_msd_threshold(HTS_Engine *engine, int stream_index, double threshold) {
    (void)engine;
    (void)stream_index;
    (void)threshold;
}

void HTS_Engine_set_duration_interpolation_weight(HTS_Engine *engine, int voice_index, double weight) {
    (void)engine;
    (void)voice_index;
    (void)weight;
}

void HTS_Engine_set_parameter_interpolation_weight(HTS_Engine *engine, int voice_index, int stream_index, double weight) {
    (void)engine;
    (void)voice_index;
    (void)stream_index;
    (void)weight;
}

void HTS_Engine_set_volume(HTS_Engine *engine, double volume) {
    (void)engine;
    (void)volume;
}

void HTS_Engine_set_audio_buff_size(HTS_Engine *engine, int buff_size) {
    (void)engine;
    (void)buff_size;
}

/* Constants */
const char *HTS_COPYRIGHT = "HTS Engine stub - not for synthesis";