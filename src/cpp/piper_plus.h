#ifndef PIPER_PLUS_H_
#define PIPER_PLUS_H_

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ===== ABI Policy =====
 * - All input structs (Config, SynthOptions) have _reserved fields for future
 *   expansion without breaking ABI. Output structs (AudioChunk, PhonemeInfo,
 *   TimingResult) are read-only and versioned via PIPER_PLUS_API_VERSION.
 * - Callers MUST zero-initialize input structs with memset() or = {0} before
 *   populating fields. This ensures that _reserved fields and any fields added
 *   in future versions default to zero.
 * - _reserved fields MUST be zero. Non-zero values in _reserved are reserved
 *   for future use and may cause errors in later versions.
 * - Query functions (piper_plus_sample_rate, num_speakers, num_languages,
 *   language_id, dict_entry_count) return a sentinel value on error (see each
 *   function's documentation) rather than a Status code, for ergonomic use in
 *   expressions. Use piper_plus_get_last_error() if you need the error message.
 */

/* ===== Export macro ===== */
#if defined(_WIN32) || defined(_WIN64)
  #ifdef PIPER_PLUS_BUILDING_DLL
    #define PIPER_PLUS_API __declspec(dllexport)
  #else
    #define PIPER_PLUS_API __declspec(dllimport)
  #endif
#elif defined(__GNUC__) && __GNUC__ >= 4
  #define PIPER_PLUS_API __attribute__((visibility("default")))
#else
  #define PIPER_PLUS_API
#endif

/* ===== Version ===== */
#define PIPER_PLUS_API_VERSION 1

/** Returns version string. The returned pointer is static storage; do not free. */
PIPER_PLUS_API const char *piper_plus_version(void);
PIPER_PLUS_API int32_t     piper_plus_api_version(void);

/* ===== Status codes ===== */

typedef enum PiperPlusStatus {
    PIPER_PLUS_OK          =  0,
    PIPER_PLUS_DONE        =  1,
    PIPER_PLUS_ERR         = -1,
    PIPER_PLUS_ERR_MODEL   = -2,
    PIPER_PLUS_ERR_CONFIG  = -3,
    PIPER_PLUS_ERR_TEXT    = -4,
    PIPER_PLUS_ERR_BUSY    = -5,
    PIPER_PLUS_ERR_ORT     = -6
} PiperPlusStatus;

/* ===== Error ===== */

/** Returns the error message for the CALLING thread (thread-local storage).
 *  @return NUL-terminated error string, or NULL if no error has occurred.
 *  @note The returned pointer is valid until the next piper_plus_* call on
 *        the same thread. Caller should copy the string if persistence is
 *        needed beyond that point.
 *  @threading Safe to call from any thread. Each thread has independent
 *             error state. */
PIPER_PLUS_API const char *piper_plus_get_last_error(void);

/* ===== Opaque engine handle ===== */

/**
 * Opaque engine handle.
 *
 * @note PiperPlusEngine is NOT thread-safe. Do not call any function on
 *       the same engine from multiple threads concurrently.
 *       Use one engine per thread, or protect with an external mutex.
 */
typedef struct PiperPlusEngine PiperPlusEngine;

/* ===== Config structs (POD, memset-safe) ===== */

typedef struct PiperPlusConfig {
    const char *model_path;       /* Required: .onnx model file path (UTF-8) */
    const char *config_path;      /* Optional: .json config path (NULL = model_path + ".json") */
    const char *provider;         /* Optional: "cpu","cuda","coreml","directml" (NULL = "cpu") */
    int32_t     num_threads;      /* ONNX intra-op threads (0 = auto) */
    int32_t     gpu_device_id;    /* GPU device index (ignored for cpu) */
    const char *dict_dir;         /* Optional: OpenJTalk dict dir (NULL = auto-detect) */
    int32_t     _reserved[7];     /* Must be zero */
} PiperPlusConfig;

/** @note Zero-init safe: noise_scale, length_scale, noise_w が 0.0 の場合は
 *        デフォルト値 (0.667, 1.0, 0.8) に自動置換されます。 */
typedef struct PiperPlusSynthOptions {
    int32_t speaker_id;                 /* Speaker index (default: 0) */
    int32_t language_id;                /* Language index (-1 = auto-detect, default: -1) */
    float   noise_scale;                /* VITS noise_scale (default: 0.667) */
    float   length_scale;               /* VITS length_scale (default: 1.0) */
    float   noise_w;                    /* VITS noise_w (default: 0.8) */
    float   sentence_silence_sec;       /* Silence between sentences in sec (default: 0.2) */
    const float *speaker_embedding;     /* Voice cloning: float32 embedding (NULL = use speaker_id) */
    int32_t      speaker_embedding_dim; /* Number of elements in speaker_embedding (0 = disabled) */
    int32_t _reserved[5];               /* Must be zero */
} PiperPlusSynthOptions;

/* ===== Lifecycle ===== */

PIPER_PLUS_API PiperPlusStatus  piper_plus_create(const PiperPlusConfig *config,
                                                  PiperPlusEngine      **out_engine);
PIPER_PLUS_API void             piper_plus_free(PiperPlusEngine *engine);

/* ===== Default options ===== */

PIPER_PLUS_API PiperPlusSynthOptions piper_plus_default_options(void);

/* ===== One-shot synthesis ===== */

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,       /* NULL = defaults */
    float                       **out_samples,
    int32_t                      *out_num_samples,
    int32_t                      *out_sample_rate);

