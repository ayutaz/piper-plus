package com.github.ayousanz.piper

import android.content.Context
import com.github.ayousanz.piper.internal.NativeBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext

/**
 * Piper text-to-speech engine for Android.
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

    companion object {
        init {
            System.loadLibrary("piper_jni")
        }

        /**
         * Load a Piper TTS model from file paths.
         */
        @JvmStatic
        fun load(config: PiperConfig): PiperTts {
            val handle = NativeBridge.nativeCreate(config.modelPath, config.configPath)
            if (handle == 0L) {
                throw RuntimeException("Failed to load Piper model: ${config.modelPath}")
            }
            return PiperTts(handle, config)
        }

        /**
         * Load a Piper TTS model from Android assets.
         */
        @JvmStatic
        fun load(context: Context, assetModelPath: String, assetConfigPath: String): PiperTts {
            // Copy assets to internal storage for native access
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
            val outFile = java.io.File(filesDir, assetPath)
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
     */
    @JvmOverloads
    suspend fun synthesize(
        text: String,
        language: String = "ja",
        speakerId: Int = config.speakerId,
    ): PiperAudio = withContext(Dispatchers.Default) {
        check(nativeHandle != 0L) { "PiperTts has been closed" }
        val samples = NativeBridge.nativeSynthesize(nativeHandle, text, language, speakerId)
        PiperAudio(samples)
    }

    override fun close() {
        if (nativeHandle != 0L) {
            NativeBridge.nativeDestroy(nativeHandle)
            nativeHandle = 0L
        }
    }

    protected fun finalize() {
        close()
    }
}
