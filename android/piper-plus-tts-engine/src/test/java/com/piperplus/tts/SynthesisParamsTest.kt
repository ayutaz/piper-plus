package com.piperplus.tts

import org.junit.Assert.assertEquals
import org.junit.Test

class SynthesisParamsTest {
    @Test
    fun `maps the default speech rate to a unit length scale`() {
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(100), TOLERANCE)
    }

    @Test
    fun `doubling the speech rate halves the length scale`() {
        assertEquals(0.5f, SynthesisParams.lengthScaleOf(200), TOLERANCE)
    }

    @Test
    fun `halving the speech rate doubles the length scale`() {
        assertEquals(2.0f, SynthesisParams.lengthScaleOf(50), TOLERANCE)
    }

    @Test
    fun `clamps the maximum android speech rate`() {
        assertEquals(0.25f, SynthesisParams.lengthScaleOf(400), TOLERANCE)
    }

    @Test
    fun `falls back to a unit length scale for non-positive rates`() {
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(0), TOLERANCE)
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(-10), TOLERANCE)
    }

    private companion object {
        const val TOLERANCE = 1e-6f
    }
}
