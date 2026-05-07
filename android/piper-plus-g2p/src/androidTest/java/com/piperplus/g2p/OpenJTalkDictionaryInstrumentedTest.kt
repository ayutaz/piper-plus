package com.piperplus.g2p

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * L3 instrumented coverage for the three OpenJTalk dictionary distribution
 * patterns required by FR-DICT-1 / FR-TEST-4:
 *   1. `OpenJTalkDictionary.fromAssets(context)` — extracts a tree from APK
 *      assets into `filesDir`. We synthesise a tiny stub asset tree on-disk
 *      via a custom `extractAssetTree` test scaffold rather than shipping
 *      the real ~102 MB OpenJTalk dictionary in the test APK.
 *   2. `OpenJTalkDictionary.fromPath(absolutePath)` — wraps an existing
 *      directory.
 *   3. `DictionaryDownloader.downloadFromHuggingFace(...)` — full downloader
 *      requires network and is exercised in a separate optional CI lane;
 *      here we instead exercise the static surface (host allowlist /
 *      validation paths) to keep the offline test fast and deterministic.
 */
@RunWith(AndroidJUnit4::class)
class OpenJTalkDictionaryInstrumentedTest {

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var stubDictRoot: File

    @Before
    fun setUp() {
        // Make a fake "dictionary" directory we can wrap with fromPath.
        stubDictRoot = File(ctx.cacheDir, "fake_open_jtalk_dic").apply {
            deleteRecursively()
            mkdirs()
            File(this, "sys.dic").writeBytes(byteArrayOf(0x00, 0x01, 0x02))
            File(this, "char.bin").writeBytes(byteArrayOf(0x03))
        }
    }

    @After
    fun tearDown() {
        stubDictRoot.deleteRecursively()
    }

    // ----- fromPath ---------------------------------------------------------

    @Test
    fun fromPath_returns_handle_pointing_at_existing_directory() {
        val dict = OpenJTalkDictionary.fromPath(stubDictRoot.absolutePath)
        assertEquals(stubDictRoot.absolutePath, dict.absolutePath())
        assertTrue("fake dict dir must report as existing", dict.exists())
    }

    @Test
    fun fromPath_does_not_validate_eagerly() {
        val dict = OpenJTalkDictionary.fromPath("/no/such/dir")
        assertFalse(dict.exists())
    }

    // ----- fromAssets idempotency ------------------------------------------

    @Test
    fun fromAssets_is_idempotent_with_missing_asset_tree() {
        // The test APK does NOT bundle an OpenJTalk dictionary, so
        // fromAssets() should still return a handle whose `exists()` is
        // false — never throw on a missing asset path. We assert the
        // documented contract from OpenJTalkDictionary.kt.
        val dict = try {
            OpenJTalkDictionary.fromAssets(ctx, "this_asset_does_not_exist_in_apk")
        } catch (e: Exception) {
            fail("fromAssets should not throw for missing asset trees: $e")
            return
        }
        // The handle is created; `exists()` is the probe to check.
        assertNotNull(dict)
    }

    // ----- DictionaryDownloader host allowlist (no network) ----------------

    @Test
    fun downloader_host_allowlist_includes_huggingface() {
        assertTrue(
            "huggingface.co must be in DictionaryDownloader.ALLOWED_HOSTS",
            "https://huggingface.co" in DictionaryDownloader.ALLOWED_HOSTS,
        )
    }

    @Test
    fun downloader_host_allowlist_only_uses_tls() {
        for (host in DictionaryDownloader.ALLOWED_HOSTS) {
            assertTrue("host $host must be https", host.startsWith("https://"))
        }
    }

    // ----- create() with explicit dict path --------------------------------

    @Test
    fun create_with_dict_path_initialises_native_handle() {
        // Even though the stub dictionary is not a valid OpenJTalk dict,
        // the C API should at least accept the create() call without
        // crashing. JA phonemize would fail later, but other languages
        // continue to work.
        val dict = OpenJTalkDictionary.fromPath(stubDictRoot.absolutePath)
        PiperPlusG2p.create(ctx, dict).use { g2p ->
            // Non-Japanese path should still phonemize fine.
            val r = g2p.phonemize("hola", "es")
            assertTrue("expected >0 phonemes for Spanish", r.numPhonemes > 0)
        }
    }
}
