package com.piperplus.tts

import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import com.piperplus.PiperPlus
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import java.util.Locale
import kotlinx.coroutines.flow.Flow

/**
 * piper-plus を Android のシステム TTS エンジンとして公開する。
 *
 * 6lang モデル 1 つが 6 言語すべてを話すため、言語切替はモデルの入れ替えでは
 * なく [SynthOptions.languageId] の変更で行う。
 *
 * このクラスは framework との境界に徹し、合成の本体は [SynthesisSession] が
 * 持つ。`SynthesisRequest` が JVM ユニットテストで組み立てられないため、
 * request をほどく責務だけをここに残している。
 */
class PiperPlusTtsService : TextToSpeechService() {

    // framework は super.onCreate() の中で既定ロケールを読むために
    // onLoadLanguage → onIsLanguageAvailable を呼ぶ。lateinit だと
    // 初期化順を 1 行動かしただけで bind 時に即死するため lazy にする。
    private val paths: ModelPaths by lazy { ModelPaths(filesDir) }

    private val engines: EngineHolder by lazy {
        EngineHolder(paths) { modelPath, configPath, dictDir ->
            NativeEngine(PiperPlus.create(this, modelPath, configPath, dictDir))
        }
    }

    private val session: SynthesisSession by lazy { SynthesisSession(paths, engines) }

    /** 直近に load された言語 (onGetLanguage が返す)。 */
    @Volatile
    private var currentIso3: String = DEFAULT_ISO3

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
        session.stop()
    }

    override fun onSynthesizeText(request: SynthesisRequest?, callback: SynthesisCallback?) {
        if (request == null || callback == null) return
        session.run(
            iso3 = request.language.orEmpty(),
            text = request.charSequenceText?.toString().orEmpty(),
            speechRate = request.speechRate,
            callback = callback,
        )
    }

    /** [PiperPlus] を [PiperPlusEngine] 境界に適合させる薄いラッパー。 */
    private class NativeEngine(private val native: PiperPlus) : PiperPlusEngine {
        override val sampleRate: Int get() = native.sampleRate

        // named argument で固定する。PiperPlus には
        // synthesizeStream(text, speakerId = 0) が併存しており、
        // 位置引数のままだと options を落とす版に黙って解決されうる
        // (コンパイルは通り、全非日本語が日本語音韻・固定速度になる)。
        override fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> =
            native.synthesizeStream(text = text, options = options)

        override fun close() = native.close()
    }

    private companion object {
        const val DEFAULT_ISO3 = "jpn"
    }
}
