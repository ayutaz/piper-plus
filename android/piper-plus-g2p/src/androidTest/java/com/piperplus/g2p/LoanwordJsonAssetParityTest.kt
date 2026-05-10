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
 * L4: AAR-bundled JSON parity for the ZH-EN loanword dictionary.
 *
 * `src/main/assets/zh_en_loanword.json` is one of 10 mirror copies of
 * `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json`, byte-equality
 * enforced by `scripts/check_loanword_consistency.py`. The CI gate fires
 * at PR time on the file as it sits in the repo, but does not verify
 * what AGP actually packs into the AAR. A misconfigured assetPackaging /
 * sourceSets shift could silently strip the resource from the bundle
 * while leaving the source file intact.
 *
 * This test re-asserts the schema invariants from inside the AAR consumer's
 * runtime view, so any drift between repo file and AAR-packed file fires.
 *
 * The byte-for-byte hash check against the canonical Python source lives
 * in the L1 `LoanwordJsonAssetSchemaTest.kt` (pure JVM) — that test reads
 * the assets file via the source path directly.
 */
@RunWith(AndroidJUnit4::class)
class LoanwordJsonAssetParityTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    /**
     * The bundled asset must be present and contain valid JSON with the
     * three documented sections (acronyms / loanwords / letter_fallback).
     */
    @Test
    fun bundled_loanword_asset_is_present_and_well_formed() {
        val raw = ctx.assets.open("zh_en_loanword.json")
            .bufferedReader().use { it.readText() }
        val root = JSONObject(raw)
        assertNotNull("acronyms section missing", root.opt("acronyms"))
        assertNotNull("loanwords section missing", root.opt("loanwords"))
        assertNotNull("letter_fallback section missing", root.opt("letter_fallback"))
    }

    /**
     * CLAUDE.md pins counts at acronyms 66 / loanwords 40 / letter_fallback 26.
     * A change is a deliberate Python source edit; this test fires on any
     * accidental drift in either source or mirror (since they are byte-equal
     * by CI gate, this asset count is a proxy for the Python source count).
     */
    @Test
    fun bundled_loanword_asset_has_documented_counts() {
        val raw = ctx.assets.open("zh_en_loanword.json")
            .bufferedReader().use { it.readText() }
        val root = JSONObject(raw)
        assertEquals(
            "acronyms count drifted from CLAUDE.md spec (66). Update CLAUDE.md if intentional.",
            66, root.getJSONObject("acronyms").length(),
        )
        assertEquals(
            "loanwords count drifted from CLAUDE.md spec (40).",
            40, root.getJSONObject("loanwords").length(),
        )
        assertEquals(
            "letter_fallback must equal 26 (A-Z)",
            26, root.getJSONObject("letter_fallback").length(),
        )
    }

    /**
     * Spot-check that headline entries (used by Issue #384's example
     * sentences) are present. A missing GPS / Python / ChatGPT key would
     * mean the embedded-English path silently falls through letter_fallback
     * for these specific tokens.
     */
    @Test
    fun bundled_loanword_asset_contains_headline_entries() {
        val raw = ctx.assets.open("zh_en_loanword.json")
            .bufferedReader().use { it.readText() }
        val root = JSONObject(raw)

        val acronyms = root.getJSONObject("acronyms")
        for (key in listOf("GPS", "USB", "CPU", "GPU", "API")) {
            assertTrue(
                "acronym '$key' missing from bundled JSON",
                acronyms.has(key),
            )
        }
        val loanwords = root.getJSONObject("loanwords")
        for (key in listOf("Python", "iPhone", "ChatGPT")) {
            assertTrue(
                "loanword '$key' missing from bundled JSON",
                loanwords.has(key),
            )
        }
        val fallback = root.getJSONObject("letter_fallback")
        // Letter fallback must cover every uppercase letter.
        for (letter in 'A'..'Z') {
            assertTrue(
                "letter_fallback missing letter '$letter'",
                fallback.has(letter.toString()),
            )
        }
    }

    /**
     * Each section's value must be a list of strings (per Python loader
     * spec). The CI gate enforces this on the source file; we verify the
     * runtime view matches.
     */
    @Test
    fun bundled_loanword_asset_values_are_string_lists() {
        val raw = ctx.assets.open("zh_en_loanword.json")
            .bufferedReader().use { it.readText() }
        val root = JSONObject(raw)
        for (section in listOf("acronyms", "loanwords", "letter_fallback")) {
            val obj = root.getJSONObject(section)
            val keys = obj.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                val arr = obj.optJSONArray(key)
                assertNotNull("$section.$key: expected JSON array, got ${obj.opt(key)}", arr)
                for (i in 0 until arr!!.length()) {
                    val v = arr.opt(i)
                    assertTrue(
                        "$section.$key[$i]: expected string, got $v (${v?.javaClass?.simpleName})",
                        v is String,
                    )
                }
            }
        }
    }
}
