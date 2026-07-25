package com.piperplus.tts

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.TextToSpeech
import android.util.Log
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.runBlocking

/**
 * 1 発話分の合成を実行する。
 *
 * [PiperPlusTtsService] から切り出してあるのは、`android.speech.tts.SynthesisRequest`
 * が final かつ全 getter が実装を持たないスタブで、JVM ユニットテストでは
 * 中身を差し替えられないため。request をほどいた形の引数を受けることで、
 * 合成の本体を Service を起動せずに検証できる。
 *
 * 停止フラグはこのクラスが所有する。[run] の入口でリセットするため、
 * 前回の [stop] が次の発話に持ち越されない。
 */
internal class SynthesisSession(
    private val paths: ModelPaths,
    private val engines: EngineHolder,
    private val modelId: String = ModelPaths.DEFAULT_MODEL_ID,
) {

    private val stopRequested = AtomicBoolean(false)

    /** 進行中の合成を打ち切る。[PiperPlusTtsService.onStop] から呼ばれる。 */
    fun stop() {
        stopRequested.set(true)
    }

    /**
     * 1 発話を合成して [callback] に流す。
     *
     * @param iso3       ISO-639-3 の言語コード (`request.language`)
     * @param text       合成するテキスト
     * @param speechRate システム設定の読み上げ速度 (100 = 等速)
     */
    fun run(iso3: String, text: String, speechRate: Int, callback: SynthesisCallback) {
        // 前回の停止要求を持ち越さない。これを忘れると、ユーザーが一度でも
        // 停止ボタンを押した時点で以降すべての発話が無音になる
        // (start / done は正常に呼ばれるため成功として通知される)。
        stopRequested.set(false)

        val languageId = LocaleResolver.languageIdOf(iso3)
        if (languageId == null) {
            callback.error(TextToSpeech.ERROR_INVALID_REQUEST)
            return
        }
        if (!paths.isInstalled(modelId)) {
            callback.error(TextToSpeech.ERROR_NOT_INSTALLED_YET)
            return
        }

        if (text.isBlank()) {
            // モデルをロードせずに空の発話として完了する。
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)
            callback.done()
            return
        }

        val options = SynthOptions(
            languageId = languageId,
            lengthScale = SynthesisParams.lengthScaleOf(speechRate),
        )

        try {
            val engine = engines.acquire(modelId)
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)

            runBlocking {
                // takeWhile で打ち切ることで、onStop 後に残りのチャンクを
                // 生成し続けないようにする (collect 内の早期 return では
                // 上流の生成が止まらない)。
                engine.synthesizeStream(text = text, options = options)
                    .takeWhile { !stopRequested.get() }
                    .collect { chunk -> PcmEmitter.emit(callback, chunk) { stopRequested.get() } }
            }
            callback.done()
        } catch (e: Exception) {
            // ネイティブ層の失敗でサービスを落とさない。
            Log.e(TAG, "Synthesis failed", e)
            callback.error(TextToSpeech.ERROR_SERVICE)
        } catch (e: LinkageError) {
            // System.loadLibrary の失敗は Error 系で送出されるため
            // catch (Exception) をすり抜ける (初回は UnsatisfiedLinkError、
            // 2 回目以降は NoClassDefFoundError)。shipped ABI 以外の端末で
            // サービスプロセスごと落ちるのを防ぐ。
            // Throwable にはしないこと — OutOfMemoryError まで飲み込む。
            Log.e(TAG, "Native library unavailable", e)
            callback.error(TextToSpeech.ERROR_SERVICE)
        }
    }

    companion object {
        const val SAMPLE_RATE = 22050
        const val CHANNEL_COUNT = 1
        private const val TAG = "PiperPlusTts"
    }
}
