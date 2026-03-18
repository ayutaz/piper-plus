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

    private val lock = Any()

    /** Sample rate of the loaded model (typically 22050). */
    val sampleRate: Int
        get() = synchronized(lock) {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            NativeBridge.nativeGetSampleRate(nativeHandle)
        }

    /** Number of speakers in the loaded model. */
    val numSpeakers: Int
        get() = synchronized(lock) {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            NativeBridge.nativeGetNumSpeakers(nativeHandle)
        }

    /** Number of languages in the loaded model. */
    val numLanguages: Int
        get() = synchronized(lock) {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            NativeBridge.nativeGetNumLanguages(nativeHandle)
        }

    /** Whether this engine instance is still valid. */
    val isOpen: Boolean
        get() = synchronized(lock) { nativeHandle != 0L }

    companion object {
        const val MAX_TEXT_LENGTH = 10_000

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
            require(!assetPath.contains("..")) { "assetPath must not contain '..'" }
            require(!assetPath.startsWith("/")) { "assetPath must not be absolute" }

            val parentDir = java.io.File(filesDir, "piper")
            val outFile = java.io.File(parentDir, assetPath)
            val canonicalParent = parentDir.canonicalPath
            require(outFile.canonicalPath.startsWith(canonicalParent)) {
                "assetPath escapes the intended directory"
            }

            if (!outFile.exists()) {
                outFile.parentFile?.mkdirs()
                val tmpFile = java.io.File.createTempFile("piper_", ".tmp", outFile.parentFile)
                try {
                    assets.open(assetPath).use { input ->
                        tmpFile.outputStream().use { output ->
                            input.copyTo(output)
                        }
                    }
                    if (!tmpFile.renameTo(outFile)) {
                        tmpFile.inputStream().use { input ->
                            outFile.outputStream().use { output ->
                                input.copyTo(output)
                            }
                        }
                    }
                } finally {
                    tmpFile.delete()
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
        require(text.length <= MAX_TEXT_LENGTH) { "Text exceeds maximum length of $MAX_TEXT_LENGTH characters" }
        require(speakerId >= 0) { "speakerId must be non-negative" }
        require(language.isNotEmpty()) { "language must not be empty" }
        if (text.isEmpty()) return@withContext PiperAudio(ShortArray(0))

        synchronized(lock) {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            val samples = NativeBridge.nativeSynthesize(nativeHandle, text, language, speakerId)
            PiperAudio(samples, sampleRate)
        }
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
        require(text.length <= MAX_TEXT_LENGTH) { "Text exceeds maximum length of $MAX_TEXT_LENGTH characters" }
        require(speakerId >= 0) { "speakerId must be non-negative" }
        require(language.isNotEmpty()) { "language must not be empty" }

        synchronized(lock) {
            check(nativeHandle != 0L) { "PiperTts has been closed" }
            try {
                NativeBridge.nativeSynthesizeStreaming(
                    nativeHandle, text, language, speakerId
                ) { chunk ->
                    trySend(chunk)
                }
                close()
            } catch (e: Exception) {
                close(e)
            }
        }

        awaitClose()
    }.flowOn(Dispatchers.Default)

    /**
     * Release native resources.
     * Safe to call multiple times.
     */
    override fun close() {
        synchronized(lock) {
            if (nativeHandle != 0L) {
                NativeBridge.nativeDestroy(nativeHandle)
                nativeHandle = 0L
            }
        }
    }
}
