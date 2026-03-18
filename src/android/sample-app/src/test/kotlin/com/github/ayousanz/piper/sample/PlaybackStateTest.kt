package com.github.ayousanz.piper.sample

import org.junit.Assert.*
import org.junit.Test

class PlaybackStateTest {

    @Test
    fun `Idle is not Error`() {
        val state: PlaybackState = PlaybackState.Idle
        assertFalse(state is PlaybackState.Error)
        assertTrue(state is PlaybackState.Idle)
    }

    @Test
    fun `Error carries message`() {
        val state = PlaybackState.Error("Model not found")
        assertEquals("Model not found", state.message)
    }

    @Test
    fun `Synthesizing carries text`() {
        val state = PlaybackState.Synthesizing("Hello world")
        assertEquals("Hello world", state.text)
    }

    @Test
    fun `Playing carries duration`() {
        val state = PlaybackState.Playing(2.5f)
        assertEquals(2.5f, state.durationSeconds, 0.001f)
    }
}

class TtsLanguageTest {

    @Test
    fun `all 6 languages are defined`() {
        assertEquals(6, TtsLanguage.entries.size)
    }

    @Test
    fun `language codes are correct`() {
        assertEquals("ja", TtsLanguage.JAPANESE.code)
        assertEquals("en", TtsLanguage.ENGLISH.code)
        assertEquals("zh", TtsLanguage.CHINESE.code)
        assertEquals("es", TtsLanguage.SPANISH.code)
        assertEquals("fr", TtsLanguage.FRENCH.code)
        assertEquals("pt", TtsLanguage.PORTUGUESE.code)
    }

    @Test
    fun `display names are non-empty`() {
        TtsLanguage.entries.forEach { lang ->
            assertTrue("${lang.name} display name should not be empty", lang.displayName.isNotEmpty())
        }
    }

    @Test
    fun `can find language by code`() {
        val found = TtsLanguage.entries.firstOrNull { it.code == "ja" }
        assertNotNull(found)
        assertEquals(TtsLanguage.JAPANESE, found)
    }
}
