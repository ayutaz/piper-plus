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
static int write_le16(FILE *f, uint16_t v) {
    uint8_t buf[2] = {(uint8_t)v, (uint8_t)(v >> 8)};
    if (fwrite(buf, 1, 2, f) != 2) {
        fprintf(stderr, "Error: failed to write 16-bit value\n");
        return -1;
    }
    return 0;
}

/* Write a 32-bit LE value */
static int write_le32(FILE *f, uint32_t v) {
    uint8_t buf[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    if (fwrite(buf, 1, 4, f) != 4) {
        fprintf(stderr, "Error: failed to write 32-bit value\n");
        return -1;
    }
    return 0;
}

/* Minimal WAV header for 16-bit mono PCM (endian-safe).
 * Returns 0 on success, -1 on write error. */
static int write_wav_header(FILE *f, int32_t num_samples, int32_t sample_rate) {
    uint32_t data_size = (uint32_t)num_samples * 2;
    uint32_t file_size = 36 + data_size;

    if (fwrite("RIFF", 1, 4, f) != 4) goto fail;
    if (write_le32(f, file_size) != 0) goto fail;
    if (fwrite("WAVE", 1, 4, f) != 4) goto fail;
    if (fwrite("fmt ", 1, 4, f) != 4) goto fail;
    if (write_le32(f, 16) != 0) goto fail;            /* fmt chunk size */
    if (write_le16(f, 1) != 0) goto fail;             /* PCM format */
    if (write_le16(f, 1) != 0) goto fail;             /* mono */
    if (write_le32(f, (uint32_t)sample_rate) != 0) goto fail;
    if (write_le32(f, (uint32_t)(sample_rate * 2)) != 0) goto fail; /* byte rate */
    if (write_le16(f, 2) != 0) goto fail;             /* block align */
    if (write_le16(f, 16) != 0) goto fail;            /* bits per sample */
    if (fwrite("data", 1, 4, f) != 4) goto fail;
    if (write_le32(f, data_size) != 0) goto fail;
    return 0;

fail:
    fprintf(stderr, "Error: failed to write WAV header\n");
    return -1;
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

    PiperPlusEngine *engine = NULL;
    int32_t create_rc = piper_plus_create(&config, &engine);
    if (create_rc != PIPER_PLUS_OK) {
        fprintf(stderr, "Error (code %d): %s\n", create_rc, piper_plus_get_last_error());
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
        int write_ok = 1;
        if (write_wav_header(f, num_samples, sample_rate) != 0) {
            write_ok = 0;
        }
        /* Convert float32 [-1,1] to int16 */
        for (int32_t i = 0; i < num_samples && write_ok; i++) {
            float s = samples[i];
            if (s > 1.0f) s = 1.0f;
            if (s < -1.0f) s = -1.0f;
            int16_t pcm = (int16_t)(s * 32767.0f);
            if (fwrite(&pcm, 2, 1, f) != 1) {
                fprintf(stderr, "Error: failed to write PCM sample %d\n", i);
                write_ok = 0;
            }
        }
        fclose(f);
        if (write_ok) {
            printf("Saved: %s\n", output_wav);
        } else {
            fprintf(stderr, "Error: WAV file may be incomplete: %s\n", output_wav);
        }
    }

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
    return 0;
}
