package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Test
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

class PiperAudioTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun `duration calculation is correct`() {
        // 22050 samples at 22050 Hz = 1.0 second
        val audio = PiperAudio(ShortArray(22050), sampleRate = 22050)
        assertEquals(1.0f, audio.durationSeconds, 0.001f)
    }

    @Test
    fun `duration for empty audio is zero`() {
        val audio = PiperAudio(ShortArray(0))
        assertEquals(0.0f, audio.durationSeconds, 0.001f)
    }

    @Test
    fun `save creates valid WAV file`() {
        val samples = ShortArray(100) { (it * 100).toShort() }
        val audio = PiperAudio(samples, sampleRate = 22050)

        val wavFile = File(tempFolder.root, "test.wav")
        audio.save(wavFile.absolutePath)

        assertTrue(wavFile.exists())
        assertTrue(wavFile.length() > 44) // At least WAV header

        // Verify WAV header
        val bytes = wavFile.readBytes()
        assertEquals('R'.code.toByte(), bytes[0])
        assertEquals('I'.code.toByte(), bytes[1])
        assertEquals('F'.code.toByte(), bytes[2])
        assertEquals('F'.code.toByte(), bytes[3])

        // Verify WAVE marker
        assertEquals('W'.code.toByte(), bytes[8])
        assertEquals('A'.code.toByte(), bytes[9])
        assertEquals('V'.code.toByte(), bytes[10])
        assertEquals('E'.code.toByte(), bytes[11])

        // Verify data size
        val dataSize = ByteBuffer.wrap(bytes, 40, 4).order(ByteOrder.LITTLE_ENDIAN).int
        assertEquals(samples.size * 2, dataSize)

        // Verify total file size
        assertEquals(44 + samples.size * 2, bytes.size)
    }

    @Test
    fun `equality based on content`() {
        val audio1 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        val audio2 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        val audio3 = PiperAudio(shortArrayOf(1, 2, 4), 22050)

        assertEquals(audio1, audio2)
        assertNotEquals(audio1, audio3)
    }

    @Test
    fun `different sample rates are not equal`() {
        val audio1 = PiperAudio(shortArrayOf(1, 2, 3), 22050)
        val audio2 = PiperAudio(shortArrayOf(1, 2, 3), 44100)
        assertNotEquals(audio1, audio2)
    }
}
