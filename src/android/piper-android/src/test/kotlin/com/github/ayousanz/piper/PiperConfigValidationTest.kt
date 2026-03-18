package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Test

class PiperConfigValidationTest {

    @Test(expected = IllegalArgumentException::class)
    fun `negative noiseScale throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseScale = -0.1f,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `zero lengthScale throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            lengthScale = 0f,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `negative lengthScale throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            lengthScale = -1.0f,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `noiseW above 1 throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseW = 1.01f,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `noiseW below 0 throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseW = -0.01f,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `negative speakerId throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            speakerId = -1,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `empty modelPath throws`() {
        PiperConfig(
            modelPath = "",
            configPath = "/config.json",
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `empty configPath throws`() {
        PiperConfig(
            modelPath = "/model.onnx",
            configPath = "",
        )
    }

    @Test
    fun `boundary value noiseScale 0 succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseScale = 0f,
        )
        assertEquals(0f, config.noiseScale, 0.001f)
    }

    @Test
    fun `boundary value noiseW 0 succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseW = 0f,
        )
        assertEquals(0f, config.noiseW, 0.001f)
    }

    @Test
    fun `boundary value noiseW 1 succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            noiseW = 1f,
        )
        assertEquals(1f, config.noiseW, 0.001f)
    }

    @Test
    fun `boundary value lengthScale just above 0 succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            lengthScale = 0.001f,
        )
        assertEquals(0.001f, config.lengthScale, 0.0001f)
    }

    @Test
    fun `boundary value speakerId 0 succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            speakerId = 0,
        )
        assertEquals(0, config.speakerId)
    }

    @Test
    fun `valid config with all boundary values succeeds`() {
        val config = PiperConfig(
            modelPath = "/model.onnx",
            configPath = "/config.json",
            speakerId = 0,
            noiseScale = 0f,
            lengthScale = 0.001f,
            noiseW = 0f,
        )
        assertNotNull(config)
    }

    @Test
    fun `companion object defaults are accessible`() {
        assertEquals(0, PiperConfig.DEFAULT_SPEAKER_ID)
        assertEquals(0.667f, PiperConfig.DEFAULT_NOISE_SCALE, 0.001f)
        assertEquals(1.0f, PiperConfig.DEFAULT_LENGTH_SCALE, 0.001f)
        assertEquals(0.8f, PiperConfig.DEFAULT_NOISE_W, 0.001f)
    }
}
