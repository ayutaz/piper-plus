package com.piperplus

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.coroutineContext

/**
 * High-level Kotlin API for piper-plus neural text-to-speech.
 *
 * Wraps the native C engine via JNI. Implements [AutoCloseable] so that
 * the native resources are freed when the instance goes out of scope
 * (e.g. via Kotlin `use {}` blocks).
 *
 * Thread safety: All public methods that touch the native engine are
 * `synchronized(this)` because the C API is single-threaded per engine.
 *
 * Usage:
 * ```kotlin
 * PiperPlus.create(context, "model.onnx").use { tts ->
 *     val audio = tts.synthesize("Hello, world!")
 *     // play audio via AudioTrack...
 * }
 * ```
 *
 * For streaming (sentence-by-sentence) synthesis:
 * ```kotlin
 * PiperPlus.create(context, "model.onnx").use { tts ->
 *     tts.synthesizeStream("Long text here...").collect { chunk ->
 *         // play each chunk as it arrives
 *     }
 * }
 * ```
 *
 * @property sampleRate Audio sample rate in Hz (typically 22050).
 * @property numSpeakers Number of speakers available in the model.
 * @property numLanguages Number of languages available in the model.
 */
class PiperPlus private constructor(
    private var nativeHandle: Long
) : AutoCloseable {

    /**
     * Lock object for all native engine access.
     * The C API is NOT thread-safe per engine, so every call must be serialised.
     */
    private val lock = Any()

    /** Whether a streaming synthesis is currently in progress. */
    @Volatile
    private var synthesizing = false

    /** Sample rate of the loaded model in Hz. */
    val sampleRate: Int
        get() = synchronized(lock) {
            checkNotClosed()
            PiperPlusNative.nativeSampleRate(nativeHandle)
        }

    /** Number of speakers available in the loaded model. */
    val numSpeakers: Int
        get() = synchronized(lock) {
            checkNotClosed()
            PiperPlusNative.nativeNumSpeakers(nativeHandle)
        }

    /** Number of languages available in the loaded model. */
    val numLanguages: Int
        get() = synchronized(lock) {
            checkNotClosed()
            PiperPlusNative.nativeNumLanguages(nativeHandle)
        }

    companion object {
        /** Default subdirectory name for the OpenJTalk dictionary inside app files. */
        private const val DICT_ASSET_DIR = "open_jtalk_dic"

        /**
         * Create a [PiperPlus] instance from a model file.
         *
         * If the model and config are bundled in the app's assets directory,
         * they must first be copied to internal storage (assets are not
         * accessible by native code via file paths).
         *
         * @param context    Android context (used for asset extraction).
         * @param modelPath  Absolute path to the .onnx model file.
         * @param configPath Absolute path to the .json config, or null for
         *                   auto-detect (looks for modelPath + ".json").
         * @param dictDir    Absolute path to the OpenJTalk dictionary directory,
         *                   or null to auto-extract from assets.
         * @return A new [PiperPlus] instance. Caller must call [close] when done.
         * @throws PiperPlusException if model loading fails.
         */
        @JvmStatic
        @JvmOverloads
        fun create(
            context: Context,
            modelPath: String,
            configPath: String? = null,
            dictDir: String? = null
        ): PiperPlus {
            val resolvedDictDir = dictDir ?: extractDictIfNeeded(context)
            val handle = PiperPlusNative.nativeCreate(modelPath, configPath, resolvedDictDir)
            return PiperPlus(handle)
        }

        /**
         * Extract the OpenJTalk dictionary from assets to internal storage
         * if it has not been extracted yet.
         *
         * @return Absolute path to the extracted dictionary directory.
         */
        private fun extractDictIfNeeded(context: Context): String? {
            val destDir = File(context.filesDir, DICT_ASSET_DIR)
            if (destDir.exists() && destDir.isDirectory) {
                val files = destDir.listFiles()
                if (files != null && files.isNotEmpty()) {
                    return destDir.absolutePath
                }
            }

            // Attempt to extract from assets. If the assets directory does
            // not contain the dictionary, return null and let the C API
            // auto-detect or fail gracefully.
            return try {
                val assetFiles = context.assets.list(DICT_ASSET_DIR)
                if (assetFiles.isNullOrEmpty()) return null

                destDir.mkdirs()
                for (filename in assetFiles) {
                    context.assets.open("$DICT_ASSET_DIR/$filename").use { input ->
                        FileOutputStream(File(destDir, filename)).use { output ->
                            input.copyTo(output)
                        }
                    }
                }
                destDir.absolutePath
            } catch (_: Exception) {
                null
            }
        }
    }

    /**
     * Synthesize text to audio in one shot.
     *
     * @param text      Text to synthesize (UTF-8). May contain multiple sentences.
     * @param speakerId Speaker index (0-based, default 0).
     * @return PCM 16-bit audio samples at [sampleRate] Hz.
     * @throws PiperPlusException on synthesis failure.
     * @throws IllegalStateException if the engine has been closed.
     */
    fun synthesize(text: String, speakerId: Int = 0): ShortArray {
        synchronized(lock) {
            checkNotClosed()
            return PiperPlusNative.nativeSynthesize(nativeHandle, text, speakerId)
        }
    }

    /**
     * Synthesize text to audio as a [Flow] of chunks (sentence-by-sentence).
     *
     * Each emitted [ShortArray] is one sentence's worth of PCM 16-bit audio.
     * The flow completes when all sentences have been synthesized.
     *
     * Collection runs on [Dispatchers.IO] by default.
     * The flow is cancellation-safe: if the collector cancels (e.g. the
     * coroutine is cancelled), the [synthesizing] flag is always reset
     * via try-finally so that subsequent calls are not blocked.
     *
     * @param text      Text to synthesize (UTF-8). Will be split into sentences.
     * @param speakerId Speaker index (0-based, default 0).
     * @return Cold [Flow] of PCM 16-bit audio chunks.
     * @throws PiperPlusException on synthesis failure.
     * @throws IllegalStateException if the engine has been closed.
     */
    fun synthesizeStream(text: String, speakerId: Int = 0): Flow<ShortArray> = flow {
        synchronized(lock) {
            checkNotClosed()
            check(!synthesizing) { "A streaming synthesis is already in progress" }
            synthesizing = true
        }
        try {
            synchronized(lock) {
                PiperPlusNative.nativeSynthStart(nativeHandle, text, speakerId)
            }

            while (true) {
                // Check for coroutine cancellation between chunks so that
                // a cancelled collector does not keep driving the native iterator.
                coroutineContext.ensureActive()

                val chunk = synchronized(lock) {
                    PiperPlusNative.nativeSynthNext(nativeHandle)
                } ?: break
                emit(chunk)
            }
        } finally {
            synthesizing = false
        }
    }.flowOn(Dispatchers.IO)

    /**
     * Release native resources. Safe to call multiple times.
     *
     * After calling [close], all other methods will throw [IllegalStateException].
     */
    override fun close() {
        synchronized(lock) {
            val handle = nativeHandle
            if (handle != 0L) {
                nativeHandle = 0L
                PiperPlusNative.nativeFree(handle)
            }
        }
    }

    private fun checkNotClosed() {
        check(nativeHandle != 0L) { "PiperPlus engine has been closed" }
    }
}
