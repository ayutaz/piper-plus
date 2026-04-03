#ifndef PIPER_PLUS_H_
#define PIPER_PLUS_H_

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

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
    PIPER_PLUS_ERR_BUSY    = -5
} PiperPlusStatus;

/* ===== Error ===== */
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
    int32_t speaker_id;           /* Speaker index (default: 0) */
    int32_t language_id;          /* Language index (-1 = auto-detect, default: -1) */
    float   noise_scale;          /* VITS noise_scale (default: 0.667) */
    float   length_scale;         /* VITS length_scale (default: 1.0) */
    float   noise_w;              /* VITS noise_w (default: 0.8) */
    float   sentence_silence_sec; /* Silence between sentences in sec (default: 0.2) */
    int32_t _reserved[8];         /* Must be zero */
} PiperPlusSynthOptions;

/* ===== Lifecycle ===== */

PIPER_PLUS_API PiperPlusEngine *piper_plus_create(const PiperPlusConfig *config);
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

/* ===== Query ===== */

PIPER_PLUS_API int32_t piper_plus_sample_rate(const PiperPlusEngine *engine);
PIPER_PLUS_API int32_t piper_plus_num_speakers(const PiperPlusEngine *engine);
PIPER_PLUS_API int32_t piper_plus_num_languages(const PiperPlusEngine *engine);
PIPER_PLUS_API int32_t piper_plus_language_id(
    const PiperPlusEngine *engine,
    const char            *language_name);

/* ===== Audio chunk (for iterator/streaming) ===== */

typedef struct PiperPlusAudioChunk {
    const float *samples;         /**< BORROWED: valid until next synth_next()
                                       or synth_start() call. Copy if needed. */
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

/** Callback that returns 0 to continue, non-zero to abort. */
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

PIPER_PLUS_API int32_t piper_plus_dict_entry_count(const PiperPlusEngine *engine);

/* ===== Phoneme timing (M4-2) ===== */

typedef struct PiperPlusPhonemeInfo {
    const char *phoneme;       /**< Phoneme string (BORROWED, valid until next synthesis) */
    float       start_time;    /**< Start time in seconds */
    float       end_time;      /**< End time in seconds */
} PiperPlusPhonemeInfo;

typedef struct PiperPlusTimingResult {
    const PiperPlusPhonemeInfo *entries;  /**< Array of phoneme timing entries */
    int32_t                     count;    /**< Number of entries */
} PiperPlusTimingResult;

/** Get phoneme timing from the last synthesis. Valid until next synthesis call. */
PIPER_PLUS_API PiperPlusStatus piper_plus_get_phoneme_timing(
    PiperPlusEngine         *engine,
    PiperPlusTimingResult   *out_timing);

/* ===== G2P / Phonemization (M4-3) ===== */

typedef struct PiperPlusPhonemeResult {
    const char *phonemes;      /**< Space-separated IPA phoneme string (BORROWED) */
    const char *language;      /**< Detected language code (BORROWED) */
    int32_t     num_phonemes;  /**< Number of phoneme tokens */
    int32_t     _reserved[4];  /**< Must be zero -- reserved for future fields */
} PiperPlusPhonemeResult;

/** Phonemize text without synthesis. language=NULL for auto-detect. */
PIPER_PLUS_API PiperPlusStatus piper_plus_phonemize(
    PiperPlusEngine         *engine,
    const char              *text,
    const char              *language,
    PiperPlusPhonemeResult  *out_result);

/** Get available language codes (comma-separated, BORROWED). */
PIPER_PLUS_API const char *piper_plus_available_languages(PiperPlusEngine *engine);

#ifdef __cplusplus
}
#endif

#endif /* PIPER_PLUS_H_ */
