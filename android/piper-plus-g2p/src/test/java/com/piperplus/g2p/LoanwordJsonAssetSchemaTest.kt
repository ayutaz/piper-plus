package com.piperplus.g2p

import java.io.File
import java.security.MessageDigest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * L1: pure-JVM byte-equality check between
 *   - `android/piper-plus-g2p/src/main/assets/zh_en_loanword.json`
 *   - `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json`
 *
 * The repo-wide CI gate `scripts/check_loanword_consistency.py` enforces
 * the same invariant against all 10 mirrors (Python source + 9 runtime
 * mirrors), but this Kotlin test gives the Android module its own
 * fast feedback loop — a `gradlew :piper-plus-g2p:test` run catches
 * loanword drift in seconds, without waiting for the cross-runtime CI
 * gate to surface the failure. Mirror of
 * `Tests/PiperPlusG2PTests/JsonByteParityTests.swift`.
 *
 * This test resolves paths relative to the Gradle `projectDir` (the
 * `android/piper-plus-g2p/` module root), then walks up two levels to
 * the repo root. If the repo layout shifts, the `assumeTrue` calls
 * skip the test rather than fail it — drift detection should not block
 * developers running tests outside a checked-out worktree (e.g. unzipped
 * source archive).
 */
class LoanwordJsonAssetSchemaTest {

    private val moduleRoot: File = File(System.getProperty("user.dir") ?: ".")

    private val pythonCanonical: File = moduleRoot.resolve(
        "../../src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json",
    ).normalize()

    private val androidMirror: File = moduleRoot.resolve(
        "src/main/assets/zh_en_loanword.json",
    ).normalize()

    private fun sha256(f: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { input ->
            val buf = ByteArray(8 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                digest.update(buf, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    @Test
    fun android_assets_loanword_json_is_byte_equal_to_python_source() {
        assumeTrue(
            "Python canonical source not reachable from $moduleRoot — " +
                "test runs only inside a piper-plus checkout",
            pythonCanonical.exists(),
        )
        assertNotNull("Android mirror missing at $androidMirror", androidMirror)
        assertEquals(
            """
            android/piper-plus-g2p/src/main/assets/zh_en_loanword.json
            drifted from src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json.

            Run from the repo root:
                python scripts/check_loanword_consistency.py --fix
                git add android/piper-plus-g2p/src/main/assets/

            python: ${pythonCanonical.absolutePath}
            android: ${androidMirror.absolutePath}
            """.trimIndent(),
            sha256(pythonCanonical),
            sha256(androidMirror),
        )
    }

    @Test
    fun android_assets_loanword_json_byte_size_is_nonzero() {
        // A zero-byte mirror would still be byte-equal to a zero-byte
        // canonical (both sha256 to the same constant). Guard explicitly.
        assertEquals(
            "android mirror is empty — packaging or sync regression",
            true,
            androidMirror.exists() && androidMirror.length() > 0,
        )
    }
}
