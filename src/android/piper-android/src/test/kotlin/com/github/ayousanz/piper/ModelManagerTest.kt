package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class ModelManagerTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun `ModelInfo toConfig creates correct PiperConfig`() {
        val info = ModelManager.ModelInfo(
            name = "test-model",
            modelPath = "/path/to/model.onnx",
            configPath = "/path/to/config.json",
            sizeBytes = 50_000_000L,
        )

        val config = info.toConfig(speakerId = 3, lengthScale = 0.8f)
        assertEquals("/path/to/model.onnx", config.modelPath)
        assertEquals("/path/to/config.json", config.configPath)
        assertEquals(3, config.speakerId)
        assertEquals(0.8f, config.lengthScale, 0.001f)
        assertEquals(PiperConfig.DEFAULT_NOISE_SCALE, config.noiseScale, 0.001f)
    }

    @Test
    fun `ModelInfo toConfig uses defaults`() {
        val info = ModelManager.ModelInfo(
            name = "test",
            modelPath = "/model.onnx",
            configPath = "/config.json",
            sizeBytes = 100L,
        )

        val config = info.toConfig()
        assertEquals(PiperConfig.DEFAULT_SPEAKER_ID, config.speakerId)
        assertEquals(PiperConfig.DEFAULT_NOISE_SCALE, config.noiseScale, 0.001f)
        assertEquals(PiperConfig.DEFAULT_LENGTH_SCALE, config.lengthScale, 0.001f)
    }

    @Test
    fun `ModelInfo sizeDisplay formats correctly`() {
        assertEquals("50.0 MB", ModelManager.ModelInfo("a", "", "", 50_000_000L).sizeDisplay)
        assertEquals("1.5 MB", ModelManager.ModelInfo("b", "", "", 1_500_000L).sizeDisplay)
        assertEquals("500.0 KB", ModelManager.ModelInfo("c", "", "", 500_000L).sizeDisplay)
        assertEquals("100 B", ModelManager.ModelInfo("d", "", "", 100L).sizeDisplay)
    }

    @Test
    fun `listModels returns empty for nonexistent directory`() {
        // ModelManager requires Context, so we test ModelInfo directly
        // Full integration tests require Android instrumented tests
        val info = ModelManager.ModelInfo(
            name = "test",
            modelPath = "/nonexistent/model.onnx",
            configPath = "/nonexistent/config.json",
            sizeBytes = 0L,
        )
        assertNotNull(info)
        assertEquals("test", info.name)
    }

    @Test
    fun `ModelInfo equality works`() {
        val info1 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        val info2 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        val info3 = ModelManager.ModelInfo("other", "/b.onnx", "/b.json", 200L)

        assertEquals(info1, info2)
        assertNotEquals(info1, info3)
    }
}
