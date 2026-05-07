package com.piperplus.g2p

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * L1: pure-JVM checks for the static surface of [DictionaryDownloader].
 *
 * The full happy-path (download + verify SHA-256 + extract TAR) requires
 * a real [android.content.Context], so it lives in the L3 instrumented test
 * suite. This test guards the parts of the contract that don't need an
 * Android runtime — the host allowlist (NFR-SEC-2 host pinning) being the
 * most important one.
 */
class DictionaryDownloaderTest {

    @Test
    fun `huggingface co is in the default allowlist`() {
        assertTrue(
            "huggingface.co must remain on the allowlist — removing it would " +
                "break the documented out-of-the-box flow.",
            "https://huggingface.co" in DictionaryDownloader.ALLOWED_HOSTS,
        )
    }

    @Test
    fun `allowlist hosts all use TLS`() {
        for (host in DictionaryDownloader.ALLOWED_HOSTS) {
            assertTrue(
                "host $host must start with https:// (NFR-SEC-2)",
                host.startsWith("https://"),
            )
        }
    }

    @Test
    fun `allowlist refuses cleartext mirror`() {
        assertFalse(
            "no http:// host should be silently allowed",
            DictionaryDownloader.ALLOWED_HOSTS.any { it.startsWith("http://") },
        )
    }

    @Test
    fun `allowlist is non-empty`() {
        assertTrue(
            "the downloader is useless without at least one trusted host",
            DictionaryDownloader.ALLOWED_HOSTS.isNotEmpty(),
        )
    }
}
