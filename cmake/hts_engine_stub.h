/* Minimal HTS Engine header for phonemizer-only build */
#ifndef HTS_ENGINE_H
#define HTS_ENGINE_H

#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Version */
#define HTS_ENGINE_VERSION "1.10-stub"

/* Stub structures - complete definitions for compilation */
typedef struct _HTS_Engine {
    void *dummy;  /* Placeholder to ensure non-zero size */
} HTS_Engine;

typedef struct _HTS_ModelSet {
    void *dummy;
} HTS_ModelSet;

typedef struct _HTS_Global {
    void *dummy;
} HTS_Global;

typedef struct _HTS_Audio {
    void *dummy;
} HTS_Audio;

/* Stub functions */
void HTS_Engine_initialize(HTS_Engine *engine);
void HTS_Engine_clear(HTS_Engine *engine);
int HTS_Engine_load(HTS_Engine *engine, char **voices, int num_voices);
int HTS_Engine_synthesize_from_strings(HTS_Engine *engine, char **lines, int num_lines);
void HTS_Engine_refresh(HTS_Engine *engine);
void HTS_Engine_save_information(HTS_Engine *engine, FILE *fp);
void HTS_Engine_save_label(HTS_Engine *engine, FILE *fp);
void HTS_Engine_save_generated_speech(HTS_Engine *engine, FILE *fp);
void HTS_Engine_save_generated_parameter(HTS_Engine *engine, int stream_index, FILE *fp);
void HTS_Engine_save_riff(HTS_Engine *engine, FILE *fp);
double HTS_Engine_get_generated_speech_size(HTS_Engine *engine);
short *HTS_Engine_get_generated_speech(HTS_Engine *engine);

/* Additional functions */
const char *HTS_Engine_get_fullcontext_label_format(HTS_Engine *engine);
void HTS_Engine_set_gv_weight(HTS_Engine *engine, int stream_index, double weight);
void HTS_Engine_set_sampling_frequency(HTS_Engine *engine, int sampling_frequency);
void HTS_Engine_set_fperiod(HTS_Engine *engine, int fperiod);
void HTS_Engine_set_gv_interpolation_weight(HTS_Engine *engine, int stream_index, int stage, double weight);
void HTS_Engine_set_alpha(HTS_Engine *engine, double alpha);
void HTS_Engine_set_beta(HTS_Engine *engine, double beta);
void HTS_Engine_set_speed(HTS_Engine *engine, double speed);
void HTS_Engine_add_half_tone(HTS_Engine *engine, double half_tone);
void HTS_Engine_set_msd_threshold(HTS_Engine *engine, int stream_index, double threshold);
void HTS_Engine_set_duration_interpolation_weight(HTS_Engine *engine, int voice_index, double weight);
void HTS_Engine_set_parameter_interpolation_weight(HTS_Engine *engine, int voice_index, int stream_index, double weight);
void HTS_Engine_set_volume(HTS_Engine *engine, double volume);
void HTS_Engine_set_audio_buff_size(HTS_Engine *engine, int buff_size);

/* Constants */
extern const char *HTS_COPYRIGHT;

#ifdef __cplusplus
}
#endif

#endif /* HTS_ENGINE_H */