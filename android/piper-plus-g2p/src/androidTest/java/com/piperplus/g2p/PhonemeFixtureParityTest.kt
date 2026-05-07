package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L4: cross-runtime parity, structural-check variant.
 *
 * Reads `tests/fixtures/g2p/phoneme_test_cases.json` (synced into
 * androidTest assets at build time) and verifies that for every non-Japanese
 * fixture the Kotlin runtime produces:
 *   - at least `expected_token_count_min` tokens (when present), and
 *   - all phonemes listed in `expected_contains` (when present).
 *
 * The fixture is the same one Python / Rust / Go / WASM / C# / C++ assert
 * against, so passing this test gives us byte-shape parity (not yet
 * byte-for-byte; that's a follow-up PR with pre-computed phoneme strings).
 *
 * Japanese cases are skipped here because they require an OpenJTalk
 * dictionary that is not bundled with the test APK.
 */
@RunWith(AndroidJUnit4::class)
class PhonemeFixtureParityTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().context

    @Test
    fun parity_for_non_japanese_fixtures() {
        val rawJson = ctx.assets.open("g2p_fixtures/phoneme_test_cases.json")
            .bufferedReader().use { it.readText() }
        val root = JSONObject(rawJson)
        val cases = root.getJSONArray("test_cases")

        var verified = 0
        PiperPlusG2p.create(InstrumentationRegistry.getInstrumentation().targetContext).use { g2p ->
            for (i in 0 until cases.length()) {
                val case = cases.getJSONObject(i)
                val lang = case.getString("language")
                if (lang == "ja") continue  // dictionary not bundled in test APK

                val input = case.getString("input")
                val description = case.optString("description", "(no description)")
                val result = try {
                    g2p.phonemize(input, lang)
                } catch (e: PiperPlusG2pException) {
                    throw AssertionError(
                        "phonemize failed for [$lang] '$input' ($description): ${e.message}",
                        e,
                    )
                }

                if (case.has("expected_token_count_min")) {
                    val min = case.getInt("expected_token_count_min")
                    assertTrue(
                        "[$lang] '$input' ($description) expected >= $min tokens, got " +
                            "${result.numPhonemes}",
                        result.numPhonemes >= min,
                    )
                }
                if (case.has("expected_contains")) {
                    val expected = case.getJSONArray("expected_contains")
                    for (j in 0 until expected.length()) {
                        val ph = expected.getString(j)
                        assertTrue(
                            "[$lang] '$input' ($description) missing expected phoneme '$ph' " +
                                "in: ${result.phonemes}",
                            result.phonemeList.contains(ph),
                        )
                    }
                }
                verified++
            }
        }
        // Sanity: the fixture file must contain at least some non-JA cases.
        assertNotEquals("no non-JA fixtures verified — fixture sync broke?", 0, verified)
    }

    @Test
    fun fixture_file_is_present_and_well_formed() {
        val raw = try {
            ctx.assets.open("g2p_fixtures/phoneme_test_cases.json")
                .bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            throw AssertionError(
                "g2p_fixtures/phoneme_test_cases.json missing — Gradle syncG2pFixture " +
                    "task did not run",
                e,
            )
        }
        val root = JSONObject(raw)
        assertNotNull(root.getJSONArray("test_cases"))
        assumeTrue(
            "fixture must have a 'version' field",
            root.has("version"),
        )
    }

    /**
     * Strict byte-for-byte parity against the Python pre-computed golden
     * fixture (`phoneme_test_cases_golden.json`). When the JNI's space-
     * separated phoneme string differs from the Python reference even by
     * one character, the test fails — so any drift in the C++ phonemize
     * pipeline relative to Python is caught immediately.
     *
     * Skipped languages:
     *   - ja: dictionary not bundled in the test APK.
     *   - ko: g2pk2 inside libpiper_plus.so should match Python g2pk2,
     *         but on hosts where Python g2pk2 cannot run (Windows / no
     *         eunjeon) the golden file may omit those cases — we only
     *         compare what's in the golden.
     */
    @Test
    fun byte_for_byte_parity_with_python_golden() {
        val rawJson = try {
            ctx.assets.open("g2p_fixtures/phoneme_test_cases_golden.json")
                .bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            // Golden file not synced yet — skip rather than fail. The
            // structural check above still catches major regressions.
            assumeTrue(
                "phoneme_test_cases_golden.json not present; run " +
                    "tools/generate_g2p_golden.py to generate",
                false,
            )
            return
        }
        val root = JSONObject(rawJson)
        val cases = root.getJSONArray("test_cases")

        var verified = 0
        val mismatches = mutableListOf<String>()
        PiperPlusG2p.create(InstrumentationRegistry.getInstrumentation().targetContext).use { g2p ->
            for (i in 0 until cases.length()) {
                val case = cases.getJSONObject(i)
                val lang = case.getString("language")
                if (lang == "ja") continue

                val input = case.getString("input")
                val expected = case.getString("expected_phonemes")
                val description = case.optString("description", "")
                val actual = try {
                    g2p.phonemize(input, lang).phonemes
                } catch (e: PiperPlusG2pException) {
                    mismatches += "[$lang] '$input': phonemize threw ${e.message}"
                    continue
                }
                if (actual != expected) {
                    mismatches += "[$lang] '$input' ($description)\n" +
                        "  expected: $expected\n" +
                        "  actual:   $actual"
                }
                verified++
            }
        }
        assertNotEquals("no parity cases verified — golden fixture empty?", 0, verified)
        if (mismatches.isNotEmpty()) {
            throw AssertionError(
                "Byte-for-byte parity failures (${mismatches.size}/${verified}):\n" +
                    mismatches.joinToString("\n\n"),
            )
        }
    }
}
