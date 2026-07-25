package com.piperplus.tts.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ModelPathsTest {

    @get:Rule
    val temp = TemporaryFolder()

    @Test
    fun `resolves model and config paths under a per-model directory`() {
        val paths = ModelPaths(temp.root)
        assertEquals(
            "${temp.root}/models/my-voice",
            paths.modelDir("my-voice").path,
        )
        assertEquals(
            "${temp.root}/models/my-voice/model.onnx",
            paths.modelFile("my-voice").path,
        )
        assertEquals(
            "${temp.root}/models/my-voice/model.onnx.json",
            paths.configFile("my-voice").path,
        )
    }

    @Test
    fun `resolves the dictionary directory at the files root`() {
        val paths = ModelPaths(temp.root)
        assertEquals("${temp.root}/open_jtalk_dic", paths.dictDir().path)
    }

    @Test
    fun `reports not installed when nothing exists`() {
        assertFalse(ModelPaths(temp.root).isInstalled("my-voice"))
    }

    @Test
    fun `reports not installed when the config is missing`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.dictDir().mkdirs()
        assertFalse(paths.isInstalled("my-voice"))
    }

    @Test
    fun `reports not installed when the dictionary is missing`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.configFile("my-voice").writeText("{}")
        assertFalse(paths.isInstalled("my-voice"))
    }

    @Test
    fun `reports installed when model config and dictionary all exist`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.configFile("my-voice").writeText("{}")
        paths.dictDir().mkdirs()
        assertTrue(paths.isInstalled("my-voice"))
    }

    @Test
    fun `exposes the default model id`() {
        assertEquals("css10-6lang", ModelPaths.DEFAULT_MODEL_ID)
    }
}
