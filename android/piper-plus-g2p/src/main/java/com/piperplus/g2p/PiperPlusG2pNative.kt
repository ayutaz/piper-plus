package com.piperplus.g2p

/**
 * Internal JNI bridge for `libpiper_plus_g2p_jni.so`.
 *
 * Exposed for testability — public app code should only touch [PiperPlusG2p].
 * All methods on this class are 1:1 wrappers around the C API exports declared
 * in `piper_plus.h` (see `piper_plus_g2p_*` functions).
 *
 * @suppress
 */
internal object PiperPlusG2pNative {

    init {
        System.loadLibrary("piper_plus")
        System.loadLibrary("piper_plus_g2p_jni")
    }

    /**
     * Create an engine-less G2P handle.
     *
     * @param dictDir Optional path to a directory containing the OpenJTalk
     *                dictionary and/or `cmudict_data.json` /
     *                `pinyin_single.json` / `pinyin_phrases.json`. Pass null
     *                for auto-detect-only behaviour.
     * @return Native handle (cast from a C pointer).
     * @throws PiperPlusG2pException on creation failure.
     */
    @JvmStatic external fun nativeCreate(dictDir: String?): Long

    /** Free a handle returned by [nativeCreate]. Safe with handle=0. */
    @JvmStatic external fun nativeFree(handle: Long)

    /**
     * Phonemize a string of text.
     *
     * @return A `String[3]` with `[phonemes, language, numPhonemesAsString]`.
     *         The wrapper class converts this back to [PhonemeResult].
     * @throws PiperPlusG2pException if the C API returns an error.
     */
    @JvmStatic external fun nativePhonemize(
        handle: Long,
        text: String,
        language: String?,
    ): Array<String>

    /** Comma-separated list of available language codes. */
    @JvmStatic external fun nativeAvailableLanguages(handle: Long): String

    /** Load (or replace) a custom dictionary from a JSON file. */
    @JvmStatic external fun nativeLoadCustomDict(handle: Long, path: String)

    /** Toggle the ZH-EN code-switching dispatch path (Issue #384). */
    @JvmStatic external fun nativeSetZhEnDispatch(handle: Long, enabled: Boolean)

    /** Query whether ZH-EN dispatch is enabled. */
    @JvmStatic external fun nativeIsZhEnDispatchEnabled(handle: Long): Boolean

    /** Underlying piper-plus C library version (e.g. "1.12.0"). */
    @JvmStatic external fun nativeVersion(): String
}
