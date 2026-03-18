#include <jni.h>
#include <android/log.h>

#include "piper_jni_utils.h"
#include "piper_engine.hpp"

// Global JavaVM pointer for callback threads
static JavaVM *g_jvm = nullptr;

extern "C" {

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    g_jvm = vm;
    PIPER_LOGI("Piper JNI library loaded (version: %s)", "0.1.0");
    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    g_jvm = nullptr;
    PIPER_LOGI("Piper JNI library unloaded");
}

// --- NativeBridge JNI methods ---
// Package: com.github.ayousanz.piper.internal
// Class: NativeBridge

JNIEXPORT jlong JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeCreate(
    JNIEnv *env, jobject thiz, jstring model_path, jstring config_path) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 0L, {
        std::string modelPath = jstringToString(env, model_path);
        std::string configPath = jstringToString(env, config_path);

        if (modelPath.empty()) {
            env->ThrowNew(env->FindClass("java/lang/IllegalArgumentException"),
                         "modelPath must not be empty");
            return 0L;
        }
        if (configPath.empty()) {
            env->ThrowNew(env->FindClass("java/lang/IllegalArgumentException"),
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
    JNIEnv *env, jobject thiz, jlong handle, jstring text,
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

        PIPER_LOGI("Synthesizing: text_len=%zu, lang=%s, speaker=%d",
                   textStr.size(), langStr.c_str(), speaker_id);

        auto audioBuffer = engine->synthesize(textStr, langStr, speaker_id);

        // Copy to Java array
        jshortArray result = env->NewShortArray(static_cast<jsize>(audioBuffer.size()));
        if (result == nullptr) {
            env->ThrowNew(env->FindClass("java/lang/OutOfMemoryError"),
                         "Failed to allocate audio buffer");
            return nullptr;
        }
        env->SetShortArrayRegion(result, 0,
                                  static_cast<jsize>(audioBuffer.size()),
                                  audioBuffer.data());
        return result;
    })
}

JNIEXPORT void JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeSynthesizeStreaming(
    JNIEnv *env, jobject thiz, jlong handle, jstring text,
    jstring language, jint speaker_id, jobject callback) {

    PIPER_JNI_TRY_CATCH_VOID(env, {
        if (!validateHandle(env, handle, "nativeSynthesizeStreaming")) return;

        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        std::string textStr = jstringToString(env, text);
        std::string langStr = jstringToString(env, language);

        if (textStr.empty()) return;

        // Get Kotlin lambda invoke method
        jclass callbackClass = env->GetObjectClass(callback);
        jmethodID invokeMethod = env->GetMethodID(callbackClass, "invoke",
                                                    "(Ljava/lang/Object;)Ljava/lang/Object;");
        if (invokeMethod == nullptr) {
            env->ThrowNew(env->FindClass("java/lang/RuntimeException"),
                         "Failed to find callback invoke method");
            return;
        }

        // Create global ref to prevent GC during streaming
        jobject callbackRef = env->NewGlobalRef(callback);

        engine->synthesizeStreaming(textStr, langStr, speaker_id,
            [env, callbackRef, invokeMethod](const std::vector<int16_t> &chunk) {
                // Create Java short array from chunk
                jshortArray jChunk = env->NewShortArray(static_cast<jsize>(chunk.size()));
                if (jChunk != nullptr) {
                    env->SetShortArrayRegion(jChunk, 0,
                                              static_cast<jsize>(chunk.size()),
                                              chunk.data());
                    // Call Kotlin callback
                    env->CallObjectMethod(callbackRef, invokeMethod, jChunk);
                    env->DeleteLocalRef(jChunk);
                }
            });

        env->DeleteGlobalRef(callbackRef);
    })
}

JNIEXPORT void JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeDestroy(
    JNIEnv *env, jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_VOID(env, {
        if (handle == 0L) return;

        PIPER_LOGI("Destroying engine");
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        delete engine;
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetSampleRate(
    JNIEnv *env, jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 22050, {
        if (!validateHandle(env, handle, "nativeGetSampleRate")) return 22050;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getSampleRate());
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetNumSpeakers(
    JNIEnv *env, jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 0, {
        if (!validateHandle(env, handle, "nativeGetNumSpeakers")) return 0;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getNumSpeakers());
    })
}

JNIEXPORT jint JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeGetNumLanguages(
    JNIEnv *env, jobject thiz, jlong handle) {

    PIPER_JNI_TRY_CATCH_RETURN(env, 1, {
        if (!validateHandle(env, handle, "nativeGetNumLanguages")) return 1;
        auto *engine = reinterpret_cast<PiperEngine *>(handle);
        return static_cast<jint>(engine->getNumLanguages());
    })
}

} // extern "C"
