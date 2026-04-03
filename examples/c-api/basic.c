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

/* Write a 16-bit LE value */
static void write_le16(FILE *f, uint16_t v) {
    uint8_t buf[2] = {(uint8_t)v, (uint8_t)(v >> 8)};
    fwrite(buf, 1, 2, f);
}

/* Write a 32-bit LE value */
static void write_le32(FILE *f, uint32_t v) {
    uint8_t buf[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    fwrite(buf, 1, 4, f);
}

/* Minimal WAV header for 16-bit mono PCM (endian-safe) */
static void write_wav_header(FILE *f, int32_t num_samples, int32_t sample_rate) {
    uint32_t data_size = (uint32_t)num_samples * 2;
    uint32_t file_size = 36 + data_size;

    fwrite("RIFF", 1, 4, f);
    write_le32(f, file_size);
    fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f);
    write_le32(f, 16);            /* fmt chunk size */
    write_le16(f, 1);             /* PCM format */
    write_le16(f, 1);             /* mono */
    write_le32(f, (uint32_t)sample_rate);
    write_le32(f, (uint32_t)(sample_rate * 2)); /* byte rate */
    write_le16(f, 2);             /* block align */
    write_le16(f, 16);            /* bits per sample */
    fwrite("data", 1, 4, f);
    write_le32(f, data_size);
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
