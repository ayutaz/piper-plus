package com.piperplus.tts

import android.media.AudioFormat
import android.speech.tts.TextToSpeech
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/**
 * 合成 1 発話分の振る舞いを固定する。
 *
 * `SynthesisRequest` は final かつ全 getter がスタブのため JVM では組み立てられない。
 * [SynthesisSession] は request をほどいた引数を受けるので、ここで検証できる。
 */
class SynthesisSessionTest {

    @get:Rule
    val temp = TemporaryFolder()

    // ---------------------------------------------------------------- fakes

    /** 渡された [SynthOptions] と、実際に生成したチャンク数を記録するエンジン。 */
    private class RecordingEngine(private val chunks: List<ShortArray>) : PiperPlusEngine {
        val seenTexts = mutableListOf<String>()
        val seenOptions = mutableListOf<SynthOptions>()

        /** 上流が実際に生成したチャンク数。中断が上流まで届いたかの判定に使う。 */
        val produced = AtomicInteger(0)

        override fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> {
            seenTexts += text
            seenOptions += options
            return flow {
                for (chunk in chunks) {
                    produced.incrementAndGet()
                    emit(chunk)
                }
            }
        }

        override fun close() = Unit
    }

    private class Harness(
        root: File,
        chunks: List<ShortArray> = listOf(ShortArray(2)),
    ) {
        val paths = ModelPaths(root)
        val engine = RecordingEngine(chunks)

        /** エンジン生成回数。モデルの再ロードが起きていないかの判定に使う。 */
        var factoryCalls = 0

        /** 非 null ならエンジン生成時にこれを投げる。 */
        var failure: (() -> Throwable)? = null

        val engines = EngineHolder(paths) { _, _, _ ->
            factoryCalls += 1
            failure?.let { throw it() }
            engine
        }

        val session = SynthesisSession(paths, engines)

        fun installModel() {
            val id = ModelPaths.DEFAULT_MODEL_ID
            paths.modelDir(id).mkdirs()
            paths.modelFile(id).writeText("onnx")
            paths.configFile(id).writeText("{}")
            paths.dictDir().mkdirs()
        }
    }

    // ------------------------------------------------- 早期エラーの判定順序

    @Test
    fun `reports invalid request for an unsupported language`() {
        val h = Harness(temp.root)
        h.installModel()
        val callback = FakeSynthesisCallback()

        h.session.run(iso3 = "kor", text = "안녕", speechRate = 100, callback = callback)

        // start も done も呼ばないこと。呼ぶと失敗が長さ 0 の正常発話に化ける。
        assertEquals(listOf("error(${TextToSpeech.ERROR_INVALID_REQUEST})"), callback.events)
        assertEquals(0, h.factoryCalls)
    }

    @Test
    fun `an unsupported language wins over a missing model`() {
        // モデルも未導入だが、非対応言語であることを先に返す。逆順にすると
        // 「モデルを入れれば話せる」という誤ったシグナルになる。
        val h = Harness(temp.root)
        val callback = FakeSynthesisCallback()

        h.session.run(iso3 = "kor", text = "안녕", speechRate = 100, callback = callback)

        assertEquals(listOf("error(${TextToSpeech.ERROR_INVALID_REQUEST})"), callback.events)
    }

    @Test
    fun `reports not installed yet for a missing model`() {
        // ERROR_INVALID_REQUEST と取り違えると、システムの TTS 設定が
        // 「データのインストール」を促さなくなり、ユーザーは永久にモデルを
        // 入れられない。
        val h = Harness(temp.root)
        val callback = FakeSynthesisCallback()

        h.session.run(iso3 = "jpn", text = "こんにちは", speechRate = 100, callback = callback)

        assertEquals(listOf("error(${TextToSpeech.ERROR_NOT_INSTALLED_YET})"), callback.events)
        assertEquals(0, h.factoryCalls)
    }

    @Test
    fun `blank text completes without loading a model`() {
        // 全角スペースだけの発話でモデルを数百 ms かけてロードしない。
        for (blank in listOf("", "   ", "　", "\n")) {
            val h = Harness(temp.root)
            h.installModel()
            val callback = FakeSynthesisCallback()

            h.session.run(iso3 = "jpn", text = blank, speechRate = 100, callback = callback)

            assertEquals("blank=[$blank]", listOf("start", "done"), callback.events)
            assertEquals("blank=[$blank]", 0, h.factoryCalls)
        }
    }

    // --------------------------------------------------------- 正常系の配線

    @Test
    fun `starts the stream as 22050 Hz PCM16 mono`() {
        val h = Harness(temp.root)
        h.installModel()
        val callback = FakeSynthesisCallback()

        h.session.run(iso3 = "jpn", text = "こんにちは", speechRate = 100, callback = callback)

        assertEquals(
            Triple(22050, AudioFormat.ENCODING_PCM_16BIT, 1),
            callback.startArgs,
        )
        assertTrue(callback.events.first() == "start")
        assertEquals("done", callback.events.last())
    }

