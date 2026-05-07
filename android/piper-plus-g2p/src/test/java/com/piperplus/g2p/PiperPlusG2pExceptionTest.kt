package com.piperplus.g2p

import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/** L1: contract checks for [PiperPlusG2pException]. */
class PiperPlusG2pExceptionTest {

    @Test
    fun `message is preserved`() {
        val ex = PiperPlusG2pException("dict not found")
        assertEquals("dict not found", ex.message)
    }

    @Test
    fun `is a RuntimeException so callers do not need checked-exception wiring`() {
        val ex: Throwable = PiperPlusG2pException("any")
        assertTrue(ex is RuntimeException)
    }

    @Test
    fun `cause defaults to null`() {
        val ex = PiperPlusG2pException("only message")
        assertNull(ex.cause)
    }

    @Test
    fun `cause is preserved when supplied`() {
        val origin = IOException("boom")
        val ex = PiperPlusG2pException("wrapped", origin)
        assertSame(origin, ex.cause)
        assertEquals("wrapped", ex.message)
    }
}
