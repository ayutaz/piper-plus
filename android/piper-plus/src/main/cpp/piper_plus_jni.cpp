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
// RAII helpers
// ---------------------------------------------------------------------------

/**
 * RAII guard for JNI GetStringUTFChars / ReleaseStringUTFChars.
 *
 * Ensures the UTF-8 string is always released, even when an earlier
 * GetStringUTFChars succeeds but a subsequent one fails (preventing
 * a resource leak in nativeCreate and similar multi-string functions).
 */
class JNIStringGuard {
    JNIEnv     *env_;
    jstring     jstr_;
    const char *str_;

    JNIStringGuard(const JNIStringGuard &) = delete;
    JNIStringGuard &operator=(const JNIStringGuard &) = delete;
public:
    JNIStringGuard(JNIEnv *env, jstring jstr)
        : env_(env), jstr_(jstr),
          str_(jstr ? env->GetStringUTFChars(jstr, nullptr) : nullptr) {}
    ~JNIStringGuard() { if (str_) env_->ReleaseStringUTFChars(jstr_, str_); }
    const char *get() const { return str_; }
    explicit operator bool() const { return str_ != nullptr; }
};

// ---------------------------------------------------------------------------
// Cached global references (initialised in JNI_OnLoad)
// ---------------------------------------------------------------------------

/** Global ref to com.piperplus.PiperPlusException (or RuntimeException). */
static jclass g_piperExceptionClass = nullptr;
/** Global ref to java.lang.RuntimeException (fallback). */
static jclass g_runtimeExceptionClass = nullptr;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void * /* reserved */) {
    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    // Cache PiperPlusException as a GlobalRef so throwPiperException()
    // never leaks a local reference from FindClass().
    jclass local = env->FindClass("com/piperplus/PiperPlusException");
    if (local) {
        g_piperExceptionClass =
            static_cast<jclass>(env->NewGlobalRef(local));
        env->DeleteLocalRef(local);
    }

    local = env->FindClass("java/lang/RuntimeException");
    if (local) {
        g_runtimeExceptionClass =
            static_cast<jclass>(env->NewGlobalRef(local));
        env->DeleteLocalRef(local);
    }

    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void * /* reserved */) {
    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return;
    }
    if (g_piperExceptionClass) {
        env->DeleteGlobalRef(g_piperExceptionClass);
        g_piperExceptionClass = nullptr;
    }
    if (g_runtimeExceptionClass) {
        env->DeleteGlobalRef(g_runtimeExceptionClass);
        g_runtimeExceptionClass = nullptr;
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Throw a Java PiperPlusException (or RuntimeException as fallback) with the
 * last C API error message.
 *
 * Uses the GlobalRef cached in JNI_OnLoad -- no FindClass() local ref leak.
 */
static void throwPiperException(JNIEnv *env, PiperPlusStatus status) {
    const char *msg = piper_plus_get_last_error();
    if (!msg || msg[0] == '\0') msg = "Unknown piper-plus error";

    jclass exClass = g_piperExceptionClass
                         ? g_piperExceptionClass
                         : g_runtimeExceptionClass;
    if (exClass) {
        env->ThrowNew(exClass, msg);
    } else {
        // Last resort: fall back to a fresh FindClass (should never happen).
        jclass fallback = env->FindClass("java/lang/RuntimeException");
        if (fallback) env->ThrowNew(fallback, msg);
    }
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
 *
 * All jstring arguments are wrapped in JNIStringGuard so they are
 * guaranteed to be released even if a later GetStringUTFChars fails.
 */
JNIEXPORT jlong JNICALL
Java_com_piperplus_PiperPlusNative_nativeCreate(
        JNIEnv *env,
        jobject /* thiz */,
        jstring modelPath,
        jstring configPath,
        jstring dictDir) {

    JNIStringGuard model(env, modelPath);
    if (!model) { throwPiperException(env, PIPER_PLUS_ERR); return 0; }

    JNIStringGuard config(env, configPath);  // nullptr-safe: returns nullptr for null jstring
    JNIStringGuard dict(env, dictDir);       // ditto

    PiperPlusConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.model_path  = model.get();
    cfg.config_path = config.get();
    cfg.dict_dir    = dict.get();
    cfg.provider    = "cpu"; // Android: CPU-only for now

    PiperPlusEngine *engine = nullptr;
    PiperPlusStatus status = piper_plus_create(&cfg, &engine);

    // JNIStringGuard destructors release all strings here.

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
    JNIStringGuard textUtf8(env, text);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return nullptr; }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = static_cast<int32_t>(speakerId);

    float   *samples     = nullptr;
    int32_t  numSamples  = 0;
    int32_t  sampleRate  = 0;

    PiperPlusStatus status = piper_plus_synthesize(
            engine, textUtf8.get(), &opts,
            &samples, &numSamples, &sampleRate);

    // JNIStringGuard destructor releases textUtf8 here.

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
    JNIStringGuard textUtf8(env, text);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return 0; }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = static_cast<int32_t>(speakerId);

    PiperPlusStatus status = piper_plus_synth_start(engine, textUtf8.get(), &opts);

    // JNIStringGuard destructor releases textUtf8 here.

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

    if (status < 0) {
        throwPiperException(env, status);
        return nullptr;
    }

    // DONE may still carry the final chunk's samples -- deliver them.
    // Return null only when there are no samples (pure end-of-stream).
    if (chunk.num_samples > 0) {
        return floatsToShortArray(env, chunk.samples, chunk.num_samples);
    }
    return nullptr; // End of stream
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
