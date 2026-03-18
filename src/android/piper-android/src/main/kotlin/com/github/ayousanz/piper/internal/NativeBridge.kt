package com.github.ayousanz.piper.internal

/**
 * JNI bridge to the native Piper C++ engine.
 * Internal API - do not use directly.
 */
internal object NativeBridge {

    external fun nativeCreate(modelPath: String, configPath: String): Long

    external fun nativeSynthesize(
        handle: Long,
        text: String,
        language: String,
        speakerId: Int,
    ): ShortArray

    external fun nativeDestroy(handle: Long)
}
