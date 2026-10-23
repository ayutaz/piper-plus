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
 * L4: cross-runtime parity, structural-check variant.
 *
 * Reads `tests/fixtures/g2p/phoneme_test_cases.json` (synced into
 * androidTest assets at build time) and verifies that for every non-Japanese
 * fixture the Kotlin runtime produces:
 *   - at least `expected_token_count_min` tokens (when present), and
 *   - all phonemes listed in `expected_contains` (when present).
 *
 * `expected_contains` lists phonemes as the golden spells them, so they are
 * mapped to the PUA characters libpiper_plus emits (`pua.json`). Cases listed
 * in `known_divergences.json` for the `cpp` runtime are phonemized but not
 * checked: they are known to fall short (Issues #821 / #822), and
 * [byte_for_byte_parity_with_python_golden] tracks them.
 *
 * Japanese cases are skipped here because they require an OpenJTalk
 * dictionary that is not bundled with the test APK.
 */
@RunWith(AndroidJUnit4::class)
class PhonemeFixtureParityTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().context

    private fun asset(name: String): String = try {
        ctx.assets.open("g2p_fixtures/$name").bufferedReader().use { it.readText() }
    } catch (e: java.io.IOException) {
        // The files are synced from the repo by the syncG2pFixture Gradle
        // task; fail loudly rather than silently skip when that breaks.
        throw AssertionError(
            "g2p_fixtures/$name missing from androidTest assets — syncG2pFixture didn't run",
            e,
        )
    }

    private fun knownDivergences(): Map<GoldenKey, KnownDivergence> {
        val json = asset("known_divergences.json")
        val golden = GoldenParity.parseGolden(asset("phoneme_test_cases_golden.json"))
        val problems = GoldenParity.validateDivergences(json, golden)
        assertEquals("known_divergences.json is invalid", emptyList<String>(), problems)
        return GoldenParity.parseDivergences(json, GoldenParity.RUNTIME)
    }

    @Test
    fun parity_for_non_japanese_fixtures() {
        val cases = JSONObject(asset("phoneme_test_cases.json")).getJSONArray("test_cases")
        val pua = GoldenParity.parsePuaTable(asset("pua.json"))
        val known = knownDivergences()

        var verified = 0
        val failures = mutableListOf<String>()
        PiperPlusG2p.create(InstrumentationRegistry.getInstrumentation().targetContext).use { g2p ->
            for (i in 0 until cases.length()) {
                val case = cases.getJSONObject(i)
                val lang = case.getString("language")
                if (lang == "ja") continue // dictionary not bundled in test APK

                val input = case.getString("input")
                val label = "[$lang] '$input' (${case.optString("description", "(no description)")})"
                val result = try {
                    g2p.phonemize(input, lang)
                } catch (e: PiperPlusG2pException) {
                    failures += "$label: phonemize failed: ${e.message}"
                    continue
                }
                verified++
                if (GoldenKey(lang, input) in known) continue

                if (case.has("expected_token_count_min")) {
                    val min = case.getInt("expected_token_count_min")
                    if (result.numPhonemes < min) {
                        failures += "$label: expected >= $min tokens, got " +
                            "${result.numPhonemes}: ${result.phonemes}"
                    }
                }
                if (case.has("expected_contains")) {
                    val expected = case.getJSONArray("expected_contains")
                    for (j in 0 until expected.length()) {
                        val ph = expected.getString(j)
                        if (!result.phonemeList.contains(pua[ph] ?: ph)) {
                            failures += "$label: missing expected phoneme '$ph' in: ${result.phonemes}"
                        }
                    }
                }
            }
        }
        // Sanity: the fixture file must contain at least some non-JA cases.
        assertNotEquals("no non-JA fixtures verified — fixture sync broke?", 0, verified)
        if (failures.isNotEmpty()) {
            throw AssertionError(
                "Structural fixture failures (${failures.size}, $verified cases):\n" +
                    failures.joinToString("\n"),
            )
        }
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
        assertTrue(
            "fixture must have a 'version' field",
            root.has("version"),
        )
    }

    /**
     * Strict parity against the Python pre-computed golden fixture
     * (`phoneme_test_cases_golden.json`), compared token by token after the
     * representation differences described in [GoldenParity].
     *
     * Fails when a case differs and is not listed in
     * `known_divergences.json`, and when a listed case starts to match, so
     * the list shrinks as the linked issues are fixed.
     *
     * Skipped languages:
     *   - ja: dictionary not bundled in the test APK.
     *   - ko: absent from the golden (Python g2pk2 does not run on every
     *         generator host); [parity_for_non_japanese_fixtures] covers it.
     */
    @Test
    fun byte_for_byte_parity_with_python_golden() {
        val golden = GoldenParity.parseGolden(asset("phoneme_test_cases_golden.json"))
        val pua = GoldenParity.parsePuaTable(asset("pua.json"))
        val known = knownDivergences()

        val results = mutableListOf<Pair<GoldenCase, String?>>()
        PiperPlusG2p.create(InstrumentationRegistry.getInstrumentation().targetContext).use { g2p ->
            for (case in golden) {
                if (case.language == "ja") continue
                val actual = try {
                    g2p.phonemize(case.input, case.language).phonemes
                } catch (e: PiperPlusG2pException) {
                    null
                }
                results += case to actual
            }
        }
        val report = GoldenParity.compare(results, known, pua)

        assertNotEquals("no parity cases verified — golden fixture empty?", 0, report.verified)
        val messages = report.unexpected + report.stale
        if (messages.isNotEmpty()) {
            throw AssertionError(
                "Golden parity failures (${report.unexpected.size} unexpected, " +
                    "${report.stale.size} stale, ${report.known} known, ${report.verified} cases):\n" +
                    messages.joinToString("\n\n"),
            )
        }
    }
}
