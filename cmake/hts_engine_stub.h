/* Minimal HTS Engine header for phonemizer-only build */
#ifndef HTS_ENGINE_H
#define HTS_ENGINE_H

#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Version */
#define HTS_ENGINE_VERSION "1.10"

/* Stub structures */
typedef struct _HTS_Engine HTS_Engine;
typedef struct _HTS_ModelSet HTS_ModelSet;
typedef struct _HTS_Global HTS_Global;
typedef struct _HTS_Audio HTS_Audio;

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

/* Constants */
extern const char *HTS_COPYRIGHT;

#ifdef __cplusplus
}
#endif

#endif /* HTS_ENGINE_H */