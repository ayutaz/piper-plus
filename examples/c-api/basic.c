/**
 * basic.c — piper-plus C API basic example
 *
 * Usage: ./basic <model.onnx> [dict_dir] [text] [output.wav]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "piper_plus.h"

/* Minimal WAV header for 16-bit mono PCM */
static void write_wav_header(FILE *f, int32_t num_samples, int32_t sample_rate) {
    int32_t data_size = num_samples * 2; /* 16-bit = 2 bytes per sample */
    int32_t file_size = 36 + data_size;
    int16_t bits_per_sample = 16;
    int16_t num_channels = 1;
    int32_t byte_rate = sample_rate * num_channels * bits_per_sample / 8;
    int16_t block_align = (int16_t)(num_channels * bits_per_sample / 8);

    fwrite("RIFF", 1, 4, f);
    fwrite(&file_size, 4, 1, f);
    fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f);
    int32_t fmt_size = 16;
    fwrite(&fmt_size, 4, 1, f);
    int16_t audio_format = 1; /* PCM */
    fwrite(&audio_format, 2, 1, f);
    fwrite(&num_channels, 2, 1, f);
    fwrite(&sample_rate, 4, 1, f);
    fwrite(&byte_rate, 4, 1, f);
    fwrite(&block_align, 2, 1, f);
    fwrite(&bits_per_sample, 2, 1, f);
    fwrite("data", 1, 4, f);
    fwrite(&data_size, 4, 1, f);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <model.onnx> [dict_dir] [text] [output.wav]\n", argv[0]);
        return 1;
    }

    const char *model_path = argv[1];
    const char *dict_dir   = argc > 2 ? argv[2] : NULL;
    const char *text       = argc > 3 ? argv[3] : "Hello, this is piper-plus.";
    const char *output_wav = argc > 4 ? argv[4] : "output.wav";

    printf("piper-plus version: %s\n", piper_plus_version());

    /* Create engine */
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = model_path;
    config.dict_dir   = dict_dir;

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
        return 1;
    }

    printf("Sample rate: %d Hz\n", piper_plus_sample_rate(engine));
    printf("Speakers: %d, Languages: %d\n",
           piper_plus_num_speakers(engine),
           piper_plus_num_languages(engine));

    /* Synthesize */
    PiperPlusSynthOptions opts = piper_plus_default_options();
    float *samples = NULL;
    int32_t num_samples = 0, sample_rate = 0;

    int32_t rc = piper_plus_synthesize(engine, text, &opts,
                                       &samples, &num_samples, &sample_rate);
    if (rc != PIPER_PLUS_OK) {
        fprintf(stderr, "Synthesis error: %s\n", piper_plus_get_last_error());
        piper_plus_free(engine);
        return 1;
    }

    printf("Generated %d samples (%.2f sec)\n",
           num_samples, (float)num_samples / sample_rate);

    /* Write WAV file */
    FILE *f = fopen(output_wav, "wb");
    if (f) {
        write_wav_header(f, num_samples, sample_rate);
        /* Convert float32 [-1,1] to int16 */
        for (int32_t i = 0; i < num_samples; i++) {
            float s = samples[i];
            if (s > 1.0f) s = 1.0f;
            if (s < -1.0f) s = -1.0f;
            int16_t pcm = (int16_t)(s * 32767.0f);
            fwrite(&pcm, 2, 1, f);
        }
        fclose(f);
        printf("Saved: %s\n", output_wav);
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
    return 0;
}
