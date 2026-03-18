package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

class PiperAudioEdgeCaseTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun `empty samples gives duration 0`() {
        val audio = PiperAudio(ShortArray(0), sampleRate = 22050)
        assertEquals(0.0f, audio.durationSeconds, 0.001f)
    }

    @Test
    fun `single sample duration calculation`() {
        val audio = PiperAudio(ShortArray(1), sampleRate = 22050)
        assertEquals(1.0f / 22050, audio.durationSeconds, 0.0001f)
    }

    @Test
    fun `large samples array duration calculation`() {
        // 10 minutes of audio at 22050 Hz
        val sampleCount = 22050 * 600
        val audio = PiperAudio(ShortArray(sampleCount), sampleRate = 22050)
        assertEquals(600.0f, audio.durationSeconds, 0.01f)
    }

    @Test
    fun `duration accuracy at 44100 Hz`() {
        val audio = PiperAudio(ShortArray(44100), sampleRate = 44100)
        assertEquals(1.0f, audio.durationSeconds, 0.001f)
    }

    @Test
    fun `duration accuracy half second`() {
        val audio = PiperAudio(ShortArray(11025), sampleRate = 22050)
        assertEquals(0.5f, audio.durationSeconds, 0.001f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `save with empty path throws`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3))
        audio.save("")
    }

    @Test(expected = IllegalArgumentException::class)
    fun `save with blank path throws`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3))
        audio.save("   ")
    }

    @Test
    fun `save empty audio creates valid WAV`() {
        val audio = PiperAudio(ShortArray(0), sampleRate = 22050)
        val wavFile = File(tempFolder.root, "empty.wav")
        audio.save(wavFile.absolutePath)

        assertTrue(wavFile.exists())
        assertEquals(44, wavFile.length().toInt()) // Header only, no data

        val bytes = wavFile.readBytes()
        // Verify RIFF header
        assertEquals('R'.code.toByte(), bytes[0])
        assertEquals('I'.code.toByte(), bytes[1])
        assertEquals('F'.code.toByte(), bytes[2])
        assertEquals('F'.code.toByte(), bytes[3])

        // Data size should be 0
        val dataSize = ByteBuffer.wrap(bytes, 40, 4).order(ByteOrder.LITTLE_ENDIAN).int
        assertEquals(0, dataSize)
    }

    @Test
    fun `save WAV preserves sample rate in header`() {
        val audio = PiperAudio(shortArrayOf(100, 200), sampleRate = 44100)
        val wavFile = File(tempFolder.root, "sr44100.wav")
        audio.save(wavFile.absolutePath)

        val bytes = wavFile.readBytes()
        val sampleRate = ByteBuffer.wrap(bytes, 24, 4).order(ByteOrder.LITTLE_ENDIAN).int
        assertEquals(44100, sampleRate)
    }

    @Test
    fun `save WAV preserves sample values`() {
        val samples = shortArrayOf(Short.MIN_VALUE, 0, Short.MAX_VALUE)
        val audio = PiperAudio(samples, sampleRate = 22050)
        val wavFile = File(tempFolder.root, "values.wav")
        audio.save(wavFile.absolutePath)

        val bytes = wavFile.readBytes()
        val pcmBuf = ByteBuffer.wrap(bytes, 44, samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(Short.MIN_VALUE, pcmBuf.short)
        assertEquals(0.toShort(), pcmBuf.short)
        assertEquals(Short.MAX_VALUE, pcmBuf.short)
    }

    @Test
    fun `save creates parent directories`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3))
        val nestedPath = File(tempFolder.root, "a/b/c/test.wav")
        audio.save(nestedPath.absolutePath)

        assertTrue(nestedPath.exists())
        assertTrue(nestedPath.length() > 44)
    }

    @Test
    fun `default sample rate is 22050`() {
        val audio = PiperAudio(ShortArray(0))
        assertEquals(22050, audio.sampleRate)
    }

    @Test
    fun `hashCode consistent with equals`() {
        val audio1 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        val audio2 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        assertEquals(audio1.hashCode(), audio2.hashCode())
    }

    @Test
    fun `hashCode differs for different samples`() {
        val audio1 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        val audio2 = PiperAudio(shortArrayOf(4, 5, 6), 22050)
        assertNotEquals(audio1.hashCode(), audio2.hashCode())
    }

    @Test
    fun `equals reflexive`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        assertEquals(audio, audio)
    }

    @Test
    fun `equals null returns false`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        assertNotEquals(audio, null)
    }

    @Test
    fun `equals different type returns false`() {
        val audio = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        assertNotEquals(audio, "not an audio")
    }
}