PIPER_PLUS_API void piper_plus_free_audio(float *samples);

/* ===== Query =====
 * These functions return scalar values directly for ergonomic use.
 * On error (NULL engine, invalid argument), they return a sentinel value
 * (0 or -1 as documented below) and set the thread-local error string. */

/** Returns sample rate in Hz, or 0 on error (NULL engine). */
PIPER_PLUS_API int32_t piper_plus_sample_rate(const PiperPlusEngine *engine);

/** Returns number of speakers in the model, or 0 on error (NULL engine). */
PIPER_PLUS_API int32_t piper_plus_num_speakers(const PiperPlusEngine *engine);

/** Returns number of languages in the model, or 0 on error (NULL engine). */
PIPER_PLUS_API int32_t piper_plus_num_languages(const PiperPlusEngine *engine);

/** Returns language index for the given name, or -1 if not found or on error.
 *  @param language_name  Language code string (e.g. "ja", "en"). */
PIPER_PLUS_API int32_t piper_plus_language_id(
    const PiperPlusEngine *engine,
    const char            *language_name);

/* ===== Audio chunk (for iterator/streaming) ===== */

/**
 * Audio data returned by iterator/streaming synthesis.
 *
 * @lifetime The samples pointer is BORROWED from the engine's internal buffer.
 *   - For synth_next(): valid until the next synth_next() or synth_start() call
 *     on the same engine.
 *   - For streaming callback (PiperPlusAudioCallback / PiperPlusAudioCallbackEx):
 *     valid only during the callback invocation.
 *   - Caller MUST copy the data if retention is needed beyond these boundaries.
 */
typedef struct PiperPlusAudioChunk {
    const float *samples;         /**< BORROWED: see struct-level @lifetime doc */
    int32_t      num_samples;     /**< Number of float samples */
    int32_t      sample_rate;     /**< Sample rate in Hz */
    int32_t      is_last;         /**< 1 if this is the last chunk, 0 otherwise */
} PiperPlusAudioChunk;

/* ===== Iterator pattern (sentence-by-sentence synthesis) ===== */

/**
 * Start iterative synthesis.
 * Splits text into sentences and prepares internal queue.
 * Call piper_plus_synth_next() repeatedly to get audio chunks.
 *
 * @note One engine = one synthesis at a time (NOT thread-safe).
 * @note out_chunk->samples points to internal buffer;
 *       valid until next synth_next() or synth_start() call.
 */
PIPER_PLUS_API PiperPlusStatus piper_plus_synth_start(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts);

PIPER_PLUS_API PiperPlusStatus piper_plus_synth_next(
    PiperPlusEngine      *engine,
    PiperPlusAudioChunk  *out_chunk);

/* ===== Streaming callback synthesis ===== */

/** Audio callback for streaming synthesis.
 *  @param samples      BORROWED: valid only during this callback invocation.
 *                      Caller MUST copy if retention is needed.
 *  @param num_samples  Number of float samples in the buffer.
 *  @param sample_rate  Sample rate in Hz.
 *  @param user_data    Opaque pointer passed to synthesize_streaming(). */
typedef void (*PiperPlusAudioCallback)(
    const float *samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    void        *user_data);

/**
 * Synthesize text with streaming callback.
 * Internally drives synth_start/synth_next and delivers chunks via callback.
 *
 * @note Callback is invoked on caller's thread (synchronous).
 * @note samples pointer in callback is valid only during invocation.
 */
PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    PiperPlusAudioCallback        callback,
    void                         *user_data);

/* ===== Cancellable streaming callback (M5-7) ===== */

/** Cancellable audio callback. Return 0 to continue, non-zero to abort.
 *  @param samples      BORROWED: valid only during this callback invocation.
 *                      Caller MUST copy if retention is needed.
 *  @param num_samples  Number of float samples in the buffer.
 *  @param sample_rate  Sample rate in Hz.
 *  @param user_data    Opaque pointer passed to synthesize_streaming_ex().
 *  @return 0 to continue synthesis, non-zero to abort (not treated as error). */
typedef int (*PiperPlusAudioCallbackEx)(
    const float *samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    void        *user_data);

/** Synthesize with cancellable streaming.
 *  If callback returns non-zero, synthesis stops and function returns
 *  PIPER_PLUS_OK (not an error -- caller requested abort). */
PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming_ex(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    PiperPlusAudioCallbackEx      callback,
    void                         *user_data);

/* ===== Custom dictionary (M4-1) ===== */

PIPER_PLUS_API PiperPlusStatus piper_plus_load_custom_dict(
    PiperPlusEngine *engine,
    const char      *dict_path);

PIPER_PLUS_API PiperPlusStatus piper_plus_clear_custom_dict(PiperPlusEngine *engine);

