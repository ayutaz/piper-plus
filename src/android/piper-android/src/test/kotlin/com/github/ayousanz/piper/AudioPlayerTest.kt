package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for AudioPlayer.
 *
 * AudioPlayer depends on Android's AudioTrack, which is not available in JVM unit tests.
 * These tests verify constructor parameters and state that can be checked without Android APIs.
 * Full playback tests require Android instrumented tests (androidTest/).
 */
class AudioPlayerTest {

    @Test
    fun `constructor with default sampleRate succeeds`() {
        // AudioPlayer constructor only stores the sampleRate field;
        // the AudioTrack is lazily created on first play().
        // This verifies the object can be instantiated.
        val player = AudioPlayer()
        assertNotNull(player)
    }

    @Test
    fun `constructor with custom sampleRate succeeds`() {
        val player = AudioPlayer(sampleRate = 44100)
        assertNotNull(player)
    }

    @Test
    fun `close on fresh instance does not throw`() {
        val player = AudioPlayer()
        // close() should be safe to call even without any playback
        player.close()
    }

    @Test
    fun `stop on fresh instance does not throw`() {
        val player = AudioPlayer()
        // stop() should be safe to call even without any playback
        player.stop()
    }

    @Test
    fun `double close does not throw`() {
        val player = AudioPlayer()
        player.close()
        player.close()
    }

    @Test
    fun `implements AutoCloseable`() {
        // Verify AudioPlayer can be used in use{} blocks
        assertTrue(AutoCloseable::class.java.isAssignableFrom(AudioPlayer::class.java))
    }
}