    @Test
    fun `maps the request language and speech rate into synth options`() {
        val h = Harness(temp.root)
        h.installModel()

        h.session.run(
            iso3 = "spa",
            text = "hola",
            speechRate = 200,
            callback = FakeSynthesisCallback(),
        )

        val options = h.engine.seenOptions.single()
        // es = 3。language_id_map (ja=0,en=1,zh=2,es=3,fr=4,pt=5) に対応する。
        assertEquals(3, options.languageId)
        // speechRate 200 (= 2 倍速) は length_scale 0.5。pitch を取り違えると
        // 設計書が「pitch は無視する」と規定した仕様に反して値が速度に化ける。
        assertEquals(0.5f, options.lengthScale, 1e-6f)
        assertEquals("hola", h.engine.seenTexts.single())
    }

    @Test
    fun `keeps the same engine when the language changes`() {
        // 6lang モデル 1 つが 6 言語を話すため、言語切替でモデルを
        // 再ロードしてはならない (数百 ms の無駄が毎回入る)。
        val h = Harness(temp.root)
        h.installModel()

        h.session.run("jpn", "こんにちは", 100, FakeSynthesisCallback())
        h.session.run("eng", "hello", 100, FakeSynthesisCallback())

        assertEquals(1, h.factoryCalls)
        assertEquals(listOf(0, 1), h.engine.seenOptions.map { it.languageId })
    }

    // ------------------------------------------------------------ 中断処理

    @Test
    fun `stop aborts the upstream flow not just the collector`() {
        // takeWhile を collect 内の早期 return に書き換えると、音も既存テストも
        // 正しいままネイティブエンジンだけが残り全文を合成し続ける
        // (CPU / バッテリー / 次発話の遅延)。produced で上流の停止を確かめる。
        val h = Harness(temp.root, chunks = List(3) { ShortArray(2) })
        h.installModel()
        val callback = FakeSynthesisCallback(onAudioAvailable = { h.session.stop() })

        h.session.run("jpn", "一つ目。二つ目。三つ目。", 100, callback)

        assertEquals(1, callback.audio.size)
        // 2 個目は生成されるが takeWhile で捨てられる。3 個目は生成されない。
        assertEquals(2, h.engine.produced.get())
    }

    @Test
    fun `stop halts partway through a chunk`() {
        val h = Harness(temp.root, chunks = listOf(ShortArray(5)))
        h.installModel()
        val callback = FakeSynthesisCallback(
            bufferSize = 2,
            onAudioAvailable = { callCount -> if (callCount == 2) h.session.stop() },
        )

        h.session.run("jpn", "長い文", 100, callback)

        // 10 バイトを 2 バイトずつなら 5 回だが、2 回目で停止する。
        assertEquals(2, callback.audio.size)
    }

    @Test
    fun `a stopped utterance still completes without an error`() {
        val h = Harness(temp.root, chunks = List(3) { ShortArray(2) })
        h.installModel()
        val callback = FakeSynthesisCallback(onAudioAvailable = { h.session.stop() })

        h.session.run("jpn", "一つ目。二つ目。", 100, callback)

        assertEquals(1, callback.events.count { it == "done" })
        assertEquals(0, callback.events.count { it.startsWith("error") })
    }

    @Test
    fun `a new utterance is not affected by a previous stop`() {
        // stopRequested のリセットを消す / try の内側に移すと、ユーザーが
        // 一度でも停止ボタンを押した瞬間から以降すべての発話が無音になる。
        // start と done は正常に呼ばれるため成功として通知され、
        // エラーもログも出ずプロセス再起動まで直らない。
        val h = Harness(temp.root, chunks = List(3) { ShortArray(2) })
        h.installModel()

        h.session.stop()
        val callback = FakeSynthesisCallback()
        h.session.run("jpn", "こんにちは", 100, callback)

        assertEquals(3, callback.audio.size)
        assertEquals(3, h.engine.produced.get())
    }

    // ------------------------------------------------------------ 例外経路

    @Test
    fun `maps a native exception to ERROR_SERVICE`() {
        val h = Harness(temp.root)
        h.installModel()
        h.failure = { IllegalStateException("model is corrupt") }
        val callback = FakeSynthesisCallback()

        h.session.run("jpn", "こんにちは", 100, callback)

        // エンジン取得が start より前にあるので、start は呼ばれない。
        assertEquals(listOf("error(${TextToSpeech.ERROR_SERVICE})"), callback.events)
    }

    @Test
    fun `maps UnsatisfiedLinkError to ERROR_SERVICE`() {
        // System.loadLibrary の失敗は Error 系なので catch (Exception) を
        // すり抜ける。shipped ABI 以外の端末でサービスごと落ちるのを防ぐ。
        val h = Harness(temp.root)
        h.installModel()
        h.failure = { UnsatisfiedLinkError("libpiper_plus_jni.so not found") }
        val callback = FakeSynthesisCallback()

        h.session.run("jpn", "こんにちは", 100, callback)

        assertEquals(listOf("error(${TextToSpeech.ERROR_SERVICE})"), callback.events)
    }

    @Test
    fun `maps NoClassDefFoundError to ERROR_SERVICE`() {
        // 2 回目以降の PiperPlusNative 参照はこちらで失敗する。
        val h = Harness(temp.root)
        h.installModel()
        h.failure = { NoClassDefFoundError("com/piperplus/PiperPlusNative") }
        val callback = FakeSynthesisCallback()

        h.session.run("jpn", "こんにちは", 100, callback)

        assertEquals(listOf("error(${TextToSpeech.ERROR_SERVICE})"), callback.events)
    }
}
