/**
 * piper_plus_g2p_jni.cpp -- JNI bridge for the engine-less G2P C API
 * (piper_plus_g2p_*) used by the piper-plus-g2p-android AAR.
 *
 * Each JNI export maps directly to one C API call. UTF-8 strings are wrapped
 * in JNIStringGuard so they are released even if a later GetStringUTFChars
 * fails. BORROWED pointers from the C API are immediately copied into a fresh
 * NewStringUTF jstring, never retained across calls.
 */

#include <jni.h>

#include <cstring>
#include <string>

// android/log.h only exists when targeting the Android NDK. The L2
// linux-jvm-smoke CI job builds this same source on a host JVM (Linux x86_64)
// where the NDK headers aren't present, so we provide a no-op shim there.
#ifdef __ANDROID__
#  include <android/log.h>
#  define LOG_TAG "PiperPlusG2pJNI"
#  define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#else
#  include <cstdio>
#  define LOGE(...) do { fprintf(stderr, "[piper-plus-g2p-jni] " __VA_ARGS__); fputc('\n', stderr); } while (0)
#endif

#include "piper_plus.h"

// ---------------------------------------------------------------------------
// RAII helpers
// ---------------------------------------------------------------------------

/// RAII guard for JNI GetStringUTFChars / ReleaseStringUTFChars.
/// Mirrors the pattern used by the existing TTS module (piper_plus_jni.cpp).
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

static jclass g_g2pExceptionClass     = nullptr;
static jclass g_runtimeExceptionClass = nullptr;

extern "C" {

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void * /* reserved */) {
    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    if (jclass local = env->FindClass("com/piperplus/g2p/PiperPlusG2pException")) {
        g_g2pExceptionClass = static_cast<jclass>(env->NewGlobalRef(local));
        env->DeleteLocalRef(local);
    }
    if (jclass local = env->FindClass("java/lang/RuntimeException")) {
        g_runtimeExceptionClass = static_cast<jclass>(env->NewGlobalRef(local));
        env->DeleteLocalRef(local);
    }
    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void * /* reserved */) {
    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return;
    }
    if (g_g2pExceptionClass) {
        env->DeleteGlobalRef(g_g2pExceptionClass);
        g_g2pExceptionClass = nullptr;
    }
    if (g_runtimeExceptionClass) {
        env->DeleteGlobalRef(g_runtimeExceptionClass);
        g_runtimeExceptionClass = nullptr;
    }
}

} // extern "C"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Throws PiperPlusG2pException (or RuntimeException as fallback) carrying the
/// thread-local error message from the C API.
static void throwG2pException(JNIEnv *env, const char *fallback = nullptr) {
    const char *msg = piper_plus_get_last_error();
    if (!msg || msg[0] == '\0') msg = fallback ? fallback : "Unknown piper-plus G2P error";

    jclass exClass = g_g2pExceptionClass
                         ? g_g2pExceptionClass
                         : g_runtimeExceptionClass;
    if (exClass) {
        env->ThrowNew(exClass, msg);
    } else if (jclass last = env->FindClass("java/lang/RuntimeException")) {
        env->ThrowNew(last, msg);
    }
}

// ---------------------------------------------------------------------------
// JNI exports — Kotlin namespace: com.piperplus.g2p.PiperPlusG2pNative
// ---------------------------------------------------------------------------

