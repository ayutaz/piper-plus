/**
 * multi_language.c — piper-plus C API multi-language example
 *
 * Demonstrates synthesizing text in 6 languages (JA/EN/ZH/ES/FR/PT)
 * using both explicit language_id and auto-detection (language_id = -1).
 *
 * Usage: ./multi_language <model.onnx> [dict_dir] [config.json]
 *
 * Requires a multi-language model (e.g., multilingual-test-medium.onnx).
 * A single-language model will still work but only the matching language
 * will produce meaningful audio.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include "piper_plus.h"

/* ===== Language samples ===== */

typedef struct {
    const char *lang;
    int32_t     language_id;
    const char *text;
} LangSample;

static const LangSample samples[] = {
    {"JA", 0, "\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf"
              "\xe3\x80\x81\xe4\xbb\x8a\xe6\x97\xa5\xe3\x81\xaf\xe8\x89\xaf"
              "\xe3\x81\x84\xe5\xa4\xa9\xe6\xb0\x97\xe3\x81\xa7\xe3\x81\x99"
              "\xe3\x81\xad\xe3\x80\x82"},                /* こんにちは、今日は良い天気ですね。 */
    {"EN", 1, "Hello, how are you today?"},
    {"ZH", 2, "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8c\xe4\xbb\x8a\xe5\xa4\xa9"
              "\xe5\xa4\xa9\xe6\xb0\x94\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82"}, /* 你好，今天天气很好。 */
    {"ES", 3, "\xc2\xbfHola, c\xc3\xb3mo est\xc3\xa1s hoy?"},                  /* ¿Hola, cómo estás hoy? */
    {"FR", 4, "Bonjour, comment allez-vous?"},
    {"PT", 5, "Ol\xc3\xa1, como voc\xc3\xaa est\xc3\xa1 hoje?"},               /* Olá, como você está hoje? */
};
#define NUM_SAMPLES (sizeof(samples) / sizeof(samples[0]))

/* ===== WAV helpers (endian-safe, same as basic.c) ===== */

static int write_le16(FILE *f, uint16_t v) {
    uint8_t buf[2] = {(uint8_t)v, (uint8_t)(v >> 8)};
    if (fwrite(buf, 1, 2, f) != 2) {
        fprintf(stderr, "Error: failed to write 16-bit value\n");
        return -1;
    }
    return 0;
}

