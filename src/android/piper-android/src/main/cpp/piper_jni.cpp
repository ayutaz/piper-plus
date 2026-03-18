#include <jni.h>
#include <android/log.h>
#include <climits>

#include "piper_jni_utils.h"
#include "piper_engine.hpp"

// Global JavaVM pointer for callback threads
static JavaVM *g_jvm = nullptr;

// Maximum text length to prevent abuse / OOM
static constexpr size_t MAX_TEXT_LENGTH = 10000;

// Helper: safely throw via FindClass with null check
static void throwJavaException(JNIEnv *env, const char *className, const char *msg) {
    jclass cls = env->FindClass(className);
    if (cls != nullptr) {
        env->ThrowNew(cls, msg);
        env->DeleteLocalRef(cls);
    }
}

// Helper: validate text length, throw IllegalArgumentException if exceeded
static bool validateTextLength(JNIEnv *env, const std::string &text) {
    if (text.size() > MAX_TEXT_LENGTH) {
        throwJavaException(env, "java/lang/IllegalArgumentException",
                           "Text exceeds maximum length (10000 chars)");
        return false;
    }
    return true;
}

// Helper: validate speaker ID bounds, throw IllegalArgumentException if out of range
static bool validateSpeakerId(JNIEnv *env, PiperEngine *engine, jint speaker_id) {
    int numSpeakers = engine->getNumSpeakers();
    if (numSpeakers > 0 && (speaker_id < 0 || speaker_id >= numSpeakers)) {
        throwJavaException(env, "java/lang/IllegalArgumentException",
                           "speaker_id out of range");
        return false;
    }
    return true;
}

extern "C" {

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, [[maybe_unused]] void *reserved) {
    g_jvm = vm;
    PIPER_LOGI("Piper JNI library loaded (version: %s)", "0.1.0");
    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL JNI_OnUnload([[maybe_unused]] JavaVM *vm,
                                     [[maybe_unused]] void *reserved) {
    g_jvm = nullptr;
    PIPER_LOGI("Piper JNI library unloaded");
}

// --- NativeBridge JNI methods ---
// Package: com.github.ayousanz.piper.internal
// Class: NativeBridge

JNIEXPORT jlong JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeCreate(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jstring model_path,
    jstring config_path) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 0L, {
        std::string modelPath = jstringToString(env, model_path);
        std::string configPath = jstringToString(env, config_path);

        if (modelPath.empty()) {
            throwJavaException(env, "java/lang/IllegalArgumentException",
                               "modelPath must not be empty");
            return 0L;
        }
        if (configPath.empty()) {
            throwJavaException(env, "java/lang/IllegalArgumentException",
                               "configPath must not be empty");
            return 0L;
        }

        PIPER_LOGI("Creating engine: model=%s, config=%s",
                   modelPath.c_str(), configPath.c_str());

        auto *engine = new PiperEngine(modelPath, configPath);
        return reinterpret_cast<jlong>(engine);
    })
}

JNIEXPORT jshortArray JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeSynthesize(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle, jstring text,
    jstring language, jint speaker_id) {

    PIPER_JNI_TRY_CATCH_RETURN(env, nullptr, {
        if (!validateHandle(env, handle, "nativeSynthesize")) return nullptr;

        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        std::string textStr = jstringToString(env, text);
        std::string langStr = jstringToString(env, language);

        if (textStr.empty()) {
            // Return empty array for empty text
            return env->NewShortArray(0);
        }

        if (!validateTextLength(env, textStr)) return nullptr;
        if (!validateSpeakerId(env, engine, speaker_id)) return nullptr;

        PIPER_LOGI("Synthesizing: text_len=%zu, lang=%s, speaker=%d",
                   textStr.size(), langStr.c_str(), speaker_id);

        auto audioBuffer = engine->synthesize(textStr, langStr, speaker_id);

        // Integer overflow check: size_t -> jsize (int32_t)
        if (audioBuffer.size() > static_cast<size_t>(INT_MAX)) {
            throwJavaException(env, "java/lang/OutOfMemoryError",
                               "Audio buffer too large for JNI array");
            return nullptr;
        }

        // Copy to Java array
        jshortArray result = env->NewShortArray(static_cast<jsize>(audioBuffer.size()));
        if (result == nullptr) {
            // NewShortArray returns null on OOM; VM may have pending exception
            if (!env->ExceptionCheck()) {
                throwJavaException(env, "java/lang/OutOfMemoryError",
                                   "Failed to allocate audio buffer");
            }
            return nullptr;
        }
        env->SetShortArrayRegion(result, 0,
                                  static_cast<jsize>(audioBuffer.size()),
                                  audioBuffer.data());
        if (env->ExceptionCheck()) {
            // SetShortArrayRegion threw ArrayIndexOutOfBoundsException
            return nullptr;
        }
        return result;
    })
}

