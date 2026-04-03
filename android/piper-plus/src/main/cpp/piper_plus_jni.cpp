/**
 * piper_plus_jni.cpp -- Thin JNI wrapper over the piper-plus C API.
 *
 * Each JNI function maps directly to one C API call.
 * Audio is returned as ShortArray (PCM 16-bit) to match Android AudioTrack.
 */

#include <jni.h>
#include <cstring>
#include <cmath>
#include <string>
#include <android/log.h>

#include "piper_plus.h"

#define LOG_TAG "PiperPlusJNI"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Throw a Java PiperPlusException (or RuntimeException as fallback) with the
 * last C API error message.
 */
static void throwPiperException(JNIEnv *env, PiperPlusStatus status) {
    const char *msg = piper_plus_get_last_error();
    if (!msg || msg[0] == '\0') msg = "Unknown piper-plus error";

    jclass exClass = env->FindClass("com/piperplus/PiperPlusException");
    if (exClass == nullptr) {
        // Fallback if the Kotlin exception class is not on the classpath.
        exClass = env->FindClass("java/lang/RuntimeException");
    }
    env->ThrowNew(exClass, msg);
}

/**
 * Convert a float audio buffer to a jshortArray (PCM 16-bit, clamped).
 */
static jshortArray floatsToShortArray(JNIEnv *env,
                                      const float *samples,
                                      int32_t numSamples) {
    jshortArray result = env->NewShortArray(numSamples);
    if (result == nullptr) return nullptr; // OOM -- JVM already threw

    jshort *dst = env->GetShortArrayElements(result, nullptr);
    for (int32_t i = 0; i < numSamples; ++i) {
        float clamped = samples[i];
        if (clamped > 1.0f)  clamped = 1.0f;
        if (clamped < -1.0f) clamped = -1.0f;
        dst[i] = static_cast<jshort>(clamped * 32767.0f);
    }
    env->ReleaseShortArrayElements(result, dst, 0);
    return result;
}

// ---------------------------------------------------------------------------
// JNI exports
// ---------------------------------------------------------------------------

extern "C" {

/**
 * Create a PiperPlusEngine.
 * Returns the native handle (pointer cast to jlong), or throws on error.
 */
JNIEXPORT jlong JNICALL
Java_com_piperplus_PiperPlusNative_nativeCreate(
        JNIEnv *env,
        jobject /* thiz */,
        jstring modelPath,
        jstring configPath,
        jstring dictDir) {

    const char *model  = env->GetStringUTFChars(modelPath, nullptr);
    if (!model) { throwPiperException(env, PIPER_PLUS_ERR); return 0; }

    const char *config = configPath
            ? env->GetStringUTFChars(configPath, nullptr)
            : nullptr;

    const char *dict = dictDir
            ? env->GetStringUTFChars(dictDir, nullptr)
            : nullptr;

    PiperPlusConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.model_path  = model;
    cfg.config_path = config;
    cfg.dict_dir    = dict;
    cfg.provider    = "cpu"; // Android: CPU-only for now

    PiperPlusEngine *engine = nullptr;
    PiperPlusStatus status = piper_plus_create(&cfg, &engine);

    // Release JNI strings regardless of result.
    env->ReleaseStringUTFChars(modelPath, model);
    if (config) env->ReleaseStringUTFChars(configPath, config);
    if (dict)   env->ReleaseStringUTFChars(dictDir, dict);

    if (status != PIPER_PLUS_OK || engine == nullptr) {
        throwPiperException(env, status);
        return 0;
    }
    return reinterpret_cast<jlong>(engine);
}

/**
 * One-shot synthesis. Returns PCM 16-bit ShortArray.
 */
JNIEXPORT jshortArray JNICALL
Java_com_piperplus_PiperPlusNative_nativeSynthesize(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring text,
        jint speakerId) {

    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    const char *textUtf8 = env->GetStringUTFChars(text, nullptr);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return nullptr; }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = static_cast<int32_t>(speakerId);

    float   *samples     = nullptr;
    int32_t  numSamples  = 0;
    int32_t  sampleRate  = 0;

    PiperPlusStatus status = piper_plus_synthesize(
            engine, textUtf8, &opts,
            &samples, &numSamples, &sampleRate);

    env->ReleaseStringUTFChars(text, textUtf8);

    if (status != PIPER_PLUS_OK) {
        throwPiperException(env, status);
        return nullptr;
    }

    jshortArray result = floatsToShortArray(env, samples, numSamples);
    piper_plus_free_audio(samples);
    return result;
}

/**
 * Start iterator-based streaming synthesis.
 * Returns the sample rate (> 0) on success, or throws.
 */
JNIEXPORT jint JNICALL
Java_com_piperplus_PiperPlusNative_nativeSynthStart(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring text,
        jint speakerId) {

    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    const char *textUtf8 = env->GetStringUTFChars(text, nullptr);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return 0; }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = static_cast<int32_t>(speakerId);

    PiperPlusStatus status = piper_plus_synth_start(engine, textUtf8, &opts);

    env->ReleaseStringUTFChars(text, textUtf8);

    if (status != PIPER_PLUS_OK) {
        throwPiperException(env, status);
        return 0;
    }
    return piper_plus_sample_rate(engine);
}

/**
 * Get next audio chunk from the iterator.
 * Returns ShortArray for each chunk, or null when synthesis is complete.
 */
JNIEXPORT jshortArray JNICALL
Java_com_piperplus_PiperPlusNative_nativeSynthNext(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle) {

    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);

    PiperPlusAudioChunk chunk;
    memset(&chunk, 0, sizeof(chunk));

    PiperPlusStatus status = piper_plus_synth_next(engine, &chunk);

    if (status == PIPER_PLUS_DONE) {
        return nullptr; // No more chunks -- signals end to Kotlin
    }
    if (status != PIPER_PLUS_OK) {
        throwPiperException(env, status);
        return nullptr;
    }

    return floatsToShortArray(env, chunk.samples, chunk.num_samples);
}

/**
 * Free the native engine. Safe to call with 0 (no-op).
 */
JNIEXPORT void JNICALL
Java_com_piperplus_PiperPlusNative_nativeFree(
        JNIEnv * /* env */,
        jobject /* thiz */,
        jlong handle) {
    if (handle != 0) {
        piper_plus_free(reinterpret_cast<PiperPlusEngine *>(handle));
    }
}

/**
 * Query sample rate for the loaded model.
 */
JNIEXPORT jint JNICALL
Java_com_piperplus_PiperPlusNative_nativeSampleRate(
        JNIEnv * /* env */,
        jobject /* thiz */,
        jlong handle) {
    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    return piper_plus_sample_rate(engine);
}

/**
 * Query number of speakers in the loaded model.
 */
JNIEXPORT jint JNICALL
Java_com_piperplus_PiperPlusNative_nativeNumSpeakers(
        JNIEnv * /* env */,
        jobject /* thiz */,
        jlong handle) {
    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    return piper_plus_num_speakers(engine);
}

/**
 * Query number of languages in the loaded model.
 */
JNIEXPORT jint JNICALL
Java_com_piperplus_PiperPlusNative_nativeNumLanguages(
        JNIEnv * /* env */,
        jobject /* thiz */,
        jlong handle) {
    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    return piper_plus_num_languages(engine);
}

} // extern "C"
