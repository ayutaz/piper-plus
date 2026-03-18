package com.github.ayousanz.piper

import android.content.Context
import com.github.ayousanz.piper.internal.NativeBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext

/**
 * Piper text-to-speech engine for Android.
 *
 * Supports 6 languages: ja, en, zh, es, fr, pt.
 *
 * Usage:
 * ```kotlin
 * val piper = PiperTts.load(config)
 * piper.use { tts ->
 *     val audio = tts.synthesize("Hello", language = "en")
 *     // play audio...
 * }
 * ```
 */
class PiperTts private constructor(
    private var nativeHandle: Long,
    val config: PiperConfig,
) : AutoCloseable {

    /** Sample rate of the loaded model (typically 22050). */
    val sampleRate: Int
        get() {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            return NativeBridge.nativeGetSampleRate(nativeHandle)
        }

    /** Number of speakers in the loaded model. */
    val numSpeakers: Int
        get() {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            return NativeBridge.nativeGetNumSpeakers(nativeHandle)
        }

    /** Number of languages in the loaded model. */
    val numLanguages: Int
        get() {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            return NativeBridge.nativeGetNumLanguages(nativeHandle)
        }

    /** Whether this engine instance is still valid. */
    val isOpen: Boolean
        get() = nativeHandle != 0L

    companion object {
        init {
            System.loadLibrary("piper_jni")
        }

        /**
         * Load a Piper TTS model from file paths.
         *
         * @param config Model configuration with file paths
         * @return Loaded PiperTts instance
         * @throws RuntimeException if model loading fails
         */
        @JvmStatic
        fun load(config: PiperConfig): PiperTts {
            require(config.modelPath.isNotEmpty()) { "modelPath must not be empty" }
            require(config.configPath.isNotEmpty()) { "configPath must not be empty" }

            val handle = NativeBridge.nativeCreate(config.modelPath, config.configPath)
            if (handle == 0L) {
                throw RuntimeException("Failed to load Piper model: ${config.modelPath}")
            }
            return PiperTts(handle, config)
        }

        /**
         * Load a Piper TTS model from Android assets.
         *
         * @param context Android context
         * @param assetModelPath Path to model within assets
         * @param assetConfigPath Path to config.json within assets
         * @return Loaded PiperTts instance
         */
        @JvmStatic
        @JvmOverloads
        fun load(
            context: Context,
            assetModelPath: String,
            assetConfigPath: String = assetModelPath.replace(".onnx", ".json"),
        ): PiperTts {
            val modelFile = context.copyAssetToInternal(assetModelPath)
            val configFile = context.copyAssetToInternal(assetConfigPath)
            return load(
                PiperConfig(
                    modelPath = modelFile.absolutePath,
                    configPath = configFile.absolutePath,
                )
            )
        }

        private fun Context.copyAssetToInternal(assetPath: String): java.io.File {
            val outFile = java.io.File(filesDir, "piper/$assetPath")
            if (!outFile.exists()) {
                outFile.parentFile?.mkdirs()
                assets.open(assetPath).use { input ->
                    outFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
            }
            return outFile
        }
    }

    /**
     * Synthesize text to audio.
     *
     * @param text Text to synthesize
     * @param language Language code (ja, en, zh, es, fr, pt)
     * @param speakerId Speaker ID (default: config.speakerId)
     * @return Generated audio data
     * @throws IllegalStateException if engine is closed
     * @throws RuntimeException on synthesis failure
     */
    @JvmOverloads
    suspend fun synthesize(
        text: String,
        language: String = "ja",
        speakerId: Int = config.speakerId,
    ): PiperAudio = withContext(Dispatchers.Default) {
        check(nativeHandle != 0L) { "PiperTts has been closed" }
        if (text.isEmpty()) return@withContext PiperAudio(ShortArray(0))

        val samples = NativeBridge.nativeSynthesize(nativeHandle, text, language, speakerId)
        PiperAudio(samples, sampleRate)
    }

    /**
     * Streaming synthesis - emits audio chunks as they are generated.
     *
     * @param text Text to synthesize
     * @param language Language code (ja, en, zh, es, fr, pt)
     * @param speakerId Speaker ID (default: config.speakerId)
     * @return Flow of audio chunks (ShortArray)
     */
    fun synthesizeStream(
        text: String,
        language: String = "ja",
        speakerId: Int = config.speakerId,
    ): Flow<ShortArray> = callbackFlow {
        check(nativeHandle != 0L) { "PiperTts has been closed" }

        NativeBridge.nativeSynthesizeStreaming(
            nativeHandle, text, language, speakerId
        ) { chunk ->
            trySend(chunk)
        }

        close()
        awaitClose()
    }.flowOn(Dispatchers.Default)

    /**
     * Release native resources.
     * Safe to call multiple times.
     */
    override fun close() {
        if (nativeHandle != 0L) {
            NativeBridge.nativeDestroy(nativeHandle)
            nativeHandle = 0L
        }
    }

    @Suppress("removal")
    protected fun finalize() {
        close()
    }
}