JNIEXPORT void JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeSynthesizeStreaming(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle, jstring text,
    jstring language, jint speaker_id, jobject callback) {

    PIPER_JNI_TRY_CATCH_VOID(env, {
        if (!validateHandle(env, handle, "nativeSynthesizeStreaming")) return;

        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        std::string textStr = jstringToString(env, text);
        std::string langStr = jstringToString(env, language);

        if (textStr.empty()) return;

        if (!validateTextLength(env, textStr)) return;
        if (!validateSpeakerId(env, engine, speaker_id)) return;

        // Get Kotlin lambda invoke method
        jclass callbackClass = env->GetObjectClass(callback);
        jmethodID invokeMethod = env->GetMethodID(callbackClass, "invoke",
                                                    "(Ljava/lang/Object;)Ljava/lang/Object;");
        // Delete local ref for callbackClass - no longer needed after GetMethodID
        env->DeleteLocalRef(callbackClass);

        if (invokeMethod == nullptr) {
            throwJavaException(env, "java/lang/RuntimeException",
                               "Failed to find callback invoke method");
            return;
        }

        // Create global ref to prevent GC during streaming
        jobject callbackRef = env->NewGlobalRef(callback);
        if (callbackRef == nullptr) {
            throwJavaException(env, "java/lang/OutOfMemoryError",
                               "Failed to create global ref for callback");
            return;
        }

        engine->synthesizeStreaming(textStr, langStr, speaker_id,
            [g_jvm_ptr = g_jvm, callbackRef, invokeMethod](
                    const std::vector<int16_t> &chunk) {
                // Attach current thread to JVM to get a valid JNIEnv*
                JNIEnv *cbEnv = nullptr;
                bool didAttach = false;
                jint getEnvResult = g_jvm_ptr->GetEnv(
                    reinterpret_cast<void **>(&cbEnv), JNI_VERSION_1_6);

                if (getEnvResult == JNI_EDETACHED) {
                    if (g_jvm_ptr->AttachCurrentThread(&cbEnv, nullptr) != JNI_OK) {
                        PIPER_LOGE("Failed to attach thread to JVM in streaming callback");
                        return;
                    }
                    didAttach = true;
                } else if (getEnvResult != JNI_OK) {
                    PIPER_LOGE("GetEnv failed in streaming callback (rc=%d)", getEnvResult);
                    return;
                }

                // Integer overflow check: size_t -> jsize (int32_t)
                if (chunk.size() > static_cast<size_t>(INT_MAX)) {
                    PIPER_LOGE("Streaming chunk too large for JNI array");
                    if (didAttach) g_jvm_ptr->DetachCurrentThread();
                    return;
                }

                // Create Java short array from chunk
                jshortArray jChunk = cbEnv->NewShortArray(static_cast<jsize>(chunk.size()));
                if (jChunk != nullptr) {
                    cbEnv->SetShortArrayRegion(jChunk, 0,
                                               static_cast<jsize>(chunk.size()),
                                               chunk.data());
                    if (!cbEnv->ExceptionCheck()) {
                        // Call Kotlin callback
                        cbEnv->CallObjectMethod(callbackRef, invokeMethod, jChunk);
                        if (cbEnv->ExceptionCheck()) {
                            PIPER_LOGE("Exception in streaming callback invoke");
                            cbEnv->ExceptionDescribe();
                            cbEnv->ExceptionClear();
                        }
                    } else {
                        PIPER_LOGE("Exception in SetShortArrayRegion (streaming)");
                        cbEnv->ExceptionDescribe();
                        cbEnv->ExceptionClear();
                    }
                    cbEnv->DeleteLocalRef(jChunk);
                } else {
                    PIPER_LOGE("Failed to allocate JNI array in streaming callback");
                    if (cbEnv->ExceptionCheck()) {
                        cbEnv->ExceptionDescribe();
                        cbEnv->ExceptionClear();
                    }
                }

                if (didAttach) {
                    g_jvm_ptr->DetachCurrentThread();
                }
            });

        env->DeleteGlobalRef(callbackRef);
    })
}

JNIEXPORT void JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeDestroy(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_VOID(env, {
        if (handle == 0L) return;

        PIPER_LOGI("Destroying engine");
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        delete engine;
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetSampleRate(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 22050, {
        if (!validateHandle(env, handle, "nativeGetSampleRate")) return 22050;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getSampleRate());
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetNumSpeakers(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 0, {
        if (!validateHandle(env, handle, "nativeGetNumSpeakers")) return 0;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getNumSpeakers());
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetNumLanguages(
    JNIEnv *env, [[maybe_unused]] jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 1, {
        if (!validateHandle(env, handle, "nativeGetNumLanguages")) return 1;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getNumLanguages());
    })
}

} // extern "C"
