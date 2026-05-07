package com.piperplus.g2p

import org.junit.Assert.assertEquals
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
}