PIPER_PLUS_API PiperPlusStatus piper_plus_add_dict_word(
    PiperPlusEngine *engine,
    const char      *word,
    const char      *pronunciation,
    int32_t          priority);

/** Returns number of entries in the custom dictionary, or 0 on error
 *  (NULL engine or no dictionary loaded). */
PIPER_PLUS_API int32_t piper_plus_dict_entry_count(const PiperPlusEngine *engine);

/* ===== Phoneme timing (M4-2) ===== */

/**
 * Phoneme timing entry from the last synthesis.
 *
 * @lifetime All BORROWED pointers (phoneme string, entries array) are valid
 *   until the next synthesis call (synthesize, synth_start, synth_next, or
 *   synthesize_streaming*) on the same engine. Caller MUST copy the data if
 *   retention is needed beyond that point.
 */
typedef struct PiperPlusPhonemeInfo {
    const char *phoneme;       /**< BORROWED: phoneme string (UTF-8, NUL-terminated) */
    float       start_time;    /**< Start time in seconds */
    float       end_time;      /**< End time in seconds */
} PiperPlusPhonemeInfo;

typedef struct PiperPlusTimingResult {
    const PiperPlusPhonemeInfo *entries;  /**< BORROWED: array of timing entries */
    int32_t                     count;    /**< Number of entries */
} PiperPlusTimingResult;

/** Get phoneme timing from the last synthesis.
 *  @lifetime Result is BORROWED; valid until next synthesis call on this engine.
 *  Caller MUST copy entries if persistence is needed. */
PIPER_PLUS_API PiperPlusStatus piper_plus_get_phoneme_timing(
    PiperPlusEngine         *engine,
    PiperPlusTimingResult   *out_timing);

/* ===== G2P / Phonemization (M4-3) ===== */

/**
 * Result of piper_plus_phonemize().
 *
 * @lifetime BORROWED pointers (phonemes, language) are valid until the next
 *   piper_plus_phonemize() or synthesis call on the same engine. Caller MUST
 *   copy strings if persistence is needed.
 */
typedef struct PiperPlusPhonemeResult {
    const char *phonemes;      /**< BORROWED: space-separated IPA phoneme string */
    const char *language;      /**< BORROWED: detected/resolved language code */
    int32_t     num_phonemes;  /**< Number of phoneme tokens */
    int32_t     _reserved[4];  /**< Must be zero -- reserved for future fields */
} PiperPlusPhonemeResult;

/** Phonemize text without synthesis. language=NULL for auto-detect. */
PIPER_PLUS_API PiperPlusStatus piper_plus_phonemize(
    PiperPlusEngine         *engine,
    const char              *text,
    const char              *language,
    PiperPlusPhonemeResult  *out_result);

/** Get available language codes as a comma-separated string (e.g. "en,fr,ja").
 *  @return BORROWED pointer; valid until next call to this function on the
 *          same engine. Returns "" (empty string) on error (NULL engine or
 *          no language map). Caller MUST copy if persistence is needed. */
PIPER_PLUS_API const char *piper_plus_available_languages(PiperPlusEngine *engine);

/* ===== Speaker Encoder (EXPERIMENTAL -- not yet implemented) ========= */

/**
 * Opaque speaker encoder handle.
 * Wraps an ECAPA-TDNN ONNX model for extracting speaker embeddings.
 *
 * @note EXPERIMENTAL: The speaker encoder API surface is defined for forward
 *       compatibility but the implementation is not yet connected to a backend.
 *       All functions currently return an error or NULL.
 */
typedef struct PiperPlusSpeakerEncoder PiperPlusSpeakerEncoder;

/** Create a speaker encoder from an ONNX model file.
 *  @param model_path  Path to the speaker encoder .onnx file.
 *  @return Handle on success, or NULL on error (see piper_plus_get_last_error()). */
PIPER_PLUS_API PiperPlusSpeakerEncoder* piper_plus_speaker_encoder_create(
    const char *model_path);

/** Encode audio samples into a speaker embedding.
 *  @param encoder        Speaker encoder handle (must not be NULL).
 *  @param audio_samples  Mono float32 PCM audio samples.
 *  @param num_samples    Number of float samples in audio_samples.
 *  @param sample_rate    Sample rate of the input audio (e.g. 16000, 22050, 44100).
 *  @param embedding_out  Output buffer to receive the embedding (caller-allocated).
 *  @param embedding_dim  Size of embedding_out buffer (e.g. 256).
 *  @return Number of embedding dimensions written on success, or -1 on error. */
PIPER_PLUS_API int32_t piper_plus_speaker_encoder_encode(
    PiperPlusSpeakerEncoder *encoder,
    const float *audio_samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    float       *embedding_out,
    int32_t      embedding_dim);

/** Destroy a speaker encoder and release its resources. */
PIPER_PLUS_API void piper_plus_speaker_encoder_destroy(
    PiperPlusSpeakerEncoder *encoder);

#ifdef __cplusplus
}
#endif

#endif /* PIPER_PLUS_H_ */
