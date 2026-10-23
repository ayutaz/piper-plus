package com.piperplus.g2p

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * L1: pure-JVM tests for [GoldenParity], which the L3 instrumented parity
 * tests use to compare libpiper_plus output with the Python golden fixture.
 *
 * The last two tests read the real fixture files, so a broken
 * `known_divergences.json` fails here in seconds instead of on the emulator.
 */
class GoldenParityTest {

    private val pua = mapOf("rr" to "", "tone3" to "")

    private fun case(lang: String, input: String, expected: String) =
        GoldenCase(lang, input, expected, "")

    private fun divergence(lang: String, input: String) =
        KnownDivergence(GoldenKey(lang, input), "planned", 1, "reason")

    // ---- normalize ------------------------------------------------------

    @Test
    fun `expected tokens are mapped to their PUA codepoints`() {
        assertEquals(
            listOf("p", "ˈ", "e", "", "o"),
            GoldenParity.normalize("es", "p ˈ e rr o", pua),
        )
    }

    @Test
    fun `word boundaries are kept outside Chinese`() {
        assertEquals(
            listOf("a", " ", "b"),
            GoldenParity.normalize("es", "a   b", pua),
        )
    }

    @Test
    fun `Chinese drops punctuation and word boundaries`() {
        assertEquals(
            listOf("n", "i", ""),
            GoldenParity.normalize("zh", "n i tone3   .", pua),
        )
    }

    // ---- compare --------------------------------------------------------

    @Test
    fun `PUA-encoded output matches a plain golden token`() {
        val report = GoldenParity.compare(
            listOf(case("es", "perro", "p ˈ e rr o") to "p ˈ e  o"),
            emptyMap(),
            pua,
        )
        assertEquals(1, report.verified)
        assertTrue(report.unexpected.isEmpty())
        assertTrue(report.stale.isEmpty())
    }

    @Test
    fun `runtime output is not mapped, so a plain multi-char token still differs`() {
        val report = GoldenParity.compare(
            listOf(case("es", "perro", "p ˈ e rr o") to "p ˈ e rr o"),
            emptyMap(),
            pua,
        )
        assertEquals(1, report.unexpected.size)
    }

    @Test
    fun `an unlisted mismatch is reported`() {
        val report = GoldenParity.compare(
            listOf(case("en", "0", "z ˈ ɪ ɹ o ʊ") to ""),
            emptyMap(),
            pua,
        )
        assertEquals(1, report.unexpected.size)
        assertTrue(report.unexpected.single().contains("[en] '0'"))
    }

    @Test
    fun `a listed mismatch is not reported`() {
        val report = GoldenParity.compare(
            listOf(case("en", "0", "z ˈ ɪ ɹ o ʊ") to ""),
            mapOf(GoldenKey("en", "0") to divergence("en", "0")),
            pua,
        )
        assertEquals(1, report.verified)
        assertEquals(1, report.known)
        assertTrue(report.unexpected.isEmpty())
        assertTrue(report.stale.isEmpty())
    }

    @Test
    fun `a listed case that now matches is reported as stale`() {
        val report = GoldenParity.compare(
            listOf(case("en", "1", "w ˈ ʌ n") to "w ˈ ʌ n"),
            mapOf(GoldenKey("en", "1") to divergence("en", "1")),
            pua,
        )
        assertEquals(1, report.stale.size)
        assertTrue(report.stale.single().contains("[en] '1'"))
    }

    @Test
    fun `a phonemize failure is a mismatch`() {
        val report = GoldenParity.compare(
            listOf(case("fr", "x", "k s") to null),
            emptyMap(),
            pua,
        )
        assertEquals(1, report.unexpected.size)
    }

    // ---- known_divergences.json ----------------------------------------

    private val golden = listOf(case("en", "0", "z"), case("fr", "c'est", "s ɛ s"))

    private fun registry(vararg entries: String) = """
        {
          "schema_version": 1,
          "runtimes": {"cpp": "libpiper_plus"},
          "divergences": [${entries.joinToString(",")}]
        }
    """.trimIndent()

    private fun entry(
        lang: String = "en",
        input: String = "0",
        runtimes: String = "[\"cpp\"]",
        status: String = "planned",
        issue: Int = 821,
        reason: String = "digits are dropped",
    ) = """
        {"runtimes": $runtimes, "language": "$lang", "input": "$input",
         "status": "$status", "issue": $issue, "reason": "$reason"}
    """

    @Test
    fun `a well-formed registry has no problems and parses per runtime`() {
        val json = registry(entry(), entry(lang = "fr", input = "c'est", runtimes = "[\"rust\"]"))
        val withRust = json.replace("{\"cpp\": \"libpiper_plus\"}", "{\"cpp\": \"a\", \"rust\": \"b\"}")

        assertEquals(emptyList<String>(), GoldenParity.validateDivergences(withRust, golden))
        val cpp = GoldenParity.parseDivergences(withRust, "cpp")
        assertEquals(setOf(GoldenKey("en", "0")), cpp.keys)
    }

    @Test
    fun `registry problems are all reported`() {
        val json = registry(
            entry(reason = " "),
            entry(lang = "fr", input = "c'est", issue = 0),
            entry(lang = "fr", input = "c'est", status = "maybe"),
            entry(input = "missing"),
            entry(runtimes = "[\"kotlin\"]"),
            entry(runtimes = "[]"),
        )
        val problems = GoldenParity.validateDivergences(json, golden)

        fun has(text: String) = assertTrue(
            "expected a problem containing '$text' in $problems",
            problems.any { it.contains(text) },
        )
        has("reason")
        has("issue")
        has("status")
        has("not in phoneme_test_cases_golden.json")
        has("unknown runtime 'kotlin'")
        has("no runtimes")
        has("duplicate")
    }

    // ---- real fixture files ---------------------------------------------

    private val fixtureDir: File = File(System.getProperty("user.dir") ?: ".")
        .resolve("../../tests/fixtures/g2p").normalize()

    private val puaJson: File = File(System.getProperty("user.dir") ?: ".")
        .resolve("../../src/python/g2p/piper_plus_g2p/data/pua.json").normalize()

    @Test
    fun `the repository registry is valid against the golden fixture`() {
        val goldenCases = GoldenParity.parseGolden(
            fixtureDir.resolve("phoneme_test_cases_golden.json").readText(),
        )
        val problems = GoldenParity.validateDivergences(
            fixtureDir.resolve("known_divergences.json").readText(),
            goldenCases,
        )
        assertEquals(emptyList<String>(), problems)
    }

    @Test
    fun `the repository PUA table maps multi-codepoint tokens`() {
        val table = GoldenParity.parsePuaTable(puaJson.readText())
        assertEquals("", table["rr"])
        assertEquals("", table["tʃ"])
    }
}