extern "C" {

/// nativeCreate(dictDir: String?): Long
JNIEXPORT jlong JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeCreate(
        JNIEnv *env,
        jobject /* thiz */,
        jstring dictDir) {

    JNIStringGuard dict(env, dictDir);  // nullptr-safe
    PiperPlusG2pHandle *h = piper_plus_g2p_create(dict.get());
    if (!h) {
        throwG2pException(env, "piper_plus_g2p_create returned NULL");
        return 0;
    }
    return reinterpret_cast<jlong>(h);
}

/// nativeFree(handle: Long)
JNIEXPORT void JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeFree(
        JNIEnv * /* env */,
        jobject /* thiz */,
        jlong handle) {
    if (handle != 0) {
        piper_plus_g2p_free(reinterpret_cast<PiperPlusG2pHandle *>(handle));
    }
}

/// nativePhonemize(handle: Long, text: String, language: String?): Array<String>
/// Returns a String[3]: [phonemes, language, num_phonemes_str].
/// (We avoid the JNI overhead of a separate result class.)
JNIEXPORT jobjectArray JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativePhonemize(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring text,
        jstring language) {

    auto *h = reinterpret_cast<PiperPlusG2pHandle *>(handle);
    JNIStringGuard textUtf8(env, text);
    JNIStringGuard langUtf8(env, language);  // nullptr-safe

    PiperPlusPhonemeResult result;
    std::memset(&result, 0, sizeof(result));
    PiperPlusStatus status = piper_plus_g2p_phonemize(
        h, textUtf8.get(), langUtf8.get(), &result);

    if (status != PIPER_PLUS_OK) {
        throwG2pException(env);
        return nullptr;
    }

    // Copy BORROWED pointers immediately. NewStringUTF allocates fresh storage.
    jstring jPhonemes = env->NewStringUTF(result.phonemes ? result.phonemes : "");
    jstring jLanguage = env->NewStringUTF(result.language ? result.language : "");
    char numBuf[16];
    std::snprintf(numBuf, sizeof(numBuf), "%d", result.num_phonemes);
    jstring jNum = env->NewStringUTF(numBuf);

    jclass strClass = env->FindClass("java/lang/String");
    if (!strClass) return nullptr;
    jobjectArray arr = env->NewObjectArray(3, strClass, nullptr);
    if (!arr) return nullptr;
    env->SetObjectArrayElement(arr, 0, jPhonemes);
    env->SetObjectArrayElement(arr, 1, jLanguage);
    env->SetObjectArrayElement(arr, 2, jNum);
    env->DeleteLocalRef(strClass);
    return arr;
}

/// nativeAvailableLanguages(handle: Long): String
/// Returns a comma-separated string ("en,es,fr,ja,ko,pt,sv,zh").
JNIEXPORT jstring JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeAvailableLanguages(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle) {

    auto *h = reinterpret_cast<PiperPlusG2pHandle *>(handle);
    const char *codes = piper_plus_g2p_available_languages(h);
    return env->NewStringUTF(codes ? codes : "");
}

/// nativeLoadCustomDict(handle: Long, path: String)
JNIEXPORT void JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeLoadCustomDict(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring path) {

    auto *h = reinterpret_cast<PiperPlusG2pHandle *>(handle);
    JNIStringGuard pathUtf8(env, path);
    if (!pathUtf8) {
        throwG2pException(env, "path is null");
        return;
    }

    PiperPlusStatus status = piper_plus_g2p_load_custom_dict(h, pathUtf8.get());
    if (status != PIPER_PLUS_OK) {
        throwG2pException(env);
    }
}

/// nativeSetZhEnDispatch(handle: Long, enabled: Boolean)
JNIEXPORT void JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeSetZhEnDispatch(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jboolean enabled) {

    auto *h = reinterpret_cast<PiperPlusG2pHandle *>(handle);
    PiperPlusStatus status =
        piper_plus_g2p_set_zh_en_dispatch(h, enabled ? 1 : 0);
    if (status != PIPER_PLUS_OK) {
        throwG2pException(env);
    }
}

/// nativeIsZhEnDispatchEnabled(handle: Long): Boolean
JNIEXPORT jboolean JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeIsZhEnDispatchEnabled(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle) {

    auto *h = reinterpret_cast<PiperPlusG2pHandle *>(handle);
    int32_t result = piper_plus_g2p_is_zh_en_dispatch_enabled(h);
    if (result < 0) {
        throwG2pException(env);
        return JNI_FALSE;
    }
    return result == 1 ? JNI_TRUE : JNI_FALSE;
}

/// nativeVersion(): String — version of the underlying piper_plus library.
JNIEXPORT jstring JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeVersion(
        JNIEnv *env,
        jobject /* thiz */) {
    const char *v = piper_plus_version();
    return env->NewStringUTF(v ? v : "");
}

} // extern "C"
