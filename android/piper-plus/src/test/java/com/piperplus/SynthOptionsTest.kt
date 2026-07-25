package com.piperplus

import org.junit.Assert.assertEquals
import org.junit.Test

class SynthOptionsTest {

    @Test
    fun `defaults match the C API defaults`() {
        val options = SynthOptions()
        assertEquals(0, options.speakerId)
        assertEquals(-1, options.languageId)
        assertEquals(1.0f, options.lengthScale, TOLERANCE)
        assertEquals(0.4f, options.noiseScale, TOLERANCE)
        assertEquals(0.5f, options.noiseW, TOLERANCE)
        assertEquals(0.2f, options.sentenceSilenceSec, TOLERANCE)
    }

    @Test
    fun `allows overriding individual fields`() {
        val options = SynthOptions(languageId = 2, lengthScale = 0.5f)
        assertEquals(2, options.languageId)
        assertEquals(0.5f, options.lengthScale, TOLERANCE)
        // 未指定のフィールドは既定値のまま
        assertEquals(0, options.speakerId)
    }

    private companion object {
        const val TOLERANCE = 1e-6f
    }
}
