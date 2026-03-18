package com.github.ayousanz.piper

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import android.util.Log
import kotlinx.coroutines.runBlocking
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Android TextToSpeechService implementation for Piper TTS.
 *
 * Register in AndroidManifest.xml:
 * ```xml
 * <service android:name=".PiperTtsService" android:exported="true">
 *     <intent-filter>
 *         <action android:name="android.intent.action.TTS_SERVICE" />
 *         <category android:name="android.intent.category.DEFAULT" />
 *     </intent-filter>
 *     <meta-data android:name="android.speech.tts" android:resource="@xml/tts_engine" />
 * </service>
 * ```
 */
class PiperTtsService : TextToSpeechService() {

    companion object {
        private const val TAG = "PiperTtsService"

        // Supported languages (ISO 639-1)
        private val SUPPORTED_LANGUAGES = setOf("ja", "en", "zh", "es", "fr", "pt")

        // ISO 639-1 to ISO 639-2/T mapping for Android TTS
        private val LANG_TO_ISO3 = mapOf(
            "ja" to "jpn", "en" to "eng", "zh" to "zho",
            "es" to "spa", "fr" to "fra", "pt" to "por",
        )
    }

    private var engine: PiperTts? = null
    private var currentLanguage: String = "ja"

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "PiperTtsService created")
        // Engine will be lazily initialized on first synthesis request
        // to avoid blocking the main thread during startup.
    }

    private fun ensureEngine(): PiperTts {
        engine?.let { return it }

        // Look for model in internal storage
        val modelDir = filesDir.resolve("piper")
        val modelFile = modelDir.listFiles()?.firstOrNull { it.name.endsWith(".onnx") }
        val configFile = modelDir.listFiles()?.firstOrNull { it.name.endsWith(".json") }

        if (modelFile == null || configFile == null) {
            throw IllegalStateException(
                "No Piper model found in ${modelDir.absolutePath}. " +
                "Copy a .onnx model and .json config to this directory."
            )
        }

        val config = PiperConfig(
            modelPath = modelFile.absolutePath,
            configPath = configFile.absolutePath,
        )

        return PiperTts.load(config).also {
            engine = it
            Log.i(TAG, "Engine loaded: ${modelFile.name}")
        }
    }

    override fun onIsLanguageAvailable(lang: String, country: String?, variant: String?): Int {
        val normalizedLang = lang.lowercase().take(2)
        return if (normalizedLang in SUPPORTED_LANGUAGES) {
            TextToSpeech.LANG_AVAILABLE
        } else {
            TextToSpeech.LANG_NOT_SUPPORTED
        }
    }

    override fun onGetLanguage(): Array<String> {
        val iso3 = LANG_TO_ISO3[currentLanguage] ?: "jpn"
        return arrayOf(currentLanguage, iso3, "")
    }

    override fun onLoadLanguage(lang: String, country: String?, variant: String?): Int {
        val result = onIsLanguageAvailable(lang, country, variant)
        if (result >= TextToSpeech.LANG_AVAILABLE) {
            currentLanguage = lang.lowercase().take(2)
            Log.i(TAG, "Language set to: $currentLanguage")
        }
        return result
    }

    override fun onSynthesizeText(request: SynthesisRequest, callback: SynthesisCallback) {
        val text = request.charSequenceText?.toString()
        if (text.isNullOrBlank()) {
            callback.done()
            return
        }

        try {
            val tts = ensureEngine()
            val lang = request.language?.lowercase()?.take(2) ?: currentLanguage

            val audio = runBlocking {
                tts.synthesize(text, language = lang)
            }

            val sampleRate = audio.sampleRate
            callback.start(sampleRate, AudioFormat.ENCODING_PCM_16BIT, 1)

            // Convert ShortArray to ByteArray (little-endian)
            val byteBuffer = ByteBuffer.allocate(audio.samples.size * 2)
                .order(ByteOrder.LITTLE_ENDIAN)
            for (sample in audio.samples) {
                byteBuffer.putShort(sample)
            }
            val bytes = byteBuffer.array()

            // Send in chunks respecting maxBufferSize
            val maxBytes = callback.maxBufferSize
            var offset = 0
            while (offset < bytes.size) {
                val size = minOf(maxBytes, bytes.size - offset)
                callback.audioAvailable(bytes, offset, size)
                offset += size
            }

            callback.done()

        } catch (e: Exception) {
            Log.e(TAG, "Synthesis failed", e)
            callback.error()
        }
    }

    override fun onStop() {
        Log.i(TAG, "onStop called")
        // Current synthesis is synchronous, so nothing to cancel
    }

    override fun onDestroy() {
        engine?.close()
        engine = null
        Log.i(TAG, "PiperTtsService destroyed")
        super.onDestroy()
    }
}
