package com.github.ayousanz.piper

import org.junit.Assert.*
import org.junit.Test

class ModelManagerInfoTest {

    @Test
    fun `toConfig with all parameters`() {
        val info = ModelManager.ModelInfo(
            name = "full-params",
            modelPath = "/models/full.onnx",
            configPath = "/models/full.json",
            sizeBytes = 75_000_000L,
        )

        val config = info.toConfig(
            speakerId = 7,
            noiseScale = 0.5f,
            lengthScale = 1.3f,
            noiseW = 0.4f,
        )

        assertEquals("/models/full.onnx", config.modelPath)
        assertEquals("/models/full.json", config.configPath)
        assertEquals(7, config.speakerId)
        assertEquals(0.5f, config.noiseScale, 0.001f)
        assertEquals(1.3f, config.lengthScale, 0.001f)
        assertEquals(0.4f, config.noiseW, 0.001f)
    }

    @Test
    fun `toConfig with custom noiseW only`() {
        val info = ModelManager.ModelInfo(
            name = "custom-nw",
            modelPath = "/model.onnx",
            configPath = "/config.json",
            sizeBytes = 1_000L,
        )

        val config = info.toConfig(noiseW = 0.2f)

        assertEquals(PiperConfig.DEFAULT_SPEAKER_ID, config.speakerId)
        assertEquals(PiperConfig.DEFAULT_NOISE_SCALE, config.noiseScale, 0.001f)
        assertEquals(PiperConfig.DEFAULT_LENGTH_SCALE, config.lengthScale, 0.001f)
        assertEquals(0.2f, config.noiseW, 0.001f)
    }

    @Test
    fun `sizeDisplay for bytes under 1KB`() {
        assertEquals("0 B", ModelManager.ModelInfo("a", "/a.onnx", "/a.json", 0L).sizeDisplay)
        assertEquals("1 B", ModelManager.ModelInfo("b", "/b.onnx", "/b.json", 1L).sizeDisplay)
        assertEquals("999 B", ModelManager.ModelInfo("c", "/c.onnx", "/c.json", 999L).sizeDisplay)
    }

    @Test
    fun `sizeDisplay for KB range`() {
        assertEquals("1.0 KB", ModelManager.ModelInfo("a", "/a.onnx", "/a.json", 1_000L).sizeDisplay)
        assertEquals("10.5 KB", ModelManager.ModelInfo("b", "/b.onnx", "/b.json", 10_500L).sizeDisplay)
        assertEquals("999.9 KB", ModelManager.ModelInfo("c", "/c.onnx", "/c.json", 999_900L).sizeDisplay)
    }

    @Test
    fun `sizeDisplay for MB range`() {
        assertEquals("1.0 MB", ModelManager.ModelInfo("a", "/a.onnx", "/a.json", 1_000_000L).sizeDisplay)
        assertEquals("75.0 MB", ModelManager.ModelInfo("b", "/b.onnx", "/b.json", 75_000_000L).sizeDisplay)
        assertEquals("999.0 MB", ModelManager.ModelInfo("c", "/c.onnx", "/c.json", 999_000_000L).sizeDisplay)
    }

    @Test
    fun `sizeDisplay for GB range formats as MB`() {
        // The current implementation formats everything >= 1_000_000 as MB
        assertEquals("1000.0 MB", ModelManager.ModelInfo("a", "/a.onnx", "/a.json", 1_000_000_000L).sizeDisplay)
        assertEquals("2500.0 MB", ModelManager.ModelInfo("b", "/b.onnx", "/b.json", 2_500_000_000L).sizeDisplay)
    }

    @Test
    fun `ModelInfo equality same values`() {
        val info1 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        val info2 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        assertEquals(info1, info2)
        assertEquals(info1.hashCode(), info2.hashCode())
    }

    @Test
    fun `ModelInfo equality different name`() {
        val info1 = ModelManager.ModelInfo("model-a", "/a.onnx", "/a.json", 100L)
        val info2 = ModelManager.ModelInfo("model-b", "/a.onnx", "/a.json", 100L)
        assertNotEquals(info1, info2)
    }

    @Test
    fun `ModelInfo equality different sizeBytes`() {
        val info1 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        val info2 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 200L)
        assertNotEquals(info1, info2)
    }

    @Test
    fun `ModelInfo equality different paths`() {
        val info1 = ModelManager.ModelInfo("model", "/a.onnx", "/a.json", 100L)
        val info2 = ModelManager.ModelInfo("model", "/b.onnx", "/b.json", 100L)
        assertNotEquals(info1, info2)
    }

    @Test
    fun `ModelInfo copy preserves values`() {
        val original = ModelManager.ModelInfo(
            name = "original",
            modelPath = "/model.onnx",
            configPath = "/config.json",
            sizeBytes = 50_000_000L,
        )

        val copied = original.copy(name = "copied")
        assertEquals("copied", copied.name)
        assertEquals(original.modelPath, copied.modelPath)
        assertEquals(original.configPath, copied.configPath)
        assertEquals(original.sizeBytes, copied.sizeBytes)
    }

    @Test
    fun `ModelInfo copy with size change`() {
        val original = ModelManager.ModelInfo("m", "/m.onnx", "/m.json", 100L)
        val updated = original.copy(sizeBytes = 200L)
        assertEquals(200L, updated.sizeBytes)
        assertEquals(original.name, updated.name)
    }

    @Test
    fun `ModelInfo toString contains name`() {
        val info = ModelManager.ModelInfo("my-model", "/m.onnx", "/m.json", 100L)
        assertTrue(info.toString().contains("my-model"))
    }
}
