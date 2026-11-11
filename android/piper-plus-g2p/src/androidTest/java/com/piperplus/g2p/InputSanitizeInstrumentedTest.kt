package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L3: [PiperPlusG2p.phonemize] reads a text with control characters like
 * the text without them.
 *
 * Contract: docs/spec/input-sanitize-contract.toml (runtime "kotlin").
 * Cases: tests/fixtures/g2p/input_sanitize_cases.json (input_sanitize_cases,
 * synced into androidTest assets by the syncG2pFixture Gradle task).
 *
 * Regression focus: JNI passes the text as modified UTF-8, where U+0000 is
 * the bytes C0 80. libpiper_plus keeps bytes that are not valid UTF-8, so a
 * NUL inside "hola" reached the phonemizer and the word gave no phonemes.
 *
 * Japanese is skipped (no OpenJTalk dictionary in the test APK), and so is
 * pt-PT, which libpiper_plus's engine-less G2P does not map.
 */
@RunWith(AndroidJUnit4::class)
class InputSanitizeInstrumentedTest {

    private val targetCtx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val testCtx get() = InstrumentationRegistry.getInstrumentation().context

    private fun fixture(): JSONObject {
        val text = testCtx.assets
            .open("g2p_fixtures/input_sanitize_cases.json")
            .bufferedReader()
            .use { it.readText() }
        return JSONObject(text)
    }

    @Test
    fun word_cases_read_like_the_clean_text() {
        val cases = fixture().getJSONArray("word_cases")
        var checked = 0
        PiperPlusG2p.create(targetCtx).use { g2p ->
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i)
                val lang = c.getString("language")
                if (lang == "ja" || lang == "pt-PT") continue
                val code = if (lang == "multilingual") null else lang
                val clean = g2p.phonemize(c.getString("clean"), code)
                assertTrue("$lang ${c.getString("control")}: empty", clean.numPhonemes > 0)
                assertEquals(
                    "$lang ${c.getString("control")} '${c.getString("clean")}'",
                    clean,
                    g2p.phonemize(c.getString("dirty"), code),
                )
                checked++
            }
        }
        assertTrue("only $checked cases checked", checked > 30)
    }

    @Test
    fun nul_inside_a_word_is_removed() {
        PiperPlusG2p.create(targetCtx).use { g2p ->
            val nul = Char(0)
            assertEquals(g2p.phonemize("hola", "es"), g2p.phonemize("ho${nul}la", "es"))
            assertEquals(g2p.phonemize("och", null), g2p.phonemize("o${nul}ch", null))
        }
    }

    @Test
    fun text_of_only_control_characters_reads_like_an_empty_text() {
        PiperPlusG2p.create(targetCtx).use { g2p ->
            val controls = listOf(0, 1, 0x7F, 0x9F).joinToString("") { Char(it).toString() }
            assertEquals(g2p.phonemize("", "es"), g2p.phonemize(controls, "es"))
        }
    }
}
