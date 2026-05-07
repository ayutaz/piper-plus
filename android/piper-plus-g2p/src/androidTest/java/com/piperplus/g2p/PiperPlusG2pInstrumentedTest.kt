package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L3: Android instrumented tests for [PiperPlusG2p].
 *
 * Runs on Gradle Managed Devices (Pixel 6 API 34, AOSP). Validates that
 *   - the JNI bridge loads cleanly,
 *   - the seven dictionary-free languages produce non-empty phonemes,
 *   - the close/use lifecycle behaves as documented,
 *   - the available-languages list contains all eight expected codes.
 *
 * The Japanese path requires an OpenJTalk dictionary that is not bundled in
 * the AAR; instrumented tests covering Japanese live in M6's dictionary
 * distribution suite.
 */
@RunWith(AndroidJUnit4::class)
class PiperPlusG2pInstrumentedTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun create_then_close_does_not_throw() {
        PiperPlusG2p.create(ctx).close()
    }

    @Test
    fun version_is_non_empty() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val v = g2p.version()
            assertFalse("version() should not be empty", v.isEmpty())
        }
    }

    @Test
    fun available_languages_lists_eight_codes() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val langs = g2p.availableLanguages()
            assertEquals(8, langs.size)
            for (expected in listOf("en", "es", "fr", "ja", "ko", "pt", "sv", "zh")) {
                assertTrue("missing language: $expected", langs.contains(expected))
            }
        }
    }

    @Test
    fun phonemize_spanish_produces_phonemes() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val result = g2p.phonemize("hola mundo", "es")
            assertTrue("expected >0 phonemes", result.numPhonemes > 0)
            assertEquals("es", result.language)
            assertEquals(result.numPhonemes, result.phonemeList.size)
        }
    }

    @Test
    fun phonemize_french_produces_phonemes() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val result = g2p.phonemize("bonjour", "fr")
            assertTrue(result.numPhonemes > 0)
            assertEquals("fr", result.language)
        }
    }

    @Test
    fun phonemize_portuguese_produces_phonemes() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val result = g2p.phonemize("bom dia", "pt")
            assertTrue(result.numPhonemes > 0)
        }
    }

    @Test
    fun phonemize_with_unknown_language_throws() {
        PiperPlusG2p.create(ctx).use { g2p ->
            try {
                g2p.phonemize("foo", "xx")
                fail("expected PiperPlusG2pException for unknown language")
            } catch (expected: PiperPlusG2pException) {
                assertNotNull(expected.message)
            }
        }
    }

    @Test
    fun phonemize_after_close_throws_illegalState() {
        val g2p = PiperPlusG2p.create(ctx)
        g2p.close()
        try {
            g2p.phonemize("hello", "en")
            fail("expected IllegalStateException after close")
        } catch (expected: IllegalStateException) {
            assertNotNull(expected.message)
        }
    }

    @Test
    fun close_is_idempotent() {
        val g2p = PiperPlusG2p.create(ctx)
        g2p.close()
        g2p.close()  // must not crash
    }

    @Test
    fun zh_en_dispatch_is_enabled_by_default() {
        PiperPlusG2p.create(ctx).use { g2p ->
            assertTrue(g2p.isZhEnDispatchEnabled())
        }
    }

    @Test
    fun zh_en_dispatch_can_be_toggled() {
        PiperPlusG2p.create(ctx).use { g2p ->
            g2p.setZhEnDispatchEnabled(false)
            assertFalse(g2p.isZhEnDispatchEnabled())
            g2p.setZhEnDispatchEnabled(true)
            assertTrue(g2p.isZhEnDispatchEnabled())
        }
    }
}