static int write_le32(FILE *f, uint32_t v) {
    uint8_t buf[4] = {(uint8_t)v, (uint8_t)(v >> 8),
                      (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    if (fwrite(buf, 1, 4, f) != 4) {
        fprintf(stderr, "Error: failed to write 32-bit value\n");
        return -1;
    }
    return 0;
}

/* Minimal WAV header for 16-bit mono PCM.
 * Returns 0 on success, -1 on write error. */
static int write_wav_header(FILE *f, int32_t num_samples,
                            int32_t sample_rate) {
    uint32_t data_size = (uint32_t)num_samples * 2;
    uint32_t file_size = 36 + data_size;

    if (fwrite("RIFF", 1, 4, f) != 4) goto fail;
    if (write_le32(f, file_size) != 0) goto fail;
    if (fwrite("WAVE", 1, 4, f) != 4) goto fail;
    if (fwrite("fmt ", 1, 4, f) != 4) goto fail;
    if (write_le32(f, 16) != 0) goto fail;                           /* fmt chunk size */
    if (write_le16(f, 1) != 0) goto fail;                            /* PCM format */
    if (write_le16(f, 1) != 0) goto fail;                            /* mono */
    if (write_le32(f, (uint32_t)sample_rate) != 0) goto fail;
    if (write_le32(f, (uint32_t)(sample_rate * 2)) != 0) goto fail;  /* byte rate */
    if (write_le16(f, 2) != 0) goto fail;                            /* block align */
    if (write_le16(f, 16) != 0) goto fail;                           /* bits per sample */
    if (fwrite("data", 1, 4, f) != 4) goto fail;
    if (write_le32(f, data_size) != 0) goto fail;
    return 0;

fail:
    fprintf(stderr, "Error: failed to write WAV header\n");
    return -1;
}

/* Write float32 audio as 16-bit PCM WAV.
 * Returns 0 on success, -1 on error. */
static int write_wav_file(const char *path, const float *audio,
                          int32_t num_samples, int32_t sample_rate) {
    FILE *f = fopen(path, "wb");
    int32_t i;
    if (!f) {
        fprintf(stderr, "  Cannot open %s for writing\n", path);
        return -1;
    }
    if (write_wav_header(f, num_samples, sample_rate) != 0) {
        fclose(f);
        return -1;
    }
    for (i = 0; i < num_samples; i++) {
        float s = audio[i];
        int16_t pcm;
        if (s > 1.0f) s = 1.0f;
        if (s < -1.0f) s = -1.0f;
        pcm = (int16_t)(s * 32767.0f);
        if (fwrite(&pcm, 2, 1, f) != 1) {
            fprintf(stderr, "  Error: failed to write PCM sample %d to %s\n", i, path);
            fclose(f);
            return -1;
        }
    }
    fclose(f);
    return 0;
}

/* ===== main ===== */

int main(int argc, char *argv[]) {
    size_t i;

    if (argc < 2) {
        fprintf(stderr,
                "Usage: %s <model.onnx> [dict_dir] [config.json]\n"
                "\n"
                "Synthesizes text in 6 languages and writes WAV files.\n"
                "  model.onnx  - Path to a multi-language ONNX model\n"
                "  dict_dir    - OpenJTalk dictionary directory (optional)\n"
                "  config.json - Model config path (optional, default: model.onnx.json)\n",
                argv[0]);
        return 1;
    }

    printf("piper-plus version: %s\n\n", piper_plus_version());

    /* 1. Create engine */
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path  = argv[1];
    config.dict_dir    = argc > 2 ? argv[2] : NULL;
    config.config_path = argc > 3 ? argv[3] : NULL;

    PiperPlusEngine *engine = NULL;
    int32_t create_rc = piper_plus_create(&config, &engine);
    if (create_rc != PIPER_PLUS_OK) {
        fprintf(stderr, "Engine creation failed (code %d): %s\n",
                create_rc, piper_plus_get_last_error());
        return 1;
    }

    printf("Languages: %d, Speakers: %d, Sample rate: %d Hz\n\n",
           piper_plus_num_languages(engine),
           piper_plus_num_speakers(engine),
           piper_plus_sample_rate(engine));

    /* 2. Explicit language_id: synthesize each language */
    printf("=== Explicit language_id ===\n\n");

    for (i = 0; i < NUM_SAMPLES; i++) {
        PiperPlusSynthOptions opts = piper_plus_default_options();
        float  *out_samples    = NULL;
        int32_t out_num_samples = 0;
        int32_t out_sample_rate = 0;
        double  elapsed, duration;
        char    filename[64];
        clock_t t_start, t_end;
        int32_t rc;

        opts.language_id = samples[i].language_id;

        printf("[%s] lang_id=%d  \"%s\"\n",
               samples[i].lang, samples[i].language_id, samples[i].text);

        t_start = clock();
        rc = piper_plus_synthesize(engine, samples[i].text, &opts,
                                   &out_samples, &out_num_samples,
                                   &out_sample_rate);
        t_end = clock();

        if (rc != PIPER_PLUS_OK) {
            fprintf(stderr, "  Synthesis error: %s\n",
                    piper_plus_get_last_error());
            continue;
        }

        elapsed  = (double)(t_end - t_start) / CLOCKS_PER_SEC;
        duration = (double)out_num_samples / out_sample_rate;
        printf("  -> %.2fs audio in %.3fs (RTF=%.2f)\n",
               duration, elapsed,
               duration > 0.0 ? elapsed / duration : 0.0);

        snprintf(filename, sizeof(filename), "output_%s.wav",
                 samples[i].lang);
        if (write_wav_file(filename, out_samples, out_num_samples,
                           out_sample_rate) == 0) {
            printf("  Saved: %s\n", filename);
        }
        printf("\n");

        piper_plus_free_audio(out_samples);
    }

    /* 3. Auto-detect mode: language_id = -1 */
    printf("=== Auto-detect mode (language_id=-1) ===\n");
    printf("Note: auto-detect relies on the built-in multilingual G2P.\n"
           "If the model has only one language, all texts use that language.\n\n");

    for (i = 0; i < NUM_SAMPLES; i++) {
        PiperPlusSynthOptions opts = piper_plus_default_options();
        float  *out_samples    = NULL;
        int32_t out_num_samples = 0;
        int32_t out_sample_rate = 0;
        double  duration;
        char    filename[64];
        int32_t rc;

        opts.language_id = -1;  /* auto-detect */

        rc = piper_plus_synthesize(engine, samples[i].text, &opts,
                                   &out_samples, &out_num_samples,
                                   &out_sample_rate);
        if (rc != PIPER_PLUS_OK) {
            fprintf(stderr, "[%s] auto-detect error: %s\n",
                    samples[i].lang, piper_plus_get_last_error());
            continue;
        }

        duration = (double)out_num_samples / out_sample_rate;
        printf("[%s] auto-detect -> %.2fs audio\n",
               samples[i].lang, duration);

        snprintf(filename, sizeof(filename), "output_%s_auto.wav",
                 samples[i].lang);
        if (write_wav_file(filename, out_samples, out_num_samples,
                           out_sample_rate) == 0) {
            printf("  Saved: %s\n", filename);
        }

        piper_plus_free_audio(out_samples);
    }

    /* 4. Cleanup */
    printf("\nDone. Generated %d WAV files.\n", (int)(NUM_SAMPLES * 2));
    piper_plus_free(engine);
    return 0;
}
