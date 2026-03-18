#ifndef PIPER_JNI_UTILS_H_
#define PIPER_JNI_UTILS_H_

#include <jni.h>
#include <string>
#include <android/log.h>

#define PIPER_LOG_TAG "PiperJNI"
#define PIPER_LOGI(...) __android_log_print(ANDROID_LOG_INFO, PIPER_LOG_TAG, __VA_ARGS__)
#define PIPER_LOGW(...) __android_log_print(ANDROID_LOG_WARN, PIPER_LOG_TAG, __VA_ARGS__)
#define PIPER_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, PIPER_LOG_TAG, __VA_ARGS__)

// Exception-safe JNI wrapper macro.
// Catches C++ exceptions and converts them to Java RuntimeException.
#define PIPER_JNI_TRY_CATCH_RETURN(env, returnOnError, block) \
    try { \
        block \
    } catch (const Ort::Exception& e) { \
        PIPER_LOGE("ONNX Runtime error: %s", e.what()); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, e.what()); \
        } \
        return returnOnError; \
    } catch (const std::exception& e) { \
        PIPER_LOGE("Native error: %s", e.what()); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, e.what()); \
        } \
        return returnOnError; \
    } catch (...) { \
        PIPER_LOGE("Unknown native error"); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, "Unknown native error in Piper JNI"); \
        } \
        return returnOnError; \
    }

// Void version (no return value)
#define PIPER_JNI_TRY_CATCH_VOID(env, block) \
    try { \
        block \
    } catch (const Ort::Exception& e) { \
        PIPER_LOGE("ONNX Runtime error: %s", e.what()); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, e.what()); \
        } \
        return; \
    } catch (const std::exception& e) { \
        PIPER_LOGE("Native error: %s", e.what()); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, e.what()); \
        } \
        return; \
    } catch (...) { \
        PIPER_LOGE("Unknown native error"); \
        jclass cls = env->FindClass("java/lang/RuntimeException"); \
        if (cls != nullptr) { \
            env->ThrowNew(cls, "Unknown native error in Piper JNI"); \
        } \
        return; \
    }

// Helper: Convert jstring to std::string (UTF-8)
inline std::string jstringToString(JNIEnv *env, jstring jstr) {
    if (jstr == nullptr) return "";
    const char *chars = env->GetStringUTFChars(jstr, nullptr);
    std::string result(chars);
    env->ReleaseStringUTFChars(jstr, chars);
    return result;
}

// Helper: Validate native handle, throw NullPointerException if invalid
inline bool validateHandle(JNIEnv *env, jlong handle, const char *funcName) {
    if (handle == 0L) {
        PIPER_LOGE("%s: null native handle", funcName);
        jclass cls = env->FindClass("java/lang/NullPointerException");
        if (cls != nullptr) {
            env->ThrowNew(cls, "Piper engine has been closed or was not initialized");
        }
        return false;
    }
    return true;
}

#endif // PIPER_JNI_UTILS_H_
