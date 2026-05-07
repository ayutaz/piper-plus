package com.piperplus.g2p

import java.io.File
import java.nio.file.Files
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * L1: pure-JVM tests for [OpenJTalkDictionary].
 *
 * [OpenJTalkDictionary.fromAssets] needs an [android.content.Context], so it
 * is exercised in L3 instrumented tests. The static `fromPath(...)` factory
 * and the [OpenJTalkDictionary.exists] probe can run here.
 */
class OpenJTalkDictionaryTest {

    private lateinit var tmp: File

    @Before
    fun setUp() {
        tmp = Files.createTempDirectory("piperplus-dict-test-").toFile()
    }

    @After
    fun tearDown() {
        tmp.deleteRecursively()
    }

    @Test
    fun `fromPath does not validate the path eagerly`() {
        val dict = OpenJTalkDictionary.fromPath("/nowhere/in/particular")
        // exists() is the documented probe — fromPath itself must not throw
        // because callers may legitimately wrap a path that will be created
        // later (e.g. asset extraction kicked off afterwards).
        assertFalse(dict.exists())
    }

    @Test
    fun `exists returns true when the directory contains files`() {
        File(tmp, "sys.dic").writeBytes(byteArrayOf(0x00, 0x01))
        val dict = OpenJTalkDictionary.fromPath(tmp.absolutePath)
        assertTrue(dict.exists())
    }

    @Test
    fun `exists returns false for empty directory`() {
        val dict = OpenJTalkDictionary.fromPath(tmp.absolutePath)
        assertFalse(dict.exists())
    }

    @Test
    fun `exists returns false for missing path`() {
        val dict = OpenJTalkDictionary.fromPath(File(tmp, "nope").absolutePath)
        assertFalse(dict.exists())
    }

    @Test
    fun `absolutePath round-trips the input`() {
        val dict = OpenJTalkDictionary.fromPath(tmp.absolutePath)
        assertEquals(tmp.absolutePath, dict.absolutePath())
    }
}
