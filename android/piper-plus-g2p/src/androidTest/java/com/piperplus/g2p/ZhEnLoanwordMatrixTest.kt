package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L4: cross-runtime ZH-EN code-switching parity (mirror of
 * `Tests/PiperPlusG2PTests/ZhEnLoanwordMatrixTests.swift`).
 *
 * Loads `src/androidTest/assets/g2p_fixtures/zh_en_loanword_matrix.json`
 * (a byte-for-byte mirror of `tests/fixtures/g2p/zh_en_loanword_matrix.json`,
 * enforced by `scripts/check_loanword_consistency.py`) and asserts the
 * Kotlin runtime produces the same token-count behavior the Go / C# /
 * C++ / WASM / Rust mirrors do.
 *
 * Why this exists: parent commit T14 (05a660be) added Kotlin to the ZH-EN
 * sync gate, so the JSON files are byte-equal to the Python source — but
 * until now no Android instrumented test consumed the matrix. A regression
 * in `phonemize_embedded_english` (Rust) or in the JNI bridge could ship
 * undetected. This test closes that hole.
 *
 * Numerical expectations (from fixture notes):
 *   - GPS     -> 11 tokens
 *   - USB     -> 10 tokens
 *   - Python  ->  6 tokens
 *   - ChatGPT -> 15 tokens
 *   - ZZ      = 2 x Z  (per-letter fallback)
 *   - empty / whitespace / punctuation -> 0 tokens
 *   - GPS, GPS. GPS! ≡ GPS  (trailing punctuation drop)
 *   - Z2Z9 ≡ ZZ            (digits dropped from letter_fallback)
 *   - Python ≠ PYTHON      (case-sensitive loanword vs. letter_fallback)
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
    // Fixture sanity
    // -----------------------------------------------------------------------

    @Test
    fun matrix_fixture_loads() {
        val root = loadMatrix()
        assertEquals(
            "schema_version drift -- update ZhEnLoanwordMatrixTest if this is intentional",
            1, root.getInt("schema_version"),
        )
        val cases = root.getJSONArray("cases")
        assertTrue(
            "matrix must keep ≥17 cases (parent commit T14)",
            cases.length() >= 17,
        )
    }

    // -----------------------------------------------------------------------
    // Per-case parity (numeric expectations only).
    // -----------------------------------------------------------------------

    @Test
    fun exact_token_count_cases_match_fixture() {
        val root = loadMatrix()
        val cases = root.getJSONArray("cases")
        var verified = 0
        PiperPlusG2p.create(ctx).use { g2p ->
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i)
                if (!c.has("input") || !c.has("expected_token_count")) continue
                val input = c.getString("input")
                val expected = c.getInt("expected_token_count")
                val got = tokenCount(g2p, input)
                assertEquals(
                    "case '${c.getString("name")}' input=\"$input\" notes=${c.optString("notes", "")}",
                    expected, got,
                )
                verified++
            }
        }
        assertTrue(
            "matrix must keep ≥4 exact-count cases (GPS / USB / Python / ChatGPT)",
            verified >= 4,
        )
    }

    @Test
    fun letter_fallback_zz_doubles_z() {
        // ZZ must produce exactly 2x the tokens of Z (per-letter fallback).
        PiperPlusG2p.create(ctx).use { g2p ->
            val z = tokenCount(g2p, "Z")
            val zz = tokenCount(g2p, "ZZ")
            assertEquals(
                "letter_fallback per-letter contract: ZZ ($zz) != 2 x Z (${z * 2})",
                z * 2, zz,
            )
        }
    }

    @Test
    fun trailing_punctuation_does_not_change_token_count() {
        PiperPlusG2p.create(ctx).use { g2p ->
            val bare = tokenCount(g2p, "GPS")
            for (trailer in listOf(",", ".", "!")) {
                val withTrailer = tokenCount(g2p, "GPS$trailer")
                assertEquals(
                    "trailing '$trailer' must not change token count (GPS=$bare)",
                    bare, withTrailer,
                )
            }
        }
    }

    @Test
    fun digits_drop_silently_from_letter_fallback() {
        // Z2Z9 must equal ZZ (digits 2 and 9 dropped).
        PiperPlusG2p.create(ctx).use { g2p ->
            val zz = tokenCount(g2p, "ZZ")
            val z2z9 = tokenCount(g2p, "Z2Z9")
            assertEquals(
                "digits silently drop: Z2Z9=$z2z9 != ZZ=$zz",
                zz, z2z9,
            )
        }
    }

    @Test
    fun case_sensitive_loanword_python_vs_PYTHON_differ() {
        // PYTHON falls through to letter_fallback (case-sensitive miss).
        PiperPlusG2p.create(ctx).use { g2p ->
            val mixed = tokenCount(g2p, "Python")
            val upper = tokenCount(g2p, "PYTHON")
            assertNotEquals(
                "case-sensitive loanword broken: Python=$mixed PYTHON=$upper must differ",
                mixed, upper,
            )
        }
    }

    @Test
    fun empty_and_whitespace_and_punctuation_produce_zero_tokens() {
        PiperPlusG2p.create(ctx).use { g2p ->
            for (input in listOf("", "   ", ",.!?")) {
                val got = tokenCount(g2p, input)
                assertEquals(
                    "input \"$input\" should yield 0 tokens, got $got",
                    0, got,
                )
            }
        }
    }

    // -----------------------------------------------------------------------
    // Issue #384 example sentences -- the embedded English token count must
    // not regress to zero (i.e., the dispatch path still fires).
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
    // ZH-EN dispatch toggle (PiperPlusG2pInstrumentedTest covers the
    // toggle mechanics; this asserts the *behavior* changes accordingly).
    // -----------------------------------------------------------------------

    @Test
    fun disabling_zh_en_dispatch_changes_GPS_token_count() {
        // With dispatch enabled (default), GPS phonemizes via Mandarin
        // pinyin (11 tokens). Disabling it should change the token count
        // (English path takes over, or letter_fallback kicks in).
        PiperPlusG2p.create(ctx).use { g2p ->
            assertTrue("dispatch should be enabled by default", g2p.isZhEnDispatchEnabled())
            val withDispatch = tokenCount(g2p, "GPS")

            g2p.setZhEnDispatchEnabled(false)
            val withoutDispatch = tokenCount(g2p, "GPS")

            assertNotEquals(
                "disabling dispatch had no effect on GPS: $withDispatch == $withoutDispatch. " +
                    "Either toggle did not propagate, or both paths happen to produce 11 tokens.",
                withDispatch, withoutDispatch,
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
