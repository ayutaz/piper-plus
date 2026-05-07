package com.piperplus.g2p

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

/**
 * Pure-Kotlin unit tests (L1) for [PhonemeResult] data class behaviour.
 *
 * Covers the contract that the Kotlin wrapper relies on when converting the
 * native `String[3]` from the JNI layer back into a structured result.
 */
class PhonemeResultTest {

    @Test
    fun `equals returns true for same content`() {
        val a = PhonemeResult("h e l o", listOf("h", "e", "l", "o"), "en", 4)
        val b = PhonemeResult("h e l o", listOf("h", "e", "l", "o"), "en", 4)
        assertEquals(a, b)
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun `equals returns false on different language`() {
        val a = PhonemeResult("h e l o", listOf("h", "e", "l", "o"), "en", 4)
        val b = PhonemeResult("h e l o", listOf("h", "e", "l", "o"), "ja", 4)
        assertNotEquals(a, b)
    }

    @Test
    fun `toString contains all fields`() {
        val r = PhonemeResult("a b", listOf("a", "b"), "en", 2)
        val s = r.toString()
        assertEquals(true, s.contains("phonemes=a b"))
        assertEquals(true, s.contains("language=en"))
        assertEquals(true, s.contains("numPhonemes=2"))
    }

    @Test
    fun `copy returns modified instance`() {
        val r = PhonemeResult("a b", listOf("a", "b"), "en", 2)
        val r2 = r.copy(language = "ja")
        assertEquals("ja", r2.language)
        assertEquals(r.phonemes, r2.phonemes)
        assertNotEquals(r, r2)
    }

    @Test
    fun `empty phoneme list is permissible`() {
        val r = PhonemeResult("", emptyList(), "unknown", 0)
        assertEquals(0, r.numPhonemes)
        assertEquals(0, r.phonemeList.size)
    }

    @Test(expected = UnsupportedOperationException::class)
    fun `phonemeList wrapped via Collections_unmodifiableList rejects mutation`() {
        // The downstream PiperPlusG2p.phonemize() wraps the list with
        // Collections.unmodifiableList. Re-assert here so a regression on
        // that contract surfaces in L1.
        val raw = mutableListOf("a", "b")
        val locked = java.util.Collections.unmodifiableList(raw)
        val r = PhonemeResult("a b", locked, "en", 2)
        @Suppress("KotlinConstantConditions")
        (r.phonemeList as MutableList<String>).add("c")  // expected: throws
    }
}
