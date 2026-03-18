#include <jni.h>
#include <string>
#include <android/log.h>

#define LOG_TAG "PiperJNI"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Piper engine wrapper - will be implemented in Phase 2
// Forward declarations for piper core
// #include "piper.hpp"

extern "C" {

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    LOGI("Piper JNI library loaded");
    return JNI_VERSION_1_6;
}

JNIEXPORT jlong JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeCreate(
    JNIEnv *env, jobject thiz, jstring model_path, jstring config_path) {
    // TODO: Phase 2 implementation
    LOGI("nativeCreate called");
    return 0L;
}

JNIEXPORT jshortArray JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeSynthesize(
    JNIEnv *env, jobject thiz, jlong handle, jstring text,
    jstring language, jint speaker_id) {
    // TODO: Phase 2 implementation
    LOGI("nativeSynthesize called");
    return env->NewShortArray(0);
}

JNIEXPORT void JNICALL
Java_com_github_ayousanz_piper_internal_NativeBridge_nativeDestroy(
    JNIEnv *env, jobject thiz, jlong handle) {
    // TODO: Phase 2 implementation
    LOGI("nativeDestroy called");
}

} // extern "C"
