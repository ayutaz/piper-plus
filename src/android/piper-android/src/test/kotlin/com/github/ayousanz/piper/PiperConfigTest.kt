package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Test

class PiperConfigTest {

    @Test
    fun `default values are correct`() {
        val config = PiperConfig(
            modelPath = "/path/to/model.onnx",
            configPath = "/path/to/config.json",
        )
        assertEquals(0, config.speakerId)
        assertEquals(0.667f, config.noiseScale, 0.001f)
        assertEquals(1.0f, config.lengthScale, 0.001f)
        assertEquals(0.8f, config.noiseW, 0.001f)
    }

    @Test
    fun `custom values are preserved`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            speakerId = 5,
            noiseScale = 0.5f,
            lengthScale = 1.2f,
            noiseW = 0.6f,
        )
        assertEquals("/model.onnx", config.modelPath)
        assertEquals("/config.json", config.configPath)
        assertEquals(5, config.speakerId)
        assertEquals(0.5f, config.noiseScale, 0.001f)
        assertEquals(1.2f, config.lengthScale, 0.001f)
        assertEquals(0.6f, config.noiseW, 0.001f)
    }

    @Test
    fun `data class equality works`() {
        val config1 = PiperConfig("/model.onnx", "/config.json")
        val config2 = PiperConfig("/model.onnx", "/config.json")
        assertEquals(config1, config2)
    }

    @Test
    fun `data class copy works`() {
        val config = PiperConfig("/model.onnx", "/config.json")
        val modified = config.copy(speakerId = 3, lengthScale = 0.8f)
        assertEquals(3, modified.speakerId)
        assertEquals(0.8f, modified.lengthScale, 0.001f)
        assertEquals(config.modelPath, modified.modelPath)
    }
}
