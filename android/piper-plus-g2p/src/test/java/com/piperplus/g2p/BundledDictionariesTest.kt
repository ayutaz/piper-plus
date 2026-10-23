package com.piperplus.g2p

import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * L1: pure-JVM tests for [BundledDictionaries.extract].
 *
 * [BundledDictionaries.configure] needs an [android.content.Context] and
 * `android.system.Os`, so it is exercised by the L3 instrumented tests
 * (English / Chinese phonemization returns phonemes only when it worked).
 */
class BundledDictionariesTest {

    private lateinit var root: File
    private val opened = mutableListOf<String>()

    @Before
    fun setUp() {
        root = Files.createTempDirectory("piperplus-bundled-dicts-").toFile()
    }

    @After
    fun tearDown() {
        root.deleteRecursively()
    }

    private fun open(name: String): InputStream {
        opened += name
        return ByteArrayInputStream("data:$name".toByteArray())
    }

    @Test
    fun `extract copies every dictionary into a version directory`() {
        val dir = BundledDictionaries.extract(root, "2.0.2", ::open)

        assertEquals(File(root, "v2.0.2"), dir)
        for (name in BundledDictionaries.FILES) {
            assertEquals("data:$name", File(dir, name).readText())
            assertFalse(File(dir, "$name.tmp").exists())
        }
    }

    @Test
    fun `extract is skipped once a previous call completed`() {
        BundledDictionaries.extract(root, "2.0.2", ::open)
        opened.clear()

        BundledDictionaries.extract(root, "2.0.2", ::open)

        assertTrue(opened.isEmpty())
    }

    @Test
    fun `interrupted extraction is redone`() {
        val failing: (String) -> InputStream = { name ->
            if (name == BundledDictionaries.FILES.last()) throw IOException("disk full")
            open(name)
        }
        try {
            BundledDictionaries.extract(root, "2.0.2", failing)
            fail("expected the failing copy to throw")
        } catch (expected: IOException) {
            assertEquals("disk full", expected.message)
        }
        opened.clear()

        val dir = BundledDictionaries.extract(root, "2.0.2", ::open)

        assertEquals(BundledDictionaries.FILES, opened)
        val last = BundledDictionaries.FILES.last()
        assertEquals("data:$last", File(dir, last).readText())
    }

    @Test
    fun `a new version replaces directories of other versions`() {
        BundledDictionaries.extract(root, "2.0.1", ::open)

        val dir = BundledDictionaries.extract(root, "2.0.2", ::open)

        assertEquals(listOf(dir), root.listFiles()!!.toList())
    }

    @Test
    fun `unsafe characters in the version do not escape the root`() {
        assertEquals(root, BundledDictionaries.extract(root, "..", ::open).parentFile)
        assertEquals("v.._x_y", BundledDictionaries.extract(root, "../x y", ::open).name)
    }
}
