package com.piperplus.g2p

import org.json.JSONArray
import org.json.JSONObject

/** A golden fixture case is identified by its language and input text. */
internal data class GoldenKey(val language: String, val input: String)

internal data class GoldenCase(
    val language: String,
    val input: String,
    val expectedPhonemes: String,
    val description: String,
)

/** One `tests/fixtures/g2p/known_divergences.json` entry for a runtime. */
internal data class KnownDivergence(
    val key: GoldenKey,
    val status: String,
    val issue: Int,
    val reason: String,
)

/**
 * @property verified   Cases compared.
 * @property known      Cases that differ and are listed as known divergences.
 * @property unexpected Cases that differ and are not listed.
 * @property stale      Listed cases that now match; their entries must go.
 */
internal data class ParityReport(
    val verified: Int,
    val known: Int,
    val unexpected: List<String>,
    val stale: List<String>,
)

/**
 * Compares libpiper_plus G2P output with `phoneme_test_cases_golden.json`,
 * which Python generates.
 *
 * One representation difference is not a divergence: libpiper_plus encodes
 * multi-codepoint phonemes (`rr`, `tʃ`, `tone3`) as single PUA characters
 * (`pua.json`); the golden spells them out. Only the golden side is mapped,
 * so a runtime that forgets the PUA encoding still fails. Chinese
 * punctuation and word boundaries are compared as they are: since Issue #823
 * Python keeps CJK punctuation too (docs/spec/cjk-punctuation-contract.toml).
 * Real differences must be listed in `known_divergences.json`.
 */
internal object GoldenParity {
    /** `known_divergences.json` runtime key for libpiper_plus (C++). */
    const val RUNTIME = "cpp"

    private val STATUSES = setOf("planned", "accepted")

    fun parsePuaTable(json: String): Map<String, String> {
        val entries = JSONObject(json).getJSONArray("entries")
        return (0 until entries.length()).associate { i ->
            val e = entries.getJSONObject(i)
            e.getString("token") to String(Character.toChars(e.getString("codepoint").removePrefix("0x").toInt(16)))
        }
    }

    fun parseGolden(json: String): List<GoldenCase> {
        val cases = JSONObject(json).getJSONArray("test_cases")
        return (0 until cases.length()).map { i ->
            val c = cases.getJSONObject(i)
            GoldenCase(
                c.getString("language"),
                c.getString("input"),
                c.getString("expected_phonemes"),
                c.optString("description", ""),
            )
        }
    }

    /** Entries that apply to [runtime]. Call [validateDivergences] first. */
    fun parseDivergences(json: String, runtime: String): Map<GoldenKey, KnownDivergence> =
        entries(json)
            .filter { e -> strings(e.optJSONArray("runtimes")).contains(runtime) }
            .associate { e ->
                val key = GoldenKey(e.optString("language"), e.optString("input"))
                key to KnownDivergence(key, e.optString("status"), e.optInt("issue"), e.optString("reason"))
            }

    /** Every problem in the registry, or an empty list when it is valid. */
    fun validateDivergences(json: String, golden: List<GoldenCase>): List<String> {
        val root = JSONObject(json)
        val runtimeNames = root.optJSONObject("runtimes")?.keySet().orEmpty()
        val goldenKeys = golden.map { GoldenKey(it.language, it.input) }.toSet()
        val seen = mutableSetOf<Pair<String, GoldenKey>>()
        val problems = mutableListOf<String>()
        if (root.optInt("schema_version") != 1) problems += "schema_version must be 1"
        entries(json).forEachIndexed { i, e ->
            val key = GoldenKey(e.optString("language"), e.optString("input"))
            val where = "divergences[$i] [${key.language}] '${key.input}'"
            val runtimes = strings(e.optJSONArray("runtimes"))
            if (runtimes.isEmpty()) problems += "$where: no runtimes"
            for (r in runtimes) {
                if (r !in runtimeNames) problems += "$where: unknown runtime '$r'"
                if (!seen.add(r to key)) problems += "$where: duplicate entry for runtime '$r'"
            }
            if (key !in goldenKeys) problems += "$where: case not in phoneme_test_cases_golden.json"
            if (e.optString("status") !in STATUSES) {
                problems += "$where: status must be one of $STATUSES"
            }
            if (e.optInt("issue") <= 0) problems += "$where: issue must be a GitHub issue number"
            if (e.optString("reason").isBlank()) problems += "$where: reason is empty"
        }
        return problems
    }

    /** [phonemes] as tokens in the form libpiper_plus emits them. */
    fun normalize(phonemes: String, pua: Map<String, String>): List<String> =
        splitPhonemeString(phonemes).map { pua[it] ?: it }

    fun compare(
        results: List<Pair<GoldenCase, String?>>,
        known: Map<GoldenKey, KnownDivergence>,
        pua: Map<String, String>,
    ): ParityReport {
        var knownCount = 0
        val unexpected = mutableListOf<String>()
        val stale = mutableListOf<String>()
        for ((case, actual) in results) {
            val key = GoldenKey(case.language, case.input)
            val matches = actual != null &&
                normalize(case.expectedPhonemes, pua) == splitPhonemeString(actual)
            val label = "[${case.language}] '${case.input}'"
            when {
                matches && key in known ->
                    stale += "$label now matches; remove it from known_divergences.json (issue #${known.getValue(key).issue})"
                matches -> Unit
                key in known -> knownCount++
                else -> unexpected += "$label (${case.description})\n" +
                    "  expected: ${case.expectedPhonemes}\n" +
                    "  actual:   ${actual ?: "(phonemize threw)"}"
            }
        }
        return ParityReport(results.size, knownCount, unexpected, stale)
    }

    private fun entries(json: String): List<JSONObject> {
        val array = JSONObject(json).optJSONArray("divergences") ?: return emptyList()
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    private fun strings(array: JSONArray?): List<String> =
        if (array == null) emptyList() else (0 until array.length()).map { array.getString(it) }
}
