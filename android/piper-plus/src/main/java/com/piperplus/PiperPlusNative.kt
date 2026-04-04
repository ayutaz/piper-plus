package com.piperplus

/**
 * Low-level JNI bridge to the piper-plus C API.
 *
 * All methods throw [PiperPlusException] on native errors.
 * This class is internal -- use [PiperPlus] for the public API.
 */
internal object PiperPlusNative {
    init {
        System.loadLibrary("piper_plus_jni")
    }

    /**
     * Create a native PiperPlusEngine.
     *
     * @param modelPath  Absolute path to the .onnx model file.
     * @param configPath Absolute path to the .json config, or null for auto-detect.
     * @param dictDir    Absolute path to the OpenJTalk dictionary directory, or null.
     * @return Native handle (pointer as Long). Never 0 on success.
     * @throws PiperPlusException on creation failure.
     */
    external fun nativeCreate(modelPath: String, configPath: String?, dictDir: String?): Long

    /**
     * One-shot synthesis.
     *
     * @param handle    Native engine handle from [nativeCreate].
     * @param text      Text to synthesize (UTF-8).
     * @param speakerId Speaker index (0-based).
     * @return PCM 16-bit audio samples.
     * @throws PiperPlusException on synthesis failure.
     */
    external fun nativeSynthesize(handle: Long, text: String, speakerId: Int): ShortArray

    /**
     * Start iterator-based streaming synthesis.
     *
     * @param handle    Native engine handle.
     * @param text      Text to synthesize.
     * @param speakerId Speaker index.
     * @return Sample rate in Hz.
     * @throws PiperPlusException on failure.
     */
    external fun nativeSynthStart(handle: Long, text: String, speakerId: Int): Int

    /**
     * Get the next audio chunk from the streaming iterator.
     *
     * @param handle Native engine handle.
     * @return PCM 16-bit chunk, or null when synthesis is complete.
     * @throws PiperPlusException on failure.
     */
    external fun nativeSynthNext(handle: Long): ShortArray?

    /**
     * Free the native engine. Safe to call multiple times (idempotent after first call).
     *
     * @param handle Native engine handle (0 is a no-op).
     */
    external fun nativeFree(handle: Long)

    /**
     * Query the sample rate of the loaded model.
     *
     * @param handle Native engine handle.
     * @return Sample rate in Hz (typically 22050).
     */
    external fun nativeSampleRate(handle: Long): Int

    /**
     * Query the number of speakers in the loaded model.
     *
     * @param handle Native engine handle.
     * @return Number of speakers.
     */
    external fun nativeNumSpeakers(handle: Long): Int

    /**
     * Query the number of languages in the loaded model.
     *
     * @param handle Native engine handle.
     * @return Number of languages.
     */
    external fun nativeNumLanguages(handle: Long): Int
}
