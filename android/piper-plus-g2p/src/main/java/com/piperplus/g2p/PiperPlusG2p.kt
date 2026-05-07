package com.piperplus.g2p

import android.content.Context

/**
 * Engine-less multilingual G2P (text → phoneme) for Android.
 *
 * Wraps the C API entrypoints `piper_plus_g2p_*` (Issue #388). No ONNX model
 * is required — all 8 supported languages (`ja`, `en`, `zh`, `ko`, `es`, `fr`,
 * `pt`, `sv`) work with the data embedded in `libpiper_plus.so`. Only the
 * Japanese path additionally requires an OpenJTalk dictionary, supplied via
 * [OpenJTalkDictionary].
 *
 * ## Threading
 *
 * Each instance is single-threaded. Calls to [phonemize] / [loadCustomDict] /
 * [setZhEnDispatchEnabled] are guarded by `@Synchronized`, but you should
 * still treat one [PiperPlusG2p] as if it were owned by a single thread —
 * the synchronization just protects against accidental misuse, not as a
 * concurrency primitive. Use multiple instances when you need parallelism.
 *
 * ## Lifecycle
 *
 * Always close the instance to release the native handle:
 * ```
 * PiperPlusG2p.create(context).use { g2p ->
 *     val result = g2p.phonemize("Hello world", "en")
 * }
 * ```
 *
 * After [close] subsequent calls throw [IllegalStateException].
 */
class PiperPlusG2p private constructor(
    @Volatile private var nativeHandle: Long,
) : AutoCloseable {

    /**
     * Phonemize text into a [PhonemeResult].
     *
     * @param text     Input UTF-8 text. Empty / whitespace yields zero
     *                 phonemes (`numPhonemes == 0`) without error.
     * @param language ISO-style language code (`"en"`, `"ja"`, ...). Pass
     *                 `null` to enable Unicode-script auto-detection.
     * @throws IllegalStateException if this instance has been closed.
     * @throws PiperPlusG2pException if the native call fails (e.g. unknown
     *                               language code).
     */
    @Synchronized
    @JvmOverloads
    fun phonemize(text: String, language: String? = null): PhonemeResult {
        val handle = requireOpen()
        val triple = PiperPlusG2pNative.nativePhonemize(handle, text, language)
        val phonemes = triple[0]
        val resolvedLang = triple[1]
        val numPhonemes = triple[2].toIntOrNull() ?: 0
        val list = if (phonemes.isEmpty()) {
            emptyList()
        } else {
            // Defensive: wrap with toList() so the returned List<String> is
            // a fresh immutable copy — callers can't mutate our internals via
            // a downcast.
            phonemes.split(' ').filter { it.isNotEmpty() }.toList()
        }
        return PhonemeResult(
            phonemes = phonemes,
            phonemeList = java.util.Collections.unmodifiableList(list),
            language = resolvedLang,
            numPhonemes = numPhonemes,
        )
    }

    /**
     * Available language codes (sorted alphabetically) supported by this
     * instance. Currently always returns the eight built-in languages.
     */
    @Synchronized
    fun availableLanguages(): List<String> {
        val handle = requireOpen()
        val codes = PiperPlusG2pNative.nativeAvailableLanguages(handle)
        if (codes.isEmpty()) return emptyList()
        return codes.split(',').filter { it.isNotEmpty() }
    }

    /**
     * Load (or replace) a custom dictionary from a JSON file (v1.0 / v2.0
     * schema). The new entries take effect on the next [phonemize] call.
     */
    @Synchronized
    fun loadCustomDict(path: String) {
        val handle = requireOpen()
        PiperPlusG2pNative.nativeLoadCustomDict(handle, path)
    }

    /**
     * Toggle the ZH-EN code-switching dispatch path (Issue #384). When
     * enabled (default), an English token sandwiched between Chinese
     * segments is phonemized as Mandarin pinyin (e.g. "GPS" → 三个声母…).
     */
    @Synchronized
    fun setZhEnDispatchEnabled(enabled: Boolean) {
        val handle = requireOpen()
        PiperPlusG2pNative.nativeSetZhEnDispatch(handle, enabled)
    }

    /** Returns whether ZH-EN dispatch is currently enabled. */
    @Synchronized
    fun isZhEnDispatchEnabled(): Boolean {
        val handle = requireOpen()
        return PiperPlusG2pNative.nativeIsZhEnDispatchEnabled(handle)
    }

    /** Underlying piper-plus C library version. */
    @Synchronized
    fun version(): String = PiperPlusG2pNative.nativeVersion()

    /** Free the native handle. Idempotent. */
    @Synchronized
    override fun close() {
        val handle = nativeHandle
        if (handle != 0L) {
            nativeHandle = 0L
            PiperPlusG2pNative.nativeFree(handle)
        }
    }

    private fun requireOpen(): Long {
        val handle = nativeHandle
        check(handle != 0L) { "PiperPlusG2p has been closed" }
        return handle
    }

    companion object {
        /**
         * Create a new G2P instance.
         *
         * @param context     Application context (used internally only when
         *                    [dictionary] needs to be extracted from assets).
         * @param dictionary  Optional handle to an extracted OpenJTalk
         *                    dictionary. Required for Japanese; the other
         *                    seven languages work without it.
         * @throws PiperPlusG2pException if native initialisation fails.
         */
        @JvmStatic
        @JvmOverloads
        fun create(
            context: Context,
            dictionary: OpenJTalkDictionary? = null,
        ): PiperPlusG2p {
            // Hold a reference to the application context so we participate
            // in the standard Android lifecycle — even though the current
            // native bridge does not need to read from it directly. This
            // also keeps the API symmetric with the TTS module.
            context.applicationContext
            val handle = PiperPlusG2pNative.nativeCreate(dictionary?.path)
            if (handle == 0L) {
                throw PiperPlusG2pException(
                    "PiperPlusG2pNative.nativeCreate returned 0",
                )
            }
            return PiperPlusG2p(handle)
        }
    }
}
