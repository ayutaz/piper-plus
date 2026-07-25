package com.piperplus.tts

import android.speech.tts.TextToSpeech
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocaleResolverTest {
    @Test
    fun `maps all six supported languages to their language ids`() {
        assertEquals(0, LocaleResolver.languageIdOf("jpn"))
        assertEquals(1, LocaleResolver.languageIdOf("eng"))
        assertEquals(2, LocaleResolver.languageIdOf("zho"))
        assertEquals(3, LocaleResolver.languageIdOf("spa"))
        assertEquals(4, LocaleResolver.languageIdOf("fra"))
        assertEquals(5, LocaleResolver.languageIdOf("por"))
    }

    @Test
    fun `accepts cmn as an alias for zho`() {
        assertEquals(2, LocaleResolver.languageIdOf("cmn"))
    }

    @Test
    fun `is case insensitive`() {
        assertEquals(0, LocaleResolver.languageIdOf("JPN"))
        assertEquals(1, LocaleResolver.languageIdOf("Eng"))
    }

    @Test
    fun `returns null for unsupported languages`() {
        assertNull(LocaleResolver.languageIdOf("kor"))
        assertNull(LocaleResolver.languageIdOf("swe"))
        assertNull(LocaleResolver.languageIdOf(""))
    }

    @Test
    fun `reports NOT_SUPPORTED for an unsupported language even when a model exists`() {
        assertEquals(
            TextToSpeech.LANG_NOT_SUPPORTED,
            LocaleResolver.availability("kor", modelInstalled = true),
        )
    }

    @Test
    fun `reports MISSING_DATA when the language is supported but no model is installed`() {
        assertEquals(
            TextToSpeech.LANG_MISSING_DATA,
            LocaleResolver.availability("jpn", modelInstalled = false),
        )
    }

    @Test
    fun `reports AVAILABLE when the language is supported and a model is installed`() {
        assertEquals(
            TextToSpeech.LANG_AVAILABLE,
            LocaleResolver.availability("jpn", modelInstalled = true),
        )
    }

    @Test
    fun `exposes exactly the six supported iso3 codes`() {
        assertEquals(
            listOf("jpn", "eng", "zho", "spa", "fra", "por"),
            LocaleResolver.SUPPORTED_ISO3,
        )
    }
}
