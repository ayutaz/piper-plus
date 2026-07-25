package com.piperplus.tts

import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class EngineHolderTest {

    @get:Rule
    val temp = TemporaryFolder()

    private class FakeEngine : PiperPlusEngine {
        override val sampleRate: Int = 22050
        var closed = false
        override fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> =
            flowOf(ShortArray(4))
        override fun close() {
            closed = true
        }
    }

    private fun installModel(paths: ModelPaths, modelId: String) {
        paths.modelDir(modelId).mkdirs()
        paths.modelFile(modelId).writeText("onnx")
        paths.configFile(modelId).writeText("{}")
        paths.dictDir().mkdirs()
    }

    @Test
    fun `creates an engine on first acquire`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var created = 0
        val holder = EngineHolder(paths) { _, _, _ -> created++; FakeEngine() }

        holder.acquire("voice-a")

        assertEquals(1, created)
    }

    @Test
    fun `reuses the cached engine for the same model`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var created = 0
        val holder = EngineHolder(paths) { _, _, _ -> created++; FakeEngine() }

        val first = holder.acquire("voice-a")
        val second = holder.acquire("voice-a")

        assertEquals(1, created)
        assertSame(first, second)
    }

    @Test
    fun `closes the previous engine when the model changes`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        installModel(paths, "voice-b")
        val engines = mutableListOf<FakeEngine>()
        val holder = EngineHolder(paths) { _, _, _ -> FakeEngine().also { engines.add(it) } }

        holder.acquire("voice-a")
        holder.acquire("voice-b")

        assertEquals(2, engines.size)
        assertTrue(engines[0].closed)
        assertFalse(engines[1].closed)
    }

    @Test
    fun `passes resolved paths to the factory`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var seenModel = ""
        var seenConfig = ""
        var seenDict = ""
        val holder = EngineHolder(paths) { model, config, dict ->
            seenModel = model
            seenConfig = config
            seenDict = dict
            FakeEngine()
        }

        holder.acquire("voice-a")

        assertEquals(paths.modelFile("voice-a").absolutePath, seenModel)
        assertEquals(paths.configFile("voice-a").absolutePath, seenConfig)
        assertEquals(paths.dictDir().absolutePath, seenDict)
    }

    @Test(expected = IllegalStateException::class)
    fun `rejects acquiring a model that is not installed`() {
        val holder = EngineHolder(ModelPaths(temp.root)) { _, _, _ -> FakeEngine() }
        holder.acquire("missing-voice")
    }

    @Test
    fun `release closes the cached engine`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        val engines = mutableListOf<FakeEngine>()
        val holder = EngineHolder(paths) { _, _, _ -> FakeEngine().also { engines.add(it) } }

        holder.acquire("voice-a")
        holder.release()

        assertTrue(engines[0].closed)
    }

    @Test
    fun `release is idempotent`() {
        val holder = EngineHolder(ModelPaths(temp.root)) { _, _, _ -> FakeEngine() }
        holder.release()
        holder.release()
    }

    @Test
    fun `a failed load leaves no stale engine behind`() {
        // モデル切替の途中で新しいモデルのロードが失敗したとき、キャッシュに
        // close 済みの旧インスタンスが残ってはならない。残ると次の acquire が
        // 早期 return でそれを返し、PiperPlus.checkNotClosed が毎回投げて
        // Service が破棄されるまで恒久的に合成不能になる。
        //
        // ModelPaths.isInstalled はファイルの存在しか見ないため、途中で切れた
        // model.onnx でも installed 判定になり、この経路は現実に踏まれる。
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        installModel(paths, "voice-b")
        val engines = mutableListOf<FakeEngine>()
        var calls = 0
        val holder = EngineHolder(paths) { _, _, _ ->
            calls++
            if (calls == 2) throw IllegalStateException("model is corrupt")
            FakeEngine().also { engines.add(it) }
        }

        val first = holder.acquire("voice-a")
        assertThrows(IllegalStateException::class.java) { holder.acquire("voice-b") }

        val retried = holder.acquire("voice-a")

        assertTrue("旧インスタンスは close 済みのはず", engines[0].closed)
        assertEquals("キャッシュが残っていると factory が呼ばれない", 3, calls)
        assertNotSame("close 済みのインスタンスを返してはならない", first, retried)
    }
}
