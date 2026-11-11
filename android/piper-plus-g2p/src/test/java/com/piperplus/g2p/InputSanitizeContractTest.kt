package com.piperplus.g2p

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * L1: [TextSanitizer.stripControlChars] follows the input-sanitize rule.
 *
 * Contract: docs/spec/input-sanitize-contract.toml (runtime "kotlin").
 * Cases: tests/fixtures/g2p/input_sanitize_cases.json, read here directly.
 *
 * Regression focus: libpiper_plus strips control characters, but the JNI
 * layer passes text as modified UTF-8, where U+0000 is the two bytes C0 80.
 * The native strip keeps bytes that are not valid UTF-8, so a NUL inside
 * "hola" reached the phonemizer. [PiperPlusG2p.phonemize] therefore strips
 * before the native call; InputSanitizeInstrumentedTest (L3) checks that on
 * the emulator.
 */
class InputSanitizeContractTest {

    private val fixture: JSONObject = JSONObject(
        File(System.getProperty("user.dir") ?: ".")
            .resolve("../../tests/fixtures/g2p/input_sanitize_cases.json")
            .normalize()
            .readText(),
    )

    @Test
    fun `matches every strip case`() {
        val cases = fixture.getJSONArray("strip_cases")
        assertTrue(cases.length() > 10)
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            assertEquals(
                c.getString("name"),
                c.getString("expected"),
                TextSanitizer.stripControlChars(c.getString("input")),
            )
        }
    }

    @Test
    fun `is idempotent`() {
        val cases = fixture.getJSONArray("strip_cases")
        for (i in 0 until cases.length()) {
            val once = TextSanitizer.stripControlChars(cases.getJSONObject(i).getString("input"))
            assertEquals(once, TextSanitizer.stripControlChars(once))
        }
    }

    @Test
    fun `every dirty case strips to its clean text`() {
        for (group in listOf("word_cases", "pipeline_cases")) {
            val cases = fixture.getJSONArray(group)
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i)
                assertEquals(
                    c.toString(),
                    c.getString("clean"),
                    TextSanitizer.stripControlChars(c.getString("dirty")),
                )
            }
        }
    }

    @Test
    fun `keeps surrogates and the characters next to a control character`() {
        val emoji = String(Character.toChars(0x1F600))
        val nul = Char(0).toString()
        assertEquals("a${emoji}b", TextSanitizer.stripControlChars("a$emoji${nul}b"))
        val lone = Char(0xD800).toString()
        assertEquals("a${lone}b", TextSanitizer.stripControlChars("a$lone${nul}b"))
        // NBSP, ZWJ, BOM and LINE SEPARATOR are not Cc.
        val kept = listOf(0xA0, 0x200D, 0xFEFF, 0x2028)
            .joinToString("", prefix = "a", postfix = "b") { Char(it).toString() }
        assertEquals(kept, TextSanitizer.stripControlChars(kept))
    }

    @Test
    fun `matches the rule for every BMP character`() {
        for (cp in 0..0xFFFF) {
            val ch = cp.toChar()
            val expected = when {
                ch == '\n' || ch == '\t' || ch == '\r' -> "a${ch}b"
                ch == '\u000B' || ch == '\u000C' || ch == '\u0085' -> "a b"
                Character.getType(ch) == Character.CONTROL.toInt() -> "ab"
                else -> "a${ch}b"
            }
            assertEquals("U+%04X".format(cp), expected, TextSanitizer.stripControlChars("a${ch}b"))
        }
    }
}
