package com.piperplus.tts

import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * PCM の詰め替えと分割を固定する。
 *
 * ここが壊れても長さもチャンク数も `done()` の呼ばれ方も変わらないため、
 * 型検査も他のテストも APK ビルドも通ったまま、端末でだけ音が壊れる。
 */
class PcmEmitterTest {

    @Test
    fun `packs samples as little endian`() {
        val callback = FakeSynthesisCallback()

        PcmEmitter.emit(
            callback,
            shortArrayOf(0x0102, -1, Short.MIN_VALUE, Short.MAX_VALUE),
        ) { false }

        // 下位バイトが先。上位バイトを先に置く (= big-endian) と
        // 全端末でホワイトノイズになる。
        assertArrayEquals(
            byteArrayOf(
                0x02, 0x01, // 0x0102
                0xFF.toByte(), 0xFF.toByte(), // -1
                0x00, 0x80.toByte(), // Short.MIN_VALUE
                0xFF.toByte(), 0x7F, // Short.MAX_VALUE
            ),
            callback.audioBytes(),
        )
    }

    @Test
    fun `round trips through a little endian ByteBuffer`() {
        // 符号拡張の独立したオラクル。上位バイトを (value / 256) と書くと
        // 整数除算が -1/256 = 0 になり、全負サンプルが 1 ずれる
        // (算術シフトなら -1)。ここで落ちる。
        val samples = shortArrayOf(0, 1, -1, 256, -256, 0x00FF, Short.MAX_VALUE, Short.MIN_VALUE)
        val callback = FakeSynthesisCallback()

        PcmEmitter.emit(callback, samples) { false }

        val readBack = ShortArray(samples.size)
        ByteBuffer.wrap(callback.audioBytes())
            .order(ByteOrder.LITTLE_ENDIAN)
            .asShortBuffer()
            .get(readBack)
        assertArrayEquals(samples, readBack)
    }

    @Test
    fun `splits into maxBufferSize slices with a moving offset`() {
        // 5 サンプル = 10 バイトを 4 バイトずつ。
        val callback = FakeSynthesisCallback(bufferSize = 4)

        PcmEmitter.emit(callback, shortArrayOf(1, 2, 3, 4, 5)) { false }

        assertEquals(
            listOf(
                "audio(offset=0,length=4)",
                "audio(offset=4,length=4)",
                "audio(offset=8,length=2)",
            ),
            callback.events,
        )
    }

    @Test
    fun `delivers every slice exactly once and in order`() {
        // offset を渡し忘れて audioAvailable(bytes, 0, length) と書くと
        // 総バイト数は変わらないまま 2 チャンク目以降が先頭を再送し、
        // 冒頭が吃音のように繰り返される。連結して初めて検出できる。
        val samples = ShortArray(9) { (it + 1).toShort() }
        val callback = FakeSynthesisCallback(bufferSize = 4)

        PcmEmitter.emit(callback, samples) { false }

        val expected = ByteArray(samples.size * 2)
        ByteBuffer.wrap(expected).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().put(samples)
        assertArrayEquals(expected, callback.audioBytes())
    }

    @Test
    fun `emits once when the buffer covers the whole chunk`() {
        val callback = FakeSynthesisCallback(bufferSize = 8192)

        PcmEmitter.emit(callback, ShortArray(100)) { false }

        assertEquals(listOf("audio(offset=0,length=200)"), callback.events)
    }

    @Test
    fun `stops between slices once a stop is requested`() {
        val callback = FakeSynthesisCallback(bufferSize = 4)
        var emitted = 0

        PcmEmitter.emit(callback, shortArrayOf(1, 2, 3, 4, 5)) {
            // 1 回渡したら停止する。
            emitted++ >= 1
        }

        assertEquals(listOf("audio(offset=0,length=4)"), callback.events)
    }

    @Test
    fun `terminates even when the callback reports a non positive buffer size`() {
        // AOSP の実装は 8192 を返すが、0 を返す callback を渡されると
        // offset が進まず無限ループになる (テストが fail ではなく hang する)。
        val callback = FakeSynthesisCallback(bufferSize = 0)

        PcmEmitter.emit(callback, shortArrayOf(1, 2)) { false }

        // 1 サンプル (2 バイト) ずつでも必ず終わり、内容は保たれる。
        assertEquals(
            listOf("audio(offset=0,length=2)", "audio(offset=2,length=2)"),
            callback.events,
        )
        assertArrayEquals(byteArrayOf(0x01, 0x00, 0x02, 0x00), callback.audioBytes())
    }

    @Test
    fun `emits nothing for an empty chunk`() {
        val callback = FakeSynthesisCallback()

        PcmEmitter.emit(callback, ShortArray(0)) { false }

        assertEquals(emptyList<String>(), callback.events)
    }
}
