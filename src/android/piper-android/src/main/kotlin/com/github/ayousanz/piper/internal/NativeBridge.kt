package com.github.ayousanz.piper.internal

/**
 * JNI bridge to the native Piper C++ engine.
 * Internal API - do not use directly.
 *
 * ## Handle lifetime
 * All functions that accept a [Long] handle require a valid, non-zero handle
 * previously returned by [nativeCreate]. Passing zero or an already-destroyed
 * handle results in undefined behaviour (likely a native crash).
 * Callers must ensure that [nativeDestroy] is called exactly once for each
 * handle, and that no other method is invoked on that handle after destruction.
 */
internal object NativeBridge {

    /**
     * Create a native Piper engine instance.
     *
     * The returned handle owns native memory and **must** be released by calling
     * [nativeDestroy] when it is no longer needed. Failing to do so will leak
     * the underlying C++ objects and ONNX Runtime session.
     *
     * @param modelPath Path to the ONNX model file
     * @param configPath Path to the config.json file
     * @return Native handle (pointer), or 0 on failure
     */
    external fun nativeCreate(modelPath: String, configPath: String): Long

    /**
     * Synthesize text to audio samples.
     *
     * The [handle] must be a live handle returned by [nativeCreate] that has not
     * yet been passed to [nativeDestroy].
     *
     * @param handle Native engine handle
     * @param text Text to synthesize
     * @param language Language code (e.g. "ja", "en")
     * @param speakerId Speaker ID
     * @return PCM audio samples (16-bit signed, mono)
     */
    external fun nativeSynthesize(
        handle: Long,
        text: String,
        language: String,
        speakerId: Int,
    ): ShortArray

    /**
     * Streaming synthesis with chunk callback.
     *
     * The [handle] must be a live handle returned by [nativeCreate] that has not
     * yet been passed to [nativeDestroy].
     *
     * **Thread-safety:** The [callback] may be invoked from a native background
     * thread. Implementations must be thread-safe -- in particular, any shared
     * mutable state accessed inside the callback must be properly synchronised.
     *
     * @param handle Native engine handle
     * @param text Text to synthesize
     * @param language Language code
     * @param speakerId Speaker ID
     * @param callback Called for each audio chunk (ShortArray). Must be thread-safe.
     */
    external fun nativeSynthesizeStreaming(
        handle: Long,
        text: String,
        language: String,
        speakerId: Int,
        callback: (ShortArray) -> Unit,
    )

    /**
     * Destroy a native Piper engine instance and release all associated resources.
     *
     * After this call the [handle] is invalid and must not be used again.
     * Calling this method more than once for the same handle is undefined behaviour.
     *
     * @param handle Native engine handle
     */
    external fun nativeDestroy(handle: Long)

    /**
     * Get sample rate of the loaded model.
     *
     * @param handle A live native engine handle.
     */
    external fun nativeGetSampleRate(handle: Long): Int

    /**
     * Get number of speakers in the loaded model.
     *
     * @param handle A live native engine handle.
     */
    external fun nativeGetNumSpeakers(handle: Long): Int

    /**
     * Get number of languages in the loaded model.
     *
     * @param handle A live native engine handle.
     */
    external fun nativeGetNumLanguages(handle: Long): Int
}
