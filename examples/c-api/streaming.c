/**
 * streaming.c — piper-plus C API streaming example
 *
 * Usage: ./streaming <model.onnx> [dict_dir] [text] [output.wav]
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

struct StreamState {
    int chunk_count;
    int32_t total_samples;
    int32_t sample_rate;
    float *all_samples;      /* accumulated samples */
    int32_t all_capacity;
    int32_t all_count;
};

static void on_audio_chunk(const float *samples, int32_t num_samples,
                           int32_t sample_rate, void *user_data) {
    struct StreamState *state = (struct StreamState *)user_data;
    state->chunk_count++;
    state->total_samples += num_samples;
    state->sample_rate = sample_rate;
    printf("  Chunk %d: %d samples (%.3f sec)\n",
           state->chunk_count, num_samples,
           (float)num_samples / sample_rate);

    /* Accumulate samples for WAV output */
    if (state->all_count + num_samples > state->all_capacity) {
        int32_t new_cap = (state->all_capacity == 0) ? 65536 : state->all_capacity * 2;
        while (new_cap < state->all_count + num_samples) new_cap *= 2;
        state->all_samples = (float *)realloc(state->all_samples, (size_t)new_cap * sizeof(float));
        state->all_capacity = new_cap;
    }
    memcpy(state->all_samples + state->all_count, samples, (size_t)num_samples * sizeof(float));
    state->all_count += num_samples;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <model.onnx> [dict_dir] [text] [output.wav]\n", argv[0]);
        return 1;
    }

    const char *model_path = argv[1];
    const char *dict_dir   = argc > 2 ? argv[2] : NULL;
    const char *text       = argc > 3 ? argv[3] :
        "First sentence. Second sentence. Third sentence.";

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = model_path;
    config.dict_dir   = dict_dir;

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
        return 1;
    }

    printf("Streaming synthesis: \"%s\"\n", text);

    PiperPlusSynthOptions opts = piper_plus_default_options();
    struct StreamState state = {0, 0, 0, NULL, 0, 0};

    int32_t rc = piper_plus_synthesize_streaming(
        engine, text, &opts, on_audio_chunk, &state);

    if (rc != PIPER_PLUS_OK) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
    } else {
        int32_t sr = piper_plus_sample_rate(engine);
        printf("Done: %d chunks, %d total samples (%.2f sec)\n",
               state.chunk_count, state.total_samples,
               (float)state.total_samples / sr);
    }

    /* Write accumulated audio to WAV */
    if (state.all_count > 0) {
        const char *output_wav = argc > 4 ? argv[4] : "streaming_output.wav";
        FILE *f = fopen(output_wav, "wb");
        if (f) {
            write_wav_header(f, state.all_count, state.sample_rate);
            for (int32_t i = 0; i < state.all_count; i++) {
                float s = state.all_samples[i];
                if (s > 1.0f) s = 1.0f;
                if (s < -1.0f) s = -1.0f;
                int16_t pcm = (int16_t)(s * 32767.0f);
                fwrite(&pcm, 2, 1, f);
            }
            fclose(f);
            printf("Saved: %s\n", output_wav);
        }
    }
    free(state.all_samples);

    piper_plus_free(engine);
    return 0;
}
