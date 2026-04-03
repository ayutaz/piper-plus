/**
 * streaming.c — piper-plus C API streaming example
 *
 * Usage: ./streaming <model.onnx> [dict_dir] [text]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "piper_plus.h"

struct StreamState {
    int chunk_count;
    int32_t total_samples;
};

static void on_audio_chunk(const float *samples, int32_t num_samples,
                           int32_t sample_rate, void *user_data) {
    struct StreamState *state = (struct StreamState *)user_data;
    state->chunk_count++;
    state->total_samples += num_samples;
    printf("  Chunk %d: %d samples (%.3f sec)\n",
           state->chunk_count, num_samples,
           (float)num_samples / sample_rate);
    (void)samples; /* unused in this example */
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <model.onnx> [dict_dir] [text]\n", argv[0]);
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
    struct StreamState state = {0, 0};

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

    piper_plus_free(engine);
    return 0;
}
