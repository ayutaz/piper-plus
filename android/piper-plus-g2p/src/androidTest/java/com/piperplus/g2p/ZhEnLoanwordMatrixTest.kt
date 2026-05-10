package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L4: cross-runtime ZH-EN code-switching parity (mirror of
 * `tests/PiperPlusG2PTests/ZhEnLoanwordMatrixTests.swift`).
 *
 * **Scope note (CI fix follow-up):** the matrix fixture at
 * `tests/fixtures/g2p/zh_en_loanword_matrix.json` pins token counts for
 * `phonemize_embedded_english` — a function on the Rust `ChinesePhonemizer`
 * that the JNI bridge does NOT expose directly. Embedded-English dispatch
 * is invoked transparently by `MultilingualPhonemizer` when the input is
 * a Chinese sentence containing English tokens. Therefore the matrix's
 * per-case exact-count expectations CANNOT be reproduced via
 * `PiperPlusG2p.phonemize(text, "zh")` with pure-ASCII input — that path
 * goes through `ChinesePhonemizer.phonemize` (no English dispatch), not
 * through `phonemize_embedded_english`.
 *
 * What this file verifies (via the *public* Kotlin API):
 *   1. The fixture loads with the expected schema (drift detector).
 *   2. ZH sentence + embedded English produces ≥ bare-English token count
 *      (proves the dispatch path fires for sentence-context inputs).
 *   3. The forward-compat (schema_v2) entry remains pinned.
 *
 * For the strict matrix counts (GPS=11 / USB=10 / Python=6 / ChatGPT=15
 * etc.), see `test_zh_en_two_crate.rs` (Rust) and the Go/C#/C++/WASM
 * mirror tests, which can call `phonemize_embedded_english` directly.
 */
@RunWith(AndroidJUnit4::class)
class ZhEnLoanwordMatrixTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val testCtx get() = InstrumentationRegistry.getInstrumentation().context

    private fun loadMatrix(): JSONObject {
        val raw = testCtx.assets.open("g2p_fixtures/zh_en_loanword_matrix.json")
            .bufferedReader().use { it.readText() }
        return JSONObject(raw)
    }

    private fun tokenCount(g2p: PiperPlusG2p, input: String): Int =
        g2p.phonemize(input, "zh").numPhonemes

    // -----------------------------------------------------------------------
    // Fixture sanity (drift detector)
    // -----------------------------------------------------------------------

    @Test
    fun matrix_fixture_loads() {
        val root = loadMatrix()
        assertEquals(
            "schema_version drift -- update ZhEnLoanwordMatrixTest if intentional",
            1, root.getInt("schema_version"),
        )
        val cases = root.getJSONArray("cases")
        assertTrue(
            "matrix must keep ≥17 cases (parent commit T14)",
            cases.length() >= 17,
        )
    }

    // -----------------------------------------------------------------------
    // Issue #384 -- full sentence smoke tests. These are the only matrix
    // assertions reproducible via the public Kotlin API: a Chinese sentence
    // with embedded English must produce ≥ the bare-English token count
    // (the embedded English MUST not be silently dropped).
    // -----------------------------------------------------------------------

    @Test
    fun issue_384_please_open_gps_includes_embedded_GPS() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val bareGPS = tokenCount(g2p, "GPS")
            val sentence = tokenCount(g2p, "请打开 GPS")
            assertTrue(
                "embedded GPS dropped in '请打开 GPS': sentence=$sentence < bare GPS=$bareGPS",
                sentence >= bareGPS,
            )
        }
    }

    @Test
    fun issue_384_python_in_sentence_includes_embedded_Python() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val barePython = tokenCount(g2p, "Python")
            val sentence = tokenCount(g2p, "我喜欢用 Python 写代码")
            assertTrue(
                "embedded Python dropped: sentence=$sentence < bare Python=$barePython",
                sentence >= barePython,
            )
        }
    }

    @Test
    fun issue_384_chatgpt_in_sentence_includes_embedded_ChatGPT() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val bareChatGPT = tokenCount(g2p, "ChatGPT")
            val sentence = tokenCount(g2p, "让我用 ChatGPT 写代码")
            assertTrue(
                "embedded ChatGPT dropped: sentence=$sentence < bare ChatGPT=$bareChatGPT",
                sentence >= bareChatGPT,
            )
        }
    }

    // -----------------------------------------------------------------------
    // Forward-compat (YELLOW-5): the matrix entry that documents future
    // schema_version: 2 acceptance.
    // -----------------------------------------------------------------------

    @Test
    fun forward_compat_entry_remains_in_fixture() {
        val root = loadMatrix()
        val cases = root.getJSONArray("cases")
        var found = false
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            if (c.optString("name") == "schema_v2_forward_compat_loader") {
                assertNotNull("forward-compat entry missing input_json", c.opt("input_json"))
                val v2 = c.getJSONObject("input_json")
                assertEquals(2, v2.getInt("schema_version"))
                assertEquals(2, v2.getInt("version"))
                found = true
                break
            }
        }
        assertTrue(
            "matrix lost the schema_v2_forward_compat_loader entry -- remove this test " +
                "explicitly when YELLOW-5 contract retires.",
            found,
        )
    }
}
