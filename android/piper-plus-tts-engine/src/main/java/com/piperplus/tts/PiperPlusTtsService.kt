package com.piperplus.tts

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import android.util.Log
import com.piperplus.PiperPlus
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.runBlocking

/**
 * piper-plus を Android のシステム TTS エンジンとして公開する。
 *
 * 6lang モデル 1 つが 6 言語すべてを話すため、言語切替はモデルの入れ替えでは
 * なく [SynthOptions.languageId] の変更で行う。
 */
class PiperPlusTtsService : TextToSpeechService() {

    private lateinit var paths: ModelPaths
    private lateinit var engines: EngineHolder

    /** 現在の合成を中断するためのフラグ。onStop から立てる。 */
    private val stopRequested = AtomicBoolean(false)

    /** 直近に load された言語 (onGetLanguage が返す)。 */
    @Volatile
    private var currentIso3: String = DEFAULT_ISO3

    override fun onCreate() {
        paths = ModelPaths(filesDir)
        engines = EngineHolder(paths) { modelPath, configPath, dictDir ->
            NativeEngine(PiperPlus.create(this, modelPath, configPath, dictDir))
        }
        // super.onCreate() は onGetLanguage を呼ぶため、初期化の後に呼ぶ。
        super.onCreate()
    }

    override fun onDestroy() {
        engines.release()
        super.onDestroy()
    }

    override fun onIsLanguageAvailable(lang: String?, country: String?, variant: String?): Int =
        LocaleResolver.availability(
            lang.orEmpty(),
            paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID),
        )

    override fun onLoadLanguage(lang: String?, country: String?, variant: String?): Int {
        val result = onIsLanguageAvailable(lang, country, variant)
        if (result == TextToSpeech.LANG_AVAILABLE) {
            currentIso3 = lang.orEmpty().lowercase(Locale.ROOT)
        }
        return result
    }

    override fun onGetLanguage(): Array<String> = arrayOf(currentIso3, "", "")

    override fun onStop() {
        stopRequested.set(true)
    }

    override fun onSynthesizeText(request: SynthesisRequest?, callback: SynthesisCallback?) {
        if (request == null || callback == null) return
        stopRequested.set(false)

        val iso3 = request.language.orEmpty()
        val languageId = LocaleResolver.languageIdOf(iso3)
        if (languageId == null) {
            callback.error(TextToSpeech.ERROR_INVALID_REQUEST)
            return
        }
        if (!paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID)) {
            callback.error(TextToSpeech.ERROR_NOT_INSTALLED_YET)
            return
        }

        val text = request.charSequenceText?.toString().orEmpty()
        if (text.isBlank()) {
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)
            callback.done()
            return
        }

        val options = SynthOptions(
            languageId = languageId,
            lengthScale = SynthesisParams.lengthScaleOf(request.speechRate),
        )

        try {
            val engine = engines.acquire(ModelPaths.DEFAULT_MODEL_ID)
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)

            runBlocking {
                // takeWhile で打ち切ることで、onStop 後に残りのチャンクを
                // 生成し続けないようにする (collect 内の早期 return では
                // 上流の生成が止まらない)。
                engine.synthesizeStream(text, options)
                    .takeWhile { !stopRequested.get() }
                    .collect { chunk -> emitChunk(callback, chunk) }
            }
            callback.done()
        } catch (e: Exception) {
            // ネイティブ層の失敗でサービスを落とさない。
            Log.e(TAG, "Synthesis failed", e)
            callback.error(TextToSpeech.ERROR_SERVICE)
        }
    }

    /**
     * PCM チャンクを [SynthesisCallback.getMaxBufferSize] 以下に分割して渡す。
     *
     * ShortArray を little-endian の ByteArray に詰め替える。
     */
    private fun emitChunk(callback: SynthesisCallback, chunk: ShortArray) {
        val bytes = ByteArray(chunk.size * BYTES_PER_SAMPLE)
        for (i in chunk.indices) {
            val value = chunk[i].toInt()
            bytes[i * BYTES_PER_SAMPLE] = (value and 0xFF).toByte()
            bytes[i * BYTES_PER_SAMPLE + 1] = ((value shr 8) and 0xFF).toByte()
        }

        val maxBufferSize = callback.maxBufferSize
        var offset = 0
        while (offset < bytes.size) {
            if (stopRequested.get()) return
            val length = minOf(maxBufferSize, bytes.size - offset)
            callback.audioAvailable(bytes, offset, length)
            offset += length
        }
    }

    /** [PiperPlus] を [PiperPlusEngine] 境界に適合させる薄いラッパー。 */
    private class NativeEngine(private val native: PiperPlus) : PiperPlusEngine {
        override fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> =
            native.synthesizeStream(text, options)

        override fun close() = native.close()
    }

    private companion object {
        const val TAG = "PiperPlusTts"
        const val SAMPLE_RATE = 22050
        const val CHANNEL_COUNT = 1
        const val BYTES_PER_SAMPLE = 2
        const val DEFAULT_ISO3 = "jpn"
    }
}
