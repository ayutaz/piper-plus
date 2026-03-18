package com.github.ayousanz.piper.internal

/**
 * JNI bridge to the native Piper C++ engine.
 * Internal API - do not use directly.
 */
internal object NativeBridge {

    /**
     * Create a native Piper engine instance.
     * @param modelPath Path to the ONNX model file
     * @param configPath Path to the config.json file
     * @return Native handle (pointer), or 0 on failure
     */
    external fun nativeCreate(modelPath: String, configPath: String): Long

    /**
     * Synthesize text to audio samples.
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
     * @param handle Native engine handle
     * @param text Text to synthesize
     * @param language Language code
     * @param speakerId Speaker ID
     * @param callback Called for each audio chunk (ShortArray)
     */
    external fun nativeSynthesizeStreaming(
        handle: Long,
        text: String,
        language: String,
        speakerId: Int,
        callback: (ShortArray) -> Unit,
    )

    /**
     * Destroy a native Piper engine instance.
     * @param handle Native engine handle
     */
    external fun nativeDestroy(handle: Long)

    /** Get sample rate of the loaded model. */
    external fun nativeGetSampleRate(handle: Long): Int

    /** Get number of speakers in the loaded model. */
    external fun nativeGetNumSpeakers(handle: Long): Int

    /** Get number of languages in the loaded model. */
    external fun nativeGetNumLanguages(handle: Long): Int
}
